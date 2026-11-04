"""Game-mode rules: Mission (checkpoints + timer) and Endless (survive + difficulty ramp).

Modes operate on a ``GameSession`` (see ``engine.py``) through duck typing so this
module never imports the engine (no circular imports).
"""
from __future__ import annotations

import math

from .collision import boxes_intersect
from .entities import Checkpoint, Obstacle, Pickup, TrafficCar

REF_SPEED = 300.0        # px/s used to size the mission timer
FUEL_CAN_VALUE = 28.0
TRAFFIC_KINDS = ("sedan", "sedan", "taxi", "van", "truck")


def _spawn_obstacle_group(s, path_s: float) -> None:
    """Place one obstacle (sometimes a small cluster) at path distance ``path_s``."""
    kind = s.rng.choice(s.map.obstacle_types)
    spread = 0.27 if kind in ("barrier", "log") else 0.36
    lateral = s.rng.uniform(-spread, spread) * s.map.road_width
    heading = s.path.heading_at(path_s)
    if kind in ("cone", "barrel"):
        rot = 0.0
    elif kind == "barrier":
        rot = heading + s.rng.choice([0, 0, 90])
    elif kind == "log":
        rot = heading + s.rng.uniform(-35, 35)
    else:
        rot = s.rng.uniform(0, 360)
    x, y = s.path.offset_pos(path_s, lateral)
    s.obstacles.append(Obstacle(kind, x, y, rot, s=path_s))
    if kind in ("cone", "barrel") and s.rng.random() < 0.3:
        for j in (1, 2):
            x2, y2 = s.path.offset_pos(path_s + j * 34, lateral + j * s.rng.choice([-1, 1]) * 20)
            s.obstacles.append(Obstacle(kind, x2, y2, 0.0, s=path_s + j * 34))


def _spawn_coin_line(s, path_s: float) -> None:
    lateral = s.rng.choice([o for o, _ in s.map.lanes]) * s.rng.uniform(0.3, 1.1)
    weave = s.rng.choice([0, 0, 14])
    for k in range(s.rng.randint(4, 7)):
        x, y = s.path.offset_pos(path_s + k * 55, lateral + math.sin(k * 0.9) * weave)
        s.pickups.append(Pickup("coin", x, y, s=path_s + k * 55))


def _spawn_fuel(s, path_s: float) -> None:
    x, y = s.path.offset_pos(path_s, s.rng.uniform(-0.3, 0.3) * s.map.road_width)
    s.pickups.append(Pickup("fuel", x, y, s=path_s, value=FUEL_CAN_VALUE))


def _try_spawn_traffic(s, path_s: float, lane_index: int | None = None, min_gap: float = 420.0) -> bool:
    lanes = s.map.lanes
    if lane_index is None:
        lane_index = s.rng.randrange(len(lanes))
    lateral, direction = lanes[lane_index]
    for t in s.traffic:
        if t.lane_index == lane_index and abs(s.path.signed_delta(t.s, path_s)) < min_gap:
            return False
    car = TrafficCar(s.rng.choice(TRAFFIC_KINDS), path_s % s.path.length, lane_index, lateral, direction,
                     s.lane_speed[lane_index])
    car.sync(s.path)
    for o in s.obstacles:                         # never spawn on top of an obstacle
        if math.hypot(o.x - car.x, o.y - car.y) < 90:
            return False
    s.traffic.append(car)
    return True


class MissionMode:
    key = "mission"
    label = "MISSION"

    def setup(self, s) -> None:
        m = s.map
        s.checkpoints = [Checkpoint(i, c["x"], c["y"], c["heading"], c["s"]) for i, c in enumerate(m.checkpoints)]
        f = m.finish
        s.finish = Checkpoint(-1, f["x"], f["y"], f["heading"], f["s"])
        s.pickups = [Pickup("coin", c["x"], c["y"]) for c in m.coins]
        s.pickups += [Pickup("fuel", c["x"], c["y"], value=FUEL_CAN_VALUE) for c in m.fuel]
        if s.hazards:
            s.obstacles = [Obstacle(o["t"], o["x"], o["y"], o["rot"]) for o in m.obstacles
                           if o["p"] < s.diff.obstacle_density]
            self._place_traffic(s)
        route = s.finish.s - m.start["s"]
        s.time_limit = route / REF_SPEED * s.diff.time_factor
        s.time_left = s.time_limit

    def _place_traffic(self, s) -> None:
        L = s.path.length
        for lane_index in range(len(s.map.lanes)):
            pos = 900 + s.rng.uniform(0, 500)
            while pos < L - 500:
                _try_spawn_traffic(s, pos, lane_index, min_gap=500)
                pos += s.rng.uniform(1000, 1700) / s.diff.traffic_density

    def update(self, s, dt: float) -> None:
        s.time_left -= dt
        car_box = s.car.box()
        nxt = s.next_checkpoint()
        if nxt is not None and boxes_intersect(car_box, nxt.gate_box(s.map.road_width)):
            nxt.reached = True
            s.checkpoints_done += 1
            s.time_left += s.diff.checkpoint_bonus
            s.bonus_score += 500
            s.add_event("checkpoint", s.checkpoints_done)
            s.set_banner(f"CHECKPOINT {s.checkpoints_done}/{len(s.checkpoints)}   +{s.diff.checkpoint_bonus:.0f}s",
                         2.0, "#ffd23c")
        elif boxes_intersect(car_box, s.finish.gate_box(s.map.road_width)):
            if s.next_checkpoint() is None:
                s.finish.reached = True
                s.time_left = max(0.0, s.time_left)
                s.bonus_score += int(s.time_left * 20) + s.lives * 300 + (500 if s.lives_lost == 0 else 0)
                s.end("victory", "Mission complete!")
                return
            if s.elapsed - s.last_gate_warning > 3.0:
                s.last_gate_warning = s.elapsed
                s.set_banner("PASS ALL CHECKPOINTS FIRST!", 2.0, "#ff6b6b")
                s.add_event("warning")
        if s.time_left <= 0.0:
            s.time_left = 0.0
            s.end("failed", "Time is up!")

    def target(self, s):
        nxt = s.next_checkpoint()
        if nxt is not None:
            return nxt.x, nxt.y, f"CP {nxt.index + 1}"
        return s.finish.x, s.finish.y, "FINISH"


class EndlessMode:
    key = "endless"
    label = "ENDLESS"
    SPAWN_AHEAD = 2400.0
    CULL_BEHIND = 900.0

    def setup(self, s) -> None:
        self.level = 1.0
        base = s.s_unwrapped
        self.next_obstacle = base + 800
        self.next_coin = base + 450
        self.next_fuel = base + 1200
        self.traffic_cooldown = 0.0
        s.time_left = None
        s.time_limit = None

    def update(self, s, dt: float) -> None:
        ramp = s.diff.endless_ramp
        self.level = 1.0 + s.elapsed / 30.0 * ramp          # +1 level every 30 s (medium)
        s.level = self.level
        horizon = s.s_unwrapped + self.SPAWN_AHEAD
        rng = s.rng
        if s.hazards:
            density = s.diff.obstacle_density * (1.0 + 0.15 * (self.level - 1.0))
            while self.next_obstacle < horizon:
                _spawn_obstacle_group(s, self.next_obstacle)
                self.next_obstacle += max(180.0, rng.uniform(300, 560) / density)
        while self.next_coin < horizon:
            _spawn_coin_line(s, self.next_coin)
            self.next_coin += rng.uniform(550, 950)
        while self.next_fuel < horizon:
            _spawn_fuel(s, self.next_fuel)
            self.next_fuel += rng.uniform(1500, 2100)

        if s.hazards:
            for t in s.traffic:                              # traffic gets faster over time
                t.speed = s.lane_speed[t.lane_index] * (1.0 + 0.04 * (self.level - 1.0))
            self.traffic_cooldown -= dt
            target = min(16, int((3 + 1.3 * self.level) * s.diff.traffic_density))
            if len(s.traffic) < target and self.traffic_cooldown <= 0:
                self.traffic_cooldown = 0.8
                for _attempt in range(8):            # dense obstacle fields can block a spot
                    ahead = s.s_unwrapped + rng.uniform(1500, 2300)
                    if _try_spawn_traffic(s, ahead):
                        break

        # Clean up everything that is far behind the player.
        limit = s.s_unwrapped - self.CULL_BEHIND
        s.obstacles = [o for o in s.obstacles if o.alive and o.s >= limit]
        s.pickups = [p for p in s.pickups if p.alive and p.s >= limit]
        loop = s.path.length
        s.traffic = [t for t in s.traffic
                     if s.path.signed_delta(s.s_unwrapped % loop, t.s) > -self.CULL_BEHIND - 300]

    def target(self, s):
        return None
