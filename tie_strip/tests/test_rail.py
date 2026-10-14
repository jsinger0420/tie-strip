"""Tests for rail.py: the rail laid on the strip. Run with ``python -m unittest`` (no Blender)."""

import math
import unittest

import numpy as np

from tie_strip import layout, meshgen, rail
from tie_strip.tests.test_layout import ho_spec

# Model Rail Generator's built-in Code 83 preset (typical proportions of 2.108 mm).
CODE83 = dict(foot=0.88 * 2.1082, head=0.46 * 2.1082, height=2.1082, foot_edge=0.08 * 2.1082,
              foot_web=0.17 * 2.1082, web=0.20 * 2.1082, head_depth=0.30 * 2.1082,
              corner=0.06 * 2.1082)


def code83():
    """The Code 83 rail shape."""
    shape, err = rail.shape_from_sizes(**CODE83)
    assert shape is not None, err
    return shape


class TestRailShape(unittest.TestCase):
    """Cross-section from the settings' rail sizes."""

    def test_needs_height(self):
        """Without a rail height the rail can't be drawn, and the message says so."""
        shape, err = rail.shape_from_sizes(1.85, 0.97, 0.0, 0.17)
        self.assertIsNone(shape)
        self.assertIn("rail height", err)

    def test_typed_in_defaults(self):
        """A typed-in rail gets typical head and web sizes and a flat foot."""
        shape, err = rail.shape_from_sizes(1.85, 0.97, 2.108, 0.17)
        self.assertEqual(err, "")
        self.assertAlmostEqual(shape.head_depth, 0.30 * 2.108)
        self.assertEqual(shape.foot_web, shape.foot_edge)
        self.assertLess(shape.web, shape.head)

    def test_too_short(self):
        """A height smaller than head plus foot is refused."""
        shape, err = rail.shape_from_sizes(1.85, 0.97, 0.5, 0.17, head_depth=0.4)
        self.assertIsNone(shape)

    def test_outline_matches_model_rail_generator(self):
        """Code 83: same corners, size and area as Model Rail Generator draws."""
        pts = rail.outline(code83())
        self.assertGreater(rail._area(pts), 0)  # counter-clockwise
        xs, zs = zip(*pts)
        self.assertAlmostEqual(max(xs) - min(xs), CODE83["foot"])
        self.assertAlmostEqual(max(zs), CODE83["height"])
        self.assertEqual(len(pts), 2 * (5 + rail.CORNER_SEGMENTS + 1))


class TestRailMesh(unittest.TestCase):
    """Rail meshes are closed and the right size."""

    def test_watertight_volume(self):
        """Closed, outward-facing, volume = cross-section x length, sliced or not."""
        shape = code83()
        area = rail._area(rail.outline(shape))
        for step in (None, 3.0):
            v, t = rail.mesh(shape, -10.0, 15.0, 9.0, 2.0, step)
            self.assertEqual(meshgen.open_edges(t), 0)
            self.assertAlmostEqual(meshgen._signed_volume(v, t), area * 25.0, places=6)
            self.assertAlmostEqual(v[:, 2].min(), 2.0)
            self.assertAlmostEqual(v[:, 1].mean(), 9.0, places=1)


class TestRailPlacement(unittest.TestCase):
    """Rail ends and seats on straight and curved strips."""

    def test_straight_flush_and_overhang(self):
        """Flush with the end tie faces at 0; overhang adds to each end."""
        lay = layout.compute(ho_spec())
        x0, x1 = rail.ends(lay.tie_x, lay.tie_width, lay.rail_y, 0.0)
        self.assertAlmostEqual(x0, lay.tie_x[0] - lay.tie_width / 2)
        self.assertAlmostEqual(x1 - x0, lay.summary["strip_length"])
        x0, x1 = rail.ends(lay.tie_x, lay.tie_width, lay.rail_y, 2.0)
        self.assertAlmostEqual(x1 - x0, lay.summary["strip_length"] + 4.0)

    def test_place_two_rails_on_seat(self):
        """Left rail at +rail_y, right at -rail_y, both on the seat height."""
        lay = layout.compute(ho_spec())
        out = rail.place(code83(), lay.tie_x, lay.tie_width, lay.rail_y, lay.tie_height)
        self.assertEqual([o[0] for o in out], ["L", "R"])
        for side, v, t, length in out:
            self.assertAlmostEqual(v[:, 2].min(), lay.tie_height)
            self.assertAlmostEqual(np.sign(v[:, 1].mean()), 1 if side == "L" else -1)
            self.assertAlmostEqual(length, lay.summary["strip_length"])

    def test_half_tie_gap_joins_strips(self):
        """Half Tie Gap: rail is N spacings long, so strips laid end to end meet exactly."""
        lay = layout.compute(ho_spec())
        p, n = lay.summary["spacing"], len(lay.tie_x)
        x0, x1 = rail.ends(lay.tie_x, lay.tie_width, lay.rail_y, None, spacing=p)
        self.assertAlmostEqual(x1 - x0, n * p)
        self.assertAlmostEqual(rail.half_gap(p, lay.tie_width, lay.rail_y), lay.summary["gap"] / 2)
        # the auto value matches entering the same overhang by hand
        o = rail.half_gap(p, lay.tie_width, lay.rail_y)
        self.assertAlmostEqual(rail.ends(lay.tie_x, lay.tie_width, lay.rail_y, o)[1], x1)

    def test_half_tie_gap_on_curve(self):
        """On a curve each rail covers N spacings of angle, and the hand-entered equivalent agrees."""
        radius = 22 * 25.4
        lay = layout.compute(ho_spec(strip_type=layout.CURVED, curve_radius=radius))
        p, n = lay.summary["spacing"], len(lay.tie_x)
        for y in (lay.rail_y, -lay.rail_y):
            x0, x1 = rail.ends(lay.tie_x, lay.tie_width, y, None, radius, p)
            self.assertAlmostEqual(rail.length(x0, x1, y, radius), n * p * (radius - y) / radius)
            o = rail.half_gap(p, lay.tie_width, y, radius)
            self.assertGreater(o, 0)
            self.assertAlmostEqual(rail.ends(lay.tie_x, lay.tie_width, y, o, radius)[1], x1)

    def test_negative_overhang_limit(self):
        """An overhang that leaves no rail is refused."""
        lay = layout.compute(ho_spec())
        with self.assertRaises(ValueError):
            rail.place(code83(), lay.tie_x, lay.tie_width, lay.rail_y, lay.tie_height,
                       overhang=-1000.0)

    def test_curved_rail_follows_radius_and_meets_tie_faces(self):
        """On a curve each rail stays at its radius and ends on the end ties' outer faces."""
        radius = 22 * 25.4
        lay = layout.compute(ho_spec(strip_type=layout.CURVED, curve_radius=radius))
        shape = code83()
        out = rail.place(shape, lay.tie_x, lay.tie_width, lay.rail_y, lay.tie_height,
                         radius=radius)
        for (side, v, t, length), y in zip(out, (lay.rail_y, -lay.rail_y)):
            self.assertEqual(meshgen.open_edges(t), 0)
            rho = np.hypot(v[:, 0], v[:, 1] - radius)
            r = radius - y
            self.assertAlmostEqual(rho.min(), r - shape.foot / 2, delta=0.003)
            self.assertAlmostEqual(rho.max(), r + shape.foot / 2, delta=0.003)
            # The rail's end, on its centreline, is half a tie width from the
            # last tie's centre line (a line through the curve's centre).
            x0, x1 = rail.ends(lay.tie_x, lay.tie_width, y, 0.0, radius)
            ex, ey = layout.curve_point(radius, x1, y)
            phi = lay.tie_x[-1] / radius
            # distance from the tie's radial centre line, direction (sin, -cos) from (0, R)
            d = abs(ex * math.cos(phi) + (ey - radius) * math.sin(phi))
            self.assertAlmostEqual(d, lay.tie_width / 2, places=6)
            self.assertAlmostEqual(length, (x1 - x0) / radius * r)


if __name__ == "__main__":
    unittest.main()
