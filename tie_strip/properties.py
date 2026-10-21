"""All Tie Strip settings, kept on the scene so they save with the .blend file.

Prototype sizes (ties, spacing, jitter, stagger, tie plates) are in the
units chosen by ``proto_units``, inches by default. Rail sizes, holes and
clearances are model millimetres. Lengths are plain numbers rather than
Blender length units, so they read the same whatever the scene units are.
The curve radius is a model size, in model inches or millimetres as chosen
by ``radius_units``.
"""

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       StringProperty)

from . import scales
from .layout import Spec
from .plates import PLATE_KEYS

PROTO_LENGTH_KEYS = (
    "tie_spacing",
    "length_jitter", "end_jitter", "stagger",
    "plate_length", "plate_width", "plate_thickness", "plate_bias",
    "shoulder_height", "shoulder_width",
)

# Set while a preset or unit change writes many values, so updates don't fire.
_quiet = False


class quiet:
    """Context manager: suppress update callbacks while writing settings."""

    def __enter__(self):
        """Turn updates off, remembering the previous state so blocks can nest."""
        global _quiet
        self._prev, _quiet = _quiet, True

    def __exit__(self, *exc):
        """Put updates back as they were."""
        global _quiet
        _quiet = self._prev


def _scale_update(self, context):
    """Set the gauge to the new scale's standard gauge (custom scales keep theirs)."""
    if _quiet:
        return
    gauge = scales.standard_gauge(self.scale)
    if gauge is not None:
        self.gauge = gauge


def _units_update(self, context):
    """Convert every prototype length when the units change."""
    if _quiet or self.proto_units == self.proto_units_prev:
        return
    with quiet():
        for key in PROTO_LENGTH_KEYS:
            mm = scales.to_full_mm(getattr(self, key), self.proto_units_prev)
            setattr(self, key, scales.from_full_mm(mm, self.proto_units))
        self.proto_units_prev = self.proto_units


def _radius_units_update(self, context):
    """Convert the curve radius when its units change between model inches and mm."""
    if _quiet or self.radius_units == self.radius_units_prev:
        return
    with quiet():
        mm = self.curve_radius * (25.4 if self.radius_units_prev == "IN" else 1.0)
        self.curve_radius = mm / 25.4 if self.radius_units == "IN" else mm
        self.radius_units_prev = self.radius_units
    _strip_update(self, context)


def _get_use_arc_angle(self):
    """True when the strip's length is set by its arc angle (Size By = Arc Angle)."""
    return self.size_mode == "ANGLE"


def _set_use_arc_angle(self, value):
    """Switch Size By to Arc Angle, or back to Number of Ties."""
    if value:
        self.size_mode = "ANGLE"
    elif self.size_mode == "ANGLE":
        self.size_mode = "COUNT"


def _plate_update(self, context):
    """Mark the chosen plate preset as modified when a plate setting is edited."""
    if not _quiet and self.plate_preset:
        self.plate_modified = True


def _strip_update(self, context):
    """Mark the chosen strip preset as modified when any setting is edited."""
    if not _quiet and self.strip_preset:
        self.strip_modified = True


def _rail_update(self, context):
    """Mark the chosen rail preset as modified when a rail size is edited by hand."""
    if not _quiet:
        if self.rail_preset:
            self.rail_modified = True
        _strip_update(self, context)


def _proto(name, default, desc, update=None, soft_max=1000.0):
    """A prototype length property, in the units chosen by ``proto_units``."""
    return FloatProperty(name=name, description=desc + " (prototype size, in the chosen units)",
                         default=default, min=0.0, soft_max=soft_max, precision=3,
                         update=update or _strip_update)


def _model(name, default, desc, update=None):
    """A model-millimetre length property."""
    return FloatProperty(name=name, description=desc + " (model millimetres)",
                         default=default, min=0.0, soft_max=50.0, precision=3, step=1,
                         update=update or _strip_update)


class TIESTRIP_Settings(bpy.types.PropertyGroup):
    """Every Tie Strip setting, stored on the scene as ``scene.tie_strip``."""

    # ---- scale and track (model mm) ----
    scale: EnumProperty(
        name="Scale", default="HO", update=_scale_update,
        description="Model railroad scale; sets the size ratio and pre-fills the standard gauge",
        items=[(k, v[0], f"1:{v[1]:g}, standard gauge {v[2]:g} mm") for k, v in scales.SCALES.items()]
        + [(scales.CUSTOM, "Custom", "Enter your own ratio")])
    scale_custom: FloatProperty(name="Ratio 1:", default=87.1, min=1.0, soft_max=500.0,
                                description="N in 1:N for a custom scale", update=_strip_update)
    gauge: _model("Gauge", 16.5, "Distance between the inner faces of the railheads")
    rail_foot: _model("Rail Foot Width", 0.0, "Width of the rail's base, measured on your rail",
                      _rail_update)
    rail_head: _model("Rail Head Width", 0.0, "Width of the railhead, measured on your rail",
                      _rail_update)
    rail_edge: _model("Foot Edge Thickness", 0.0,
                      "Thickness of the rail foot at its outer edge; needed for printed spikes",
                      _rail_update)
    rail_height: _model("Rail Height", 0.0,
                        "Overall height of the rail, foot bottom to railhead top (Code 83 is "
                        "2.108 mm). Filled by the rail profile; needed only for Include Rail",
                        _rail_update)
    # From a rail preset only (0 = unknown): used for the printed spike head height and reach,
    # and for drawing the rail (head depth and corner radius only for drawing).
    rail_foot_web: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    rail_web: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    rail_head_depth: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    rail_corner: FloatProperty(default=0.0, min=0.0, options={"HIDDEN"})
    rail_preset: StringProperty(default="", options={"HIDDEN"})
    rail_modified: BoolProperty(default=False, options={"HIDDEN"})

    # ---- ties (prototype) ----
    proto_units: EnumProperty(
        name="Prototype Units", default="IN", update=_units_update,
        description="Units for the full-size (prototype) measurements: spacing, variation, "
                    "stagger and tie plates. Changing it converts the values",
        items=[("IN", "Inches", "Prototype sizes in inches"),
               ("MM", "Millimetres", "Prototype sizes in millimetres")])
    proto_units_prev: StringProperty(default="IN", options={"HIDDEN"})
    size_mode: EnumProperty(
        name="Size By", default="COUNT", update=_strip_update,
        description="Set the strip by its number of ties, by the longest strip that fits "
                    "your printer, or (curved strips) by the angle of curve it covers",
        items=[("COUNT", "Number of Ties", "Enter how many ties the strip has"),
               ("LENGTH", "Max Length", "Enter the longest strip your printer takes; "
                                        "the number of ties is worked out to fit"),
               ("ANGLE", "Arc Angle", "Curved strips only: enter the angle of curve the strip "
                                      "covers, such as 30 degrees; the number of ties is worked "
                                      "out and the spacing adjusted slightly to fill it exactly")])
    tie_count: IntProperty(name="Number of Ties", default=20, min=2, soft_max=200,
                           update=_strip_update, description="How many ties the strip has")
    max_length: FloatProperty(
        name="Max Length", default=200.0, min=1.0, soft_max=1000.0, precision=1,
        description="Longest printed strip, in model millimetres, for example your printer's "
                    "build plate length. A curved strip is measured straight across, end to end",
        update=_strip_update)
    arc_angle: FloatProperty(
        name="Arc Angle", default=30.0, min=1.0, max=180.0, precision=1, step=100,
        update=_strip_update,
        description="Angle of curve the strip covers, in degrees. Strips laid end to end add "
                    "up: twelve 30 degree strips make a full circle. The tie spacing is "
                    "adjusted slightly so a whole number of ties fills the angle")
    use_arc_angle: BoolProperty(
        name="Set Length by Arc Angle", get=_get_use_arc_angle, set=_set_use_arc_angle,
        description="Make the curved strip cover a set angle of curve, such as 30 degrees, "
                    "instead of a number of ties. The ties are counted for you and the spacing "
                    "is adjusted slightly so they fill the angle exactly")
    tie_spacing: _proto("Tie Spacing", 19.5, "Centre-to-centre distance between ties")

    # ---- strip ----
    strip_type: EnumProperty(
        name="Strip Type", default="STRAIGHT", update=_strip_update,
        description="Straight strips are joined under both rails; flexible strips under one "
                    "rail per gap, so they bend into curves; curved strips print already "
                    "curved to a set radius",
        items=[("STRAIGHT", "Straight", "Two connectors between each pair of ties"),
               ("FLEX", "Flexible", "One connector between each pair of ties, alternating "
                                    "sides, so the printed strip bends into curves"),
               ("CURVED", "Curved", "Printed already curved to the radius below: ties point "
                                    "at the centre of the curve and two connectors per gap "
                                    "follow the rails")])
    curve_radius: FloatProperty(
        name="Radius", default=22.0, min=0.0, soft_min=1.0, soft_max=2000.0, precision=2,
        update=_strip_update,
        description="Radius of the curve, measured to the track centreline, in model units "
                    "(inches or millimetres, as chosen beside it). For example 22 in for an "
                    "HO mainline curve. Tie spacing is measured along the centreline")
    radius_units: EnumProperty(
        name="Radius Units", default="IN", update=_radius_units_update,
        description="Units for the curve radius, a model size: inches, as most layout "
                    "plans give it, or millimetres. Changing it converts the value",
        items=[("IN", "in", "Curve radius in model inches"),
               ("MM", "mm", "Curve radius in model millimetres")])
    radius_units_prev: StringProperty(default="IN", options={"HIDDEN"})
    flex_first: EnumProperty(
        name="First Connector", default="LEFT", update=_strip_update,
        description="Which rail gets the connector in the first gap of a flexible strip; "
                    "the sides alternate after that",
        items=[("LEFT", "Left Rail", "First connector under the left rail, looking along the strip"),
               ("RIGHT", "Right Rail", "First connector under the right rail, looking along the strip")])
    connector_width: _model("Connector Width", 0.0,
                            "Width of each connector across the track; 0 uses the rail foot width")
    connector_height: FloatProperty(
        name="Connector Height", subtype="FACTOR", default=0.5, min=0.05, max=1.0,
        description="Connector height as a fraction of the tie height", update=_strip_update)

    # ---- boards (Weathered Board) ----
    board_preset: StringProperty(name="Tie Preset", default="",
                                 description="Weathered Board preset that sets the ties' look "
                                             "and size (length, width, thickness)",
                                 update=_strip_update)
    printer: EnumProperty(
        name="Printer", default="RESIN", update=_strip_update,
        description="Printer type: sets the grain detail Weathered Board builds and the "
                    "too-small-to-print warnings",
        items=[("RESIN", "Resin", "Fine detail; resin printer thresholds"),
               ("FDM", "FDM", "Filament printer; coarser detail and thresholds")])
    seed: IntProperty(name="Seed", default=0, min=0, update=_strip_update,
                      description="Number that picks the ties' random grain, lengths and "
                                  "offsets. Generate shows the seed it used here; the same "
                                  "seed and settings always give the same strip")
    lock_seed: BoolProperty(
        name="Lock Seed", default=False,
        description="Use the seed above for new strips instead of a random one, to repeat a "
                    "strip you liked. Also makes regenerating faster, since the ties are reused")
    pool_threshold: IntProperty(
        name="Unique Up To", default=50, min=2, soft_max=500, update=_strip_update,
        description="Strips with up to this many ties get a separate board per tie; "
                    "longer strips reuse a pool of boards")
    pool_size: IntProperty(name="Pool Size", default=12, min=2, soft_max=50, update=_strip_update,
                           description="Boards built for long strips")
    max_triangles: IntProperty(
        name="Max Triangles per Tie", default=15000, min=500, soft_max=100000, update=_strip_update,
        description="Each tie is simplified to about this many triangles before joining")

    # ---- variation (prototype) ----
    length_jitter: _proto("Length Variation", 2.0, "Ties vary in length by up to this, plus or minus")
    end_jitter: _proto("End Offset", 1.0, "Ties shift across the track by up to this, plus or minus")
    yaw_jitter: FloatProperty(name="Angle Variation", default=0.5, min=0.0, max=5.0,
                              description="Ties turn by up to this many degrees, plus or minus",
                              update=_strip_update)
    random_turn: BoolProperty(name="Random Turn", default=True, update=_strip_update,
                              description="Turn random ties end for end")

    # ---- spikes (model mm) ----
    fastening: EnumProperty(
        name="Fastening", default="HOLES", update=_strip_update,
        description="How the rail is held: holes for real spikes, or spikes printed on the ties "
                    "that the rail slides in under",
        items=[("HOLES", "Spike Holes", "Holes for real spikes; you spike the rail down"),
               ("PRINTED", "Printed Spikes", "Spikes printed on the ties; the rail slides in "
                                             "from the end of the strip, under the spike heads")])
    spike_shank: _model("Shank Width", 0.4, "Width of each printed spike's square shank")
    spike_overhang: _model("Head Overhang", 0.2, "How far each spike head reaches over the rail foot")
    spike_head: _model("Head Thickness", 0.2, "Thickness of each printed spike head")
    spike_side_clear: _model("Side Clearance", 0.15,
                             "Gap between the rail foot edge and each shank; generous so the "
                             "rail slides in easily")
    spike_top_clear: _model("Top Clearance", 0.10,
                            "Gap between the top of the rail foot and the underside of each head")
    spike_chamfer: FloatProperty(
        name="Head Chamfer", default=45.0, min=0.0, max=80.0, precision=0, step=500,
        update=_strip_update,
        description="Angle from horizontal of the slope under each spike head, so the head "
                    "doesn't overhang straight out from the shank. 45 prints without supports; "
                    "0 leaves the underside flat. Over the rail foot the underside stays flat")
    spike_every: IntProperty(name="Spike Every Nth Tie", default=1, min=1, soft_max=6,
                             update=_strip_update,
                             description="1 spikes every tie; 2 or 3 makes long rails easier to slide in")
    spike_bare_ends: IntProperty(name="Bare End Ties", default=1, min=0, soft_max=5,
                                 update=_strip_update,
                                 description="Ties at each end of the strip left without spikes, "
                                             "so rail joiners slide onto the foot")
    hole_diameter: _model("Hole Diameter", 0.5, "Spike hole diameter; match your spikes")
    hole_clearance: _model("Clearance from Foot", 0.0, "Gap between the rail foot and each hole")
    use_stagger: BoolProperty(name="Stagger", default=True, update=_strip_update,
                              description="Offset gauge-side and field-side spikes along the tie, "
                                          "as on the prototype")
    stagger: _proto("Stagger", 2.0, "Distance between gauge-side and field-side holes, along the track")

    # ---- tie plates ----
    plates_on: BoolProperty(name="Tie Plates", default=False, update=_plate_update,
                            description="Add a tie plate under each rail on every tie")
    plate_length: _proto("Plate Length", 14.0, "Tie plate length, across the track", _plate_update)
    plate_width: _proto("Plate Width", 7.75, "Tie plate width, along the track", _plate_update)
    plate_thickness: _proto("Plate Thickness", 0.75, "Tie plate thickness", _plate_update)
    plate_bias: _proto("Field-Side Bias", 1.0, "Plate shifted toward the outside of the rail",
                       _plate_update)
    shoulders: EnumProperty(
        name="Shoulders", default="DOUBLE", update=_plate_update,
        description="Raised ribs on the tie plate beside the rail foot",
        items=[("NONE", "None", "Flat plate"),
               ("FIELD", "Field Side Only", "One shoulder outboard of each rail"),
               ("DOUBLE", "Double", "Shoulders on both sides of the rail foot")])
    shoulder_height: _proto("Shoulder Height", 0.5, "Shoulder height above the plate", _plate_update)
    shoulder_width: _proto("Shoulder Width", 0.75, "Shoulder width", _plate_update)
    shoulder_clearance: _model("Shoulder Clearance", 0.05,
                               "Gap between the rail foot and each shoulder, so the rail drops in")
    # ---- rail laid on the strip (for fit checks and renders) ----
    rail_on: BoolProperty(
        name="Include Rail", default=False, update=_strip_update,
        description="Also add two rail objects sitting on the rail seats, parented to the "
                    "strip, to check the fit and for renders. They use the rail profile and "
                    "sizes above. Export STL can write the tie strip, the rail, or both")
    rail_overhang_auto: BoolProperty(
        name="Half Tie Gap", default=True, update=_strip_update,
        description="End each rail half a tie gap past the end ties, so rail on strips laid "
                    "end to end meets in the middle of the gap between them. Turn off to "
                    "enter your own End Overhang")
    rail_overhang: FloatProperty(
        name="End Overhang", default=0.0, soft_min=-20.0, soft_max=50.0, precision=2, step=10,
        update=_strip_update,
        description="With Half Tie Gap off: how far the rail sticks out past the outer face of "
                    "the end ties, at each end, in model millimetres, measured along the rail. "
                    "0 ends it flush with the ties; negative stops it short, for example to "
                    "leave room for rail joiners")
    seat_pad: BoolProperty(name="Flatten Rail Seats", default=True, update=_strip_update,
                           description="Fill the grain flat where the rail or tie plate sits")

    # ---- presets and output ----
    plate_preset: StringProperty(default="Modern heavy", options={"HIDDEN"})
    plate_modified: BoolProperty(default=False, options={"HIDDEN"})
    strip_preset: StringProperty(default="", options={"HIDDEN"})
    strip_modified: BoolProperty(default=False, options={"HIDDEN"})
    export_what: EnumProperty(
        name="Export", default="STRIP",
        description="What Export STL writes for each selected strip: the entire track (tie "
                    "strip and its rail), the tie strip only, or the rail only. Rail exists "
                    "only on strips generated with Include Rail",
        items=[("BOTH", "Entire Track", "The tie strip and its rail, together in one file"),
               ("STRIP", "Tie Strip Only", "Just the tie strip, ready to print"),
               ("RAIL", "Rail Only", "Just the rail laid on the tie strip")])
    export_template: StringProperty(
        name="File Name", default="tie_strip_{scale}_{type}_{n}.stl",
        description="Default STL file name; {scale}, {type} and {n} are filled in")
    last_report: StringProperty(default="", options={"HIDDEN"})

    # ------------------------------------------------------------------

    def scale_n(self) -> float:
        """N in 1:N for the chosen scale."""
        return scales.scale_n(self.scale, self.scale_custom)

    def full_mm(self, key: str) -> float:
        """A prototype setting in full-size millimetres."""
        return scales.to_full_mm(getattr(self, key), self.proto_units)

    def radius_mm(self) -> float:
        """The curve radius in model millimetres (0 unless the strip is Curved)."""
        if self.strip_type != "CURVED":
            return 0.0
        return self.curve_radius * (25.4 if self.radius_units == "IN" else 1.0)

    def angle_mode(self) -> bool:
        """True when the strip is sized by arc angle (Arc Angle chosen on a curved strip)."""
        return self.size_mode == "ANGLE" and self.strip_type == "CURVED"

    def ties(self) -> int:
        """The number of ties: as entered, the most that fit in Max Length, or for the arc angle.

        Arc Angle on a strip that isn't curved counts as Number of Ties.
        """
        return self.to_spec().tie_count

    def tie_size(self):
        """The tie size from the board preset, as wb_bridge.board_size returns it.

        Returns ((length, width, thickness) in full-size mm, the preset's
        units "IN" or "MM", error text or "").
        """
        from .wb_bridge import board_size
        return board_size(self.board_preset)

    def to_spec(self, count: bool = True, **overrides) -> Spec:
        """The settings as a layout Spec, prototype lengths in full-size mm.

        The tie count is worked out for Max Length and Arc Angle; in Arc
        Angle mode the spacing is adjusted too, so the ties fill the angle.
        With ``count=False`` the tie count and spacing are taken as entered.
        ``overrides`` set Spec fields the settings don't hold, such as values
        measured from the built boards.
        """
        f = self.full_mm
        (tl, tw, th), _units, tie_error = self.tie_size()
        spec = Spec(
            scale_n=self.scale_n(), gauge=self.gauge, foot_width=self.rail_foot,
            head_width=self.rail_head, tie_length=tl, tie_width=tw,
            tie_height=th, tie_error=tie_error, tie_count=self.tie_count,
            spacing=f("tie_spacing"),
            strip_type=self.strip_type, flex_first=self.flex_first,
            curve_radius=self.radius_mm(),
            connector_width=self.connector_width, connector_height_frac=self.connector_height,
            hole_diameter=self.hole_diameter, hole_clearance=self.hole_clearance,
            fastening=self.fastening, foot_edge=self.rail_edge,
            foot_web=self.rail_foot_web if self.rail_preset else 0.0,
            web_width=self.rail_web if self.rail_preset else 0.0,
            spike_shank=self.spike_shank, spike_overhang=self.spike_overhang,
            spike_head=self.spike_head, spike_side_clear=self.spike_side_clear,
            spike_top_clear=self.spike_top_clear, spike_chamfer=self.spike_chamfer,
            spike_every=self.spike_every,
            spike_bare_ends=self.spike_bare_ends,
            stagger=f("stagger") if self.use_stagger else 0.0,
            length_jitter=f("length_jitter"), end_jitter=f("end_jitter"),
            yaw_jitter=self.yaw_jitter,
            plates=self.plates_on, plate_length=f("plate_length"), plate_width=f("plate_width"),
            plate_thickness=f("plate_thickness"), plate_bias=f("plate_bias"),
            shoulders=self.shoulders, shoulder_height=f("shoulder_height"),
            shoulder_width=f("shoulder_width"), shoulder_clearance=self.shoulder_clearance,
            seat_pad=self.seat_pad,
        )
        for k, v in overrides.items():
            setattr(spec, k, v)
        if count and self.angle_mode():
            from .layout import ties_for_angle
            n, spacing = ties_for_angle(spec, self.arc_angle)
            if n >= 2:
                spec.tie_count, spec.spacing = n, spacing
        elif count and self.size_mode == "LENGTH":
            from .layout import ties_for_length
            spec.tie_count = ties_for_length(spec, self.max_length)
        return spec

    def rail_overhang_value(self):
        """The End Overhang to build with: None for Half Tie Gap, else the value entered (model mm)."""
        return None if self.rail_overhang_auto else self.rail_overhang

    def rail_shape(self):
        """The rail cross-section for the rail objects, as rail.shape_from_sizes returns it.

        Returns (rail.RailShape or None, error text or ""). Preset-only
        sizes are used only while a rail preset is chosen; typed-in rail
        gets typical proportions for them.
        """
        from . import rail
        preset = bool(self.rail_preset)
        return rail.shape_from_sizes(
            self.rail_foot, self.rail_head, self.rail_height, self.rail_edge,
            self.rail_foot_web if preset else 0.0, self.rail_web if preset else 0.0,
            self.rail_head_depth if preset else 0.0, self.rail_corner if preset else 0.0)

    # ---- presets ----

    def apply_rail_values(self, values: dict, name: str) -> None:
        """Fill the rail sizes from a Model Rail Generator preset, or clear to Custom.

        ``values`` is keyed by setting name (see rail_bridge.FIELDS). With
        ``name`` empty the typed-in sizes are kept and the preset-only values
        (foot thickness at the web, web width, head depth, corner radius)
        are cleared.
        """
        with quiet():
            for key, value in values.items():
                setattr(self, key, value)
            if not name:
                self.rail_foot_web = self.rail_web = 0.0
                self.rail_head_depth = self.rail_corner = 0.0
            self.rail_preset = name
            self.rail_modified = False
        _strip_update(self, None)

    def plate_values(self) -> dict:
        """Tie plate settings with lengths in inches, for a plate preset."""
        out = {}
        for key in PLATE_KEYS:
            value = getattr(self, key)
            if key in PROTO_LENGTH_KEYS:
                value = scales.from_full_mm(self.full_mm(key), "IN")
            out[key] = value
        return out

    def apply_plate_values(self, values: dict, name: str) -> None:
        """Load a plate preset's values (lengths in inches) and select it as ``name``.

        Keys the preset lacks are left as they are.
        """
        with quiet():
            for key in PLATE_KEYS:
                if key not in values:
                    continue
                value = values[key]
                if key in PROTO_LENGTH_KEYS:
                    value = scales.from_full_mm(scales.to_full_mm(float(value), "IN"),
                                                self.proto_units)
                setattr(self, key, value)
            self.plate_preset = name
            self.plate_modified = False

    def strip_values(self) -> dict:
        """Every setting, for a strip preset."""
        skip = {"rna_type", "name", "proto_units_prev", "radius_units_prev", "use_arc_angle",
                "plate_modified",
                "strip_preset",
                "strip_modified", "last_report", "export_what"}
        return {p.identifier: getattr(self, p.identifier)
                for p in self.bl_rna.properties if p.identifier not in skip}

    def apply_strip_values(self, values: dict, name: str) -> None:
        """Load a strip preset's values and select it as ``name``.

        Units are set first so saved lengths aren't converted. Unknown keys
        and values this version rejects are skipped, so older presets load.
        """
        names = {p.identifier for p in self.bl_rna.properties}
        with quiet():
            for units in ("proto_units", "radius_units"):
                if units in values:
                    setattr(self, units, values[units])
                    setattr(self, units + "_prev", values[units])
            for key, value in values.items():
                if key in names and key not in ("proto_units", "radius_units"):
                    try:
                        setattr(self, key, value)
                    except (TypeError, ValueError):
                        pass  # a setting this version no longer accepts
            self.strip_preset = name
            self.strip_modified = False


    def apply_built_values(self, values: dict, meta: dict) -> None:
        """Load the settings a strip was built with into the panel (Load Settings From Selected).

        ``values`` and ``meta`` come from build.stored_settings. Every stored
        setting is loaded, including the seed the strip used, except the
        ones in ``LOAD_KEEP``, which are about how the panel is used rather
        than about the strip. The strip preset name and the modified marks
        are put back as they were when the strip was built; strips made
        before 0.6.0 didn't record them, so they load with no strip preset
        and an unmodified plate preset.
        """
        self.apply_strip_values({k: v for k, v in values.items() if k not in LOAD_KEEP},
                                str(meta.get("strip_preset", "")))
        with quiet():
            self.strip_modified = bool(meta.get("strip_modified", False))
            self.plate_modified = bool(meta.get("plate_modified", False))


# Settings Load Settings From Selected leaves as they are: Lock Seed (whether
# new strips repeat the seed) and the Export choice describe how the panel is
# used, not the strip. strip_values() already leaves out the export choice.
LOAD_KEEP = ("lock_seed", "export_what")


def register():
    """Add ``scene.tie_strip``. TIESTRIP_Settings must already be registered."""
    bpy.types.Scene.tie_strip = bpy.props.PointerProperty(type=TIESTRIP_Settings)


def unregister():
    """Remove ``scene.tie_strip``."""
    del bpy.types.Scene.tie_strip
