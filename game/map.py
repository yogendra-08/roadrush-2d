"""Loads a playable map: layout data, road collision mask and background image.

Everything normally comes from ``assets/maps``. If a file is missing or broken
the map is rebuilt procedurally (see ``mapgen``), so a map never fails to load.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from . import mapgen
from .paths import asset
from .roadpath import RoadPath

METERS_PER_PX = 0.25


def _load_json(map_id: str) -> dict:
    path = asset("maps", f"{map_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for key in ("path", "start", "finish", "checkpoints", "coins", "fuel", "obstacles", "road_width", "lanes"):
            if key not in data:
                raise ValueError(f"missing key {key}")
        return data
    except (OSError, ValueError, TypeError):
        return mapgen.build_map_data(map_id)


class GameMap:
    """Immutable description of one playable map."""

    def __init__(self, map_id: str):
        if map_id not in mapgen.MAP_DEFS:
            raise KeyError(f"unknown map '{map_id}'")
        self.map_id = map_id
        data = _load_json(map_id)
        self.data = data
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.theme: str = data["theme"]
        self.stars: int = data.get("stars", 2)
        self.world_w, self.world_h = int(data["world"][0]), int(data["world"][1])
        self.road_width: float = float(data["road_width"])
        self.lanes: list[tuple[float, int]] = [(float(o), int(d)) for o, d in data["lanes"]]
        self.path = RoadPath([tuple(p) for p in data["path"]])
        self.start: dict = data["start"]
        self.finish: dict = data["finish"]
        self.checkpoints: list[dict] = data["checkpoints"]
        self.coins: list[dict] = data["coins"]
        self.fuel: list[dict] = data["fuel"]
        self.obstacles: list[dict] = data["obstacles"]
        self.obstacle_types: list[str] = list(mapgen.MAP_DEFS[map_id]["obstacles"])
        self._mask = self._load_mask()
        self._background: Image.Image | None = None

    # ------------------------------------------------------------ road mask
    def _load_mask(self) -> bytes:
        size = (self.world_w, self.world_h)
        try:
            with Image.open(asset("maps", f"{self.map_id}_mask.png")) as im:
                if im.size != size:
                    raise ValueError("mask size mismatch")
                return im.convert("L").tobytes()
        except (OSError, ValueError):
            return mapgen._disc_mask(self.path, self.road_width / 2, size).tobytes()

    def is_road(self, x: float, y: float) -> bool:
        ix, iy = int(x), int(y)
        if ix < 0 or iy < 0 or ix >= self.world_w or iy >= self.world_h:
            return False
        return self._mask[iy * self.world_w + ix] > 127

    # ------------------------------------------------------------ images
    def background(self) -> Image.Image:
        """The full-size background (loaded lazily, rebuilt if the file is missing)."""
        if self._background is None:
            try:
                with Image.open(asset("maps", f"{self.map_id}.jpg")) as im:
                    img = im.convert("RGB")
                if img.size != (self.world_w, self.world_h):
                    raise ValueError("background size mismatch")
                self._background = img
            except (OSError, ValueError):
                img, _ = mapgen.render_map_images(self.data)
                self._background = img
                try:
                    img.save(asset("maps", f"{self.map_id}.jpg"), quality=86)
                except OSError:
                    pass
        return self._background

    def release_background(self) -> None:
        self._background = None

    # ------------------------------------------------------------ helpers
    @property
    def length_m(self) -> int:
        return int(self.path.length * METERS_PER_PX)


def load_thumbnail(map_id: str) -> Image.Image:
    """Small preview image for the map selection screen."""
    try:
        with Image.open(asset("maps", f"{map_id}_thumb.png")) as im:
            return im.convert("RGB")
    except OSError:
        try:
            with Image.open(asset("maps", f"{map_id}.jpg")) as im:
                return im.convert("RGB").resize((300, 225), Image.LANCZOS)
        except OSError:
            return Image.new("RGB", (300, 225), (40, 44, 60))
