import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import json
import unittest
from pathlib import Path

from PIL import Image

import helpers  # noqa: F401
from game import mapgen, procart
from game.car import CAR_ORDER, CARS
from game.map import GameMap, load_thumbnail
from game.paths import ASSETS, asset

SOUNDS = ["engine_low", "engine_mid", "engine_high", "coin", "fuel", "checkpoint", "crash", "nitro", "victory",
          "gameover", "click", "warning", "music"]


class TestMaps(unittest.TestCase):
    def test_four_maps_exist(self):
        self.assertEqual(set(mapgen.MAP_ORDER), {"city", "desert", "forest", "highway"})

    def test_map_geometry_is_drivable(self):
        for map_id in mapgen.MAP_ORDER:
            with self.subTest(map=map_id):
                m = GameMap(map_id)
                self.assertGreaterEqual(m.path.min_turn_radius(), 170)
                self.assertGreater(m.path.min_separation(), m.road_width + 80)     # no overlapping roads
                self.assertEqual((m.world_w, m.world_h), (mapgen.WORLD_W, mapgen.WORLD_H))
                self.assertEqual(len(m.checkpoints), 5)

    def test_key_positions_are_on_the_road(self):
        for map_id in mapgen.MAP_ORDER:
            with self.subTest(map=map_id):
                m = GameMap(map_id)
                pts = [m.start, m.finish] + m.checkpoints + m.coins + m.fuel + m.obstacles
                bad = [p for p in pts if not m.is_road(p["x"], p["y"])]
                self.assertEqual(bad, [])
                self.assertFalse(m.is_road(5, 5))              # corner of the world is grass/buildings
                self.assertFalse(m.is_road(-10, 100))

    def test_checkpoint_order_and_finish(self):
        for map_id in mapgen.MAP_ORDER:
            m = GameMap(map_id)
            ss = [c["s"] for c in m.checkpoints]
            self.assertEqual(ss, sorted(ss))
            self.assertGreater(m.finish["s"], ss[-1])
            self.assertLess(m.start["s"], ss[0])

    def test_maps_look_different(self):
        thumbs = [load_thumbnail(m) for m in mapgen.MAP_ORDER]
        means = [tuple(v / 255 * 255 for v in __import__('PIL.ImageStat', fromlist=['x']).Stat(im).mean) for im in thumbs]
        for i in range(4):
            for j in range(i + 1, 4):
                self.assertGreater(sum(abs(a - b) for a, b in zip(means[i], means[j])), 25)

    def test_procedural_fallback_matches_assets(self):
        data = mapgen.build_map_data("highway")
        with open(asset("maps", "highway.json")) as fh:
            saved = json.load(fh)
        self.assertEqual(data["path"][:5], saved["path"][:5])
        self.assertEqual(len(data["checkpoints"]), len(saved["checkpoints"]))


class TestAssets(unittest.TestCase):
    def _open(self, rel, size=None, alpha=False):
        p = ASSETS / rel
        self.assertTrue(p.exists(), f"missing {rel}")
        with Image.open(p) as im:
            im.load()
            if size:
                self.assertEqual(im.size, size, rel)
            if alpha:
                rgba = im.convert("RGBA")
                self.assertLessEqual(rgba.getpixel((0, 0))[3], 8, f"{rel} has no transparent background")
                self.assertTrue(any(a > 200 for a in rgba.getchannel("A").getdata()), rel)

    def test_car_images_transparent_and_present(self):
        for c in CAR_ORDER:
            self._open(f"cars/{c}.png", procart.CAR_SIZE, alpha=True)
            self._open(f"cars/{c}_preview.png", procart.PREVIEW_SIZE, alpha=True)
            self.assertIn(c, CARS)
        self.assertGreaterEqual(len(CAR_ORDER), 3)

    def test_cars_are_top_down_tall_sprites(self):
        for c in CAR_ORDER:                       # top-down: longer than wide, symmetric left/right
            with Image.open(ASSETS / "cars" / f"{c}.png") as im:
                w, h = im.size
            self.assertGreater(h, w)

    def test_all_other_images(self):
        for k in procart.TRAFFIC_TYPES:
            self._open(f"cars/traffic_{k}.png", alpha=True)
        for k, (w, h, _) in procart.OBSTACLE_TYPES.items():
            self._open(f"obstacles/{k}.png", (w, h), alpha=True)
        for i in range(procart.COIN_FRAMES):
            self._open(f"obstacles/coin_{i}.png")
        self._open("obstacles/fuel.png")
        for n in ("heart", "heart_empty", "coin", "fuel", "nitro", "icon"):
            self._open(f"ui/{n}.png")
        for m in mapgen.MAP_ORDER:
            self._open(f"maps/{m}.jpg", (mapgen.WORLD_W, mapgen.WORLD_H))
            self._open(f"maps/{m}_mask.png", (mapgen.WORLD_W, mapgen.WORLD_H))
            self._open(f"maps/{m}_thumb.png")
            self.assertTrue((ASSETS / "maps" / f"{m}.json").exists())

    def test_sounds_exist_and_are_valid(self):
        import wave
        for n in SOUNDS:
            p = ASSETS / "sounds" / f"{n}.wav"
            self.assertTrue(p.exists(), n)
            with wave.open(str(p)) as w:
                self.assertGreater(w.getnframes(), 1000)

    def test_data_files_present(self):
        for n in ("scores.json", "settings.json"):
            with open(Path(__file__).resolve().parent.parent / "data" / n) as fh:
                json.load(fh)

    def test_audio_manager_never_crashes(self):
        import os
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from game.audio import AudioManager
        a = AudioManager()
        a.play("coin"), a.play("does_not_exist"), a.start_engine(), a.update_engine(0.5, 1.0)
        a.play_music(), a.set_volumes(0.3, 0.3), a.pause_engine(), a.resume_engine()
        a.shutdown()
        a.shutdown()                                # safe to call twice


if __name__ == "__main__":
    unittest.main()
