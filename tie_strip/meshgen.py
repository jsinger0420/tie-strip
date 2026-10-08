"""Simple closed meshes as numpy arrays, and board placement. No bpy.

Every function returns (vertices (N, 3) float64, triangles (M, 3) int32),
triangles wound outward, every shape watertight.
"""

from __future__ import annotations

import math

import numpy as np

from .layout import Box, Hole

# Triangles of a box whose 8 corners are ordered
# (x0y0z0, x1y0z0, x1y1z0, x0y1z0, x0y0z1, x1y0z1, x1y1z1, x0y1z1).
_BOX_TRIS = np.array([
    (0, 2, 1), (0, 3, 2),  # bottom (-Z)
    (4, 5, 6), (4, 6, 7),  # top (+Z)
    (0, 1, 5), (0, 5, 4),  # -Y
    (2, 3, 7), (2, 7, 6),  # +Y
    (0, 4, 7), (0, 7, 3),  # -X
    (1, 2, 6), (1, 6, 5),  # +X
], dtype=np.int32)


def empty() -> tuple[np.ndarray, np.ndarray]:
    """A mesh with no vertices or triangles."""
    return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32)


def boxes(items: list[Box]) -> tuple[np.ndarray, np.ndarray]:
    """All boxes as one mesh of separate closed shells."""
    if not items:
        return empty()
    b = np.array([(i.x0, i.x1, i.y0, i.y1, i.z0, i.z1) for i in items], dtype=np.float64)
    x0, x1, y0, y1, z0, z1 = b.T
    corners = np.stack([
        np.stack([x0, y0, z0], 1), np.stack([x1, y0, z0], 1),
        np.stack([x1, y1, z0], 1), np.stack([x0, y1, z0], 1),
        np.stack([x0, y0, z1], 1), np.stack([x1, y0, z1], 1),
        np.stack([x1, y1, z1], 1), np.stack([x0, y1, z1], 1),
    ], axis=1)  # (k, 8, 3)
    verts = corners.reshape(-1, 3)
    tris = (_BOX_TRIS[None, :, :] + 8 * np.arange(len(items))[:, None, None]).reshape(-1, 3)
    return verts, tris.astype(np.int32)


def hole_segments(d: float) -> int:
    """Sides for a hole cutter: about one per 0.1 mm of circumference, 12 to 32."""
    return int(min(32, max(12, round(math.pi * d / 0.1))))


def cylinders(items: list[Hole], segments: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Vertical prisms for spike holes.

    The polygon is sized so the circle of diameter d fits inside it, so a
    spike of that diameter always passes through.
    """
    if not items:
        return empty()
    n = segments or hole_segments(min(h.d for h in items))
    ang = 2 * math.pi * np.arange(n) / n
    ring = np.stack([np.cos(ang), np.sin(ang)], 1) / math.cos(math.pi / n)
    side = []
    for a in range(n):
        b = (a + 1) % n
        side += [(a, b, n + b), (a, n + b, n + a)]
    cap_b = [(2 * n, b, a) for a, b in ((a, (a + 1) % n) for a in range(n))]
    cap_t = [(2 * n + 1, n + a, n + b) for a, b in ((a, (a + 1) % n) for a in range(n))]
    template = np.array(side + cap_b + cap_t, dtype=np.int32)
    vs, ts = [], []
    for k, h in enumerate(items):
        r = h.d / 2
        xy = np.array([h.x, h.y]) + r * ring
        bottom = np.column_stack([xy, np.full(n, h.z0)])
        top = np.column_stack([xy, np.full(n, h.z1)])
        centres = np.array([[h.x, h.y, h.z0], [h.x, h.y, h.z1]])
        vs.append(np.vstack([bottom, top, centres]))
        ts.append(template + k * (2 * n + 2))
    return np.vstack(vs), np.vstack(ts).astype(np.int32)


def combine(*parts: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Several meshes as one, keeping each shell separate."""
    vs, ts, offset = [], [], 0
    for v, t in parts:
        if len(v) == 0:
            continue
        vs.append(v)
        ts.append(t + offset)
        offset += len(v)
    if not vs:
        return empty()
    return np.vstack(vs), np.vstack(ts).astype(np.int32)


def place_board(verts: np.ndarray, tie_height: float, x: float, y_offset: float,
                turn: bool, yaw_deg: float) -> np.ndarray:
    """Move a Weathered Board board into its place on the strip.

    Boards come centred on the origin with length on X, width on Y and
    thickness on Z. The tie's length must run across the track (Y), so the
    board is turned 90 degrees about Z, optionally a further 180 degrees,
    given a small yaw, raised so its bottom is at Z = 0, and moved to its
    position along the track. No mirroring, so triangle winding is kept.
    """
    angle = math.radians(90.0 + (180.0 if turn else 0.0) + yaw_deg)
    c, s = math.cos(angle), math.sin(angle)
    out = np.empty_like(verts)
    out[:, 0] = c * verts[:, 0] - s * verts[:, 1] + x
    out[:, 1] = s * verts[:, 0] + c * verts[:, 1] + y_offset
    out[:, 2] = verts[:, 2] + tie_height / 2
    return out


def open_edges(triangles: np.ndarray) -> int:
    """Number of edges not shared by exactly two triangles in opposite directions."""
    if len(triangles) == 0:
        return 0
    t = triangles.astype(np.int64)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    n = int(e.max()) + 1
    fwd = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    fwd_u, fwd_c = np.unique(fwd, return_counts=True)
    bad = int(np.sum(fwd_c != 1))  # an edge used twice in the same direction
    missing = np.isin(rev, fwd_u, invert=True)  # an edge with no partner
    return bad + int(missing.sum())
