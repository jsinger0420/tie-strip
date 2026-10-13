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


class TestPrintedSpikes(unittest.TestCase):
    """Printed spikes instead of holes: placement, head height, ties chosen, checks."""

    def spec(self, **kw):
        """HO Code 83 sizes from Model Rail Generator's typical proportions."""
        base = dict(foot_width=1.855, head_width=0.97, fastening=layout.PRINTED,
                    foot_edge=0.169, foot_web=0.358, web_width=0.422)
        base.update(kw)
        return ho_spec(**base)

    def test_no_holes_four_spikes_per_spiked_tie(self):
        """Printed spikes replace the holes; one bare tie each end by default."""
        lay = layout.compute(self.spec(tie_count=10))
        self.assertTrue(lay.ok, lay.errors)
        self.assertEqual(lay.holes, [])
        self.assertEqual(len(lay.spikes), 4 * 8)

    def test_every_nth_and_bare_ends(self):
        """Every Nth tie counts from the first spiked tie."""
        s = self.spec(spike_every=3, spike_bare_ends=2)
        self.assertEqual(layout.spiked_ties(s, 12), [2, 5, 8])
        self.assertEqual(layout.spiked_ties(self.spec(spike_bare_ends=0), 3), [0, 1, 2])

    def test_head_clears_the_foot_where_it_sits(self):
        """The head's underside is above the foot thickness under its inner edge, plus clearance."""
        s = self.spec(spike_overhang=0.2, spike_top_clear=0.1)
        tu = layout.foot_under_head(s)
        run = (1.855 - 0.422) / 2
        self.assertAlmostEqual(tu, 0.169 + (0.358 - 0.169) * 0.2 / run)
        lay = layout.compute(s)
        sp = lay.spikes[0]
        self.assertAlmostEqual(sp.z_head, lay.tie_height + tu + 0.1)
        self.assertAlmostEqual(sp.z_top - sp.z_head, s.spike_head)
        self.assertLess(sp.z0, lay.tie_height)  # shank reaches into the tie

    def test_typed_in_rail_is_flat(self):
        """Without the web values the foot is treated as flat at the edge thickness."""
        s = self.spec(foot_web=0.0, web_width=0.0)
        self.assertEqual(layout.foot_under_head(s), 0.169)

    def test_head_over_foot_shank_beside_it(self):
        """Shank stands clear of the foot; head reaches back over it by the overhang."""
        s = self.spec(spike_side_clear=0.15, spike_shank=0.4, spike_overhang=0.2)
        lay = layout.compute(s)
        yr, hf = lay.rail_y, 1.855 / 2
        for sp in lay.spikes:
            rail = yr if sp.y_head > 0 else -yr
            self.assertAlmostEqual(abs(sp.y_shank_in - rail), hf + 0.15)
            self.assertAlmostEqual(abs(sp.y_shank_out - rail), hf + 0.55)
            self.assertAlmostEqual(abs(sp.y_head - rail), hf - 0.2)

    def test_on_tie_plates_heads_rise_by_the_plate(self):
        """With plates the rail sits on the plate, so the heads move up by its thickness."""
        flat = layout.compute(self.spec())
        plated = layout.compute(self.spec(plates=True))
        tp = plated.plates[0].z1 - flat.tie_height
        self.assertAlmostEqual(plated.spikes[0].z_head - flat.spikes[0].z_head, tp)

    def test_errors(self):
        """Missing foot thickness, no overhang, or a head reaching the web stop the build."""
        self.assertFalse(layout.compute(self.spec(foot_edge=0.0)).ok)
        self.assertFalse(layout.compute(self.spec(spike_overhang=0.0)).ok)
        self.assertFalse(layout.compute(self.spec(spike_overhang=0.8)).ok)

    def test_fdm_warns_below_o(self):
        """Printed spikes are flagged on FDM at HO, not on resin."""
        s = self.spec()
        lay = layout.compute(s)
        self.assertTrue(any("FDM below O" in w for w in layout.printability(s, lay, "FDM")))
        self.assertFalse(any("FDM below O" in w for w in layout.printability(s, lay, "RESIN")))

    def test_chamfer_shortens_the_flat_overhang(self):
        """A chamfer leaves only the part over the foot flat; 0 degrees leaves it all flat."""
        flat = layout.compute(self.spec(spike_chamfer=0.0)).summary["flat_overhang"]
        self.assertAlmostEqual(flat, 0.2 + 0.15)
        chamfered = layout.compute(self.spec(spike_chamfer=45.0)).summary["flat_overhang"]
        self.assertLess(chamfered, 0.21)
        self.assertGreater(chamfered, 0.0)

    def test_chamfer_clears_the_foot_corner(self):
        """The slope passes the foot's top corner by the top and the side clearance."""
        for angle in (30.0, 45.0, 60.0, 80.0):
            s = self.spec(spike_chamfer=angle)
            hf = s.foot_width / 2
            under, _z, _flat = layout.spike_underside(s, hf)
            (u1, z1), (u2, z2) = under[-2], under[-1]  # the sloped segment
            k = (z1 - z2) / (u2 - u1)  # rise per mm toward the rail
            at_edge = z2 + (u2 - hf) * k
            self.assertGreaterEqual(at_edge + 1e-9, s.foot_edge + s.spike_top_clear)
            u_at_foot_top = u2 - (s.foot_edge - z2) / k if s.foot_edge > z2 else u2
            self.assertGreaterEqual(u_at_foot_top - hf + 1e-9, min(s.spike_side_clear, u2 - hf))

    def test_chamfer_angle_limits(self):
        """Chamfers must be 0 or 30 to 80 degrees."""
        self.assertTrue(layout.compute(self.spec(spike_chamfer=0.0)).ok)
        self.assertFalse(layout.compute(self.spec(spike_chamfer=20.0)).ok)
        self.assertFalse(layout.compute(self.spec(spike_chamfer=85.0)).ok)

    def test_chamfered_spike_volume_matches_its_outline(self):
        """The fan fills the chamfered outline exactly: volume = outline area x length."""
        lay = layout.compute(self.spec(tie_count=3, spike_bare_ends=0, spike_chamfer=30.0))
        for sp in lay.spikes[:4]:
            v, t = meshgen.spikes([sp])
            area = abs(sum(y1 * z2 - y2 * z1 for (y1, z1), (y2, z2)
                           in zip(sp.outline(), sp.outline()[1:] + sp.outline()[:1]))) / 2
            self.assertEqual(meshgen.open_edges(t), 0)
            self.assertAlmostEqual(meshgen._signed_volume(v, t), area * (sp.x1 - sp.x0))

    def test_spike_meshes_are_watertight_and_outward(self):
        """Each spike is one closed solid, facing outward on both rails."""
        lay = layout.compute(self.spec(tie_count=3, spike_bare_ends=0))
        v, t = meshgen.spikes(lay.spikes)
        self.assertEqual(meshgen.open_edges(t), 0)
        for sp in lay.spikes:
            self.assertGreater(meshgen._signed_volume(*meshgen.spikes([sp])), 0)


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
