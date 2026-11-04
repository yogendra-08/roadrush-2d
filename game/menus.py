"""All non-gameplay screens: splash, main menu, mode/map selection, garage,
settings, high scores and the result (victory / game over) screen."""
from __future__ import annotations

import math
import tkinter as tk

from PIL import ImageTk

from . import __version__
from .car import CAR_ORDER, CARS, car_stats
from .map import GameMap, load_thumbnail
from .mapgen import MAP_ORDER, MAP_DEFS
from .save_manager import ACHIEVEMENTS
from .settings import DIFFICULTIES, DIFFICULTY_ORDER, get_difficulty
from .ui import (ACCENT, CYAN, GOLD, GREEN, MUTED, PANEL, PANEL_LIGHT, RED, TEXT, VIEW_H, VIEW_W, CanvasButton,
                 Segmented, Slider, draw_panel, draw_title, font, round_rect, stat_bar)


class Screen(tk.Frame):
    """Base class: a frame with a full-window canvas and the shared gradient backdrop."""

    def __init__(self, app):
        super().__init__(app.container, width=VIEW_W, height=VIEW_H)
        self.app = app
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H, highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=app.backdrop)
        self._afters: list[str] = []
        self._alive = True

    @property
    def play(self):
        return self.app.audio.play

    def button(self, x, y, w, h, text, command, style="secondary", size=16):
        return CanvasButton(self.canvas, x, y, w, h, text, command, style, size, self.play)

    def every(self, ms: int, fn) -> None:
        """Run ``fn`` repeatedly until the screen is destroyed (single chain per call)."""
        def tick():
            if not self._alive:
                return
            fn()
            self._afters.append(self.after(ms, tick))
        self._afters.append(self.after(ms, tick))

    def destroy(self) -> None:
        self._alive = False
        for a in self._afters:
            try:
                self.after_cancel(a)
            except tk.TclError:
                pass
        super().destroy()

    def back_button(self, target="main", label="◀  Back"):
        return self.button(110, 616, 170, 44, label, lambda: self.app.show(target), "secondary", 14)


# =========================================================================== splash
class SplashScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        c = self.canvas
        draw_title(c, 500, 220, "ROAD", 84)
        c.create_text(500, 300, text="R U S H", fill=ACCENT, font=font(46))
        c.create_text(500, 352, text="2D ARCADE DRIVING", fill=MUTED, font=font(14))
        round_rect(c, 300, 460, 700, 478, 9, fill="#10143a", outline="#3a4390")
        self.bar = round_rect(c, 300, 460, 318, 478, 9, fill=ACCENT, outline="")
        self.status = c.create_text(500, 506, text="Starting...", fill=MUTED, font=font(12))
        self._steps = [
            ("Checking assets...", app.sprites.preload),
            ("Warming up the engine...", app.init_audio),
            ("Loading maps...", lambda: [load_thumbnail(m) for m in MAP_ORDER]),
            ("Ready!", lambda: None),
        ]
        self._i = 0
        self.after(80, self._step)

    def _step(self):
        if not self._alive:
            return
        text, fn = self._steps[self._i]
        self.canvas.itemconfig(self.status, text=text)
        self.update_idletasks()
        try:
            fn()
        except Exception as exc:       # never block start-up on a non-essential step
            print("startup step failed:", exc)
        self._i += 1
        frac = self._i / len(self._steps)
        pts = self._rr(300, 460, 300 + 400 * frac, 478, 9)
        self.canvas.coords(self.bar, *pts)
        if self._i < len(self._steps):
            self._afters.append(self.after(220, self._step))
        else:
            self._afters.append(self.after(500, lambda: self.app.show("main")))

    @staticmethod
    def _rr(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
                x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# ======================================================================= main menu
class MainMenuScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        c = self.canvas
        draw_title(c, 290, 92, "ROAD", 58)
        c.create_text(290, 152, text="R U S H", fill=ACCENT, font=font(34))
        c.create_text(290, 190, text="Drive fast. Dodge everything.", fill=MUTED, font=font(12, False, True))
        entries = [("▶  PLAY", lambda: app.show("mode"), "primary"), ("GARAGE", lambda: app.show("garage"), "secondary"),
                   ("HIGH SCORES", lambda: app.show("scores"), "secondary"),
                   ("SETTINGS", lambda: app.show("settings"), "secondary"), ("EXIT", app.quit_app, "danger")]
        for i, (label, cmd, style) in enumerate(entries):
            self.button(290, 262 + i * 66, 280, 52, label, cmd, style, 17)
        # decorative animated road with the selected car
        round_rect(c, 590, 40, 960, 620, 24, fill="#12163a", outline="#3a4390", width=2)
        c.create_rectangle(640, 40, 910, 620, fill="#34383f", outline="")
        c.create_line(640, 40, 640, 620, fill="#e8e8e8", width=4)
        c.create_line(910, 40, 910, 620, fill="#e8e8e8", width=4)
        self.dashes = [c.create_rectangle(772, y, 778, y + 50, fill=GOLD, outline="") for y in range(-60, 640, 120)]
        self.car_item = c.create_image(775, 360, image=app.sprites.car_preview(app.settings.selected_car, 0.85))
        spec = CARS[app.settings.selected_car]
        c.create_text(775, 580, text=spec.name.upper(), fill=TEXT, font=font(14))
        c.create_text(500, 646, text=f"RoadRush v{__version__}   •   Use ← ↑ → ↓ to drive", fill=MUTED, font=font(9, False))
        self._t = 0.0
        self.every(30, self._animate)

    def _animate(self):
        self._t += 0.03
        for d in self.dashes:
            self.canvas.move(d, 0, 9)
            if self.canvas.coords(d)[1] > 640:
                self.canvas.move(d, 0, -700)
        self.canvas.coords(self.car_item, 775 + math.sin(self._t * 2.2) * 14, 360 + math.sin(self._t * 3.1) * 4)


# ===================================================================== mode select
class ModeSelectScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        c = self.canvas
        draw_title(c, 500, 60, "SELECT GAME MODE", 36)
        cards = [
            ("mission", "MISSION MODE", GOLD,
             ["Start at the line and hit", "5 checkpoints against the clock.", "Dodge traffic and obstacles,",
              "grab coins, then cross the", "finish line. You have 3 lives."]),
            ("endless", "ENDLESS MODE", CYAN,
             ["No finish line. Survive as", "long as you can while traffic", "and obstacles keep getting",
              "tougher. Score = distance", "+ survival + coins."]),
        ]
        for i, (key, title, col, lines) in enumerate(cards):
            x1 = 80 + i * 450
            draw_panel(c, x1, 110, x1 + 410, 440)
            c.create_text(x1 + 205, 150, text=title, fill=col, font=font(24))
            for j, line in enumerate(lines):
                c.create_text(x1 + 205, 210 + j * 28, text=line, fill=TEXT, font=font(13, False))
            best = max((app.save.best(key, m) for m in MAP_ORDER), default=0)
            c.create_text(x1 + 205, 372, text=f"BEST SCORE: {best:,}", fill=MUTED, font=font(12))
            self.button(x1 + 205, 410, 200, 42, "PLAY", lambda k=key: app.show("maps", mode=k), "primary", 15)
        c.create_text(500, 480, text="DIFFICULTY", fill=MUTED, font=font(12))
        Segmented(c, 500, 522, [(k, DIFFICULTIES[k].label) for k in DIFFICULTY_ORDER], app.settings.difficulty,
                  self._set_diff, 130, 42, 14, self.play)
        self.back_button()

    def _set_diff(self, key):
        self.app.settings.difficulty = key
        self.app.save_settings()


# ====================================================================== map select
class MapSelectScreen(Screen):
    def __init__(self, app, mode="mission"):
        super().__init__(app)
        self.mode = mode
        c = self.canvas
        draw_title(c, 500, 52, f"SELECT MAP  •  {mode.upper()}", 32)
        self._thumbs = {}
        self._cards = {}
        for i, map_id in enumerate(MAP_ORDER):
            x1 = 50 + i * 225
            img = load_thumbnail(map_id).resize((190, 142))
            self._thumbs[map_id] = ImageTk.PhotoImage(img)
            tag = f"card_{map_id}"
            frame = round_rect(c, x1, 96, x1 + 205, 300, 16, fill=PANEL, outline="#3a4390", width=3, tags=(tag,))
            c.create_image(x1 + 102, 180, image=self._thumbs[map_id], tags=(tag,))
            c.create_text(x1 + 102, 275, text=MAP_DEFS[map_id]["name"].upper(), fill=TEXT, font=font(13), tags=(tag,))
            self._cards[map_id] = frame
            c.tag_bind(tag, "<Button-1>", lambda e, m=map_id: self.select(m))
        draw_panel(c, 50, 322, 950, 560)
        self.t_name = c.create_text(80, 352, anchor="w", fill=GOLD, font=font(22))
        self.t_desc = c.create_text(80, 392, anchor="nw", fill=TEXT, font=font(13, False), width=560)
        self.t_info = c.create_text(80, 462, anchor="nw", fill=MUTED, font=font(12), width=640)
        self.t_best = c.create_text(80, 524, anchor="w", fill=CYAN, font=font(14))
        self.preview_car = c.create_image(820, 442, image=app.sprites.car_preview(app.settings.selected_car, 0.5))
        c.create_text(820, 540, text=CARS[app.settings.selected_car].name.upper(), fill=MUTED, font=font(11))
        self.back_button("mode")
        self.button(500, 616, 170, 44, "GARAGE", lambda: app.show("garage", back="maps", mode=mode), "secondary", 14)
        self.button(860, 616, 220, 48, "START  ▶", self.start, "primary", 18)
        self.select(app.settings.selected_map)

    def select(self, map_id):
        self.app.settings.selected_map = map_id
        self.play("click", 0.6)
        for m, frame in self._cards.items():
            self.canvas.itemconfig(frame, outline=GOLD if m == map_id else "#3a4390")
        gm = GameMap(map_id)
        c = self.canvas
        stars = "★" * MAP_DEFS[map_id]["stars"] + "☆" * (3 - MAP_DEFS[map_id]["stars"])
        c.itemconfig(self.t_name, text=f"{gm.name}    {stars}")
        c.itemconfig(self.t_desc, text=gm.description)
        diff = get_difficulty(self.app.settings.difficulty)
        extra = (f"Loop: {gm.length_m / 1000:.1f} km  •  5 checkpoints  •  Difficulty: {diff.label}"
                 if self.mode == "mission" else f"Loop: {gm.length_m / 1000:.1f} km  •  Endless laps  •  Difficulty: {diff.label}")
        c.itemconfig(self.t_info, text=extra)
        best = self.app.save.best(self.mode, map_id)
        c.itemconfig(self.t_best, text=f"BEST SCORE: {best:,}" if best else "BEST SCORE: —")

    def start(self):
        self.app.save_settings()
        self.app.show("game", mode=self.mode, map_id=self.app.settings.selected_map)


# ========================================================================== garage
class GarageScreen(Screen):
    def __init__(self, app, back="main", mode=None):
        super().__init__(app)
        self.back_target, self.mode = back, mode
        self.index = CAR_ORDER.index(app.settings.selected_car)
        c = self.canvas
        draw_title(c, 500, 52, "GARAGE", 36)
        c.create_oval(330, 470, 670, 560, fill="#12163a", outline="#3a4390", width=3)
        c.create_oval(360, 485, 640, 545, fill="#1c2250", outline="")
        self.car_item = c.create_image(500, 330, image=app.sprites.car_preview(CAR_ORDER[self.index]))
        self.t_name = c.create_text(500, 108, fill=GOLD, font=font(26))
        self.t_desc = c.create_text(500, 144, fill=MUTED, font=font(12, False))
        draw_panel(c, 700, 150, 960, 440)
        c.create_text(830, 180, text="STATS", fill=MUTED, font=font(12))
        self.stat_items = []
        self.button(100, 330, 70, 70, "◀", lambda: self.cycle(-1), "secondary", 22)
        self.button(260, 330, 70, 70, "▶", lambda: self.cycle(1), "secondary", 22)
        self.t_pos = c.create_text(180, 400, fill=MUTED, font=font(11))
        self.select_btn = self.button(830, 500, 210, 52, "SELECT", self.choose, "primary", 16)
        self.back_button(back, "◀  Back")
        self.canvas.bind("<Left>", lambda e: self.cycle(-1))
        self.canvas.bind("<Right>", lambda e: self.cycle(1))
        self.canvas.bind("<Return>", lambda e: self.choose())
        self.canvas.focus_set()
        self.refresh()

    def cycle(self, d):
        self.index = (self.index + d) % len(CAR_ORDER)
        self.play("click", 0.6)
        self.refresh()

    def refresh(self):
        car_id = CAR_ORDER[self.index]
        spec = CARS[car_id]
        c = self.canvas
        c.itemconfig(self.car_item, image=self.app.sprites.car_preview(car_id))
        c.itemconfig(self.t_name, text=spec.name.upper())
        c.itemconfig(self.t_desc, text=spec.description)
        c.itemconfig(self.t_pos, text=f"{self.index + 1} / {len(CAR_ORDER)}")
        for it in self.stat_items:
            c.delete(it)
        self.stat_items = []
        values = {"Speed": f"{int(spec.max_speed * 0.6)} km/h", "Acceleration": f"{spec.accel:.0f}",
                  "Handling": f"{spec.handling:.0f}°/s"}
        y = 218
        before = set(c.find_all())
        for label, v in car_stats(spec).items():
            c.create_text(724, y, anchor="w", text=label.upper(), fill=TEXT, font=font(11))
            c.create_text(938, y, anchor="e", text=values[label], fill=MUTED, font=font(10, False))
            stat_bar(c, 724, y + 14, 214, v, ACCENT if label == "Speed" else (CYAN if label == "Handling" else GOLD))
            y += 68
        self.stat_items = list(set(c.find_all()) - before)
        chosen = car_id == self.app.settings.selected_car
        self.select_btn.set_text("✔  SELECTED" if chosen else "SELECT")
        self.select_btn.set_style("success" if chosen else "primary")

    def choose(self):
        self.app.settings.selected_car = CAR_ORDER[self.index]
        self.app.save_settings()
        self.play("checkpoint", 0.6)
        self.refresh()

    def back_button(self, target="main", label="◀  Back"):
        mode = self.mode
        if target == "maps":
            return self.button(110, 616, 170, 44, label, lambda: self.app.show("maps", mode=mode or "mission"),
                               "secondary", 14)
        return super().back_button(target, label)


# ======================================================================== settings
class SettingsScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        c = self.canvas
        draw_title(c, 500, 60, "SETTINGS", 36)
        draw_panel(c, 190, 110, 810, 540)
        c.create_text(240, 170, anchor="w", text="Music volume", fill=TEXT, font=font(15))
        Slider(c, 460, 170, 260, app.settings.music_volume, self._music, app.save_settings)
        c.create_text(240, 240, anchor="w", text="Effects volume", fill=TEXT, font=font(15))
        Slider(c, 460, 240, 260, app.settings.sfx_volume, self._sfx, lambda: (app.save_settings(), self.play("coin")))
        c.create_text(240, 320, anchor="w", text="Difficulty", fill=TEXT, font=font(15))
        Segmented(c, 590, 320, [(k, DIFFICULTIES[k].label) for k in DIFFICULTY_ORDER], app.settings.difficulty,
                  self._diff, 110, 40, 10, self.play, 13)
        c.create_text(500, 378, text="Affects traffic speed, obstacle frequency, timer, collision penalties and\n"
                      "how fast Endless mode ramps up.", fill=MUTED, font=font(11, False), justify="center")
        self.reset_btn = self.button(500, 470, 300, 46, "Reset High Scores", self._reset, "danger", 14)
        self._armed = False
        self.back_button()

    def _music(self, v):
        self.app.settings.music_volume = v
        self.app.apply_volumes()

    def _sfx(self, v):
        self.app.settings.sfx_volume = v
        self.app.apply_volumes()

    def _diff(self, key):
        self.app.settings.difficulty = key
        self.app.save_settings()

    def _reset(self):
        if not self._armed:
            self._armed = True
            self.reset_btn.set_text("Click again to confirm")
            self._afters.append(self.after(3000, self._disarm))
        else:
            self.app.save.reset()
            self._disarm()
            self.reset_btn.set_text("Scores cleared ✔")

    def _disarm(self):
        if self._alive:
            self._armed = False
            self.reset_btn.set_text("Reset High Scores")


# ===================================================================== high scores
class HighScoresScreen(Screen):
    def __init__(self, app, tab="endless"):
        super().__init__(app)
        self.tab = tab
        self.dynamic: list[int] = []
        draw_title(self.canvas, 500, 52, "HIGH SCORES", 36)
        self.tab_buttons = {}
        for i, (key, label) in enumerate((("endless", "ENDLESS"), ("mission", "MISSION"), ("ach", "ACHIEVEMENTS"))):
            self.tab_buttons[key] = self.button(280 + i * 220, 108, 200, 42, label, lambda k=key: self.set_tab(k),
                                                "primary" if key == tab else "secondary", 14)
        self.back_button()
        self.set_tab(tab)

    def set_tab(self, tab):
        self.tab = tab
        c = self.canvas
        for it in self.dynamic:
            c.delete(it)
        before = set(c.find_all())
        for k, b in self.tab_buttons.items():
            b.set_style("primary" if k == tab else "secondary")
        if tab == "ach":
            self._draw_achievements()
        else:
            self._draw_scores(tab)
        self.dynamic = list(set(c.find_all()) - before)

    def _draw_scores(self, mode):
        c, save = self.canvas, self.app.save
        for i, map_id in enumerate(MAP_ORDER):
            x1 = 40 + i * 230
            draw_panel(c, x1, 150, x1 + 215, 575)
            c.create_text(x1 + 107, 178, text=MAP_DEFS[map_id]["name"].upper(), fill=GOLD, font=font(14))
            entries = save.top(mode, map_id, 5)
            if not entries:
                c.create_text(x1 + 107, 330, text="No scores yet", fill=MUTED, font=font(12, False, True))
            for r, e in enumerate(entries):
                y = 225 + r * 70
                c.create_text(x1 + 24, y, text=f"{r + 1}", fill=GOLD if r == 0 else MUTED, font=font(20))
                c.create_text(x1 + 50, y - 10, anchor="w", text=f"{int(e['score']):,}", fill=TEXT, font=font(16))
                detail = f"{e.get('date', '')}  •  {str(e.get('difficulty', '')).title()}"
                c.create_text(x1 + 50, y + 14, anchor="w", text=detail, fill=MUTED, font=font(9, False))

    def _draw_achievements(self):
        c, save = self.canvas, self.app.save
        st = save.data["stats"]
        summary = (f"Games: {st['games_played']}    Coins: {st['total_coins']}    Victories: {st['victories']}"
                   f"    Top speed: {st['top_speed_kmh']} km/h    Distance: {st['total_distance'] * 0.25 / 1000:.1f} km")
        c.create_text(500, 176, text=summary, fill=MUTED, font=font(12))
        for i, (key, (title, desc)) in enumerate(ACHIEVEMENTS.items()):
            col, row = i % 2, i // 2
            x1, y1 = 60 + col * 450, 215 + row * 115
            got = key in save.data["achievements"]
            draw_panel(c, x1, y1, x1 + 430, y1 + 98, fill=PANEL_LIGHT if got else PANEL, outline=GOLD if got else "#3a4390")
            c.create_text(x1 + 40, y1 + 49, text="★" if got else "☆", fill=GOLD if got else MUTED, font=font(30))
            c.create_text(x1 + 80, y1 + 34, anchor="w", text=title, fill=TEXT if got else MUTED, font=font(16))
            c.create_text(x1 + 80, y1 + 64, anchor="w", text=desc, fill=MUTED, font=font(11, False))
            if got:
                c.create_text(x1 + 415, y1 + 14, anchor="e", text=save.data["achievements"][key], fill=GREEN, font=font(9))


# ==================================================================== result screen
class ResultScreen(Screen):
    TITLES = {"victory": ("VICTORY!", GREEN), "game_over": ("GAME OVER", RED), "failed": ("MISSION FAILED", RED)}

    def __init__(self, app, result: dict, new_best: bool = False, achievements=()):
        super().__init__(app)
        self.result = result
        c = self.canvas
        title, col = self.TITLES.get(result["state"], ("RESULT", TEXT))
        draw_title(c, 500, 72, title, 56, col)
        c.create_text(500, 126, text=result["reason"], fill=MUTED, font=font(15, False, True))
        draw_panel(c, 250, 160, 750, 500)
        c.create_text(500, 205, text=f"{result['score']:,}", fill=GOLD, font=font(46))
        c.create_text(500, 244, text="FINAL SCORE" + ("   •   NEW BEST!" if new_best else ""),
                      fill=CYAN if new_best else MUTED, font=font(12))
        rows = [("Mode", f"{result['mode'].title()}  •  {MAP_DEFS[result['map']]['name']}"),
                ("Coins", str(result["coins"])), ("Distance", f"{result['distance_m']} m"),
                ("Time", f"{result['time']:.1f} s"), ("Top speed", f"{result['top_speed_kmh']} km/h")]
        if result["mode"] == "mission":
            rows.insert(2, ("Checkpoints", f"{result['checkpoints']} / 5"))
        for i, (k, v) in enumerate(rows):
            y = 285 + i * 30
            c.create_text(290, y, anchor="w", text=k.upper(), fill=MUTED, font=font(11))
            c.create_text(710, y, anchor="e", text=v, fill=TEXT, font=font(14))
        for i, key in enumerate(achievements):
            c.create_text(500, 482 + i * 18, text=f"★ Achievement unlocked: {ACHIEVEMENTS[key][0]}", fill=GOLD,
                          font=font(12))
        self.button(300, 560, 220, 52, "PLAY AGAIN", lambda: app.show("game", mode=result["mode"], map_id=result["map"]),
                    "primary", 17)
        self.button(560, 560, 200, 52, "MAIN MENU", lambda: app.show("main"), "secondary", 16)
        self.button(790, 560, 150, 52, "SCORES", lambda: app.show("scores", tab=result["mode"]), "secondary", 14)
