import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import json
import os
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from game.save_manager import ACHIEVEMENTS, SaveManager
from game.settings import Settings, SettingsManager


class TestSaveManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "scores.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_starts_empty_without_file(self):
        sm = SaveManager(self.path)
        self.assertEqual(sm.best("endless", "city"), 0)
        self.assertEqual(sm.top("mission", "forest"), [])

    def test_high_score_persists_across_instances(self):
        sm = SaveManager(self.path)
        self.assertTrue(sm.add_score("endless", "city", {"score": 1200}))
        self.assertFalse(sm.add_score("endless", "city", {"score": 900}))
        self.assertTrue(sm.add_score("endless", "city", {"score": 5000}))
        again = SaveManager(self.path)
        self.assertEqual(again.best("endless", "city"), 5000)
        self.assertEqual([e["score"] for e in again.top("endless", "city")], [5000, 1200, 900])
        self.assertEqual(again.best("endless", "desert"), 0)

    def test_keeps_only_ten_entries(self):
        sm = SaveManager(self.path)
        for i in range(25):
            sm.add_score("mission", "highway", {"score": i * 10})
        self.assertEqual(len(sm.data["scores"]["mission"]["highway"]), 10)
        self.assertEqual(sm.best("mission", "highway"), 240)

    def test_corrupt_file_is_recovered(self):
        self.path.write_text("{ this is not json", encoding="utf-8")
        sm = SaveManager(self.path)
        self.assertEqual(sm.best("endless", "city"), 0)
        self.assertTrue(sm.add_score("endless", "city", {"score": 10}))

    def test_wrong_structure_is_sanitised(self):
        self.path.write_text(json.dumps({"scores": {"endless": {"city": "bad", "desert": [1, {"score": "x"},
                             {"score": 77}]}}, "stats": {"games_played": "lots"}, "achievements": [1]}), encoding="utf-8")
        sm = SaveManager(self.path)
        self.assertEqual(sm.best("endless", "desert"), 77)
        self.assertEqual(sm.data["stats"]["games_played"], 0)
        self.assertEqual(sm.data["achievements"], {})

    def test_unknown_mode_or_map_ignored(self):
        sm = SaveManager(self.path)
        self.assertFalse(sm.add_score("nope", "city", {"score": 1}))
        self.assertFalse(sm.add_score("endless", "mars", {"score": 1}))

    def test_achievements_and_stats(self):
        sm = SaveManager(self.path)
        got = sm.record_run("mission", "city", coins=120, distance=1000, top_speed_kmh=310, victory=True,
                            lives_lost=0, score=2000)
        self.assertEqual(set(got), {"first_win", "coin_100", "speed_demon", "untouchable"})
        self.assertEqual(sm.record_run("mission", "city", coins=0, distance=0, top_speed_kmh=0, victory=True,
                                       lives_lost=0, score=1), [])        # not unlocked twice
        for m in ("desert", "forest", "highway"):
            last = sm.record_run("mission", m, coins=0, distance=0, top_speed_kmh=0, victory=True, lives_lost=1, score=1)
        self.assertIn("world_tour", last)
        self.assertEqual(SaveManager(self.path).data["stats"]["victories"], 5)
        self.assertTrue(set(sm.data["achievements"]) <= set(ACHIEVEMENTS))

    def test_reset(self):
        sm = SaveManager(self.path)
        sm.add_score("endless", "city", {"score": 5})
        sm.reset()
        self.assertEqual(SaveManager(self.path).best("endless", "city"), 0)


class TestSettings(unittest.TestCase):
    def test_roundtrip_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            mgr = SettingsManager(path)
            self.assertEqual(mgr.settings.difficulty, "medium")       # default difficulty
            mgr.settings.music_volume = 0.2
            mgr.settings.selected_car = "supercar"
            self.assertTrue(mgr.save())
            again = SettingsManager(path)
            self.assertEqual(again.settings.music_volume, 0.2)
            self.assertEqual(again.settings.selected_car, "supercar")

    def test_invalid_values_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text(json.dumps({"music_volume": 7, "sfx_volume": "loud", "difficulty": "insane",
                                        "selected_car": "tank", "selected_map": 3}), encoding="utf-8")
            s = SettingsManager(path).settings
            self.assertEqual((s.music_volume, s.sfx_volume), (1.0, 0.7))
            self.assertEqual((s.difficulty, s.selected_car, s.selected_map), ("medium", "sports", "city"))

    def test_garbage_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text("[1,2,3]", encoding="utf-8")
            self.assertEqual(SettingsManager(path).settings, Settings())


if __name__ == "__main__":
    unittest.main()
