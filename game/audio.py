"""Sound effects, engine loop and music via ``pygame.mixer``.

pygame is used for audio ONLY (rendering is pure Tkinter). If pygame or an audio
device is unavailable the manager silently becomes a no-op, so the game still runs.
"""
from __future__ import annotations

import os

from .paths import asset

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:                                    # pragma: no cover - depends on the machine
    import pygame
    from pygame import mixer
except Exception:                       # ImportError or SDL problems
    pygame = None
    mixer = None

SFX_NAMES = ("coin", "fuel", "checkpoint", "crash", "nitro", "victory", "gameover", "click", "warning")
ENGINE_NAMES = ("engine_low", "engine_mid", "engine_high")


class AudioManager:
    def __init__(self, music_volume: float = 0.5, sfx_volume: float = 0.7):
        self.music_volume = music_volume
        self.sfx_volume = sfx_volume
        self.enabled = False
        self._sfx: dict[str, object] = {}
        self._engine: list[tuple[object, object]] = []   # (Sound, Channel)
        self._engine_on = False
        self._music_on = False
        self._nitro_cooldown = 0.0
        if mixer is None:
            return
        try:
            mixer.pre_init(22050, -16, 1, 512)
            mixer.init()
            mixer.set_num_channels(16)
            self.enabled = True
        except Exception:
            self.enabled = False
            return
        for name in SFX_NAMES:
            snd = self._load(name)
            if snd is not None:
                self._sfx[name] = snd
        for i, name in enumerate(ENGINE_NAMES):
            snd = self._load(name)
            if snd is not None:
                self._engine.append((snd, mixer.Channel(i)))

    # ----------------------------------------------------------------- loading
    @staticmethod
    def _load(name: str):
        try:
            return mixer.Sound(str(asset("sounds", f"{name}.wav")))
        except Exception:
            return None

    # ------------------------------------------------------------------ volume
    def set_volumes(self, music: float, sfx: float) -> None:
        self.music_volume = max(0.0, min(1.0, music))
        self.sfx_volume = max(0.0, min(1.0, sfx))
        if self.enabled:
            try:
                mixer.music.set_volume(self.music_volume * 0.6)
            except Exception:
                pass

    # --------------------------------------------------------------------- sfx
    def play(self, name: str, volume: float = 1.0) -> None:
        snd = self._sfx.get(name) if self.enabled else None
        if snd is None:
            return
        try:
            snd.set_volume(max(0.0, min(1.0, volume * self.sfx_volume)))
            snd.play()
        except Exception:
            pass

    # ------------------------------------------------------------------- music
    def play_music(self) -> None:
        if not self.enabled or self._music_on:
            return
        try:
            mixer.music.load(str(asset("sounds", "music.wav")))
            mixer.music.set_volume(self.music_volume * 0.6)
            mixer.music.play(-1)
            self._music_on = True
        except Exception:
            self._music_on = False

    def stop_music(self) -> None:
        if self.enabled and self._music_on:
            try:
                mixer.music.stop()
            except Exception:
                pass
        self._music_on = False

    def pause_music(self, paused: bool) -> None:
        if not (self.enabled and self._music_on):
            return
        try:
            mixer.music.pause() if paused else mixer.music.unpause()
        except Exception:
            pass

    # ------------------------------------------------------------------ engine
    def start_engine(self) -> None:
        if not self.enabled or self._engine_on:
            return
        for snd, ch in self._engine:
            try:
                snd.set_volume(0.0)
                ch.play(snd, loops=-1)
            except Exception:
                pass
        self._engine_on = True

    def update_engine(self, speed_ratio: float, throttle: float) -> None:
        """Cross-fade three looped engine tones by speed (ratio 0..1.35)."""
        if not (self.enabled and self._engine_on) or len(self._engine) < 3:
            return
        r = max(0.0, min(1.4, speed_ratio))
        weights = (max(0.0, 1.0 - r * 2.0), max(0.0, 1.0 - abs(r - 0.5) * 2.5), max(0.0, min(1.0, (r - 0.45) * 2.2)))
        load = 0.55 + 0.45 * throttle
        for (snd, _ch), w in zip(self._engine, weights):
            try:
                snd.set_volume(min(1.0, w * load * 0.55 * self.sfx_volume))
            except Exception:
                pass

    def pause_engine(self) -> None:
        if self.enabled and self._engine_on:
            for _snd, ch in self._engine:
                try:
                    ch.pause()
                except Exception:
                    pass

    def resume_engine(self) -> None:
        if self.enabled and self._engine_on:
            for _snd, ch in self._engine:
                try:
                    ch.unpause()
                except Exception:
                    pass

    def stop_engine(self) -> None:
        if self.enabled:
            for _snd, ch in self._engine:
                try:
                    ch.stop()
                except Exception:
                    pass
        self._engine_on = False

    # ---------------------------------------------------------------- shutdown
    def shutdown(self) -> None:
        """Release audio resources (called when the window closes)."""
        if not self.enabled:
            return
        try:
            self.stop_engine()
            self.stop_music()
            mixer.stop()
            mixer.quit()
        except Exception:
            pass
        self.enabled = False
