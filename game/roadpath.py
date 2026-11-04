"""Closed-loop road centre-lines (pure geometry, no GUI / imaging dependencies)."""
from __future__ import annotations

import math

Point = tuple[float, float]


def catmull_rom_closed(ctrl: list[Point], per_unit: float = 0.06) -> list[Point]:
    """Smooth closed curve through ``ctrl`` points (uniform Catmull-Rom spline)."""
    n = len(ctrl)
    out: list[Point] = []
    for i in range(n):
        p0, p1, p2, p3 = ctrl[(i - 1) % n], ctrl[i], ctrl[(i + 1) % n], ctrl[(i + 2) % n]
        seg_len = math.dist(p1, p2)
        samples = max(8, int(seg_len * per_unit * 4))
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def resample_closed(points: list[Point], spacing: float) -> list[Point]:
    """Resample a closed polyline so consecutive points are (almost) ``spacing`` apart."""
    n = len(points)
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + math.dist(points[i], points[(i + 1) % n]))
    total = cum[-1]
    count = max(8, round(total / spacing))
    step = total / count
    out: list[Point] = []
    j = 0
    for k in range(count):
        target = k * step
        while cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j] or 1.0
        t = (target - cum[j]) / seg
        a, b = points[j], points[(j + 1) % n]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def smooth_closed(points: list[Point], half_window: int = 10, passes: int = 6) -> list[Point]:
    """Moving-average low-pass filter for a closed polyline (removes tight kinks)."""
    pts = list(points)
    n = len(pts)
    width = 2 * half_window + 1
    for _ in range(passes):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        new = []
        sx = sum(xs[(k) % n] for k in range(-half_window, half_window + 1))
        sy = sum(ys[(k) % n] for k in range(-half_window, half_window + 1))
        for i in range(n):
            new.append((sx / width, sy / width))
            sx += xs[(i + half_window + 1) % n] - xs[(i - half_window) % n]
            sy += ys[(i + half_window + 1) % n] - ys[(i - half_window) % n]
        pts = new
    return pts


class RoadPath:
    """A closed loop of evenly spaced points describing the road centre-line."""

    def __init__(self, points: list[Point]):
        if len(points) < 8:
            raise ValueError("a road path needs at least 8 points")
        self.points = [(float(x), float(y)) for x, y in points]
        self.n = len(self.points)
        self.xs = [p[0] for p in self.points]
        self.ys = [p[1] for p in self.points]
        total = sum(math.dist(self.points[i], self.points[(i + 1) % self.n]) for i in range(self.n))
        self.length = total
        self.step = total / self.n
        self.headings = []
        for i in range(self.n):
            ax, ay = self.points[i]
            bx, by = self.points[(i + 1) % self.n]
            self.headings.append(math.degrees(math.atan2(bx - ax, -(by - ay))) % 360.0)

    # ------------------------------------------------------------------ lookups
    def _locate(self, s: float) -> tuple[int, float]:
        f = (s % self.length) / self.step
        i = int(f) % self.n
        return i, f - int(f)

    def pos_at(self, s: float) -> Point:
        i, t = self._locate(s)
        ax, ay = self.points[i]
        bx, by = self.points[(i + 1) % self.n]
        return ax + (bx - ax) * t, ay + (by - ay) * t

    def heading_at(self, s: float) -> float:
        i, t = self._locate(s)
        a, b = self.headings[i], self.headings[(i + 1) % self.n]
        diff = (b - a + 180.0) % 360.0 - 180.0
        return (a + diff * t) % 360.0

    def right_normal_at(self, s: float) -> Point:
        h = math.radians(self.heading_at(s))
        return math.cos(h), math.sin(h)

    def offset_pos(self, s: float, lateral: float) -> Point:
        """Point at path distance ``s`` shifted ``lateral`` px to the right of travel."""
        x, y = self.pos_at(s)
        nx, ny = self.right_normal_at(s)
        return x + nx * lateral, y + ny * lateral

    def s_of_index(self, i: int) -> float:
        return (i % self.n) * self.step

    def nearest_index(self, x: float, y: float, around: int | None = None, window: int = 90) -> int:
        """Index of the closest path point (optionally only searching near ``around``)."""
        if around is None:
            candidates = range(self.n)
        else:
            candidates = ((around + k) % self.n for k in range(-window, window + 1))
        best_i, best_d = 0, math.inf
        xs, ys = self.xs, self.ys
        for i in candidates:
            d = (xs[i] - x) ** 2 + (ys[i] - y) ** 2
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def signed_delta(self, s_from: float, s_to: float) -> float:
        """Shortest signed distance along the loop from ``s_from`` to ``s_to``."""
        return (s_to - s_from + self.length / 2) % self.length - self.length / 2

    # --------------------------------------------------------------- validation
    def min_turn_radius(self, span: int = 8) -> float:
        """Smallest circumscribed-circle radius along the loop (px)."""
        best = math.inf
        for i in range(self.n):
            a, b, c = self.points[i], self.points[(i + span) % self.n], self.points[(i + 2 * span) % self.n]
            ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
            area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))
            if area2 > 1e-6:
                best = min(best, ab * bc * ca / (2 * area2))
        return best

    def min_separation(self, min_arc: float = 700.0) -> float:
        """Smallest distance between two parts of the road that are far apart along the loop."""
        best = math.inf
        skip = int(min_arc / self.step)
        for i in range(0, self.n, 3):
            for j in range(i + skip, self.n, 3):
                if self.n - (j - i) < skip:
                    continue
                d = math.hypot(self.xs[i] - self.xs[j], self.ys[i] - self.ys[j])
                if d < best:
                    best = d
        return best
