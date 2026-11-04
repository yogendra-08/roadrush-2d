"""Car specifications and arcade driving physics (frame-rate independent)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .collision import OrientedBox, forward_vec, right_vec

KMH_PER_PX = 0.6          # displayed km/h = pixels-per-second * 0.6
HIT_W, HIT_H = 38.0, 80.0  # collision box of every player car (px)
FUEL_MAX = 100.0
NITRO_MAX = 100.0


@dataclass(frozen=True)
class CarSpec:
    car_id: str
    name: str
    description: str
    max_speed: float    # px/s
    accel: float        # px/s^2 (peak)
    brake: float        # px/s^2
    handling: float     # steering rate in deg/s at ideal speed
    grip: float         # lateral grip (higher = less sliding)
    sprite: str


CARS: dict[str, CarSpec] = {
    "sports": CarSpec("sports", "Sports Car", "Balanced and forgiving. A great all-rounder.",
                      360.0, 190.0, 520.0, 125.0, 7.5, "sports.png"),
    "racing": CarSpec("racing", "Racing Car", "Razor-sharp handling and fast acceleration.",
                      400.0, 235.0, 560.0, 150.0, 9.5, "racing.png"),
    "supercar": CarSpec("supercar", "Supercar", "Highest top speed, but a real handful in the corners.",
                        450.0, 215.0, 540.0, 108.0, 6.0, "supercar.png"),
}
CAR_ORDER = ("sports", "racing", "supercar")


def car_stats(spec: CarSpec) -> dict[str, float]:
    """Normalised 0..1 values used by the garage stat bars."""
    return {
        "Speed": spec.max_speed / 460.0,
        "Acceleration": spec.accel / 260.0,
        "Handling": spec.handling / 160.0,
    }


@dataclass
class Controls:
    throttle: float = 0.0     # 0..1
    brake: float = 0.0        # 0..1
    steer: float = 0.0        # -1 (left) .. +1 (right)
    handbrake: bool = False
    nitro: bool = False


def _approach(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    return max(target, value - step)


class Car:
    """Mutable car state plus the physics step."""

    ROLLING_RESISTANCE = 28.0     # px/s^2 constant slow-down
    DRAG = 0.55                   # 1/s proportional slow-down
    NITRO_TOP = 1.35              # top-speed multiplier while boosting
    NITRO_ACCEL = 1.9
    NITRO_DRAIN = 32.0            # units/s
    NITRO_RECHARGE = 6.0          # units/s

    def __init__(self, spec: CarSpec, x: float = 0.0, y: float = 0.0, heading: float = 0.0):
        self.spec = spec
        self.x, self.y, self.heading = x, y, heading
        self.vx = self.vy = 0.0
        self.steer = 0.0
        self.fuel = FUEL_MAX
        self.nitro = NITRO_MAX
        self.nitro_active = False
        self.sliding = 0.0        # lateral speed, used for smoke effects
        self.off_fraction = 0.0   # 0..1 share of the car that is off the road

    # ----------------------------------------------------------------- queries
    @property
    def forward_speed(self) -> float:
        fx, fy = forward_vec(self.heading)
        return self.vx * fx + self.vy * fy

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    @property
    def speed_kmh(self) -> float:
        return self.speed * KMH_PER_PX

    def box(self, scale: float = 1.0) -> OrientedBox:
        return OrientedBox(self.x, self.y, HIT_W * scale, HIT_H * scale, self.heading)

    def place(self, x: float, y: float, heading: float, speed: float = 0.0) -> None:
        self.x, self.y, self.heading = x, y, heading % 360
        fx, fy = forward_vec(self.heading)
        self.vx, self.vy = fx * speed, fy * speed
        self.steer = 0.0

    # ------------------------------------------------------------------ physics
    def update(self, dt: float, ctl: Controls) -> None:
        if dt <= 0:
            return
        spec = self.spec
        fx, fy = forward_vec(self.heading)
        rx, ry = right_vec(self.heading)
        vf = self.vx * fx + self.vy * fy        # forward component
        vl = self.vx * rx + self.vy * ry        # lateral (sliding) component

        has_fuel = self.fuel > 0.0
        throttle = ctl.throttle if has_fuel else 0.0
        boosting = bool(ctl.nitro and self.nitro > 0.0 and has_fuel and vf > -5.0)
        self.nitro_active = boosting

        # Off-road surfaces cap speed and slow the car down.
        off = self.off_fraction
        top = spec.max_speed * (self.NITRO_TOP if boosting else 1.0) * (1.0 - 0.6 * off)

        if throttle > 0.0 or boosting:
            power = max(throttle, 1.0 if boosting else 0.0)
            accel = spec.accel * power * (self.NITRO_ACCEL if boosting else 1.0)
            if vf < top:
                vf += accel * (1.0 - 0.7 * max(0.0, vf) / top) * dt
                vf = min(vf, top)
        if vf > top:                              # over the cap (nitro ended / grass)
            vf -= (vf - top) * min(1.0, 2.5 * dt)

        if ctl.brake > 0.0:
            if vf > 4.0:
                vf = max(0.0, vf - spec.brake * ctl.brake * dt)
            else:                                 # reverse
                vf = max(-spec.max_speed * 0.3, vf - spec.accel * 0.55 * ctl.brake * dt)
        if ctl.handbrake and abs(vf) > 0.0:
            drop = spec.brake * 0.7 * dt
            vf = max(0.0, vf - drop) if vf > 0 else min(0.0, vf + drop)

        # Natural slow-down: rolling resistance + drag (+ extra on grass).
        if throttle <= 0.0 and not boosting and ctl.brake <= 0.0:
            drop = (self.ROLLING_RESISTANCE + self.DRAG * abs(vf)) * dt
            vf = _approach(vf, 0.0, drop)
        vf = _approach(vf, 0.0, off * (90.0 + 1.6 * abs(vf)) * dt)

        # Lateral grip: the handbrake lets the rear slide (drift).
        grip = spec.grip * (0.2 if ctl.handbrake else 1.0) * (1.0 - 0.4 * off)
        vl *= math.exp(-grip * dt)
        self.sliding = abs(vl)

        # Steering: ramps smoothly, and depends on speed.
        self.steer = _approach(self.steer, ctl.steer, (6.0 if ctl.steer else 9.0) * dt)
        speed_factor = min(1.0, abs(vf) / (0.22 * spec.max_speed))
        high_speed_penalty = 1.0 - 0.45 * min(1.0, abs(vf) / spec.max_speed)
        turn_rate = spec.handling * self.steer * speed_factor * high_speed_penalty
        if ctl.handbrake:
            turn_rate *= 1.35
        direction = 1.0 if vf >= -0.5 else -1.0
        self.heading = (self.heading + turn_rate * direction * dt) % 360.0

        # Recompose velocity with the OLD basis; the next step re-projects onto the
        # new heading, which produces natural understeer / drifting.
        self.vx = fx * vf + rx * vl
        self.vy = fy * vf + ry * vl
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Resources.
        if has_fuel and (throttle > 0.0 or boosting) and vf > 1.0:
            burn = 0.35 + 1.15 * max(throttle, 0.3)
            self.fuel = max(0.0, self.fuel - burn * (2.0 if boosting else 1.0) * dt)
        elif has_fuel:
            self.fuel = max(0.0, self.fuel - 0.12 * dt)   # idling
        if boosting:
            self.nitro = max(0.0, self.nitro - self.NITRO_DRAIN * dt)
        else:
            self.nitro = min(NITRO_MAX, self.nitro + self.NITRO_RECHARGE * dt)
