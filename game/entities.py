"""Plain data classes for everything that lives on the road (no GUI code)."""
from __future__ import annotations

from dataclasses import dataclass

from .collision import OrientedBox
from .procart import OBSTACLE_TYPES, TRAFFIC_TYPES

PICKUP_RADIUS = 17.0
HITBOX_SHRINK = 0.82   # obstacle hitboxes are a little smaller than their sprites (forgiving)


@dataclass
class Obstacle:
    kind: str
    x: float
    y: float
    rot: float = 0.0
    s: float = 0.0           # path distance where it was spawned (endless clean-up)
    alive: bool = True

    @property
    def breakable(self) -> bool:
        return OBSTACLE_TYPES[self.kind][2]

    def box(self) -> OrientedBox:
        w, h, _ = OBSTACLE_TYPES[self.kind]
        return OrientedBox(self.x, self.y, w * HITBOX_SHRINK, h * HITBOX_SHRINK, self.rot)


@dataclass
class Pickup:
    kind: str                # "coin" or "fuel"
    x: float
    y: float
    s: float = 0.0
    alive: bool = True
    value: float = 0.0       # fuel amount for cans


@dataclass
class TrafficCar:
    kind: str
    s: float                 # distance along the loop
    lane_index: int
    lateral: float           # lateral offset from the centre line (right of travel is +)
    direction: int           # +1 same way as the path, -1 oncoming
    speed: float = 0.0
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0

    def sync(self, path) -> None:
        self.x, self.y = path.offset_pos(self.s, self.lateral)
        self.heading = (path.heading_at(self.s) + (0.0 if self.direction > 0 else 180.0)) % 360.0

    def box(self) -> OrientedBox:
        w, h, _ = TRAFFIC_TYPES[self.kind]
        return OrientedBox(self.x, self.y, w * 0.9, h * 0.92, self.heading)


@dataclass
class Checkpoint:
    index: int               # 0-based; -1 for the finish line
    x: float
    y: float
    heading: float
    s: float
    reached: bool = False

    def gate_box(self, road_width: float) -> OrientedBox:
        return OrientedBox(self.x, self.y, road_width + 10, 34, self.heading)
