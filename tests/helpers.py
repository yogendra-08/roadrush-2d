"""Shared test helpers: an autopilot that drives the car around the road loop."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.car import Controls  # noqa: E402


class Autopilot:
    """Very small pure-pursuit driver used to prove the maps are completable."""

    def __init__(self, session, lateral: float | None = None, lat_accel: float = 480.0, use_nitro: bool = False):
        self.s = session
        self.lateral = lateral if lateral is not None else min(o for o, _ in session.map.lanes if o > 0)
        self.lat_accel = lat_accel
        self.use_nitro = use_nitro

    def controls(self) -> Controls:
        s, car, path = self.s, self.s.car, self.s.path
        here = path.s_of_index(s._index)
        speed = max(car.speed, 1.0)
        look = 70 + 0.28 * speed
        tx, ty = path.offset_pos(here + look, self.lateral)
        want = math.degrees(math.atan2(tx - car.x, -(ty - car.y)))
        err = (want - car.heading + 180) % 360 - 180
        steer = max(-1.0, min(1.0, err / 18.0))
        # curvature ahead decides the target speed
        dh = abs((path.heading_at(here + 260) - path.heading_at(here + 20) + 180) % 360 - 180)
        radius = 240.0 / max(math.radians(dh), 0.02)
        target = max(130.0, min(car.spec.max_speed, math.sqrt(self.lat_accel * radius)))
        ctl = Controls(steer=steer)
        if car.forward_speed < target:
            ctl.throttle = 1.0
            ctl.nitro = self.use_nitro and car.nitro > 30 and dh < 8
        elif car.forward_speed > target * 1.12:
            ctl.brake = 1.0
        return ctl


def run(session, seconds: float, bot: Autopilot | None = None, dt: float = 1 / 60, stop_on_end: bool = True):
    steps = int(seconds / dt)
    for _ in range(steps):
        ctl = bot.controls() if bot else Controls()
        session.update(dt, ctl)
        if stop_on_end and session.state != "running":
            break
    return session
