"""User settings (persisted as JSON) and difficulty profiles."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import DATA

DIFFICULTY_ORDER = ("easy", "medium", "hard")
CAR_IDS = ("sports", "racing", "supercar")
MAP_IDS = ("city", "desert", "forest", "highway")


@dataclass(frozen=True)
class DifficultyProfile:
    """Tunable numbers that make a difficulty level easier or harder."""

    key: str
    label: str
    traffic_speed: float      # multiplier for traffic speed
    traffic_density: float    # multiplier for number of traffic cars
    obstacle_density: float   # fraction of obstacles placed / spawn rate
    time_factor: float        # mission timer allowance (bigger = more time)
    checkpoint_bonus: float   # seconds added when a checkpoint is reached
    invuln_time: float        # seconds of invulnerability after damage
    crash_speed_keep: float   # fraction of speed kept after a collision
    offroad_grace: float      # seconds allowed off-road before losing a life
    endless_ramp: float       # how quickly endless mode gets harder


DIFFICULTIES = {
    "easy": DifficultyProfile("easy", "Easy", 0.8, 0.7, 0.55, 1.9, 5.0, 2.2, 0.50, 5.0, 0.6),
    "medium": DifficultyProfile("medium", "Medium", 1.0, 1.0, 0.80, 1.5, 4.0, 1.6, 0.35, 3.5, 1.0),
    "hard": DifficultyProfile("hard", "Hard", 1.3, 1.35, 1.00, 1.2, 3.0, 1.0, 0.20, 2.0, 1.5),
}


def get_difficulty(key: str) -> DifficultyProfile:
    return DIFFICULTIES.get(key, DIFFICULTIES["medium"])


@dataclass
class Settings:
    music_volume: float = 0.5
    sfx_volume: float = 0.7
    difficulty: str = "medium"
    selected_car: str = "sports"
    selected_map: str = "city"

    def sanitize(self) -> "Settings":
        """Clamp / repair values so corrupted files can never crash the game."""
        def clamp(v, default):
            try:
                return max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                return default
        self.music_volume = clamp(self.music_volume, 0.5)
        self.sfx_volume = clamp(self.sfx_volume, 0.7)
        if self.difficulty not in DIFFICULTIES:
            self.difficulty = "medium"
        if self.selected_car not in CAR_IDS:
            self.selected_car = CAR_IDS[0]
        if self.selected_map not in MAP_IDS:
            self.selected_map = MAP_IDS[0]
        return self


class SettingsManager:
    """Loads and saves Settings to ``data/settings.json``."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DATA / "settings.json"
        self.settings = self.load()

    def load(self) -> Settings:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("settings root must be an object")
            known = {k: raw[k] for k in Settings.__dataclass_fields__ if k in raw}
            return Settings(**known).sanitize()
        except (OSError, ValueError, TypeError):
            return Settings()

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(asdict(self.settings), fh, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False
