"""End-to-end GUI test using real Tk events. Skipped automatically when no display
is available (on Linux run with:  xvfb-run -a python -m unittest tests.test_gui_smoke)."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import helpers
from helpers import Autopilot

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")      # no sound card needed in CI

import tkinter as tk


def _display_available() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_display_available(), "no display available for Tkinter")
class TestGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import game.save_manager, game.settings
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        cls._orig = (game.save_manager.DATA, game.settings.DATA)
        game.save_manager.DATA = game.settings.DATA = cls.data       # never touch the real data folder
        from game.app import RoadRushApp
        cls.app = RoadRushApp()
        cls.root = cls.app.root

    @classmethod
    def tearDownClass(cls):
        import game.save_manager, game.settings
        cls.app.quit_app()
        game.save_manager.DATA, game.settings.DATA = cls._orig
        cls.tmp.cleanup()

    # ---------------------------------------------------------------- helpers
    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            time.sleep(0.004)

    def click(self, x, y):
        c = self.app.current.canvas
        c.event_generate("<Motion>", x=x, y=y)
        c.event_generate("<ButtonPress-1>", x=x, y=y)
        c.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.pump(0.15)

    def key(self, sym, seconds=0.0):
        c = self.app.current.canvas
        c.event_generate("<KeyPress>", keysym=sym)
        self.pump(seconds)

    def keyup(self, sym):
        self.app.current.canvas.event_generate("<KeyRelease>", keysym=sym)
        self.pump(0.1)

    def kind(self):
        return type(self.app.current).__name__

    def start_game(self, mode="mission", map_id="city", skip_countdown=True):
        self.app.show("game", mode=mode, map_id=map_id)
        g = self.app.current
        self.pump(0.2)
        if skip_countdown:
            g.countdown = 0.01
            self.pump(0.2)
        return g

    # ------------------------------------------------------------------ tests
    def test_01_splash_then_main_menu(self):
        self.app.show("splash")
        self.pump(2.5)
        self.assertEqual(self.kind(), "MainMenuScreen")

    def test_02_menu_navigation_by_clicking(self):
        self.app.show("main")
        self.click(290, 262)                      # PLAY
        self.assertEqual(self.kind(), "ModeSelectScreen")
        self.click(130 + 160, 410)                # Mission PLAY
        self.assertEqual(self.kind(), "MapSelectScreen")
        self.assertEqual(self.app.current.mode, "mission")
        self.click(50 + 225 + 100, 180)           # choose Desert card
        self.assertEqual(self.app.settings.selected_map, "desert")
        self.click(860, 616)                      # START
        self.assertEqual(self.kind(), "GameplayScreen")
        self.assertEqual(self.app.current.map_id, "desert")
        self.app.show("main")

    def test_03_garage_selection_is_saved(self):
        self.app.show("garage")
        self.click(260, 330)                      # next car
        self.click(830, 500)                      # SELECT
        self.assertEqual(self.app.settings.selected_car, "racing")
        saved = json.loads((self.data / "settings.json").read_text())
        self.assertEqual(saved["selected_car"], "racing")
        self.app.current.canvas.event_generate("<Right>")
        self.pump(0.1)
        self.click(830, 500)
        self.assertEqual(self.app.settings.selected_car, "supercar")
        self.app.settings.selected_car = "sports"
        self.app.show("main")

    def test_04_settings_persist(self):
        self.app.show("settings")
        c = self.app.current.canvas
        self.click(460 + 260 * 0.2, 170)          # music slider to ~20 %
        self.click(590 + 120, 320)                # Hard
        self.assertEqual(self.app.settings.difficulty, "hard")
        self.assertAlmostEqual(self.app.settings.music_volume, 0.2, delta=0.05)
        saved = json.loads((self.data / "settings.json").read_text())
        self.assertEqual(saved["difficulty"], "hard")
        self.app.settings.difficulty = "medium"
        self.app.show("main")

    def test_05_keyboard_driving_pause_and_single_loop(self):
        g = self.start_game()
        c = g.canvas
        self.assertEqual(g.session.state, "running")
        e0 = g.session.elapsed
        self.pump(1.0)
        rate = g.session.elapsed - e0
        self.assertTrue(0.7 < rate < 1.3, f"game loop runs at {rate:.2f}x real time (duplicate loops?)")
        self.key("Up", 1.5)
        self.assertGreater(g.session.car.speed, 80)
        h0 = g.session.car.heading
        self.key("Right", 0.8)
        self.keyup("Right")
        self.assertNotEqual(round(g.session.car.heading), round(h0))
        self.assertNotIn("right", g.input.down)
        self.keyup("Up")
        # pause / resume with ESC
        self.key("Escape", 0.3)
        self.assertTrue(g.paused)
        t = g.session.elapsed
        self.pump(0.6)
        self.assertEqual(g.session.elapsed, t)
        self.key("Escape", 0.3)
        self.assertFalse(g.paused)
        self.pump(0.3)
        self.assertGreater(g.session.elapsed, t)
        self.app.show("main")

    def test_06_pause_menu_buttons_and_restart(self):
        g = self.start_game()
        self.key("Up", 0.8)
        self.keyup("Up")
        g.pause()
        self.pump(0.2)
        self.click(500, 255)                      # Restart
        self.assertFalse(g.paused)
        self.assertEqual((g.session.lives, g.session.coins), (3, 0))
        self.assertLess(g.session.elapsed, 1.0)
        self.assertGreater(g.countdown, 2.0)      # countdown again
        g.pause()
        self.pump(0.2)
        self.click(500, 520)                      # Main Menu
        self.assertEqual(self.kind(), "MainMenuScreen")

    def test_07_victory_flow_saves_score(self):
        g = self.start_game()
        s = g.session
        s.obstacles.clear()
        s.traffic.clear()
        bot = Autopilot(s)
        for _ in range(60 * 90):
            s.update(1 / 60, bot.controls())
            if s.state != "running":
                break
        self.assertEqual(s.state, "victory")
        self.pump(2.6)
        self.assertEqual(self.kind(), "ResultScreen")
        self.assertEqual(self.app.current.result["state"], "victory")
        data = json.loads((self.data / "scores.json").read_text())
        self.assertEqual(len(data["scores"]["mission"]["city"]), 1)
        self.assertIn("first_win", data["achievements"])
        self.click(300, 560)                      # PLAY AGAIN
        self.assertEqual(self.kind(), "GameplayScreen")
        self.app.show("main")

    def test_08_game_over_flow(self):
        g = self.start_game()
        s = g.session
        s.lives = 1
        from game.entities import Obstacle
        s.obstacles.append(Obstacle("rock", s.car.x, s.car.y, 0))
        self.pump(0.3)
        self.assertEqual(s.state, "game_over")
        self.pump(2.6)
        self.assertEqual(self.kind(), "ResultScreen")
        self.assertEqual(self.app.current.result["state"], "game_over")
        self.click(560, 560)                      # MAIN MENU
        self.assertEqual(self.kind(), "MainMenuScreen")

    def test_09_mission_failed_timeout(self):
        g = self.start_game()
        g.session.time_left = 0.3
        self.pump(3.0)
        self.assertEqual(self.kind(), "ResultScreen")
        self.assertEqual(self.app.current.result["state"], "failed")
        self.app.show("main")

    def test_10_endless_mode_and_highscore_screen(self):
        g = self.start_game("endless", "forest")
        s = g.session
        s.lives = 1
        bot = Autopilot(s)
        for _ in range(60 * 10):
            s.update(1 / 60, bot.controls())
        self.assertGreater(s.score, 0)
        from game.entities import Obstacle
        s.obstacles.append(Obstacle("rock", s.car.x, s.car.y, 0))
        s.invuln = 0
        self.pump(3.0)
        self.assertEqual(self.kind(), "ResultScreen")
        data = json.loads((self.data / "scores.json").read_text())
        self.assertEqual(len(data["scores"]["endless"]["forest"]), 1)
        self.app.show("scores", tab="endless")
        self.pump(0.3)
        self.app.show("scores", tab="ach")
        self.pump(0.3)
        self.app.show("main")

    def test_11_screens_do_not_leak_game_loops(self):
        for _ in range(3):
            self.start_game()
            self.app.show("main")
        self.pump(0.3)
        self.assertEqual(self.kind(), "MainMenuScreen")


if __name__ == "__main__":
    unittest.main()
