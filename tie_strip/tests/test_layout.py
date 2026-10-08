"""Tests for the pure-Python parts: layout, mesh shapes, plate presets.

Run from the folder that contains the tie_strip package:

    python -m unittest discover -s tie_strip/tests -t .

No Blender needed.
"""

import math
import unittest

import numpy as np

from tie_strip import layout, meshgen, plates, scales
from tie_strip.layout import FLEX, STRAIGHT, Spec

IN = 25.4


def ho_spec(**kw) -> Spec:
    """An HO strip: 8'6" x 9" x 7" ties at 19.5 in, 16.5 mm gauge."""
    base = dict(scale_n=87.1, gauge=16.5, foot_width=1.6, head_width=0.8,
                tie_length=102 * IN, tie_width=9 * IN, tie_height=7 * IN,
                tie_count=10, spacing=19.5 * IN)
    base.update(kw)
    return Spec(**base)


class TestLayout(unittest.TestCase):
    """layout.compute: tie, connector, hole, plate and seat placement, and errors."""

    def test_tie_sizes_and_centring(self):
        """Ties are scaled to model size and centred on the origin at the set spacing."""
        lay = layout.compute(ho_spec())
        self.assertTrue(lay.ok, lay.errors)
        self.assertAlmostEqual(lay.tie_length, 102 * IN / 87.1, places=6)
        self.assertAlmostEqual(lay.tie_height, 7 * IN / 87.1, places=6)
        self.assertAlmostEqual(sum(lay.tie_x), 0.0, places=9)
        self.assertAlmostEqual(lay.tie_x[1] - lay.tie_x[0], 19.5 * IN / 87.1, places=9)

    def test_rail_centre_from_gauge_and_head(self):
        """Rail centrelines sit half the gauge plus half the head width from the centre."""
        lay = layout.compute(ho_spec())
        self.assertAlmostEqual(lay.rail_y, 16.5 / 2 + 0.8 / 2)

    def test_straight_has_two_connectors_per_gap(self):
        """A straight strip joins every pair of ties under both rails."""
        lay = layout.compute(ho_spec(strip_type=STRAIGHT))
        self.assertEqual(len(lay.connectors), 2 * 9)

    def test_flex_alternates_sides(self):
        """A flex strip has one connector per gap, alternating rails from the chosen side."""
        lay = layout.compute(ho_spec(strip_type=FLEX, flex_first="LEFT"))
        self.assertEqual(len(lay.connectors), 9)
        signs = [math.copysign(1, (c.y0 + c.y1) / 2) for c in lay.connectors]
        self.assertEqual(signs, [1, -1, 1, -1, 1, -1, 1, -1, 1])
        lay_r = layout.compute(ho_spec(strip_type=FLEX, flex_first="RIGHT"))
        self.assertEqual((lay_r.connectors[0].y0 + lay_r.connectors[0].y1) / 2, -lay.rail_y)

    def test_connectors_flush_to_bottom_half_height_and_overlap_ties(self):
        """Connectors sit on the bed, reach the set height, overlap the ties, match the foot."""
        s = ho_spec(connector_overlap=0.5)
        lay = layout.compute(s)
        c = lay.connectors[0]
        self.assertEqual(c.z0, 0.0)
        self.assertAlmostEqual(c.z1, lay.tie_height / 2)
        self.assertAlmostEqual(c.x0, lay.tie_x[0] + lay.tie_width / 2 - 0.5)
        self.assertAlmostEqual(c.x1, lay.tie_x[1] - lay.tie_width / 2 + 0.5)
        self.assertAlmostEqual(c.y1 - c.y0, 1.6)  # rail foot width by default

    def test_four_holes_per_tie_touching_the_foot(self):
        """Each tie gets four holes, each touching the rail foot."""
        lay = layout.compute(ho_spec(tie_count=3, hole_diameter=0.5))
        self.assertEqual(len(lay.holes), 12)
        ys = sorted({round(h.y, 6) for h in lay.holes})
        yr = lay.rail_y
        off = 0.8 + 0.25
        self.assertEqual(ys, sorted(round(v, 6) for v in (yr + off, yr - off, -yr + off, -yr - off)))

    def test_holes_go_through_tie_and_plate(self):
        """Hole cutters run past the bottom and past the top of the plates and shoulders."""
        lay = layout.compute(ho_spec(plates=True))
        top = lay.tie_height + 19.05 / 87.1 + 12.7 / 87.1
        for h in lay.holes:
            self.assertLess(h.z0, 0)
            self.assertGreater(h.z1, top)

    def test_stagger_mirrors_between_rails(self):
        """Stagger moves gauge-side holes opposite ways on the two rails."""
        lay = layout.compute(ho_spec(tie_count=2, stagger=2 * IN))
        st = 2 * IN / 87.1 / 2
        x = lay.tie_x[0]
        left = [h for h in lay.holes[:4] if h.y > 0]
        right = [h for h in lay.holes[:4] if h.y < 0]
        left_gauge = min(left, key=lambda h: h.y)
        right_gauge = max(right, key=lambda h: h.y)
        self.assertAlmostEqual(left_gauge.x, x + st)
        self.assertAlmostEqual(right_gauge.x, x - st)

    def test_overlapping_ties_is_an_error(self):
        """Spacing smaller than the tie width is reported as an overlap."""
        lay = layout.compute(ho_spec(spacing=8 * IN))
        self.assertFalse(lay.ok)
        self.assertIn("overlap", lay.errors[0])

    def test_missing_rail_inputs_are_errors(self):
        """Zero foot and head widths give one error each."""
        lay = layout.compute(ho_spec(foot_width=0, head_width=0))
        self.assertEqual(len(lay.errors), 2)

    def test_missing_tie_preset_is_the_error_shown(self):
        """With no tie preset, its error is shown instead of the zero-size error."""
        lay = layout.compute(ho_spec(tie_length=0, tie_width=0, tie_height=0,
                                     tie_error="Choose a Weathered Board preset for the ties."))
        self.assertEqual(lay.errors, ["Choose a Weathered Board preset for the ties."])

    def test_gauge_too_wide_for_ties(self):
        """A gauge too wide for the ties is an error."""
        lay = layout.compute(ho_spec(gauge=30))
        self.assertFalse(lay.ok)

    def test_plates_and_double_shoulders(self):
        """Double shoulders give two per plate, just clear of the rail foot."""
        lay = layout.compute(ho_spec(tie_count=2, plates=True, shoulders="DOUBLE"))
        self.assertTrue(lay.ok, lay.errors)
        self.assertEqual(len(lay.plates), 4)
        self.assertEqual(len(lay.shoulders), 8)
        yr = lay.rail_y
        # Left rail shoulders sit just outside the foot on both sides.
        left = sorted((b for b in lay.shoulders[:4] if b.y0 > 0), key=lambda b: b.y0)
        self.assertAlmostEqual(left[0].y1, yr - 0.8 - 0.05)
        self.assertAlmostEqual(left[1].y0, yr + 0.8 + 0.05)

    def test_field_only_shoulder_is_outboard(self):
        """Field-side-only shoulders are all outside the rails."""
        lay = layout.compute(ho_spec(tie_count=2, plates=True, shoulders="FIELD"))
        self.assertEqual(len(lay.shoulders), 4)
        for b in lay.shoulders:
            mid = (b.y0 + b.y1) / 2
            self.assertGreater(abs(mid), lay.rail_y)

    def test_seat_pads_only_without_plates(self):
        """Seat pads fill the grain without plates; with plates, the plate reaches down instead."""
        lay = layout.compute(ho_spec(seat_depth=0.4, seat_inset=0.5))
        self.assertEqual(len(lay.seats), 20)
        self.assertAlmostEqual(lay.seats[0].z1, lay.tie_height)
        lay2 = layout.compute(ho_spec(seat_depth=0.4, plates=True))
        self.assertEqual(lay2.seats, [])
        # With plates, the plate reaches down past the grain instead.
        self.assertAlmostEqual(lay2.plates[0].z0, lay2.tie_height - 0.42)

    def test_overall_size_includes_variation(self):
        """Length, end and angle variation make the reported overall size bigger."""
        plain = layout.compute(ho_spec())
        varied = layout.compute(ho_spec(length_jitter=2 * IN, end_jitter=1 * IN, yaw_jitter=0.5))
        self.assertAlmostEqual(plain.summary["overall_length"], plain.summary["strip_length"])
        self.assertGreater(varied.summary["overall_length"], plain.summary["overall_length"])
        self.assertAlmostEqual(plain.summary["overall_width"], plain.tie_length)
        self.assertGreater(varied.summary["overall_width"], plain.tie_length)

    def test_ties_for_length_fits_and_is_the_most(self):
        """ties_for_length gives the most ties that fit, and one more doesn't."""
        for max_len in (20.0, 53.8, 120.0, 200.0, 250.0):
            s = ho_spec(length_jitter=2 * IN, end_jitter=1 * IN, yaw_jitter=0.5)
            n = layout.ties_for_length(s, max_len)
            s.tie_count = n
            self.assertLessEqual(layout.compute(s).summary["overall_length"], max_len + 1e-9)
            s.tie_count = n + 1
            self.assertGreater(layout.compute(s).summary["overall_length"], max_len)

    def test_ties_for_length_too_short(self):
        """A max length shorter than two ties gives fewer than 2."""
        self.assertLess(layout.ties_for_length(ho_spec(), 5.0), 2)

    def test_printability_by_printer(self):
        """FDM thresholds warn about more features than resin."""
        s = ho_spec(plates=True)
        lay = layout.compute(s)
        resin = layout.printability(s, lay, "RESIN")
        fdm = layout.printability(s, lay, "FDM")
        self.assertLess(len(resin), len(fdm))
        self.assertTrue(any("Spike holes" in w for w in fdm))

    def test_grain_warning(self):
        """The grain warning appears only past the limit, naming the preset and percentage."""
        self.assertEqual(layout.grain_warning(0.3, 2.04, "Dock Plank", 20), "")
        msg = layout.grain_warning(0.7, 2.04, "Barn Siding", 20)
        self.assertIn("Barn Siding", msg)
        self.assertIn("34 %", msg)


class TestMeshgen(unittest.TestCase):
    """meshgen: shapes are closed and outward-facing, and boards land in place."""

    def test_boxes_are_watertight_and_outward(self):
        """Boxes have no open edges and a positive volume."""
        b = [layout.Box(0, 1, 0, 2, 0, 3), layout.Box(5, 6, 0, 1, 0, 1)]
        v, t = meshgen.boxes(b)
        self.assertEqual(meshgen.open_edges(t), 0)
        # Signed volume of the first box = 6.
        tri = v[t[:12]]
        vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
        self.assertAlmostEqual(vol, 6.0)

    def test_cylinders_are_watertight_and_contain_the_circle(self):
        """Hole cutters are closed and the hole's circle fits inside them."""
        holes = [layout.Hole(0, 0, 0.5, -1, 3), layout.Hole(2, 2, 0.5, -1, 3)]
        v, t = meshgen.cylinders(holes)
        self.assertEqual(meshgen.open_edges(t), 0)
        n = meshgen.hole_segments(0.5)
        ring = v[:n, :2]
        r_mid = np.linalg.norm((ring[0] + ring[1]) / 2)
        self.assertAlmostEqual(r_mid, 0.25, places=9)  # inscribed circle = d/2
        tri = v[t[: len(t) // 2]]
        vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
        self.assertGreater(vol, math.pi * 0.25 ** 2 * 4 * 0.99)

    def test_place_board_turns_length_across_track(self):
        """A board's length turns onto Y, its bottom lands on Z = 0 and it moves to x."""
        v = np.array([[10.0, 0.0, -1.0], [0.0, 2.0, 1.0]])
        out = meshgen.place_board(v, 2.0, x=5.0, y_offset=0.0, turn=False, yaw_deg=0.0)
        np.testing.assert_allclose(out[0], [5.0, 10.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(out[1], [3.0, 0.0, 2.0], atol=1e-12)


class TestPresetsAndScales(unittest.TestCase):
    """Built-in plate presets and the scale table."""

    def test_builtin_plates_have_every_key(self):
        """Every built-in plate preset sets every plate key."""
        for p in plates.BUILTIN_PLATES:
            self.assertEqual(set(p.values), set(plates.PLATE_KEYS), p.name)

    def test_scales(self):
        """Scale ratios, custom ratios, standard gauges and inch conversion."""
        self.assertEqual(scales.scale_n("HO", 0), 87.1)
        self.assertEqual(scales.scale_n("CUSTOM", 100), 100)
        self.assertEqual(scales.standard_gauge("N"), 9.0)
        self.assertAlmostEqual(scales.to_full_mm(1, "IN"), 25.4)


if __name__ == "__main__":
    unittest.main()
