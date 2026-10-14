"""Rail laid on the strip, for fit checks and renders. Pure Python and numpy, no bpy.

Each strip can get two rail objects sitting on the rail seats (the tie top,
or the tie plate top when plates are on). They are separate from the
strip, so the strip STL is unchanged.

The cross-section is the same flat-bottom (Vignoles) shape that Model Rail
Generator draws, built from the rail sizes in the Tie Strip settings:
foot width, head width, foot edge thickness and rail height, plus head
depth, foot thickness at the web, web width and head corner radius when a
rail preset filled them in. With typed-in sizes the missing ones use Model
Rail Generator's typical proportions of rail height, and the foot is drawn
flat (foot thickness at the web = edge thickness), as the printed spike
layout assumes. Because the sizes are copied into Tie Strip's settings,
rail still builds when Model Rail Generator is later disabled.

Positions follow layout.py: X along the track, Y across it (+Y is the left
rail), Z up, model millimetres. Each rail runs from the outer face of the
first tie to the outer face of the last, plus ``overhang`` at each end
(negative stops it short). On a curved strip the rail is laid out straight
in slices short enough to follow the arc, then bent onto it with
``meshgen.curve_map``, so it lies exactly on the rail seats of the rigid,
radial ties.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Typical proportions of rail height, as Model Rail Generator's profile_from_code.
HEAD_DEPTH = 0.30
WEB = 0.20
EDGE = 0.08
CORNER_SEGMENTS = 3


@dataclass
class RailShape:
    """A rail cross-section, all model mm.

    ``foot`` is the foot (base) width, ``head`` the head width, ``height``
    the overall rail height, ``head_depth`` the depth of the head, ``web``
    the web thickness, ``foot_edge`` and ``foot_web`` the foot thickness at
    its outer edge and at the web, and ``corner`` the radius of the head's
    top corners (0 = square).
    """

    foot: float
    head: float
    height: float
    head_depth: float
    web: float
    foot_edge: float
    foot_web: float
    corner: float = 0.0


def shape_from_sizes(foot: float, head: float, height: float, foot_edge: float = 0.0,
                     foot_web: float = 0.0, web: float = 0.0, head_depth: float = 0.0,
                     corner: float = 0.0) -> tuple[RailShape | None, str]:
    """The rail shape from the settings' rail sizes, or (None, why it can't be drawn).

    Zero for any of ``foot_edge``, ``foot_web``, ``web`` or ``head_depth``
    means "not known": it is filled from typical proportions of the height
    (a typed-in rail's foot is drawn flat). Foot width, head width and
    height must be given.
    """
    if foot <= 0 or head <= 0:
        return None, "Enter the rail foot and head widths in Scale and Track."
    if height <= 0:
        return None, ("Enter the rail height in Scale and Track (or pick a rail preset); "
                      "it's needed to draw the rail.")
    te = foot_edge if foot_edge > 0 else EDGE * height
    tw = foot_web if foot_web > 0 else te
    hd = head_depth if head_depth > 0 else HEAD_DEPTH * height
    w = web if web > 0 else min(WEB * height, 0.5 * head, 0.5 * foot)
    if tw < te:
        tw = te
    if w >= head or w > foot:
        return None, "The rail web must be thinner than the rail head and foot."
    if hd + tw >= height:
        return None, (f"The rail is too short ({height:.2f} mm) for its head and foot; "
                      "check the rail height.")
    r = max(0.0, corner)
    if r >= min(head / 2, hd):
        r = 0.0
    return RailShape(foot, head, height, hd, w, te, tw, r), ""


def outline(shape: RailShape) -> list[tuple[float, float]]:
    """The cross-section as counter-clockwise (across, up) points, model mm.

    Across is 0 at the rail centreline; up is 0 at the bottom of the foot.
    The same outline as Model Rail Generator's RailProfile.outline with no cant.
    """
    s = shape
    right = [(s.foot / 2, 0.0), (s.foot / 2, s.foot_edge), (s.web / 2, s.foot_web),
             (s.web / 2, s.height - s.head_depth), (s.head / 2, s.height - s.head_depth)]
    if s.corner > 0:
        cx, cz = s.head / 2 - s.corner, s.height - s.corner
        for i in range(CORNER_SEGMENTS + 1):
            a = (math.pi / 2) * i / CORNER_SEGMENTS
            right.append((cx + s.corner * math.cos(a), cz + s.corner * math.sin(a)))
    else:
        right.append((s.head / 2, s.height))
    pts = right + [(-x, z) for x, z in reversed(right)]
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    return out


def _area(pts) -> float:
    """Signed area of a 2D polygon (positive = counter-clockwise)."""
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])) / 2


def triangulate(pts) -> list[tuple[int, int, int]]:
    """Counter-clockwise triangles filling a simple 2D polygon, by ear clipping.

    The rail outline is concave (an I shape), so a plain fan won't do.
    """
    idx = list(range(len(pts)))
    if _area(pts) < 0:
        idx.reverse()

    def cross(o, a, b):
        """Z of (a - o) x (b - o): positive when o, a, b turn left."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    tris = []
    while len(idx) > 3:
        for i in range(len(idx)):
            a, b, c = idx[i - 1], idx[i], idx[(i + 1) % len(idx)]
            pa, pb, pc = pts[a], pts[b], pts[c]
            if cross(pa, pb, pc) <= 1e-12:
                continue  # reflex or straight corner: not an ear
            if any(cross(pa, pb, pts[o]) >= -1e-12 and cross(pb, pc, pts[o]) >= -1e-12
                   and cross(pc, pa, pts[o]) >= -1e-12
                   for o in idx if o not in (a, b, c)):
                continue  # another corner lies inside
            tris.append((a, b, c))
            idx.pop(i)
            break
        else:
            raise ValueError("rail outline can't be triangulated")
    tris.append(tuple(idx))
    return tris


def ends(tie_x, tie_width: float, y: float, overhang: float,
         radius: float = 0.0) -> tuple[float, float]:
    """Where a rail at ``y`` starts and stops, as distances along the strip centreline (X).

    Flush with the outer faces of the end ties, plus ``overhang`` model mm
    at each end. On a curve the ties are rigid and point at the centre, so
    on a rail at radius r = radius - y a tie face is asin((Wt/2) / r) from
    its tie's centre line, and the overhang is measured along the rail.
    """
    first, last = min(tie_x), max(tie_x)
    if radius <= 0:
        d = tie_width / 2 + overhang
    else:
        r = radius - y
        d = radius * (math.asin(min(1.0, tie_width / 2 / r)) + overhang / r)
    return first - d, last + d


def length(x0: float, x1: float, y: float, radius: float = 0.0) -> float:
    """Length of a rail from ``x0`` to ``x1`` (centreline X) at ``y``, measured along the rail."""
    if radius <= 0:
        return x1 - x0
    return (x1 - x0) / radius * (radius - y)


def mesh(shape: RailShape, x0: float, x1: float, y: float, z: float,
         max_step: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """A closed rail from ``x0`` to ``x1`` along X, centred at ``y``, foot bottom at ``z``.

    Cut into equal slices no longer than ``max_step`` (one slice when
    None), so it can be bent onto a curve. Returns (vertices, triangles)
    as meshgen does, triangles facing outward.
    """
    yz = outline(shape)
    n = len(yz)
    k = 1 if not max_step else max(1, int(math.ceil((x1 - x0) / max_step - 1e-9)))
    xs = np.linspace(x0, x1, k + 1)
    verts = np.array([(x, y + a, z + b) for x in xs for a, b in yz], dtype=np.float64)
    tris = []
    for j in range(k):
        a0, a1 = j * n, (j + 1) * n
        for i in range(n):
            q = (i + 1) % n
            tris += [(a0 + i, a0 + q, a1 + q), (a0 + i, a1 + q, a1 + i)]
    cap = triangulate(yz)
    last = k * n
    tris += [(c, b, a) for a, b, c in cap]  # x0 end
    tris += [(last + a, last + b, last + c) for a, b, c in cap]  # x1 end
    t = np.array(tris, dtype=np.int32)
    a, b, c = verts[t[:, 0]], verts[t[:, 1]], verts[t[:, 2]]
    if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:
        t = t[:, ::-1].copy()
    return verts, t


def place(shape: RailShape, tie_x, tie_width: float, rail_y: float, seat_z: float,
          overhang: float = 0.0, radius: float = 0.0) -> list[tuple[str, np.ndarray, np.ndarray, float]]:
    """Both rails for a strip: [(side, vertices, triangles, length mm), ...], left rail first.

    ``rail_y`` is the rail centreline offset (layout.rail_y), ``seat_z`` the
    rail seat height, ``radius`` the curve radius (0 for straight and
    flexible strips). Raises ValueError when a negative overhang leaves no rail.
    """
    from . import meshgen
    out = []
    for side, y in (("L", rail_y), ("R", -rail_y)):
        x0, x1 = ends(tie_x, tie_width, y, overhang, radius)
        if x1 - x0 <= 0.01:
            raise ValueError("The end overhang is so far negative that no rail is left; "
                             "make it closer to 0.")
        step = None
        if radius > 0:
            step = meshgen.bend_step(radius - abs(y) - max(shape.foot, shape.head) / 2)
        v, t = mesh(shape, x0, x1, y, seat_z, step)
        if radius > 0:
            v = meshgen.curve_map(v, radius)
        out.append((side, v, t, length(x0, x1, y, radius)))
    return out
