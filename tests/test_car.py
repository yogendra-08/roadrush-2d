import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import math
import unittest

import helpers  # noqa: F401
from game.car import CARS, Car, Controls, FUEL_MAX, KMH_PER_PX


def drive(car, ctl, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        car.update(dt, ctl)


class TestCarPhysics(unittest.TestCase):
    def setUp(self):
        self.car = Car(CARS["sports"], 500, 500, 0)

    def test_accelerates_and_caps_at_max_speed(self):
        drive(self.car, Controls(throttle=1), 3)
        self.assertGreater(self.car.speed, 100)
        drive(self.car, Controls(throttle=1), 30)
        self.assertLessEqual(self.car.forward_speed, CARS["sports"].max_speed + 0.5)
        self.assertGreater(self.car.forward_speed, CARS["sports"].max_speed * 0.97)
        self.assertLess(self.car.y, 500)          # heading 0 = driving up the screen

    def test_not_teleporting_motion_is_continuous(self):
        positions = []
        for _ in range(30):
            self.car.update(1 / 60, Controls(throttle=1))
            positions.append(self.car.y)
        steps = [abs(b - a) for a, b in zip(positions, positions[1:])]
        self.assertTrue(all(s < 8 for s in steps))  # never jumps
        self.assertTrue(steps[-1] > steps[0])        # accelerating, not constant

    def test_natural_deceleration(self):
        drive(self.car, Controls(throttle=1), 4)
        v = self.car.speed
        drive(self.car, Controls(), 2)
        self.assertLess(self.car.speed, v)
        drive(self.car, Controls(), 60)
        self.assertLess(self.car.speed, 1.0)

    def test_brake_and_reverse(self):
        drive(self.car, Controls(throttle=1), 4)
        drive(self.car, Controls(brake=1), 1.2)
        self.assertLess(self.car.forward_speed, 5)
        drive(self.car, Controls(brake=1), 6)
        self.assertLess(self.car.forward_speed, 0)
        self.assertGreaterEqual(self.car.forward_speed, -CARS["sports"].max_speed * 0.3 - 1)

    def test_no_steering_when_stationary_and_speed_dependent(self):
        drive(self.car, Controls(steer=1), 1)
        self.assertAlmostEqual(self.car.heading, 0, places=3)
        drive(self.car, Controls(throttle=1, steer=1), 1.5)
        self.assertGreater(self.car.heading, 5)

    def test_left_right_directions(self):
        a, b = Car(CARS["sports"], 0, 0, 0), Car(CARS["sports"], 0, 0, 0)
        for c in (a, b):
            c.vy = -200
        drive(a, Controls(throttle=1, steer=-1), 1)
        drive(b, Controls(throttle=1, steer=1), 1)
        self.assertGreater(a.heading, 180)    # wrapped negative => turned left
        self.assertLess(b.heading, 180)
        self.assertLess(a.x, b.x)

    def test_frame_rate_independence(self):
        results = []
        for dt in (1 / 30, 1 / 60, 1 / 120):
            c = Car(CARS["racing"], 0, 0, 0)
            for _ in range(int(2.0 / dt)):
                c.update(dt, Controls(throttle=1, steer=0.3))
            results.append((c.speed, c.heading))
        speeds = [r[0] for r in results]
        self.assertLess(max(speeds) / min(speeds), 1.04)
        heads = [r[1] for r in results]
        self.assertLess(max(heads) - min(heads), 4.0)

    def test_handbrake_creates_slide(self):
        drive(self.car, Controls(throttle=1), 3)
        drive(self.car, Controls(steer=1, handbrake=True), 0.5)
        self.assertGreater(self.car.sliding, 20)

    def test_nitro_boost_and_drain(self):
        a, b = Car(CARS["sports"]), Car(CARS["sports"])
        drive(a, Controls(throttle=1), 3)
        drive(b, Controls(throttle=1, nitro=True), 3)
        self.assertGreater(b.speed, a.speed * 1.15)
        self.assertLess(b.nitro, 20)
        drive(b, Controls(), 5)
        self.assertGreater(b.nitro, 20)       # recharges when not used

    def test_fuel_consumed_and_engine_dies_when_empty(self):
        drive(self.car, Controls(throttle=1), 5)
        self.assertLess(self.car.fuel, FUEL_MAX)
        self.car.fuel = 0.0
        drive(self.car, Controls(throttle=1), 40)
        self.assertLess(self.car.speed, 1.0)

    def test_offroad_slows_car(self):
        on, off = Car(CARS["sports"]), Car(CARS["sports"])
        off.off_fraction = 1.0
        for _ in range(240):
            on.update(1 / 60, Controls(throttle=1))
            off.update(1 / 60, Controls(throttle=1))
        self.assertLess(off.speed, on.speed * 0.6)

    def test_cars_have_different_handling(self):
        turn = {}
        for cid, spec in CARS.items():
            c = Car(spec)
            c.vy = -200
            drive(c, Controls(throttle=1, steer=1), 1.0)
            turn[cid] = c.heading
        self.assertGreater(turn["racing"], turn["sports"])
        self.assertGreater(turn["sports"], turn["supercar"])
        self.assertGreater(CARS["supercar"].max_speed, CARS["racing"].max_speed)

    def test_speed_kmh(self):
        self.car.vx, self.car.vy = 300, 0
        self.assertAlmostEqual(self.car.speed_kmh, 300 * KMH_PER_PX)


if __name__ == "__main__":
    unittest.main()
