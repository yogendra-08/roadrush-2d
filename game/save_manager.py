"""High scores, lifetime statistics and achievements (JSON on disk)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .paths import DATA

MODES = ("mission", "endless")
MAP_IDS = ("city", "desert", "forest", "highway")
MAX_ENTRIES = 10

ACHIEVEMENTS = {
    "first_win": ("First Victory", "Complete a mission."),
    "coin_100": ("Coin Collector", "Collect 100 coins in total."),
    "speed_demon": ("Speed Demon", "Reach 300 km/h."),
    "untouchable": ("Untouchable", "Win a mission without losing a life."),
    "marathon": ("Marathon", "Score 3000 points in Endless mode."),
    "world_tour": ("World Tour", "Win a mission on every map."),
}


def _default_data() -> dict:
    return {
        "version": 1,
        "scores": {m: {k: [] for k in MAP_IDS} for m in MODES},
        "stats": {"games_played": 0, "total_coins": 0, "total_distance": 0.0,
                  "top_speed_kmh": 0, "victories": 0, "maps_won": []},
        "achievements": {},
    }


class SaveManager:
    """Owns ``scores.json``. Every public method is safe against bad data."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DATA / "scores.json"
        self.data = self._load()

    # ------------------------------------------------------------ persistence
    def _load(self) -> dict:
        base = _default_data()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("root is not an object")
        except FileNotFoundError:
            return base
        except (OSError, ValueError):
            self._backup_corrupt()
            return base
        # Merge defensively so missing / malformed sections fall back to defaults.
        scores = raw.get("scores")
        if isinstance(scores, dict):
            for mode in MODES:
                section = scores.get(mode)
                if not isinstance(section, dict):
                    continue
                for map_id in MAP_IDS:
                    entries = section.get(map_id, [])
                    if isinstance(entries, list):
                        base["scores"][mode][map_id] = [
                            e for e in entries
                            if isinstance(e, dict) and isinstance(e.get("score"), (int, float))]
        stats = raw.get("stats")
        if isinstance(stats, dict):
            for key, default in base["stats"].items():
                val = stats.get(key, default)
                if isinstance(default, list):
                    base["stats"][key] = [v for v in val if v in MAP_IDS] if isinstance(val, list) else default
                elif isinstance(val, (int, float)) and not isinstance(val, bool):
                    base["stats"][key] = val
        ach = raw.get("achievements")
        if isinstance(ach, dict):
            base["achievements"] = {k: v for k, v in ach.items() if k in ACHIEVEMENTS}
        return base

    def _backup_corrupt(self) -> None:
        try:
            os.replace(self.path, self.path.with_suffix(".corrupt.bak"))
        except OSError:
            pass

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    def reset(self) -> None:
        self.data = _default_data()
        self.save()

    # ------------------------------------------------------------------ scores
    def top(self, mode: str, map_id: str, n: int = 5) -> list[dict]:
        entries = self.data["scores"].get(mode, {}).get(map_id, [])
        return sorted(entries, key=lambda e: e["score"], reverse=True)[:n]

    def best(self, mode: str, map_id: str) -> int:
        top = self.top(mode, map_id, 1)
        return int(top[0]["score"]) if top else 0

    def add_score(self, mode: str, map_id: str, entry: dict) -> bool:
        """Store a run. Returns True when it is a new personal best for that map."""
        if mode not in MODES or map_id not in MAP_IDS:
            return False
        previous_best = self.best(mode, map_id)
        entry = dict(entry)
        entry["score"] = int(entry.get("score", 0))
        entry.setdefault("date", time.strftime("%Y-%m-%d"))
        lst = self.data["scores"][mode][map_id]
        lst.append(entry)
        lst.sort(key=lambda e: e["score"], reverse=True)
        del lst[MAX_ENTRIES:]
        self.save()
        return entry["score"] > previous_best

    # ------------------------------------------------------ stats & achievements
    def record_run(self, mode: str, map_id: str, *, coins: int, distance: float,
                   top_speed_kmh: float, victory: bool, lives_lost: int, score: int) -> list[str]:
        """Update lifetime stats; return ids of achievements unlocked by this run."""
        st = self.data["stats"]
        st["games_played"] += 1
        st["total_coins"] += int(coins)
        st["total_distance"] += float(distance)
        st["top_speed_kmh"] = max(st["top_speed_kmh"], int(top_speed_kmh))
        if victory and mode == "mission":
            st["victories"] += 1
            if map_id not in st["maps_won"]:
                st["maps_won"].append(map_id)

        earned: list[str] = []

        def unlock(key: str, cond: bool) -> None:
            if cond and key not in self.data["achievements"]:
                self.data["achievements"][key] = time.strftime("%Y-%m-%d")
                earned.append(key)

        unlock("first_win", victory and mode == "mission")
        unlock("coin_100", st["total_coins"] >= 100)
        unlock("speed_demon", st["top_speed_kmh"] >= 300)
        unlock("untouchable", victory and mode == "mission" and lives_lost == 0)
        unlock("marathon", mode == "endless" and score >= 3000)
        unlock("world_tour", all(m in st["maps_won"] for m in MAP_IDS))
        self.save()
        return earned
