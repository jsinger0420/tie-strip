"""Finding Weathered Board's public API, and building and caching boards.

Weathered Board (0.1.5 or later) provides ``api.build_board``. Blender
extensions can't declare dependencies on each other, so the add-on is
found at runtime among the enabled add-ons.

Boards are simplified (Blender's Decimate, collapse) to about
``max_triangles`` each and cached, so changing spacing, count, strip type,
holes or plates rebuilds quickly. The cache key includes the preset's
current values, so editing a Weathered Board preset is picked up.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass

import bpy
import numpy as np

MIN_VERSION_TEXT = "Weathered Board 0.1.5 or later"


class BridgeError(RuntimeError):
    """Weathered Board is missing, too old, or couldn't build a board."""


@dataclass(frozen=True)
class Board:
    """One simplified board, as Weathered Board orients it (length on X)."""

    vertices: np.ndarray
    triangles: np.ndarray
    face_depth: dict


def find_api():
    """Weathered Board's api module. Raises BridgeError with a fix if it can't."""
    for name in bpy.context.preferences.addons.keys():
        if name == "weathered_board" or name.endswith(".weathered_board"):
            try:
                api = importlib.import_module(name + ".api")
            except ImportError:
                raise BridgeError(f"Weathered Board is enabled but too old. Install "
                                  f"{MIN_VERSION_TEXT}.") from None
            if tuple(getattr(api, "API_VERSION", (0, 0)))[0] != 1:
                raise BridgeError("This Weathered Board's API version isn't supported. "
                                  "Update Tie Strip Generator.")
            return api
    raise BridgeError(f"Weathered Board isn't enabled. Install and enable {MIN_VERSION_TEXT}.")


def available() -> str:
    """"" if Weathered Board can be used, otherwise why not."""
    try:
        find_api()
    except BridgeError as err:
        return str(err)
    return ""


def preset_names() -> list[tuple[str, str]]:
    """(name, description) for every Weathered Board preset, or [] if unavailable."""
    try:
        return [(p.name, p.description) for p in find_api().list_presets()]
    except BridgeError:
        return []


MM_PER_INCH = 25.4


def board_size(preset: str) -> tuple[tuple[float, float, float], str, str]:
    """A Weathered Board preset's full-size (length, width, thickness).

    Returns (sizes in full-size mm, the preset's own units "IN" or "MM",
    error). On error the sizes are zeros and the error says what to do.
    """
    if not preset:
        return (0.0, 0.0, 0.0), "IN", "Choose a Weathered Board preset for the ties."
    try:
        api = find_api()
        v = api.get_preset_values(preset)
    except BridgeError as err:
        return (0.0, 0.0, 0.0), "IN", str(err)
    except Exception as err:  # api.BoardError: preset deleted or unreadable
        return (0.0, 0.0, 0.0), "IN", f'Weathered Board preset "{preset}": {err}'
    units = v.get("units", "IN")
    k = MM_PER_INCH if units == "IN" else 1.0
    return (float(v["length"]) * k, float(v["width"]) * k, float(v["thickness"]) * k), units, ""


_cache: dict[tuple, Board] = {}
CACHE_LIMIT = 400


def clear_cache() -> None:
    _cache.clear()


def get_board(api, preset: str, length_mm: float, width_mm: float, thickness_mm: float,
              scale: float, printer: str, seed: int, max_triangles: int) -> Board:
    """One board, simplified, from the cache or freshly built."""
    try:
        look = json.dumps(api.get_preset_values(preset), sort_keys=True, default=str)
    except api.BoardError as err:
        raise BridgeError(str(err)) from None
    key = (look, round(length_mm, 6), round(width_mm, 6), round(thickness_mm, 6),
           round(scale, 6), printer, int(seed), int(max_triangles))
    board = _cache.get(key)
    if board is not None:
        return board
    try:
        mesh = api.build_board(preset=preset, length_mm=length_mm, width_mm=width_mm,
                               thickness_mm=thickness_mm, scale=scale, printer=printer,
                               seed=seed, weather_bottom=False)
    except api.BoardError as err:
        raise BridgeError(f'Weathered Board preset "{preset}": {err}') from None
    verts, tris = decimate(np.asarray(mesh.vertices), np.asarray(mesh.triangles), max_triangles)
    board = Board(verts, tris, dict(mesh.face_depth))
    if len(_cache) >= CACHE_LIMIT:
        _cache.clear()
    _cache[key] = board
    return board


def mesh_from_arrays(name: str, verts: np.ndarray, tris: np.ndarray) -> bpy.types.Mesh:
    """A new Blender mesh from vertex and triangle arrays."""
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(len(tris) * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(len(tris))
    mesh.polygons.foreach_set("loop_start", np.arange(0, len(tris) * 3, 3, dtype=np.int32))
    mesh.update()
    mesh.validate()
    return mesh


def arrays_from_mesh(mesh: bpy.types.Mesh) -> tuple[np.ndarray, np.ndarray]:
    """Vertex and triangle arrays from a Blender mesh."""
    mesh.calc_loop_triangles()
    verts = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", verts)
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", tris)
    return verts.reshape(-1, 3).astype(np.float64), tris.reshape(-1, 3)


def decimate(verts: np.ndarray, tris: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    """Simplify a mesh to about ``target`` triangles with Blender's Decimate (collapse)."""
    if len(tris) <= target:
        return verts, tris
    mesh = mesh_from_arrays("_tie_strip_decimate", verts, tris)
    obj = bpy.data.objects.new("_tie_strip_decimate", mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        mod = obj.modifiers.new("Decimate", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.use_collapse_triangulate = True
        mod.ratio = target / len(tris)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        result = evaluated.to_mesh()
        out = arrays_from_mesh(result)
        evaluated.to_mesh_clear()
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)
    return out
