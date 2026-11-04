"""Heads-up display drawn on top of the gameplay canvas."""
from __future__ import annotations

import math

from .car import KMH_PER_PX
from .map import METERS_PER_PX
from .ui import (ACCENT, CYAN, GOLD, GREEN, MUTED, PANEL, RED, TEXT, VIEW_H, VIEW_W, CanvasButton, font,
                 round_rect)

GAUGE_START, GAUGE_SWEEP = 210.0, 240.0      # degrees (Tk convention: counter-clockwise from east)


class Hud:
    def __init__(self, canvas, sprites, session, on_pause, sound=None):
        self.c, self.sp, self.s = canvas, sprites, session
        self._cache: dict = {}
        c = canvas
        self.vmax = int(math.ceil(session.car.spec.max_speed * 1.4 * KMH_PER_PX / 40.0) * 40)
        mission = session.mode_key == "mission"

        # ---- top-left: mode, score, coins
        self._panel(12, 12, 262, 96)
        self.t_mode = c.create_text(26, 28, anchor="w", fill=MUTED, font=font(10), tags=("hud",))
        self.t_score = c.create_text(26, 54, anchor="w", fill=TEXT, font=font(24), tags=("hud",))
        c.create_image(30, 80, image=sprites.icon("coin"), tags=("hud",))
        self.t_coins = c.create_text(50, 80, anchor="w", fill=GOLD, font=font(14), tags=("hud",))
        self.t_dist = c.create_text(250, 80, anchor="e", fill=MUTED, font=font(11), tags=("hud",))

        # ---- top-centre: timer + progress
        self._panel(372, 12, 628, 86)
        self.t_timer = c.create_text(500, 40, fill=TEXT, font=font(26), tags=("hud",))
        self.t_sub = c.create_text(500, 70, fill=MUTED, font=font(11), tags=("hud",))
        self.dots = []
        if mission:
            n = len(session.checkpoints)
            for i in range(n):
                x = 500 - (n - 1) * 14 + i * 28
                self.dots.append(c.create_oval(x - 6, 66, x + 6, 78, fill="#2b3370", outline="#8a90b8", width=2,
                                               tags=("hud",)))
            c.itemconfig(self.t_sub, state="hidden")

        # ---- top-right: lives + pause
        self._panel(712, 12, 988, 66)
        self.hearts = [c.create_image(740 + i * 38, 39, image=sprites.icon("heart"), tags=("hud",)) for i in range(3)]
        self.pause_btn = CanvasButton(c, 948, 39, 44, 36, "II", on_pause, "secondary", 13, sound)
        c.addtag_withtag("hud", self.pause_btn.tag)
        c.create_text(862, 39, text="ESC", fill=MUTED, font=font(10), tags=("hud",))

        # ---- bottom-left: fuel + nitro
        self._panel(12, 566, 272, 648)
        c.create_image(34, 592, image=sprites.icon("fuel"), tags=("hud",))
        c.create_image(34, 626, image=sprites.icon("nitro"), tags=("hud",))
        self.fuel_bg = round_rect(c, 56, 584, 258, 600, 8, fill="#0d1030", outline="", tags=("hud",))
        self.fuel_fg = round_rect(c, 56, 584, 258, 600, 8, fill=GREEN, outline="", tags=("hud",))
        self.nitro_bg = round_rect(c, 56, 618, 258, 634, 8, fill="#0d1030", outline="", tags=("hud",))
        self.nitro_fg = round_rect(c, 56, 618, 258, 634, 8, fill=CYAN, outline="", tags=("hud",))

        # ---- bottom-right: speedometer
        gx, gy, gr = 884, 560, 84
        self.g = (gx, gy, gr)
        c.create_oval(gx - gr - 10, gy - gr - 10, gx + gr + 10, gy + gr + 10, fill=PANEL, outline="#3a4390",
                      width=2, tags=("hud",))
        c.create_arc(gx - gr, gy - gr, gx + gr, gy + gr, start=GAUGE_START, extent=-GAUGE_SWEEP, style="arc",
                     outline="#323a78", width=10, tags=("hud",))
        self.gauge_arc = c.create_arc(gx - gr, gy - gr, gx + gr, gy + gr, start=GAUGE_START, extent=-1, style="arc",
                                      outline=ACCENT, width=10, tags=("hud",))
        for v in range(0, self.vmax + 1, 40):
            a = math.radians(GAUGE_START - GAUGE_SWEEP * v / self.vmax)
            c.create_text(gx + math.cos(a) * (gr - 24), gy - math.sin(a) * (gr - 24), text=str(v), fill=MUTED,
                          font=font(8), tags=("hud",))
        self.needle = c.create_line(gx, gy, gx, gy - gr, fill="#ffffff", width=3, capstyle="round", tags=("hud",))
        c.create_oval(gx - 7, gy - 7, gx + 7, gy + 7, fill="#ffffff", outline="", tags=("hud",))
        self.t_speed = c.create_text(gx, gy + 34, fill=TEXT, font=font(22), tags=("hud",))
        c.create_text(gx, gy + 54, text="km/h", fill=MUTED, font=font(10), tags=("hud",))

        # ---- minimap
        self._panel(12, 104, 192, 244)
        self._build_minimap(20, 112, 164, 124)

        # ---- objective arrow
        self.arrow = None
        if mission:
            round_rect(c, 452, 584, 548, 650, 14, fill=PANEL, outline="#3a4390", width=2, tags=("hud",))
            self.arrow = c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, fill=GOLD, outline="#000000", tags=("hud",))
            self.t_target = c.create_text(500, 636, fill=TEXT, font=font(10), tags=("hud",))

        # ---- banners
        self.t_banner = c.create_text(500, 134, fill=TEXT, font=font(22), tags=("hud",))
        self.t_off = c.create_text(500, 170, fill=RED, font=font(18), tags=("hud",))
        self.t_big = c.create_text(500, 300, fill=GOLD, font=font(72), tags=("hud",))
        c.tag_raise("hud")

    # ------------------------------------------------------------------ builders
    def _panel(self, x1, y1, x2, y2):
        round_rect(self.c, x1, y1, x2, y2, 14, fill=PANEL, outline="#3a4390", width=2, tags=("hud",))

    def _build_minimap(self, x, y, w, h):
        s = self.s
        sc = min(w / s.map.world_w, h / s.map.world_h)
        ox = x + (w - s.map.world_w * sc) / 2
        oy = y + (h - s.map.world_h * sc) / 2
        self.mm = (ox, oy, sc)
        pts = []
        for px, py in s.path.points[::8]:
            pts += [ox + px * sc, oy + py * sc]
        pts += pts[:2]
        self.c.create_line(*pts, fill="#6e78c8", width=5, capstyle="round", joinstyle="round", tags=("hud",))
        self.c.create_line(*pts, fill="#2b3370", width=2, tags=("hud",))
        self.mm_cps = []
        for cp in s.checkpoints + ([s.finish] if s.finish else []):
            cx, cy = ox + cp.x * sc, oy + cp.y * sc
            self.mm_cps.append((cp, self.c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#ffffff", outline="",
                                                       tags=("hud",))))
        self.mm_dot = self.c.create_oval(0, 0, 0, 0, fill=ACCENT, outline="#ffffff", width=1, tags=("hud",))

    # -------------------------------------------------------------------- update
    def _set(self, item, **kw):
        key = (item, tuple(sorted(kw.items())))
        if self._cache.get(item) != key:
            self._cache[item] = key
            self.c.itemconfig(item, **kw)

    @staticmethod
    def _fmt(seconds: float) -> str:
        seconds = max(0.0, seconds)
        return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"

    def update(self, countdown: float = 0.0) -> None:
        s, c = self.s, self.c
        mission = s.mode_key == "mission"
        car = s.car
        self._set(self.t_mode, text=f"{'MISSION' if mission else 'ENDLESS'}  •  {s.map.name.upper()}")
        self._set(self.t_score, text=f"{s.score:,}")
        self._set(self.t_coins, text=str(s.coins))
        self._set(self.t_dist, text=f"{s.distance_m} m")
        if mission:
            left = s.time_left or 0.0
            self._set(self.t_timer, text=self._fmt(left), fill=RED if left < 10 else TEXT)
            for i, d in enumerate(self.dots):
                done = i < s.checkpoints_done
                self._set(d, fill=GOLD if done else "#2b3370", outline="#ffffff" if done else "#8a90b8")
        else:
            self._set(self.t_timer, text=self._fmt(s.elapsed))
            self._set(self.t_sub, text=f"DIFFICULTY LEVEL {int(s.level)}")
        for i, h in enumerate(self.hearts):
            self._set(h, image=self.sp.icon("heart" if i < s.lives else "heart_empty"))

        self._bar(self.fuel_fg, 56, 584, 202, 16, car.fuel / 100.0, RED if car.fuel < 20 else GREEN)
        self._bar(self.nitro_fg, 56, 618, 202, 16, car.nitro / 100.0, "#ffffff" if car.nitro_active else CYAN)

        kmh = car.speed_kmh
        gx, gy, gr = self.g
        frac = max(0.0, min(1.0, kmh / self.vmax))
        a = math.radians(GAUGE_START - GAUGE_SWEEP * frac)
        c.coords(self.needle, gx, gy, gx + math.cos(a) * (gr - 12), gy - math.sin(a) * (gr - 12))
        self._set(self.gauge_arc, extent=-max(1.0, GAUGE_SWEEP * frac), outline=CYAN if car.nitro_active else ACCENT)
        self._set(self.t_speed, text=str(int(kmh)))

        ox, oy, sc = self.mm
        c.coords(self.mm_dot, ox + car.x * sc - 4, oy + car.y * sc - 4, ox + car.x * sc + 4, oy + car.y * sc + 4)
        nxt = s.next_checkpoint()
        for cp, item in self.mm_cps:
            col = "#35d07f" if cp.reached else (GOLD if cp is nxt else "#ffffff")
            self._set(item, fill=col)

        if self.arrow is not None:
            tgt = s.target()
            if tgt:
                tx, ty, label = tgt
                dx, dy = tx - car.x, ty - car.y
                th = math.atan2(dx, -dy)
                cs, sn = math.cos(th), math.sin(th)
                base = [(0, -22), (15, 12), (0, 5), (-15, 12)]
                pts = []
                for px, py in base:
                    pts += [500 + px * cs - py * sn, 610 + px * sn + py * cs]
                c.coords(self.arrow, *pts)
                self._set(self.t_target, text=f"{label} • {int(math.hypot(dx, dy) * METERS_PER_PX)} m")

        if s.banner:
            self._set(self.t_banner, text=s.banner[0], fill=s.banner[2])
        else:
            self._set(self.t_banner, text="")
        if s.offroad_timer > 0.15:
            left = max(0.0, s.diff.offroad_grace - s.offroad_timer)
            self._set(self.t_off, text=f"OFF ROAD!  Return to the road  {left:.1f}s")
        else:
            self._set(self.t_off, text="")
        if countdown > 0:
            self._set(self.t_big, text=str(int(math.ceil(countdown))), fill=GOLD)
        elif s.elapsed < 0.7 and s.state == "running":
            self._set(self.t_big, text="GO!", fill=GREEN)
        elif s.state != "running":
            labels = {"victory": ("FINISH!", GREEN), "game_over": ("CRASHED!", RED), "failed": ("TIME UP!", RED)}
            text, col = labels.get(s.state, ("", TEXT))
            self._set(self.t_big, text=text, fill=col)
        else:
            self._set(self.t_big, text="")

    def _bar(self, item, x, y, full_w, h, frac, color):
        frac = max(0.0, min(1.0, frac))
        self.c.coords(item, *self._rr_points(x, y, x + max(h, full_w * frac), y + h, 8))
        self._set(item, fill=color)

    @staticmethod
    def _rr_points(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
                x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
