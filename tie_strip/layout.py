"""Where everything goes on a tie strip. Pure Python, no bpy.

All output positions are model (printed) millimetres. Axes: X runs along
the track, Y across it (+Y is the left rail, looking along +X), Z up.
The strip is centred on the origin in X and Y, and tie bottoms sit on
Z = 0, which becomes the print bed.

``Spec`` holds the inputs. Prototype sizes (ties, spacing, plates, jitter)
are full-size millimetres; rail sizes, holes and clearances are model
millimetres, because that is what a modeler measures on their rail.
``compute`` turns a Spec into a ``Layout``: tie centres, connector boxes,
spike holes or printed spikes, tie plates, shoulders and rail seat pads,
plus any errors
(the strip cannot be built) and fit warnings. ``printability`` adds
warnings for features too small for the chosen printer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

STRAIGHT, FLEX = "STRAIGHT", "FLEX"
LEFT, RIGHT = "LEFT", "RIGHT"
SHOULDERS_NONE, SHOULDERS_FIELD, SHOULDERS_DOUBLE = "NONE", "FIELD", "DOUBLE"
HOLES, PRINTED = "HOLES", "PRINTED"  # how the rail is fastened

HOLE_EXTRA = 1.0  # hole cutters run this far past the bottom and the top, model mm


@dataclass(frozen=True)
class Box:
    """An axis-aligned box, model mm."""

    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float

    @property
    def size(self) -> tuple[float, float, float]:
        """(length along X, width along Y, height along Z)."""
        return (self.x1 - self.x0, self.y1 - self.y0, self.z1 - self.z0)


@dataclass(frozen=True)
class Hole:
    """A vertical spike hole: centre (x, y), diameter d, from z0 to z1. Model mm."""

    x: float
    y: float
    d: float
    z0: float
    z1: float


@dataclass(frozen=True)
class Spike:
    """A printed spike: a square shank with a head reaching over the rail foot.

    Its cross-section across the track is the same along its whole length
    in X: an L, with a chamfer under the head so the head doesn't stick
    straight out from the shank. ``y_shank_in`` and ``y_shank_out`` are the
    shank faces nearest and furthest from the rail; ``y_head`` is the head's
    inner edge, over the rail foot. The shank runs from ``z0`` to ``z_top``.
    ``z_head`` is the head's underside over the foot. ``under`` lists the
    (y, z) points of the underside from the head's inner edge out to the
    shank face: flat over the foot, then sloping down to the shank. Model mm.
    """

    x0: float
    x1: float
    y_head: float
    y_shank_in: float
    y_shank_out: float
    z0: float
    z_head: float
    z_top: float
    under: tuple[tuple[float, float], ...] = ()

    def outline(self) -> list[tuple[float, float]]:
        """The cross-section as (y, z) points in order, repeated points removed.

        Shank bottom, up the shank's outer face, across the head top, then
        back along the underside to the shank's inner face.
        """
        pts = [(self.y_shank_in, self.z0), (self.y_shank_out, self.z0),
               (self.y_shank_out, self.z_top), (self.y_head, self.z_top)]
        pts += list(self.under) or [(self.y_head, self.z_head), (self.y_shank_in, self.z_head)]
        out = []
        for p in pts:
            if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
                out.append(p)
        return out


@dataclass
class Spec:
    """Every input to the layout. See the module docstring for units."""

    scale_n: float
    gauge: float  # model mm, between the inner faces of the railheads
    foot_width: float  # model mm
    head_width: float  # model mm
    tie_length: float  # full-size mm, across the track
    tie_width: float  # full-size mm, along the track
    tie_height: float  # full-size mm
    tie_count: int
    spacing: float  # full-size mm, centre to centre
    tie_error: str = ""  # why the tie size is unknown (e.g. no board preset chosen)

    strip_type: str = STRAIGHT
    flex_first: str = LEFT
    connector_width: float = 0.0  # model mm; 0 = the rail foot width
    connector_height_frac: float = 0.5  # of the tie height
    connector_overlap: float = 0.3  # model mm into each tie

    hole_diameter: float = 0.5  # model mm
    hole_clearance: float = 0.0  # model mm, foot edge to hole edge
    stagger: float = 0.0  # full-size mm between gauge-side and field-side holes; 0 = none

    # Printed spikes (fastening == PRINTED), all model mm.
    fastening: str = HOLES
    foot_edge: float = 0.0  # rail foot thickness at its outer edge
    foot_web: float = 0.0  # rail foot thickness at the web; 0 = treat the foot as flat
    web_width: float = 0.0  # rail web thickness; 0 = unknown, the head width stands in
    spike_shank: float = 0.4  # square shank width
    spike_overhang: float = 0.2  # how far the head reaches over the foot
    spike_head: float = 0.2  # head thickness
    spike_side_clear: float = 0.15  # foot edge to shank
    spike_chamfer: float = 45.0  # degrees from horizontal under the head; 0 = flat underside
    spike_top_clear: float = 0.10  # top of the foot to the head's underside
    spike_every: int = 1  # spike every Nth tie
    spike_bare_ends: int = 1  # ties at each end left without spikes

    length_jitter: float = 0.0  # full-size mm, +/-
    end_jitter: float = 0.0  # full-size mm, +/- shift of a tie across the track
    yaw_jitter: float = 0.0  # degrees, +/- turn of a tie

    plates: bool = False
    plate_length: float = 355.6  # full-size mm, across the track
    plate_width: float = 196.85  # full-size mm, along the track
    plate_thickness: float = 19.05  # full-size mm
    plate_bias: float = 25.4  # full-size mm, plate shifted toward the field side
    shoulders: str = SHOULDERS_DOUBLE
    shoulder_height: float = 12.7  # full-size mm
    shoulder_width: float = 19.05  # full-size mm
    shoulder_clearance: float = 0.05  # model mm, foot edge to shoulder

    seat_pad: bool = True  # fill the grain under each rail seat flat
    seat_depth: float = 0.0  # model mm: how deep the grain goes (from the boards)
    seat_inset: float = 0.0  # model mm: keep the pad this far inside the tie faces
    seat_margin: float = 0.2  # model mm beyond each side of the rail foot

    def model(self, full_mm: float) -> float:
        """A full-size length in model mm."""
        return full_mm / self.scale_n


@dataclass
class Layout:
    """The computed strip. All model mm."""

    tie_x: list[float] = field(default_factory=list)
    tie_length: float = 0.0
    tie_width: float = 0.0
    tie_height: float = 0.0
    rail_y: float = 0.0  # each rail's centreline is at +rail_y and -rail_y
    connectors: list[Box] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)
    spikes: list[Spike] = field(default_factory=list)
    plates: list[Box] = field(default_factory=list)
    shoulders: list[Box] = field(default_factory=list)
    seats: list[Box] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, float] = field(default_factory=dict)
    summary_extra: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when there are no errors and the strip can be built."""
        return not self.errors


def _check_inputs(s: Spec) -> list[str]:
    """Errors for inputs that can't describe a strip at all."""
    errs = []
    if s.scale_n < 1:
        errs.append("Scale must be 1:1 or smaller.")
    if s.gauge <= 0:
        errs.append("Enter the gauge (distance between the railheads).")
    if s.foot_width <= 0:
        errs.append("Enter the rail foot width.")
    if s.head_width <= 0:
        errs.append("Enter the rail head width.")
    if s.tie_error:
        errs.append(s.tie_error)
    elif min(s.tie_length, s.tie_width, s.tie_height) <= 0:
        errs.append("The board preset's length, width and thickness must be positive.")
    if s.tie_count < 2:
        errs.append("A strip needs at least 2 ties.")
    if s.spacing <= 0:
        errs.append("Tie spacing must be positive.")
    if s.fastening not in (HOLES, PRINTED):
        errs.append(f"Unknown fastening '{s.fastening}'.")
    elif s.fastening == HOLES and s.hole_diameter <= 0:
        errs.append("Spike hole diameter must be positive.")
    elif s.fastening == PRINTED:
        if s.foot_edge <= 0:
            errs.append("Printed spikes need the rail foot edge thickness: pick a rail preset "
                        "or measure your rail.")
        if min(s.spike_shank, s.spike_head) <= 0:
            errs.append("Printed spike shank width and head thickness must be positive.")
        if s.spike_overhang <= 0:
            errs.append("The printed spike head must reach over the rail foot: "
                        "make the head overhang more than 0.")
        if s.spike_every < 1:
            errs.append("Spike every Nth tie must be 1 or more.")
        if s.spike_chamfer and not 30.0 <= s.spike_chamfer <= 80.0:
            errs.append("The chamfer under the spike heads must be 0 (none) or 30 to 80 degrees.")
    if not 0 < s.connector_height_frac <= 1:
        errs.append("Connector height must be between 0 and 1 times the tie height.")
    if s.strip_type not in (STRAIGHT, FLEX):
        errs.append(f"Unknown strip type '{s.strip_type}'.")
    if s.plates and min(s.plate_length, s.plate_width, s.plate_thickness) <= 0:
        errs.append("Tie plate length, width and thickness must be positive.")
    return errs


def compute(s: Spec) -> Layout:
    """Lay out the whole strip. Check ``layout.errors`` before building."""
    lay = Layout()
    lay.errors = _check_inputs(s)
    if lay.errors:
        return lay

    lt, wt, ht = s.model(s.tie_length), s.model(s.tie_width), s.model(s.tie_height)
    p = s.model(s.spacing)
    n = int(s.tie_count)
    lay.tie_length, lay.tie_width, lay.tie_height = lt, wt, ht

    # Rail centreline: the gauge is between the inner railhead faces.
    yr = s.gauge / 2 + s.head_width / 2
    lay.rail_y = yr
    half_foot = s.foot_width / 2

    # Ties, centred on the origin.
    lay.tie_x = [(i - (n - 1) / 2) * p for i in range(n)]
    gap = p - wt
    if gap <= 0:
        lay.errors.append(
            f"Ties overlap: spacing {p:.2f} mm is not more than the tie width {wt:.2f} mm.")
        return lay

    # Shortest tie end, after length and end jitter.
    end_min = lt / 2 - s.model(s.length_jitter) / 2 - s.model(s.end_jitter)
    if yr + half_foot >= end_min:
        lay.errors.append("The rails hang off the ends of the ties: the gauge is too wide "
                          "for this tie length.")

    # Connectors under each rail, from Z = 0 to a fraction of the tie height.
    wc = s.connector_width if s.connector_width > 0 else s.foot_width
    hc = s.connector_height_frac * ht
    e = s.connector_overlap
    if e >= wt / 2:
        lay.errors.append("Connector overlap is more than half the tie width.")
    first = 1 if s.flex_first == LEFT else -1
    for k in range(n - 1):
        x0 = lay.tie_x[k] + wt / 2 - e
        x1 = lay.tie_x[k + 1] - wt / 2 + e
        if s.strip_type == STRAIGHT:
            sides = (1, -1)
        else:
            sides = (first,) if k % 2 == 0 else (-first,)
        for side in sides:
            y = side * yr
            lay.connectors.append(Box(x0, x1, y - wc / 2, y + wc / 2, 0.0, hc))

    # Tie plates and shoulders.
    top = ht
    tp = s.model(s.plate_thickness) if s.plates else 0.0
    hs = s.model(s.shoulder_height) if s.plates and s.shoulders != SHOULDERS_NONE else 0.0
    if s.plates:
        lp, wp, bias = s.model(s.plate_length), s.model(s.plate_width), s.model(s.plate_bias)
        ws, cs = s.model(s.shoulder_width), s.shoulder_clearance
        embed = max(0.1, s.seat_depth + 0.02) if s.seat_pad else 0.1
        if wp > wt:
            lay.warnings.append(f"Tie plates ({wp:.2f} mm) are wider than the ties ({wt:.2f} mm).")
        if half_foot > lp / 2 - abs(bias):
            lay.errors.append("The rail foot is wider than the tie plate allows; "
                              "lengthen the plate or reduce the field-side bias.")
        reach = half_foot + cs + ws
        if s.shoulders != SHOULDERS_NONE and reach > lp / 2 + bias:
            lay.warnings.append("The field-side shoulder hangs off the tie plate.")
        if s.shoulders == SHOULDERS_DOUBLE and reach > lp / 2 - bias:
            lay.warnings.append("The gauge-side shoulder hangs off the tie plate.")
        if yr + bias + lp / 2 > end_min:
            lay.warnings.append("Tie plates hang off the ends of the shortest ties.")
        for x in lay.tie_x:
            for side in (1, -1):
                yc = side * (yr + bias)
                lay.plates.append(Box(x - wp / 2, x + wp / 2, yc - lp / 2, yc + lp / 2,
                                      ht - embed, ht + tp))
                if s.shoulders == SHOULDERS_NONE:
                    continue
                z0, z1 = ht + tp - 0.05, ht + tp + hs
                # Field side is outward: +Y for the left rail, -Y for the right.
                faces = [side] if s.shoulders == SHOULDERS_FIELD else [side, -side]
                for f in faces:
                    inner = side * yr + f * (half_foot + cs)
                    outer = inner + f * ws
                    y0, y1 = sorted((inner, outer))
                    lay.shoulders.append(Box(x - wp / 2, x + wp / 2, y0, y1, z0, z1))
        top = ht + tp + hs
    elif s.seat_pad and s.seat_depth > 0:
        # No plates: fill the grain flat where the rail sits.
        half_x = wt / 2 - s.seat_inset
        if half_x > 0:
            hy = half_foot + s.seat_margin
            for x in lay.tie_x:
                for side in (1, -1):
                    y = side * yr
                    lay.seats.append(Box(x - half_x, x + half_x, y - hy, y + hy,
                                         ht - s.seat_depth - 0.02, ht))

    st = s.model(s.stagger) / 2
    if s.fastening == PRINTED:
        outer, top = _printed_spikes(s, lay, half_foot, st, end_min, top, tp)
    else:
        outer = _spike_holes(s, lay, half_foot, st, end_min, top)

    half_x, half_y = tie_extent(s)
    lay.summary = {
        "tie_length": lt, "tie_width": wt, "tie_height": ht,
        "gap": gap, "strip_length": (n - 1) * p + wt,
        "overall_length": (n - 1) * p + 2 * half_x, "overall_width": 2 * half_y,
        "rail_centre": yr, "outer_hole": outer,
        "connector_width": wc, "connector_height": hc,
        "connectors": float(len(lay.connectors)),
        "top": top,
    }
    lay.summary.update(lay.summary_extra)
    return lay


def _spike_holes(s: Spec, lay: Layout, half_foot: float, st: float, end_min: float,
                 top: float) -> float:
    """Four spike holes per tie, touching the rail foot. Returns the outer hole edge."""
    yr, wt = lay.rail_y, lay.tie_width
    d = s.hole_diameter
    off = half_foot + s.hole_clearance + d / 2
    if st + d / 2 > wt / 2:
        lay.errors.append("Spike hole stagger puts holes off the tie faces; reduce the stagger.")
    if yr + off + d / 2 > end_min:
        lay.errors.append("Field-side spike holes fall off the ends of the shortest ties.")
    if yr - off - d / 2 < 0:
        lay.errors.append("Gauge-side spike holes cross the track centreline.")
    if s.plates and st + d / 2 > s.model(s.plate_width) / 2:
        lay.warnings.append("Staggered spike holes fall outside the tie plates; "
                            "reduce the stagger or widen the plates.")
    z0, z1 = -HOLE_EXTRA, top + HOLE_EXTRA
    for x in lay.tie_x:
        for side in (1, -1):
            y = side * yr
            # Gauge-side hole one way along the tie, field-side the other,
            # mirrored on the other rail.
            lay.holes.append(Hole(x + side * st, y - side * off, d, z0, z1))  # gauge side
            lay.holes.append(Hole(x - side * st, y + side * off, d, z0, z1))  # field side
    return yr + off + d / 2


def foot_under_head(s: Spec) -> float:
    """Rail foot thickness under the inner edge of a printed spike head, model mm.

    The foot thickens from its edge toward the web, so the head must clear
    the foot where its inner edge sits, not at the foot tip. Without the
    web values (a typed-in rail) the foot is treated as flat.
    """
    te, tw = s.foot_edge, s.foot_web
    run = (s.foot_width - s.web_width) / 2
    if tw <= te or s.web_width <= 0 or run <= 0:
        return te
    return te + (tw - te) * min(1.0, s.spike_overhang / run)


def foot_slope(s: Spec) -> float:
    """Rise per mm of the rail foot's top surface toward the web (0 for a flat foot)."""
    run = (s.foot_width - s.web_width) / 2
    if s.foot_web <= s.foot_edge or s.web_width <= 0 or run <= 0:
        return 0.0
    return (s.foot_web - s.foot_edge) / run


def spike_underside(s: Spec, half_foot: float) -> tuple[list[tuple[float, float]], float, float]:
    """The underside of a printed spike head, measured from the rail centre and the rail seat.

    Returns (points as (u, z) from the head's inner edge out to the shank's
    inner face, the underside height over the foot, the flat overhang
    length left after the chamfer). u is the distance from the rail
    centreline, z the height above the rail seat, both model mm.

    The chamfer is a straight slope at ``spike_chamfer`` degrees from
    horizontal, rising from the shank toward the rail. It passes the rail
    foot's top outer corner with at least the top clearance above it and
    the side clearance beside it, so the rail still slides in. Over the
    foot the underside must stay flat (the foot is there), so only the part
    beyond the foot edge can be angled.
    """
    o, cp, cv = s.spike_overhang, s.spike_side_clear, s.spike_top_clear
    u_tip, u_shank = half_foot - o, half_foot + cp
    z_flat = foot_under_head(s) + cv
    if not s.spike_chamfer:
        return [(u_tip, z_flat), (u_shank, z_flat)], z_flat, o + cp
    t = math.tan(math.radians(s.spike_chamfer))
    z_edge = s.foot_edge + max(cv, cp * t)  # the slope's height above the foot edge

    def slope(u):
        """Height of the chamfer line at distance u from the rail centre."""
        return z_edge + (half_foot - u) * t

    u_join = half_foot + (z_edge - z_flat) / t  # where the slope meets the flat underside
    if u_join <= u_tip:  # the slope reaches the tip: no flat part left
        return [(u_tip, slope(u_tip)), (u_shank, slope(u_shank))], slope(u_tip), 0.0
    return ([(u_tip, z_flat), (u_join, z_flat), (u_shank, slope(u_shank))], z_flat,
            u_join - u_tip)


def spiked_ties(s: Spec, n: int) -> list[int]:
    """Indexes of the ties that get printed spikes: every Nth, skipping the bare end ties."""
    bare = max(0, int(s.spike_bare_ends))
    every = max(1, int(s.spike_every))
    return [i for i in range(bare, n - bare) if (i - bare) % every == 0]


def _printed_spikes(s: Spec, lay: Layout, half_foot: float, st: float, end_min: float,
                    top: float, tp: float) -> tuple[float, float]:
    """Four printed spikes per spiked tie. Returns (outer shank edge, new top of the strip)."""
    yr, wt, ht = lay.rail_y, lay.tie_width, lay.tie_height
    a, o = s.spike_shank, s.spike_overhang
    cp, cv, th = s.spike_side_clear, s.spike_top_clear, s.spike_head
    web = s.web_width if s.web_width > 0 else s.head_width
    if o >= (s.foot_width - web) / 2:
        lay.errors.append("The printed spike heads reach the rail web; reduce the head overhang.")
    u_in, u_out = half_foot + cp, half_foot + cp + a  # shank faces, from the rail centre
    if yr + u_out > end_min:
        lay.errors.append("Field-side printed spikes fall off the ends of the shortest ties.")
    if yr - u_out < 0:
        lay.errors.append("Gauge-side printed spikes cross the track centreline.")
    if st + a / 2 > wt / 2:
        lay.errors.append("Spike stagger puts printed spikes off the tie faces; reduce the stagger.")
    if s.plates and st + a / 2 > s.model(s.plate_width) / 2:
        lay.warnings.append("Staggered printed spikes stand off the tie plates; "
                            "reduce the stagger or widen the plates.")
    if s.spike_chamfer and math.tan(math.radians(s.spike_chamfer)) <= foot_slope(s):
        lay.errors.append("The chamfer under the spike heads is shallower than the rail foot's "
                          "slope; make the chamfer angle steeper.")
    seat = ht + tp  # where the rail foot sits
    embed = max(0.1, s.seat_depth + 0.02) if s.seat_pad else 0.1
    z0 = ht - embed  # the shank always reaches down into the tie
    under, z_under, flat = spike_underside(s, half_foot)
    z_head = seat + z_under
    z_top = seat + foot_under_head(s) + cv + th
    ties = spiked_ties(s, len(lay.tie_x))
    if not ties:
        lay.warnings.append("No ties get printed spikes: reduce the bare end ties or "
                            "spike every Nth tie.")
    for i in ties:
        x = lay.tie_x[i]
        for side in (1, -1):
            for f, xs in ((-side, x + side * st), (side, x - side * st)):  # gauge, field
                y_rail = side * yr
                lay.spikes.append(Spike(
                    xs - a / 2, xs + a / 2,
                    y_head=y_rail + f * (half_foot - o),
                    y_shank_in=y_rail + f * u_in, y_shank_out=y_rail + f * u_out,
                    z0=z0, z_head=z_head, z_top=z_top,
                    under=tuple((y_rail + f * u, seat + z) for u, z in under)))
    lay.summary_extra = {"head_slot": z_head - seat, "head_top": z_top - seat,
                         "flat_overhang": flat, "spiked_ties": float(len(ties))}
    return yr + u_out, max(top, z_top)


def tie_extent(s: Spec) -> tuple[float, float]:
    """Worst-case half-size of one tie along and across the track, model mm.

    Includes the length variation, end offset and angle variation, so the
    printed strip never comes out bigger than the reported overall size.
    """
    lt, wt = s.model(s.tie_length), s.model(s.tie_width)
    a = math.radians(abs(s.yaw_jitter))
    half_len = lt / 2 + s.model(s.length_jitter) / 2 + s.model(s.end_jitter)
    half_x = wt / 2 * math.cos(a) + (lt / 2 + s.model(s.length_jitter) / 2) * math.sin(a)
    half_y = half_len * math.cos(a) + wt / 2 * math.sin(a)
    return max(half_x, wt / 2), max(half_y, half_len)


def ties_for_length(s: Spec, max_length: float) -> int:
    """The most ties whose overall printed length fits in ``max_length`` model mm.

    May be less than 2 when even two ties don't fit; ``compute`` then
    reports the error.
    """
    p = s.model(s.spacing)
    if p <= 0:
        return 0
    half_x, _ = tie_extent(s)
    return int(math.floor((max_length - 2 * half_x) / p + 1e-9)) + 1


# Smallest printable features, model mm, by printer.
DEFAULT_THRESHOLDS = {
    "RESIN": {"hole": 0.3, "plate": 0.05, "connector": 0.4, "gap": 0.3, "shoulder": 0.05},
    "FDM": {"hole": 0.6, "plate": 0.2, "connector": 0.8, "gap": 0.5, "shoulder": 0.2},
}


def printability(s: Spec, lay: Layout, printer: str,
                 thresholds: dict[str, float] | None = None) -> list[str]:
    """Warnings for features likely too small to print on ``printer``."""
    t = thresholds or DEFAULT_THRESHOLDS.get(printer, DEFAULT_THRESHOLDS["RESIN"])
    name = "resin" if printer == "RESIN" else "FDM"
    out = []
    if not lay.summary:
        return out
    if s.fastening == PRINTED:
        if s.spike_shank < t["connector"]:
            out.append(f"Printed spike shanks ({s.spike_shank:.2f} mm) are thinner than "
                       f"{t['connector']:.2f} mm and may not print on {name}.")
        if min(s.spike_head, s.spike_overhang) < t["shoulder"]:
            out.append(f"Printed spike heads ({s.spike_head:.2f} mm thick, "
                       f"{s.spike_overhang:.2f} mm overhang) are under {t['shoulder']:.2f} mm "
                       f"and may not print on {name}.")
        if printer == "FDM" and s.scale_n > 48:
            out.append("Printed spikes are too fine for FDM below O scale; "
                       "use spike holes or a resin printer.")
    elif s.hole_diameter < t["hole"]:
        out.append(f"Spike holes ({s.hole_diameter:.2f} mm) are smaller than {t['hole']:.2f} mm, "
                   f"the smallest hole a {name} printer is set to print.")
    wc, hc = lay.summary["connector_width"], lay.summary["connector_height"]
    if min(wc, hc) < t["connector"]:
        out.append(f"Connectors ({wc:.2f} x {hc:.2f} mm) are thinner than {t['connector']:.2f} mm "
                   f"and may not print on {name}.")
    if lay.summary["gap"] < t["gap"]:
        out.append(f"The gap between ties ({lay.summary['gap']:.2f} mm) is under "
                   f"{t['gap']:.2f} mm and may fill in on {name}.")
    if s.plates:
        tp = s.model(s.plate_thickness)
        if tp < t["plate"]:
            out.append(f"Tie plates ({tp:.3f} mm thick) are thinner than {t['plate']:.2f} mm "
                       f"and may not show on {name}.")
        if s.shoulders != SHOULDERS_NONE:
            hs, ws = s.model(s.shoulder_height), s.model(s.shoulder_width)
            if min(hs, ws) < t["shoulder"]:
                out.append(f"Plate shoulders ({hs:.3f} mm high) are under {t['shoulder']:.2f} mm "
                           f"and may not print on {name}.")
    return out


def grain_warning(top_cut: float, tie_height: float, preset: str, limit_pct: float) -> str:
    """The grain-too-deep warning, or "" when the cut is within the limit."""
    if tie_height <= 0:
        return ""
    pct = 100.0 * top_cut / tie_height
    if pct <= limit_pct:
        return ""
    return (f'Grain on "{preset}" cuts {top_cut:.2f} mm into a {tie_height:.2f} mm tie '
            f"({pct:.0f} %). To make it shallower, lower Depth or turn off Auto Detail in that "
            "Weathered Board preset, then regenerate.")
