"""Pure-geometry collision helpers (no GUI, fully unit-testable).

Conventions
-----------
* Screen coordinates: +x right, +y down.
* Heading is in degrees, 0 = facing up (north), increasing clockwise.
  The forward vector is ``(sin h, -cos h)`` and the right vector ``(cos h, sin h)``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


def forward_vec(heading_deg: float) -> Point:
    h = math.radians(heading_deg)
    return math.sin(h), -math.cos(h)


def right_vec(heading_deg: float) -> Point:
    h = math.radians(heading_deg)
    return math.cos(h), math.sin(h)


@dataclass
class OrientedBox:
    """A rectangle ``w`` (across, local x) by ``h`` (along heading, local y)."""

    cx: float
    cy: float
    w: float
    h: float
    heading: float = 0.0

    def corners(self) -> list[Point]:
        fx, fy = forward_vec(self.heading)
        rx, ry = right_vec(self.heading)
        hw, hh = self.w / 2, self.h / 2
        return [
            (self.cx - rx * hw + fx * hh, self.cy - ry * hw + fy * hh),  # front-left
            (self.cx + rx * hw + fx * hh, self.cy + ry * hw + fy * hh),  # front-right
            (self.cx + rx * hw - fx * hh, self.cy + ry * hw - fy * hh),  # rear-right
            (self.cx - rx * hw - fx * hh, self.cy - ry * hw - fy * hh),  # rear-left
        ]

    def probe_points(self) -> list[Point]:
        """Corners plus edge midpoints: used for reliable road-boundary tests."""
        c = self.corners()
        mids = [((c[i][0] + c[(i + 1) % 4][0]) / 2, (c[i][1] + c[(i + 1) % 4][1]) / 2) for i in range(4)]
        return c + mids

    def bounding_radius(self) -> float:
        return math.hypot(self.w, self.h) / 2


def _axes(corners: list[Point]) -> list[Point]:
    axes = []
    for i in range(2):  # a rectangle only needs two unique edge normals
        x1, y1 = corners[i]
        x2, y2 = corners[i + 1]
        ex, ey = x2 - x1, y2 - y1
        length = math.hypot(ex, ey) or 1.0
        axes.append((-ey / length, ex / length))
    return axes


def _project(corners: list[Point], axis: Point) -> tuple[float, float]:
    dots = [x * axis[0] + y * axis[1] for x, y in corners]
    return min(dots), max(dots)


def sat_collision(a: OrientedBox, b: OrientedBox) -> tuple[float, float] | None:
    """Separating-axis test for two oriented boxes.

    Returns ``None`` when they do not overlap, otherwise the minimum translation
    vector ``(dx, dy)`` that moves **a** out of **b**.
    """
    # Quick reject using bounding circles.
    if math.hypot(a.cx - b.cx, a.cy - b.cy) > a.bounding_radius() + b.bounding_radius():
        return None
    ca, cb = a.corners(), b.corners()
    best_overlap = math.inf
    best_axis = (0.0, 0.0)
    for axis in _axes(ca) + _axes(cb):
        min_a, max_a = _project(ca, axis)
        min_b, max_b = _project(cb, axis)
        overlap = min(max_a, max_b) - max(min_a, min_b)
        if overlap <= 0:
            return None
        if overlap < best_overlap:
            best_overlap = overlap
            best_axis = axis
    # Make the axis point from b towards a.
    if (a.cx - b.cx) * best_axis[0] + (a.cy - b.cy) * best_axis[1] < 0:
        best_axis = (-best_axis[0], -best_axis[1])
    return best_axis[0] * best_overlap, best_axis[1] * best_overlap


def boxes_intersect(a: OrientedBox, b: OrientedBox) -> bool:
    return sat_collision(a, b) is not None


def circle_box_collision(cx: float, cy: float, radius: float, box: OrientedBox) -> bool:
    """True when a circle overlaps an oriented box (used for coins / pickups)."""
    fx, fy = forward_vec(box.heading)
    rx, ry = right_vec(box.heading)
    dx, dy = cx - box.cx, cy - box.cy
    local_x = dx * rx + dy * ry      # across
    local_y = dx * fx + dy * fy      # along
    nearest_x = max(-box.w / 2, min(box.w / 2, local_x))
    nearest_y = max(-box.h / 2, min(box.h / 2, local_y))
    return math.hypot(local_x - nearest_x, local_y - nearest_y) <= radius


def count_points_off_road(points: list[Point], is_road) -> int:
    """How many of ``points`` are outside the road (``is_road(x, y) -> bool``)."""
    return sum(0 if is_road(x, y) else 1 for x, y in points)
