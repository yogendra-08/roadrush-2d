"""The gameplay screen: owns the single game loop (Tkinter ``after``) and input."""
from __future__ import annotations

import time
import tkinter as tk

from .camera import Camera
from .car import CARS, Controls
from .engine import RUNNING, GameSession
from .hud import Hud
from .map import GameMap
from .renderer import WorldRenderer, build_tiles
from .settings import get_difficulty
from .ui import (ACCENT, MUTED, TEXT, VIEW_H, VIEW_W, CanvasButton, Slider, draw_panel, draw_title, font)

FRAME_MS = 15
COUNTDOWN_SECONDS = 3.0
END_DELAY = 1.6          # seconds the final frame stays on screen before the result screen


class InputState:
    """Tracks held keys. Includes a tiny release debounce so X11 key auto-repeat
    (release+press pairs) never makes the car stutter."""

    UP = {"up", "w"}
    DOWN = {"down", "s"}
    LEFT = {"left", "a"}
    RIGHT = {"right", "d"}
    NITRO = {"shift_l", "shift_r", "n"}

    def __init__(self, widget: tk.Misc):
        self.widget = widget
        self.down: set[str] = set()
        self._pending: dict[str, str] = {}

    def press(self, key: str) -> None:
        pending = self._pending.pop(key, None)
        if pending:
            self.widget.after_cancel(pending)
        self.down.add(key)

    def release(self, key: str) -> None:
        if key in self._pending:
            return
        self._pending[key] = self.widget.after(18, lambda k=key: self._really_release(k))

    def _really_release(self, key: str) -> None:
        self._pending.pop(key, None)
        self.down.discard(key)

    def clear(self) -> None:
        for p in self._pending.values():
            try:
                self.widget.after_cancel(p)
            except tk.TclError:
                pass
        self._pending.clear()
        self.down.clear()

    def controls(self) -> Controls:
        d = self.down
        steer = (1.0 if d & self.RIGHT else 0.0) - (1.0 if d & self.LEFT else 0.0)
        return Controls(throttle=1.0 if d & self.UP else 0.0, brake=1.0 if d & self.DOWN else 0.0,
                        steer=steer, handbrake="space" in d, nitro=bool(d & self.NITRO))


class GameplayScreen(tk.Frame):
    def __init__(self, app, mode: str, map_id: str):
        super().__init__(app.container, width=VIEW_W, height=VIEW_H, bg="black")
        self.app, self.mode, self.map_id = app, mode, map_id
        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H, highlightthickness=0, bg="#101018")
        self.canvas.pack()
        self.game_map = GameMap(map_id)
        self.tiles = build_tiles(self.game_map.background())
        self.game_map.release_background()           # tiles hold the pixels now
        self.input = InputState(self.canvas)
        self._after: str | None = None
        self._pause_items = False
        self.paused = False
        self.finished = False
        self._nitro_was_on = False
        self.canvas.bind("<KeyPress>", self._on_press)
        self.canvas.bind("<KeyRelease>", self._on_release)
        self.canvas.bind("<FocusOut>", lambda e: self.pause() if self._can_pause() else None)
        self.start_session()

    # --------------------------------------------------------------- lifecycle
    def start_session(self) -> None:
        """(Re)build everything for a fresh run - used for first start and 'restart'."""
        self._cancel_loop()
        self.input.clear()
        self.canvas.delete("all")
        self.paused = False
        self.finished = False
        self._pause_items = False
        s = self.app.settings
        self.session = GameSession(self.game_map, CARS[s.selected_car], self.mode, get_difficulty(s.difficulty))
        self.camera = Camera(VIEW_W, VIEW_H, self.game_map.world_w, self.game_map.world_h)
        car = self.session.car
        self.camera.snap_to(car.x, car.y)
        self.renderer = WorldRenderer(self.canvas, self.app.sprites, self.session, self.camera, self.tiles)
        self.hud = Hud(self.canvas, self.app.sprites, self.session, self.toggle_pause, self.app.audio.play)
        self.countdown = COUNTDOWN_SECONDS
        self.end_timer = END_DELAY
        self._last_count_tick = 99
        self.app.audio.stop_engine()
        self.app.audio.start_engine()
        self.canvas.focus_set()
        self._last = time.perf_counter()
        self._loop()

    def destroy(self) -> None:
        self._cancel_loop()
        self.input.clear()
        self.app.audio.stop_engine()
        super().destroy()

    def _cancel_loop(self) -> None:
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    # -------------------------------------------------------------------- input
    def _on_press(self, e: tk.Event) -> None:
        key = e.keysym.lower()
        if key == "escape":
            self.toggle_pause()
            return
        self.input.press(key)

    def _on_release(self, e: tk.Event) -> None:
        self.input.release(e.keysym.lower())

    def _can_pause(self) -> bool:
        return not self.paused and not self.finished and self.session.state == RUNNING

    # --------------------------------------------------------------- game loop
    def _loop(self) -> None:
        self._after = None
        now = time.perf_counter()
        dt = min(now - self._last, 0.05)
        self._last = now
        s = self.session
        if not self.paused:
            if self.countdown > 0:
                self.countdown -= dt
                tick = int(self.countdown) + 1
                if tick != self._last_count_tick and self.countdown > 0:
                    self._last_count_tick = tick
                    self.app.audio.play("click", 0.7)
                if self.countdown <= 0:
                    self.app.audio.play("checkpoint", 0.6)
            elif s.state == RUNNING:
                s.update(dt, self.input.controls())
                self._handle_events()
                self.app.audio.update_engine(s.car.speed / s.car.spec.max_speed, self.input.controls().throttle)
            else:
                self.end_timer -= dt
                s.car.vx *= 0.96
                s.car.vy *= 0.96
                if self.end_timer <= 0 and not self.finished:
                    self._finish()
                    return
            lead = 0.22
            self.camera.follow(s.car.x + s.car.vx * lead, s.car.y + s.car.vy * lead, dt)
            self.renderer.draw(dt)
            self.hud.update(self.countdown)
        try:
            self._after = self.after(FRAME_MS, self._loop)
        except tk.TclError:
            self._after = None

    def _handle_events(self) -> None:
        audio, s = self.app.audio, self.session
        for name, data in s.pop_events():
            if name == "coin":
                audio.play("coin", 0.8)
            elif name == "fuel":
                audio.play("fuel")
            elif name == "checkpoint":
                audio.play("checkpoint")
            elif name == "crash":
                audio.play("crash")
                self.renderer.shake = 0.35
                car = s.car
                self.renderer.burst(car.x, car.y)
            elif name == "warning" or name == "offroad":
                audio.play("warning", 0.6)
            elif name == "victory":
                audio.play("victory")
                audio.stop_engine()
            elif name in ("game_over", "failed"):
                audio.play("gameover")
                audio.stop_engine()
        nitro_on = s.car.nitro_active
        if nitro_on and not self._nitro_was_on:
            audio.play("nitro", 0.7)
        self._nitro_was_on = nitro_on

    def _finish(self) -> None:
        self.finished = True
        s = self.session
        result = s.result()
        save = self.app.save
        new_best = False
        if result["mode"] == "endless" or result["victory"]:
            new_best = save.add_score(result["mode"], result["map"], {
                "score": result["score"], "coins": result["coins"], "time": result["time"],
                "distance_m": result["distance_m"], "car": result["car"], "difficulty": result["difficulty"]})
        achievements = save.record_run(result["mode"], result["map"], coins=result["coins"],
                                       distance=result["distance_px"], top_speed_kmh=result["top_speed_kmh"],
                                       victory=result["victory"], lives_lost=result["lives_lost"],
                                       score=result["score"])
        self.app.show("result", result=result, new_best=new_best, achievements=achievements)

    # -------------------------------------------------------------------- pause
    def toggle_pause(self) -> None:
        if self.paused:
            self.resume()
        elif self._can_pause() or (self.countdown > 0 and not self.finished):
            self.pause()

    def pause(self) -> None:
        if self.paused or self.finished:
            return
        self.paused = True
        self.input.clear()
        self.app.audio.pause_engine()
        self._draw_pause_menu()

    def resume(self) -> None:
        if not self.paused:
            return
        self.canvas.delete("pause")
        self.paused = False
        self.app.audio.resume_engine()
        self.canvas.focus_set()
        self._last = time.perf_counter()

    def _draw_pause_menu(self) -> None:
        c, app = self.canvas, self.app
        play = app.audio.play
        items_before = set(c.find_all())
        c.create_rectangle(0, 0, VIEW_W, VIEW_H, fill="#05060f", stipple="gray50", outline="")
        draw_panel(c, 330, 70, 670, 600)
        draw_title(c, 500, 118, "PAUSED", 34)
        widgets = []
        widgets.append(CanvasButton(c, 500, 190, 240, 50, "Resume", self.resume, "primary", 17, play))
        widgets.append(CanvasButton(c, 500, 255, 240, 50, "Restart", self._restart, "secondary", 17, play))
        c.create_text(405, 335, text="Music", fill=MUTED, font=font(12), anchor="w")
        Slider(c, 405, 362, 190, app.settings.music_volume, self._set_music, app.save_settings)
        c.create_text(405, 405, text="Effects", fill=MUTED, font=font(12), anchor="w")
        Slider(c, 405, 432, 190, app.settings.sfx_volume, self._set_sfx, lambda: (app.save_settings(), play("coin")))
        widgets.append(CanvasButton(c, 500, 520, 240, 50, "Main Menu", self._to_menu, "danger", 17, play))
        for item in set(c.find_all()) - items_before:
            c.addtag_withtag("pause", item)
        for w in widgets:
            c.addtag_withtag("pause", w.tag)
        c.tag_raise("pause")

    def _set_music(self, v: float) -> None:
        self.app.settings.music_volume = v
        self.app.apply_volumes()

    def _set_sfx(self, v: float) -> None:
        self.app.settings.sfx_volume = v
        self.app.apply_volumes()

    def _restart(self) -> None:
        self.start_session()

    def _to_menu(self) -> None:
        self.app.show("main")
