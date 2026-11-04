"""Application shell: window, screen navigation, shared services."""
from __future__ import annotations

import tkinter as tk
import traceback

from PIL import ImageTk

from .audio import AudioManager
from .gameplay import GameplayScreen
from .menus import (GarageScreen, HighScoresScreen, MainMenuScreen, MapSelectScreen, ModeSelectScreen,
                    ResultScreen, SettingsScreen, SplashScreen)
from .save_manager import SaveManager
from .settings import SettingsManager
from .sprites import Sprites
from .ui import VIEW_H, VIEW_W, gradient_image, pick_font_family


class RoadRushApp:
    SCREENS = {
        "splash": SplashScreen, "main": MainMenuScreen, "mode": ModeSelectScreen, "maps": MapSelectScreen,
        "garage": GarageScreen, "settings": SettingsScreen, "scores": HighScoresScreen,
        "result": ResultScreen, "game": GameplayScreen,
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RoadRush")
        self.root.resizable(False, False)
        self.root.configure(bg="black")
        x = max(0, (self.root.winfo_screenwidth() - VIEW_W) // 2)
        y = max(0, (self.root.winfo_screenheight() - VIEW_H) // 3)
        self.root.geometry(f"{VIEW_W}x{VIEW_H}+{x}+{y}")
        self.root.report_callback_exception = self._on_error
        pick_font_family(self.root)

        self.settings_mgr = SettingsManager()
        self.settings = self.settings_mgr.settings
        self.save = SaveManager()
        self.sprites = Sprites()
        self.audio = AudioManager(self.settings.music_volume, self.settings.sfx_volume)
        self.backdrop = ImageTk.PhotoImage(gradient_image())
        try:
            self.root.iconphoto(True, self.sprites.app_icon())
        except tk.TclError:
            pass

        self.container = tk.Frame(self.root, width=VIEW_W, height=VIEW_H, bg="black")
        self.container.pack()
        self.container.pack_propagate(False)
        self.current: tk.Frame | None = None
        self._closing = False
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    # ---------------------------------------------------------------- services
    def init_audio(self) -> None:
        self.apply_volumes()
        self.audio.play_music()

    def apply_volumes(self) -> None:
        self.audio.set_volumes(self.settings.music_volume, self.settings.sfx_volume)

    def save_settings(self) -> None:
        self.settings_mgr.save()

    # -------------------------------------------------------------- navigation
    def show(self, name: str, **kwargs) -> None:
        if self._closing:
            return
        if self.current is not None:
            self.current.destroy()
            self.current = None
        self.audio.stop_engine() if name != "game" else None
        screen = self.SCREENS[name](self, **kwargs)
        screen.pack()
        self.current = screen
        self.root.update_idletasks()

    def run(self) -> None:
        self.show("splash")
        self.root.mainloop()

    def quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            if self.current is not None:
                self.current.destroy()
            self.settings_mgr.save()
            self.save.save()
        finally:
            self.audio.shutdown()
            self.root.destroy()

    @staticmethod
    def _on_error(exc, val, tb) -> None:
        traceback.print_exception(exc, val, tb)
