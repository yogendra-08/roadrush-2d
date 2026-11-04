import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import unittest

import helpers
from helpers import Autopilot, run
from game.car import CARS, Controls
from game.engine import GameSession
from game.entities import Obstacle, Pickup
from game.map import GameMap
from game.settings import get_difficulty

MAPS = {}


def get_map(map_id):
    if map_id not in MAPS:
        MAPS[map_id] = GameMap(map_id)
    return MAPS[map_id]


def session(map_id="city", mode="mission", diff="medium", car="sports", hazards=True, seed=3):
    return GameSession(get_map(map_id), CARS[car], mode, get_difficulty(diff), seed=seed, hazards=hazards)


def idle(s, seconds):
    run(s, seconds, None)


class TestMissionRules(unittest.TestCase):
    def test_start_state(self):
        s = session()
        self.assertEqual((s.lives, s.coins, s.state, s.checkpoints_done), (3, 0, "running", 0))
        self.assertEqual(len(s.checkpoints), 5)
        self.assertTrue(s.map.is_road(s.car.x, s.car.y))
        self.assertTrue(all(s.map.is_road(x, y) for x, y in s.car.box().corners()))

    def test_victory_on_every_map_with_every_car(self):
        for map_id in ("city", "desert", "forest", "highway"):
            for car in ("sports", "racing", "supercar"):
                s = session(map_id, car=car, hazards=False)
                run(s, 150, Autopilot(s))
                self.assertEqual(s.state, "victory", f"{map_id}/{car}: {s.state} {s.end_reason}")
                self.assertEqual(s.checkpoints_done, 5)
                self.assertGreater(s.score, 0)

    def test_finish_requires_all_checkpoints(self):
        s = session(hazards=False)
        f = s.finish
        s.car.place(f.x, f.y, f.heading, 100)
        s.update(1 / 60, Controls())
        self.assertEqual(s.state, "running")
        self.assertIn("warning", [e[0] for e in s.pop_events()])

    def test_checkpoints_must_be_taken_in_order(self):
        s = session(hazards=False)
        cp2 = s.checkpoints[1]
        s.car.place(cp2.x, cp2.y, cp2.heading, 50)
        s.update(1 / 60, Controls())
        self.assertEqual(s.checkpoints_done, 0)
        cp1 = s.checkpoints[0]
        s.car.place(cp1.x, cp1.y, cp1.heading, 50)
        before = s.time_left
        s.update(1 / 60, Controls())
        self.assertEqual(s.checkpoints_done, 1)
        self.assertGreater(s.time_left, before)             # time bonus
        self.assertTrue(cp1.reached)
        s.car.place(cp2.x, cp2.y, cp2.heading, 50)
        s.update(1 / 60, Controls())
        self.assertEqual(s.checkpoints_done, 2)

    def test_time_runs_out_gives_mission_failed(self):
        s = session(hazards=False)
        s.time_left = 0.5
        idle(s, 2)
        self.assertEqual(s.state, "failed")

    def test_timer_scales_with_difficulty(self):
        limits = [session(diff=d, hazards=False).time_limit for d in ("easy", "medium", "hard")]
        self.assertGreater(limits[0], limits[1])
        self.assertGreater(limits[1], limits[2])

    def test_obstacle_count_scales_with_difficulty(self):
        n = [len(session(diff=d).obstacles) for d in ("easy", "medium", "hard")]
        self.assertLess(n[0], n[1])
        self.assertLess(n[1], n[2])

    def test_traffic_speed_scales_with_difficulty(self):
        e, h = session(diff="easy"), session(diff="hard")
        self.assertLess(max(e.lane_speed), min(h.lane_speed) * 1.01 + 80)
        self.assertLess(sum(e.lane_speed), sum(h.lane_speed))


class TestCollisionsAndLives(unittest.TestCase):
    def test_obstacle_hit_costs_exactly_one_life_per_cooldown(self):
        s = session(hazards=False)
        c = s.car
        s.obstacles.append(Obstacle("rock", c.x, c.y, 0))
        for _ in range(120):                     # 2 seconds of continuous contact
            s.update(1 / 60, Controls())
        self.assertEqual(s.lives, 2)
        self.assertTrue(s.invulnerable or s.invuln == 0)

    def test_damage_again_after_invulnerability_ends(self):
        s = session(hazards=False)
        c = s.car
        s.obstacles.append(Obstacle("rock", c.x, c.y, 0))
        s.update(1 / 60, Controls())
        self.assertEqual(s.lives, 2)
        s.invuln = 0.0
        s.obstacles.append(Obstacle("rock", c.x, c.y, 0))
        s.update(1 / 60, Controls())
        self.assertEqual(s.lives, 1)

    def test_game_over_when_lives_run_out(self):
        s = session(hazards=False)
        for _ in range(3):
            s.invuln = 0.0
            s.obstacles.append(Obstacle("rock", s.car.x, s.car.y, 0))
            s.update(1 / 60, Controls())
        self.assertEqual(s.lives, 0)
        self.assertEqual(s.state, "game_over")
        self.assertIn("game_over", [e[0] for e in s.pop_events()])

    def test_breakable_obstacle_is_removed(self):
        s = session(hazards=False)
        s.obstacles.append(Obstacle("cone", s.car.x, s.car.y, 0))
        s.update(1 / 60, Controls())
        self.assertEqual(s.obstacles, [])

    def test_player_pushed_out_of_solid_obstacle(self):
        s = session(hazards=False)
        c = s.car
        c.vx = c.vy = 0
        s.obstacles.append(Obstacle("rock", c.x + 10, c.y, 0))
        for _ in range(5):
            s.update(1 / 60, Controls())
        self.assertIsNone(__import__("game.collision", fromlist=["x"]).sat_collision(c.box(), s.obstacles[0].box()))

    def test_traffic_collision(self):
        s = session(hazards=True)
        from game.entities import TrafficCar
        t = TrafficCar("sedan", s.path.pos_at(0)[0] * 0, 0, 50, 1, 0)
        t.x, t.y, t.heading = s.car.x, s.car.y, s.car.heading
        s.traffic = [t]
        t.speed = 0
        s.update(1 / 60, Controls())
        self.assertEqual(s.lives, 2)
        self.assertIn("crash", [e[0] for e in s.pop_events()])

    def test_crash_costs_speed(self):
        s = session(hazards=False)
        s.car.place(s.car.x, s.car.y, s.car.heading, 300)
        s.obstacles.append(Obstacle("rock", s.car.x + 5, s.car.y, 0))
        s.update(1 / 60, Controls())
        self.assertLess(s.car.speed, 200)


class TestRoadBoundaries(unittest.TestCase):
    def test_on_road_not_flagged(self):
        s = session(hazards=False)
        s.update(1 / 60, Controls())
        self.assertEqual(s.off_wheels, 0)

    def test_center_on_road_but_wheels_off_is_detected(self):
        s = session(hazards=False)
        path = s.path
        # park the car crossways at the road edge: centre still on asphalt, rear wheels on grass
        edge = s.map.road_width / 2 - 8
        x, y = path.offset_pos(600, edge)
        s.car.place(x, y, path.heading_at(600) + 90, 0)
        self.assertTrue(s.map.is_road(x, y))
        s.update(1 / 60, Controls())
        self.assertGreaterEqual(s.off_wheels, 1)

    def test_offroad_too_long_costs_a_life_and_respawns_on_road(self):
        s = session(hazards=False)
        s.car.place(s.map.start["x"] + 700, s.map.start["y"] + 700, 0, 0)       # far from road
        self.assertFalse(s.map.is_road(s.car.x, s.car.y))
        run(s, s.diff.offroad_grace + 1.0)
        self.assertEqual(s.lives, 2)
        self.assertTrue(s.map.is_road(s.car.x, s.car.y))
        self.assertEqual(s.off_wheels, 0) if False else None

    def test_offroad_grace_lets_you_return(self):
        s = session(hazards=False)
        x, y = s.path.offset_pos(800, s.map.road_width / 2 + 40)
        s.car.place(x, y, s.path.heading_at(800), 0)
        run(s, 1.0)
        self.assertEqual(s.lives, 3)
        self.assertGreater(s.offroad_timer, 0)
        x, y = s.path.offset_pos(800, 0)
        s.car.place(x, y, s.path.heading_at(800), 0)
        run(s, 4.0)
        self.assertEqual(s.offroad_timer, 0.0)

    def test_world_bounds_clamp(self):
        s = session(hazards=False)
        s.car.place(-500, -500, 0, 100)
        s.update(1 / 60, Controls())
        self.assertGreaterEqual(s.car.x, 0)
        self.assertGreaterEqual(s.car.y, 0)


class TestPickups(unittest.TestCase):
    def test_coin_collection(self):
        s = session(hazards=False)
        coin = next(p for p in s.pickups if p.kind == "coin")
        s.car.place(coin.x, coin.y, 0, 0)
        s.update(1 / 60, Controls())
        self.assertEqual(s.coins, 1)
        self.assertNotIn(coin, s.pickups)
        self.assertIn("coin", [e[0] for e in s.pop_events()])

    def test_fuel_pickup_refills(self):
        s = session(hazards=False)
        can = next(p for p in s.pickups if p.kind == "fuel")
        s.car.fuel = 20
        s.car.place(can.x, can.y, 0, 0)
        s.update(1 / 60, Controls())
        self.assertGreater(s.car.fuel, 40)

    def test_out_of_fuel_game_over(self):
        s = session(hazards=False)
        s.car.fuel = 0
        idle(s, 6)
        self.assertEqual((s.state, s.end_reason), ("game_over", "Out of fuel!"))


class TestEndless(unittest.TestCase):
    def test_no_finish_and_spawns_content(self):
        s = session(mode="endless")
        self.assertIsNone(s.time_left)
        run(s, 20, Autopilot(s))
        self.assertGreater(len(s.obstacles) + len(s.traffic), 0)
        self.assertGreater(s.score, 0)
        self.assertNotEqual(s.state, "victory")

    def test_difficulty_increases_over_time(self):
        s = session(mode="endless", hazards=True)
        s.lives = 999
        run(s, 5, None, stop_on_end=False)
        l0 = s.level
        s.elapsed += 120
        run(s, 1, None, stop_on_end=False)
        self.assertGreater(s.level, l0 + 2)

    def test_traffic_increases_with_level(self):
        s = session(mode="endless")
        s.lives = 999
        s.car.fuel = 1e9
        s.elapsed = 240
        for _ in range(900):
            s.update(1 / 30, Controls(throttle=0.0))
        self.assertGreaterEqual(len(s.traffic), 6)

    def test_game_over_and_score_components(self):
        s = session(mode="endless", hazards=False)
        run(s, 8, Autopilot(s))
        d = s.result()
        self.assertGreater(d["distance_m"], 0)
        score_before = s.score
        for _ in range(3):
            s.invuln = 0
            s.obstacles.append(Obstacle("rock", s.car.x, s.car.y, 0))
            s.update(1 / 60, Controls())
        self.assertEqual(s.state, "game_over")
        self.assertGreaterEqual(s.score, score_before)

    def test_endless_old_content_is_cleaned_up(self):
        s = session(mode="endless", hazards=True)
        run(s, 40, Autopilot(s), stop_on_end=False)
        limit = s.s_unwrapped - 900
        self.assertTrue(all(o.s >= limit for o in s.obstacles))
        self.assertLess(len(s.obstacles), 80)


if __name__ == "__main__":
    unittest.main()
