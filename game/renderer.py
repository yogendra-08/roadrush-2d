"""Draws a GameSession onto a Tkinter Canvas (world layer: map, entities, effects)."""
from __future__ import annotations

import math
import random
import tkinter as tk

from PIL import ImageTk

from .collision import right_vec
from .ui import VIEW_H, VIEW_W

TILE = 512
MAX_PARTICLES = 80


def build_tiles(background) -> list[tuple[int, int, ImageTk.PhotoImage]]:
    """Cut the big background into canvas-friendly PhotoImage tiles."""
    tiles = []
    w, h = background.size
    for ty in range(0, h, TILE):
        for tx in range(0, w, TILE):
            crop = background.crop((tx, ty, min(tx + TILE, w), min(ty + TILE, h)))
            tiles.append((tx, ty, ImageTk.PhotoImage(crop)))
    return tiles


class WorldRenderer:
    LAYERS = ("gates", "pickups", "obstacles", "traffic", "player", "fx")

    def __init__(self, canvas: tk.Canvas, sprites, session, camera, tiles):
        self.c, self.sp, self.s, self.cam = canvas, sprites, session, camera
        self.shake = 0.0
        self.time = 0.0
        self.rng = random.Random(5)
        self._items: dict[int, int] = {}
        self._tile_items = [(canvas.create_image(0, 0, anchor="nw", image=ph, tags=("world",)), tx, ty)
                            for tx, ty, ph in tiles]
        self._anchors = {n: canvas.create_rectangle(0, 0, 0, 0, state="hidden") for n in self.LAYERS}
        self._coin_frames = sprites.coin_frames()
        self._fuel_img = sprites.fuel()
        self._build_gates()
        car = session.car
        self._player = canvas.create_image(0, 0, image=sprites.car_frame(car.spec.car_id, car.heading))
        canvas.tag_lower(self._player, self._anchors["player"])
        self._particles = []
        for _ in range(MAX_PARTICLES):
            item = canvas.create_oval(0, 0, 0, 0, state="hidden", outline="")
            canvas.tag_lower(item, self._anchors["fx"])
            self._particles.append({"item": item, "life": 0.0, "max": 1.0, "x": 0.0, "y": 0.0,
                                    "vx": 0.0, "vy": 0.0, "size": 4.0})
        self._flash = canvas.create_rectangle(0, 0, VIEW_W, VIEW_H, fill="#ff1030", stipple="gray50",
                                              outline="", state="hidden")

    # ------------------------------------------------------------------ gates
    def _build_gates(self) -> None:
        c, s = self.c, self.s
        self._gates = []
        gates = list(s.checkpoints)
        if s.finish is not None:
            gates.append(s.finish)
        half = s.map.road_width / 2 + 6
        for cp in gates:
            rx, ry = right_vec(cp.heading)
            ax, ay, bx, by = cp.x - rx * half, cp.y - ry * half, cp.x + rx * half, cp.y + ry * half
            line = c.create_line(0, 0, 0, 0, width=6, dash=(14, 8), fill="#ffffff")
            pa = c.create_oval(0, 0, 0, 0, fill="#ffffff", outline="#000000", width=2)
            pb = c.create_oval(0, 0, 0, 0, fill="#ffffff", outline="#000000", width=2)
            label = "FINISH" if cp.index < 0 else str(cp.index + 1)
            text = c.create_text(0, 0, text=label, fill="#101020", font=("Helvetica", 11, "bold"))
            for it in (line, pa, pb, text):
                c.tag_lower(it, self._anchors["gates"])
            self._gates.append({"cp": cp, "pts": (ax, ay, bx, by), "items": (line, pa, pb, text), "state": None})

    def _update_gates(self) -> None:
        c, cam, s = self.c, self.cam, self.s
        nxt = s.next_checkpoint()
        pulse = 0.5 + 0.5 * math.sin(self.time * 6)
        for g in self._gates:
            cp = g["cp"]
            ax, ay, bx, by = g["pts"]
            line, pa, pb, text = g["items"]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if not cam.is_visible(mx, my, s.map.road_width):
                if g["state"] != "hidden":
                    for it in g["items"]:
                        c.itemconfig(it, state="hidden")
                    g["state"] = "hidden"
                continue
            if cp.reached:
                state, col = "done", "#35d07f"
            elif cp is nxt:
                state, col = "next", "#ffd23c" if pulse > 0.5 else "#fff2a8"
            elif cp.index < 0:
                state, col = "finish", "#ffffff" if nxt is None else "#8a90b8"
            else:
                state, col = "future", "#8a90b8"
            if g["state"] in ("hidden", None):
                for it in g["items"]:
                    c.itemconfig(it, state="normal")
            c.itemconfig(line, fill=col)
            c.itemconfig(pa, fill=col)
            c.itemconfig(pb, fill=col)
            g["state"] = state if state != "next" else f"next{int(pulse > 0.5)}"
            c.coords(line, ax - cam.x, ay - cam.y, bx - cam.x, by - cam.y)
            c.coords(pa, ax - cam.x - 9, ay - cam.y - 9, ax - cam.x + 9, ay - cam.y + 9)
            c.coords(pb, bx - cam.x - 9, by - cam.y - 9, bx - cam.x + 9, by - cam.y + 9)
            c.coords(text, mx - cam.x, my - cam.y - 18)
            c.itemconfig(text, fill="#ffffff" if cp.reached or cp is nxt else "#b8bde0")

    # ---------------------------------------------------------------- effects
    def emit(self, x, y, vx, vy, life, color, size) -> None:
        for p in self._particles:
            if p["life"] <= 0:
                p.update(x=x, y=y, vx=vx, vy=vy, life=life, max=life, size=size)
                self.c.itemconfig(p["item"], fill=color, state="normal")
                return

    def burst(self, x, y, color="#ffb347", n=16, speed=220) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.3, 1.0) * speed
            self.emit(x, y, math.cos(a) * v, math.sin(a) * v, self.rng.uniform(0.25, 0.55), color, self.rng.uniform(3, 6))

    def _spawn_trail_particles(self, dt: float) -> None:
        car = self.s.car
        fx, fy = -math.sin(math.radians(car.heading)), math.cos(math.radians(car.heading))   # backwards
        rx, ry = right_vec(car.heading)
        if car.nitro_active and self.rng.random() < 0.9:
            for side in (-1, 1):
                self.emit(car.x + fx * 46 + rx * side * 10, car.y + fy * 46 + ry * side * 10,
                          fx * 120 + self.rng.uniform(-30, 30), fy * 120 + self.rng.uniform(-30, 30), 0.22,
                          self.rng.choice(["#ffb02e", "#ff6a1f", "#6ad8ff"]), self.rng.uniform(5, 9))
        drifting = car.sliding > 90 or (car.speed > 120 and abs(car.steer) > 0.9 and car.sliding > 60)
        if drifting and self.rng.random() < 0.7:
            for side in (-1, 1):
                self.emit(car.x + fx * 30 + rx * side * 15, car.y + fy * 30 + ry * side * 15,
                          self.rng.uniform(-15, 15), self.rng.uniform(-15, 15), 0.6, "#d8dae6",
                          self.rng.uniform(5, 10))
        if self.s.off_wheels and car.speed > 70 and self.rng.random() < 0.6:
            self.emit(car.x + fx * 30 + rx * self.rng.uniform(-14, 14), car.y + fy * 30 + ry * self.rng.uniform(-14, 14),
                      self.rng.uniform(-25, 25), self.rng.uniform(-25, 25), 0.5, "#a8845a", self.rng.uniform(4, 8))

    def _update_particles(self, dt: float) -> None:
        c, cam = self.c, self.cam
        for p in self._particles:
            if p["life"] <= 0:
                continue
            p["life"] -= dt
            if p["life"] <= 0:
                c.itemconfig(p["item"], state="hidden")
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            r = p["size"] * (0.4 + 0.6 * p["life"] / p["max"])
            sx, sy = p["x"] - cam.x, p["y"] - cam.y
            c.coords(p["item"], sx - r, sy - r, sx + r, sy + r)

    # -------------------------------------------------------------- entities
    def _sync_entities(self) -> None:
        c, cam, s, sp = self.c, self.cam, self.s, self.sp
        live: set[int] = set()
        frame = int(self.time * 12)

        def place(ent, layer, image_fn, margin=90):
            key = id(ent)
            live.add(key)
            item = self._items.get(key)
            if not cam.is_visible(ent.x, ent.y, margin):
                if item is not None:
                    c.itemconfig(item, state="hidden")
                return
            img = image_fn()
            if item is None:
                item = c.create_image(0, 0, image=img)
                c.tag_lower(item, self._anchors[layer])
                self._items[key] = item
            else:
                c.itemconfig(item, image=img, state="normal")
            c.coords(item, ent.x - cam.x, ent.y - cam.y)

        for i, p in enumerate(s.pickups):
            if p.alive:
                if p.kind == "coin":
                    place(p, "pickups", lambda i=i: self._coin_frames[(frame + i) % len(self._coin_frames)], 40)
                else:
                    place(p, "pickups", lambda: self._fuel_img, 40)
        for o in s.obstacles:
            if o.alive:
                place(o, "obstacles", lambda o=o: sp.obstacle(o.kind, o.rot), 120)
        for t in s.traffic:
            place(t, "traffic", lambda t=t: sp.traffic_frame(t.kind, t.heading), 140)
        for key in [k for k in self._items if k not in live]:
            c.delete(self._items.pop(key))

    # ------------------------------------------------------------------ frame
    def draw(self, dt: float) -> None:
        c, cam, s = self.c, self.cam, self.s
        self.time += dt
        self.shake = max(0.0, self.shake - dt)
        if self.shake > 0:
            amp = 9 * self.shake / 0.35
            cam_dx, cam_dy = self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp)
        else:
            cam_dx = cam_dy = 0.0
        real_x, real_y = cam.x, cam.y
        cam.x, cam.y = round(real_x + cam_dx), round(real_y + cam_dy)   # integer pixels: no tile seams

        for item, tx, ty in self._tile_items:
            sx, sy = tx - cam.x, ty - cam.y
            if -TILE < sx < VIEW_W and -TILE < sy < VIEW_H:
                c.coords(item, sx, sy)
                c.itemconfig(item, state="normal")
            else:
                c.itemconfig(item, state="hidden")

        self._update_gates()
        self._sync_entities()
        car = s.car
        c.itemconfig(self._player, image=self.sp.car_frame(car.spec.car_id, car.heading))
        c.coords(self._player, car.x - cam.x, car.y - cam.y)
        blink = s.invulnerable and int(self.time * 12) % 2 == 0 and s.state == "running"
        c.itemconfig(self._player, state="hidden" if blink else "normal")
        self._spawn_trail_particles(dt)
        self._update_particles(dt)
        c.itemconfig(self._flash, state="normal" if s.damage_flash > 0 else "hidden")
        cam.x, cam.y = real_x, real_y
