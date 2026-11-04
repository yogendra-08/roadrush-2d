"""The GameSession: all game rules and per-frame simulation, with no GUI code.

The Tkinter layer only feeds ``Controls`` in, calls ``update(dt)`` and draws
what the session contains, which keeps the logic unit-testable.
"""
from __future__ import annotations

import math
import random

from .car import Car, CarSpec, Controls
from .collision import sat_collision, circle_box_collision
from .entities import PICKUP_RADIUS
from .map import GameMap, METERS_PER_PX
from .modes import EndlessMode, MissionMode
from .settings import DifficultyProfile

MAX_LIVES = 3
WORLD_MARGIN = 28.0
RUNNING, VICTORY, GAME_OVER, FAILED = "running", "victory", "game_over", "failed"


class GameSession:
    def __init__(self, game_map: GameMap, car_spec: CarSpec, mode_key: str, difficulty: DifficultyProfile,
                 seed: int | None = None, hazards: bool = True):
        self.map = game_map
        self.path = game_map.path
        self.diff = difficulty
        self.mode_key = mode_key
        self.hazards = hazards
        self.rng = random.Random(seed)

        start = game_map.start
        self.car = Car(car_spec, start["x"], start["y"], start["heading"])
        self.state = RUNNING
        self.end_reason = ""
        self.events: list[tuple[str, object]] = []
        self.banner: tuple[str, float, str] | None = None

        self.lives = MAX_LIVES
        self.lives_lost = 0
        self.coins = 0
        self.elapsed = 0.0
        self.invuln = 0.0
        self.damage_flash = 0.0
        self.offroad_timer = 0.0
        self.off_wheels = 0
        self.stuck_timer = 0.0
        self.bonus_score = 0
        self.top_speed_kmh = 0.0
        self.last_gate_warning = -10.0
        self.level = 1.0
        self.low_fuel_warned = False

        self.obstacles: list = []
        self.pickups: list = []
        self.traffic: list = []
        self.checkpoints: list = []
        self.checkpoints_done = 0
        self.finish = None
        self.time_left: float | None = None
        self.time_limit: float | None = None

        # progress along the loop (unwrapped, so laps keep counting up)
        self._index = self.path.nearest_index(start["x"], start["y"])
        self.s_unwrapped = self.path.s_of_index(self._index)
        self._s_start = self.s_unwrapped
        self.best_s = self.s_unwrapped

        # every lane gets one constant speed, so cars in a lane never catch each other
        self.lane_speed = [(150.0 + self.rng.uniform(0, 70)) * difficulty.traffic_speed for _ in game_map.lanes]

        self.mode = MissionMode() if mode_key == "mission" else EndlessMode()
        self.mode.setup(self)
        for t in self.traffic:
            t.speed = self.lane_speed[t.lane_index]

    # ------------------------------------------------------------------ helpers
    def add_event(self, name: str, data: object = None) -> None:
        self.events.append((name, data))

    def pop_events(self) -> list[tuple[str, object]]:
        ev, self.events = self.events, []
        return ev

    def set_banner(self, text: str, seconds: float, color: str = "#ffffff") -> None:
        self.banner = (text, seconds, color)

    def next_checkpoint(self):
        for cp in self.checkpoints:
            if not cp.reached:
                return cp
        return None

    def target(self):
        return self.mode.target(self)

    def end(self, state: str, reason: str) -> None:
        if self.state != RUNNING:
            return
        self.state = state
        self.end_reason = reason
        self.add_event(state, reason)

    @property
    def distance_px(self) -> float:
        return max(0.0, self.best_s - self._s_start)

    @property
    def distance_m(self) -> int:
        return int(self.distance_px * METERS_PER_PX)

    @property
    def score(self) -> int:
        total = self.distance_px * 0.1 + self.coins * 50 + self.bonus_score
        if self.mode_key == "endless":
            total += self.elapsed * 3          # survival bonus
        return int(total)

    @property
    def invulnerable(self) -> bool:
        return self.invuln > 0.0

    def result(self) -> dict:
        return {
            "mode": self.mode_key, "map": self.map.map_id, "car": self.car.spec.car_id,
            "difficulty": self.diff.key, "state": self.state, "reason": self.end_reason,
            "victory": self.state == VICTORY, "score": self.score, "coins": self.coins,
            "distance_m": self.distance_m, "distance_px": self.distance_px,
            "time": round(self.elapsed, 1), "time_left": None if self.time_left is None else round(self.time_left, 1),
            "checkpoints": self.checkpoints_done, "lives_lost": self.lives_lost,
            "lives_left": self.lives, "top_speed_kmh": int(self.top_speed_kmh),
        }

    # -------------------------------------------------------------------- update
    def update(self, dt: float, ctl: Controls) -> None:
        if self.state != RUNNING or dt <= 0:
            return
        dt = min(dt, 0.05)
        self.elapsed += dt
        self.invuln = max(0.0, self.invuln - dt)
        self.damage_flash = max(0.0, self.damage_flash - dt)
        if self.banner:
            text, left, color = self.banner
            self.banner = (text, left - dt, color) if left - dt > 0 else None

        car = self.car
        # ---- road surface under the car: four wheels (corners) are probed
        corners = car.box().corners()
        self.off_wheels = sum(0 if self.map.is_road(x, y) else 1 for x, y in corners)
        car.off_fraction = self.off_wheels / 4.0
        car.update(dt, ctl)
        self._clamp_to_world()
        self.top_speed_kmh = max(self.top_speed_kmh, car.speed_kmh)
        self._track_progress()

        self._collect_pickups()
        self._move_traffic(dt)
        self._collide_obstacles()
        self._collide_traffic()
        self._check_offroad(dt)
        self._check_fuel(dt)
        if self.state == RUNNING:
            self.mode.update(self, dt)

    # --------------------------------------------------------------- sub-steps
    def _clamp_to_world(self) -> None:
        car, w, h = self.car, self.map.world_w, self.map.world_h
        if car.x < WORLD_MARGIN:
            car.x, car.vx = WORLD_MARGIN, abs(car.vx) * 0.3
        elif car.x > w - WORLD_MARGIN:
            car.x, car.vx = w - WORLD_MARGIN, -abs(car.vx) * 0.3
        if car.y < WORLD_MARGIN:
            car.y, car.vy = WORLD_MARGIN, abs(car.vy) * 0.3
        elif car.y > h - WORLD_MARGIN:
            car.y, car.vy = h - WORLD_MARGIN, -abs(car.vy) * 0.3

    def _track_progress(self) -> None:
        idx = self.path.nearest_index(self.car.x, self.car.y, around=self._index, window=60)
        n = self.path.n
        delta = (idx - self._index + n // 2) % n - n // 2
        self._index = idx
        self.s_unwrapped += delta * self.path.step
        if self.s_unwrapped > self.best_s:
            self.best_s = self.s_unwrapped

    def _collect_pickups(self) -> None:
        box = self.car.box()
        px, py = self.car.x, self.car.y
        reach = box.bounding_radius() + PICKUP_RADIUS + 4
        for p in self.pickups:
            if not p.alive or abs(p.x - px) > reach or abs(p.y - py) > reach:
                continue
            if circle_box_collision(p.x, p.y, PICKUP_RADIUS, box):
                p.alive = False
                if p.kind == "coin":
                    self.coins += 1
                    self.add_event("coin")
                else:
                    self.car.fuel = min(100.0, self.car.fuel + p.value)
                    self.low_fuel_warned = False
                    self.add_event("fuel")
                    self.set_banner("FUEL +%d" % p.value, 1.2, "#7dff9b")
        if self.mode_key == "mission":
            self.pickups = [p for p in self.pickups if p.alive]

    def _move_traffic(self, dt: float) -> None:
        loop = self.path.length
        for t in self.traffic:
            t.s = (t.s + t.direction * t.speed * dt) % loop
            t.sync(self.path)

    def _collide_obstacles(self) -> None:
        car = self.car
        car_box = car.box()
        reach = car_box.bounding_radius() + 80
        for o in self.obstacles:
            if not o.alive or abs(o.x - car.x) > reach or abs(o.y - car.y) > reach:
                continue
            mtv = sat_collision(car_box, o.box())
            if mtv is None:
                continue
            self._crash(mtv, "obstacle")
            if o.breakable:
                o.alive = False
            car_box = car.box()
        if self.mode_key == "mission" and any(not o.alive for o in self.obstacles):
            self.obstacles = [o for o in self.obstacles if o.alive]

    def _collide_traffic(self) -> None:
        car = self.car
        car_box = car.box()
        reach = car_box.bounding_radius() + 90
        for t in self.traffic:
            if abs(t.x - car.x) > reach or abs(t.y - car.y) > reach:
                continue
            mtv = sat_collision(car_box, t.box())
            if mtv is not None:
                self._crash(mtv, "traffic")
                car_box = car.box()

    def _crash(self, mtv: tuple[float, float], source: str) -> None:
        """Push the car out of whatever it hit and apply damage (once per cool-down)."""
        car = self.car
        car.x += mtv[0]
        car.y += mtv[1]
        length = math.hypot(*mtv) or 1.0
        nx, ny = mtv[0] / length, mtv[1] / length
        vn = car.vx * nx + car.vy * ny
        if vn < 0:                                   # bounce off, losing energy
            car.vx -= 1.25 * vn * nx
            car.vy -= 1.25 * vn * ny
        if self.invuln > 0.0:
            return
        keep = self.diff.crash_speed_keep
        car.vx *= keep
        car.vy *= keep
        self._lose_life("Crashed!")
        self.add_event("crash", source)

    def _lose_life(self, reason: str) -> None:
        self.lives -= 1
        self.lives_lost += 1
        self.invuln = self.diff.invuln_time
        self.damage_flash = 0.35
        if self.lives <= 0:
            self.lives = 0
            self.end("game_over", "You ran out of lives!")
        else:
            self.set_banner(reason + f"  {self.lives} {'life' if self.lives == 1 else 'lives'} left", 1.6, "#ff6b6b")

    def _check_offroad(self, dt: float) -> None:
        if self.off_wheels >= 3:
            if self.offroad_timer == 0.0:
                self.add_event("offroad")
            self.offroad_timer += dt
            if self.offroad_timer >= self.diff.offroad_grace:
                self.offroad_timer = 0.0
                self._lose_life("Left the road!")
                if self.state == RUNNING:
                    self._respawn_on_road()
                self.add_event("crash", "offroad")
        else:
            self.offroad_timer = max(0.0, self.offroad_timer - 2.0 * dt)

    def _respawn_on_road(self) -> None:
        idx = self.path.nearest_index(self.car.x, self.car.y)
        s = self.path.s_of_index(idx)
        lateral = min(o for o, _ in self.map.lanes if o > 0)
        x, y = self.path.offset_pos(s, lateral)
        self.car.place(x, y, self.path.heading_at(s), speed=0.0)
        self.car.off_fraction = 0.0
        self._index = idx
        self.invuln = max(self.invuln, 2.0)

    def _check_fuel(self, dt: float) -> None:
        car = self.car
        if car.fuel <= 15.0 and not self.low_fuel_warned and car.fuel > 0:
            self.low_fuel_warned = True
            self.add_event("warning")
            self.set_banner("LOW FUEL!", 1.8, "#ffb347")
        if car.fuel <= 0.0 and car.speed < 8.0:
            self.stuck_timer += dt
            if self.stuck_timer > 2.5:
                self.end("game_over", "Out of fuel!")
        else:
            self.stuck_timer = 0.0
