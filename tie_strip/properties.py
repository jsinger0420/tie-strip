"""All Tie Strip settings, kept on the scene so they save with the .blend file.

Prototype sizes (ties, spacing, jitter, stagger, tie plates) are in the
units chosen by ``proto_units``, inches by default. Rail sizes, holes and
clearances are model millimetres. Lengths are plain numbers rather than
Blender length units, so they read the same whatever the scene units are.
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
        global _quiet
        self._prev, _quiet = _quiet, True

    def __exit__(self, *exc):
        global _quiet
        _quiet = self._prev


def _scale_update(self, context):
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


def _plate_update(self, context):
    if not _quiet and self.plate_preset:
        self.plate_modified = True


def _strip_update(self, context):
    if not _quiet and self.strip_preset:
        self.strip_modified = True


def _proto(name, default, desc, update=None, soft_max=1000.0):
    return FloatProperty(name=name, description=desc + " (prototype size, in the chosen units)",
                         default=default, min=0.0, soft_max=soft_max, precision=3,
                         update=update or _strip_update)


def _model(name, default, desc, update=None):
    return FloatProperty(name=name, description=desc + " (model millimetres)",
                         default=default, min=0.0, soft_max=50.0, precision=3, step=1,
                         update=update or _strip_update)


class TIESTRIP_Settings(bpy.types.PropertyGroup):
    # ---- scale and track (model mm) ----
    scale: EnumProperty(
        name="Scale", default="HO", update=_scale_update,
        items=[(k, v[0], f"1:{v[1]:g}, standard gauge {v[2]:g} mm") for k, v in scales.SCALES.items()]
        + [(scales.CUSTOM, "Custom", "Enter your own ratio")])
    scale_custom: FloatProperty(name="Ratio 1:", default=87.1, min=1.0, soft_max=500.0,
                                description="N in 1:N for a custom scale", update=_strip_update)
    gauge: _model("Gauge", 16.5, "Distance between the inner faces of the railheads")
    rail_foot: _model("Rail Foot Width", 0.0, "Width of the rail's base, measured on your rail")
    rail_head: _model("Rail Head Width", 0.0, "Width of the railhead, measured on your rail")

    # ---- ties (prototype) ----
    proto_units: EnumProperty(
        name="Prototype Units", default="IN", update=_units_update,
        items=[("IN", "Inches", "Prototype sizes in inches"),
               ("MM", "Millimetres", "Prototype sizes in millimetres")])
    proto_units_prev: StringProperty(default="IN", options={"HIDDEN"})
    size_mode: EnumProperty(
        name="Size By", default="COUNT", update=_strip_update,
        items=[("COUNT", "Number of Ties", "Enter how many ties the strip has"),
               ("LENGTH", "Max Length", "Enter the longest strip your printer takes; "
                                        "the number of ties is worked out to fit")])
    tie_count: IntProperty(name="Number of Ties", default=20, min=2, soft_max=200,
                           update=_strip_update)
    max_length: FloatProperty(
        name="Max Length", default=200.0, min=1.0, soft_max=1000.0, precision=1,
        description="Longest printed strip, in model millimetres, for example your printer's "
                    "build plate length", update=_strip_update)
    tie_spacing: _proto("Tie Spacing", 19.5, "Centre-to-centre distance between ties")

    # ---- strip ----
    strip_type: EnumProperty(
        name="Strip Type", default="STRAIGHT", update=_strip_update,
        items=[("STRAIGHT", "Straight", "Two connectors between each pair of ties"),
               ("FLEX", "Flexible", "One connector between each pair of ties, alternating "
                                    "sides, so the printed strip bends into curves")])
    flex_first: EnumProperty(
        name="First Connector", default="LEFT", update=_strip_update,
        items=[("LEFT", "Left Rail", ""), ("RIGHT", "Right Rail", "")])
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
        items=[("RESIN", "Resin", "Fine detail; resin printer thresholds"),
               ("FDM", "FDM", "Filament printer; coarser detail and thresholds")])
    seed: IntProperty(name="Seed", default=0, min=0, update=_strip_update,
                      description="Same seed and settings always give the same strip")
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

    # ---- spike holes (model mm) ----
    hole_diameter: _model("Hole Diameter", 0.5, "Spike hole diameter; match your spikes")
    hole_clearance: _model("Clearance from Foot", 0.0, "Gap between the rail foot and each hole")
    use_stagger: BoolProperty(name="Stagger Holes", default=True, update=_strip_update,
                              description="Offset gauge-side and field-side holes along the tie, "
                                          "as on the prototype")
    stagger: _proto("Stagger", 2.0, "Distance between gauge-side and field-side holes, along the track")

    # ---- tie plates ----
    plates_on: BoolProperty(name="Tie Plates", default=False, update=_plate_update)
    plate_length: _proto("Plate Length", 14.0, "Tie plate length, across the track", _plate_update)
    plate_width: _proto("Plate Width", 7.75, "Tie plate width, along the track", _plate_update)
    plate_thickness: _proto("Plate Thickness", 0.75, "Tie plate thickness", _plate_update)
    plate_bias: _proto("Field-Side Bias", 1.0, "Plate shifted toward the outside of the rail",
                       _plate_update)
    shoulders: EnumProperty(
        name="Shoulders", default="DOUBLE", update=_plate_update,
        items=[("NONE", "None", "Flat plate"),
               ("FIELD", "Field Side Only", "One shoulder outboard of each rail"),
               ("DOUBLE", "Double", "Shoulders on both sides of the rail foot")])
    shoulder_height: _proto("Shoulder Height", 0.5, "Shoulder height above the plate", _plate_update)
    shoulder_width: _proto("Shoulder Width", 0.75, "Shoulder width", _plate_update)
    shoulder_clearance: _model("Shoulder Clearance", 0.05,
                               "Gap between the rail foot and each shoulder, so the rail drops in")
    seat_pad: BoolProperty(name="Flatten Rail Seats", default=True, update=_strip_update,
                           description="Fill the grain flat where the rail or tie plate sits")

    # ---- presets and output ----
    plate_preset: StringProperty(default="Modern heavy", options={"HIDDEN"})
    plate_modified: BoolProperty(default=False, options={"HIDDEN"})
    strip_preset: StringProperty(default="", options={"HIDDEN"})
    strip_modified: BoolProperty(default=False, options={"HIDDEN"})
    export_template: StringProperty(
        name="File Name", default="tie_strip_{scale}_{type}_{n}.stl",
        description="Default STL file name; {scale}, {type} and {n} are filled in")
    last_report: StringProperty(default="", options={"HIDDEN"})

    # ------------------------------------------------------------------

    def scale_n(self) -> float:
        return scales.scale_n(self.scale, self.scale_custom)

    def full_mm(self, key: str) -> float:
        """A prototype setting in full-size millimetres."""
        return scales.to_full_mm(getattr(self, key), self.proto_units)

    def ties(self) -> int:
        """The number of ties: as entered, or the most that fit in Max Length."""
        if self.size_mode == "LENGTH":
            from .layout import ties_for_length
            return ties_for_length(self.to_spec(count=False), self.max_length)
        return self.tie_count

    def tie_size(self):
        """The board preset's (length, width, thickness) in full-size mm, its units, error."""
        from .wb_bridge import board_size
        return board_size(self.board_preset)

    def to_spec(self, count: bool = True, **overrides) -> Spec:
        f = self.full_mm
        (tl, tw, th), _units, tie_error = self.tie_size()
        spec = Spec(
            scale_n=self.scale_n(), gauge=self.gauge, foot_width=self.rail_foot,
            head_width=self.rail_head, tie_length=tl, tie_width=tw,
            tie_height=th, tie_error=tie_error, tie_count=self.ties() if count else self.tie_count,
            spacing=f("tie_spacing"),
            strip_type=self.strip_type, flex_first=self.flex_first,
            connector_width=self.connector_width, connector_height_frac=self.connector_height,
            hole_diameter=self.hole_diameter, hole_clearance=self.hole_clearance,
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
        return spec

    # ---- presets ----

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
        skip = {"rna_type", "name", "proto_units_prev", "plate_modified", "strip_preset",
                "strip_modified", "last_report"}
        return {p.identifier: getattr(self, p.identifier)
                for p in self.bl_rna.properties if p.identifier not in skip}

    def apply_strip_values(self, values: dict, name: str) -> None:
        names = {p.identifier for p in self.bl_rna.properties}
        with quiet():
            if "proto_units" in values:
                self.proto_units = values["proto_units"]
                self.proto_units_prev = values["proto_units"]
            for key, value in values.items():
                if key in names and key != "proto_units":
                    try:
                        setattr(self, key, value)
                    except (TypeError, ValueError):
                        pass  # a setting this version no longer accepts
            self.strip_preset = name
            self.strip_modified = False


def register():
    bpy.types.Scene.tie_strip = bpy.props.PointerProperty(type=TIESTRIP_Settings)


def unregister():
    del bpy.types.Scene.tie_strip
