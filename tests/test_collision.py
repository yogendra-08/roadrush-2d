import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import math
import unittest

import helpers  # noqa: F401  (adds project root to sys.path)
from game.collision import (OrientedBox, boxes_intersect, circle_box_collision, count_points_off_road,
                            forward_vec, right_vec, sat_collision)


class TestGeometry(unittest.TestCase):
    def test_vectors(self):
        fx, fy = forward_vec(0)
        self.assertAlmostEqual(fx, 0), self.assertAlmostEqual(fy, -1)
        rx, ry = right_vec(90)
        self.assertAlmostEqual(rx, 0), self.assertAlmostEqual(ry, 1)

    def test_corners_axis_aligned(self):
        xs = sorted(c[0] for c in OrientedBox(100, 100, 40, 80, 0).corners())
        ys = sorted(c[1] for c in OrientedBox(100, 100, 40, 80, 0).corners())
        self.assertEqual((round(xs[0]), round(xs[-1])), (80, 120))
        self.assertEqual((round(ys[0]), round(ys[-1])), (60, 140))

    def test_rotation_swaps_extents(self):
        pts = OrientedBox(0, 0, 40, 80, 90).corners()
        self.assertAlmostEqual(max(p[0] for p in pts), 40)
        self.assertAlmostEqual(max(p[1] for p in pts), 20)


class TestSAT(unittest.TestCase):
    def test_overlap_and_separation(self):
        a = OrientedBox(0, 0, 40, 80)
        self.assertTrue(boxes_intersect(a, OrientedBox(30, 0, 40, 80)))
        self.assertFalse(boxes_intersect(a, OrientedBox(41, 0, 40, 80)))
        self.assertFalse(boxes_intersect(a, OrientedBox(500, 500, 40, 80)))

    def test_rotated_boxes(self):
        a = OrientedBox(0, 0, 40, 80, 0)
        # a diagonal box whose bounding circle touches but shapes do not overlap
        self.assertFalse(boxes_intersect(a, OrientedBox(58, 58, 40, 80, 45)))
        self.assertTrue(boxes_intersect(a, OrientedBox(30, 20, 40, 80, 45)))

    def test_mtv_pushes_a_out(self):
        a, b = OrientedBox(30, 0, 40, 80), OrientedBox(0, 0, 40, 80)
        mtv = sat_collision(a, b)
        self.assertIsNotNone(mtv)
        self.assertGreater(mtv[0], 0)           # a is to the right: pushed right
        self.assertAlmostEqual(mtv[1], 0, places=6)
        moved = OrientedBox(a.cx + mtv[0] + 0.01, a.cy + mtv[1], 40, 80)
        self.assertFalse(boxes_intersect(moved, b))

    def test_circle_box(self):
        box = OrientedBox(0, 0, 40, 80, 0)
        self.assertTrue(circle_box_collision(0, 0, 5, box))
        self.assertTrue(circle_box_collision(30, 0, 12, box))
        self.assertFalse(circle_box_collision(60, 0, 12, box))
        rot = OrientedBox(0, 0, 40, 80, 90)       # long axis now horizontal
        self.assertTrue(circle_box_collision(44, 0, 5, rot))
        self.assertFalse(circle_box_collision(0, 50, 5, rot))

    def test_probe_points_and_off_road(self):
        box = OrientedBox(0, 0, 40, 80, 0)
        self.assertEqual(len(box.probe_points()), 8)
        road = lambda x, y: x < 0          # only the left half is road
        off = count_points_off_road(box.corners(), road)
        self.assertEqual(off, 2)           # the two right-hand wheels


if __name__ == "__main__":
    unittest.main()
