"""Top-down camera that follows the player and never leaves the map."""
from __future__ import annotations

import math


class Camera:
    def __init__(self, view_w: int, view_h: int, world_w: int, world_h: int, smoothing: float = 7.0):
        self.view_w, self.view_h = view_w, view_h
        self.world_w, self.world_h = world_w, world_h
        self.smoothing = smoothing
        self.x = 0.0   # top-left corner of the view in world coordinates
        self.y = 0.0

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        # If the world is smaller than the view on an axis, keep it centred (fixed camera).
        if self.world_w <= self.view_w:
            x = (self.world_w - self.view_w) / 2
        else:
            x = max(0.0, min(self.world_w - self.view_w, x))
        if self.world_h <= self.view_h:
            y = (self.world_h - self.view_h) / 2
        else:
            y = max(0.0, min(self.world_h - self.view_h, y))
        return x, y

    def snap_to(self, tx: float, ty: float) -> None:
        self.x, self.y = self._clamp(tx - self.view_w / 2, ty - self.view_h / 2)

    def follow(self, tx: float, ty: float, dt: float) -> None:
        """Smoothly move towards centring (tx, ty); frame-rate independent."""
        goal_x, goal_y = self._clamp(tx - self.view_w / 2, ty - self.view_h / 2)
        k = 1.0 - math.exp(-self.smoothing * dt)
        self.x += (goal_x - self.x) * k
        self.y += (goal_y - self.y) * k

    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return wx - self.x, wy - self.y

    def is_visible(self, wx: float, wy: float, margin: float = 80.0) -> bool:
        return (self.x - margin <= wx <= self.x + self.view_w + margin and
                self.y - margin <= wy <= self.y + self.view_h + margin)
