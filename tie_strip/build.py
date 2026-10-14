"""Building the tie strip object and exporting it.

1. Lay out the strip (layout.py) and stop on any error.
2. Build the boards with Weathered Board: one per tie, or a pool for long
   strips, each simplified and cached (wb_bridge.py).
3. Re-run the layout with the boards' real grain depth, which sets the
   connector overlap and the rail seat fill.
4. Place the ties (turned, offset, angled) and make the connectors,
   rail seat pads, tie plates, shoulders, and either hole cutters or
   printed spikes. For a curved strip, each tie and its parts are then
   turned onto the curve as one rigid piece, and the connectors (cut into
   short slices) are bent to follow the rails.
5. Join everything with Boolean modifiers (Manifold solver, falling back
   to Exact), then cut any spike holes.
6. Clean up and check the result is watertight.
7. Place the new strip at the 3D cursor and select it.
8. With Include Rail on, lay two rail objects on the rail seats (rail.py),
   parented to the strip, for fit checks and renders. A rail problem is
   reported as a warning and the strip is still built.

Like Weathered Board's Add button, every Generate adds a new strip to the
active collection and leaves earlier strips alone, and uses a new random
seed unless Lock Seed is on. The seed used is written back to the panel,
so locking it repeats the last strip.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field

import bmesh
import bpy
import numpy as np

from . import layout, meshgen, prefs, rail, wb_bridge

RESULT_NAME = "TieStrip"  # new strips are named this; Blender adds .001, .002...
TAG = "tie_strip"  # custom property marking an object as a generated strip
RAIL_TAG = "tie_strip_rail"  # custom property marking a rail laid on a strip ("L" or "R")
RAIL_MATERIAL = "Tie Strip Rail"
SETTINGS_KEY = "tie_strip_settings"  # the settings the strip was built with, as JSON
SEED_LIMIT = 2**31


class BuildError(RuntimeError):
    """The strip can't be built; the message says why and how to fix it."""


@dataclass
class BuildResult:
    """The built strip object, warnings to show, and build statistics for the report."""

    obj: bpy.types.Object
    warnings: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)


def set_scene_millimetres(scene) -> None:
    """1 Blender unit = 1 mm, so the STL comes out in millimetres."""
    us = scene.unit_settings
    us.system = "METRIC"
    us.length_unit = "MILLIMETERS"
    us.scale_length = 0.001


def is_strip(obj) -> bool:
    """True when ``obj`` is a tie strip made by Generate."""
    return obj is not None and obj.type == "MESH" and bool(obj.get(TAG))


def is_rail(obj) -> bool:
    """True when ``obj`` is a rail laid on a tie strip by Include Rail."""
    return obj is not None and obj.type == "MESH" and bool(obj.get(RAIL_TAG))


def rails_of(strip) -> list:
    """The rail objects on ``strip`` (left rail first), if any."""
    return sorted((o for o in strip.children if is_rail(o)), key=lambda o: str(o.get(RAIL_TAG)))


def selected_strips(context, include_rail_parents: bool = False) -> list:
    """The selected tie strips, in selection order, each once.

    With ``include_rail_parents`` a selected rail counts as selecting the
    strip it sits on.
    """
    out = []
    for o in context.selected_objects:
        if include_rail_parents and is_rail(o) and is_strip(o.parent):
            o = o.parent
        if is_strip(o) and o not in out:
            out.append(o)
    return out


def export_objects(strip, what: str) -> list:
    """What to export for ``strip``: "BOTH" (strip and rail), "STRIP" or "RAIL"."""
    if what == "STRIP":
        return [strip]
    rails = rails_of(strip)
    return rails if what == "RAIL" else [strip] + rails


def _new_object(name, verts, tris, coll) -> bpy.types.Object:
    """A new mesh object from vertex and triangle arrays, linked to ``coll``."""
    obj = bpy.data.objects.new(name, wb_bridge.mesh_from_arrays(name, verts, tris))
    coll.objects.link(obj)
    return obj


def _boolean(base, adds, cutters, solver) -> tuple[np.ndarray, np.ndarray]:
    """Union ``adds`` into ``base``, subtract ``cutters``; return the result arrays."""
    base.modifiers.clear()
    for op, objs in (("UNION", adds), ("DIFFERENCE", cutters)):
        for obj in objs:
            mod = base.modifiers.new(f"{op.title()} {obj.name}", "BOOLEAN")
            mod.operation = op
            mod.operand_type = "OBJECT"
            mod.object = obj
            mod.solver = solver
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluated = base.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        verts, tris = wb_bridge.arrays_from_mesh(mesh)
    finally:
        evaluated.to_mesh_clear()
    base.modifiers.clear()
    return verts, tris


def _clean(mesh: bpy.types.Mesh) -> int:
    """Merge duplicate points, fix normals, drop loose bits. Returns open-edge count."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        open_edges = sum(1 for e in bm.edges if not e.is_manifold)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return open_edges


def _rail_material() -> bpy.types.Material:
    """The shared steel-grey material for rail objects, made on first use."""
    mat = bpy.data.materials.get(RAIL_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(RAIL_MATERIAL)
        mat.diffuse_color = (0.35, 0.33, 0.32, 1.0)
        mat.metallic, mat.roughness = 0.9, 0.45
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.35, 0.33, 0.32, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.9
            bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def add_rails(s, spec, lay, strip, coll) -> tuple[list, str]:
    """Lay two rail objects on ``strip``'s rail seats and parent them to it.

    Built in the strip's own coordinates (the strip was built at the
    origin), so with the strip as parent they sit on it wherever it is
    moved. Returns (rail objects, warning text or "").
    """
    shape, err = s.rail_shape()
    if shape is None:
        return [], f"Rail not added: {err}"
    seat = lay.tie_height + (spec.model(spec.plate_thickness) if spec.plates else 0.0)
    try:
        rails = rail.place(shape, lay.tie_x, lay.tie_width, lay.rail_y, seat,
                           s.rail_overhang_value(), lay.curve_radius, lay.summary["spacing"])
    except ValueError as e:
        return [], f"Rail not added: {e}"
    mat = _rail_material()
    objs = []
    for side, verts, tris, length in rails:
        name = f"{strip.name} Rail {side}"
        obj = _new_object(name, verts, tris, coll)
        obj.data.materials.append(mat)
        obj.parent = strip
        obj[RAIL_TAG] = side
        obj["rail_length_mm"] = round(length, 3)
        objs.append(obj)
    return objs, ""


def generate(context, progress=None) -> BuildResult:
    """Build the strip from the scene's Tie Strip settings.

    ``progress(done, total)``, if given, is called as each board is ready.
    """
    started = time.perf_counter()
    scene = context.scene
    s = scene.tie_strip
    api = wb_bridge.find_api()

    lay = layout.compute(s.to_spec())
    if not lay.ok:
        raise BuildError("\n".join(lay.errors))
    spec = s.to_spec()
    n = spec.tie_count
    seed = s.seed if s.lock_seed else random.randrange(1, SEED_LIMIT)
    rng = random.Random(seed)

    # ---- choose a board for every tie ----
    unique = n <= s.pool_threshold
    count = n if unique else min(s.pool_size, n)
    lj = spec.length_jitter
    lengths = [spec.tie_length + rng.uniform(-lj, lj) for _ in range(count)]
    boards = []
    for j in range(count):
        boards.append(wb_bridge.get_board(
            api, s.board_preset, lengths[j], spec.tie_width, spec.tie_height,
            spec.scale_n, s.printer, (seed + j) % SEED_LIMIT, s.max_triangles))
        if progress:
            progress(j + 1, count + 1)
    if unique:
        choice = list(range(n))
    else:
        choice, prev = [], -1
        for _ in range(n):
            j = rng.randrange(count)
            if j == prev:
                j = (j + 1 + rng.randrange(count - 1)) % count
            choice.append(j)
            prev = j
    ej = spec.model(spec.end_jitter)
    turns = [s.random_turn and rng.random() < 0.5 for _ in range(n)]
    offsets = [rng.uniform(-ej, ej) for _ in range(n)]
    yaws = [rng.uniform(-s.yaw_jitter, s.yaw_jitter) for _ in range(n)]

    # ---- re-lay with the real grain depth ----
    top_cut = max(b.face_depth.get("top", 0.0) for b in boards)
    side_cut = max(max(b.face_depth.get("front", 0.0), b.face_depth.get("back", 0.0))
                   for b in boards)
    spec = s.to_spec(connector_overlap=side_cut + 0.2,
                     seat_depth=top_cut if s.seat_pad else 0.0,
                     seat_inset=side_cut + 0.1)
    lay = layout.compute(spec)
    if not lay.ok:
        raise BuildError("\n".join(lay.errors))

    # ---- meshes ----
    ties = meshgen.combine(*[
        (meshgen.place_board(boards[choice[i]].vertices, lay.tie_height, x, offsets[i],
                             turns[i], yaws[i]), boards[choice[i]].triangles)
        for i, x in enumerate(lay.tie_x)
    ])
    parts = [("RailSeats", meshgen.boxes(lay.seats)),
             ("TiePlates", meshgen.boxes(lay.plates)),
             ("Shoulders", meshgen.boxes(lay.shoulders)),
             ("Spikes", meshgen.spikes(lay.spikes))]
    holes = meshgen.cylinders(lay.holes)
    if lay.curve_radius > 0:
        # Ties and everything standing on them move rigidly onto the curve;
        # connectors are sliced and bent so they follow the rails.
        r = lay.curve_radius
        ties = (meshgen.curve_map(ties[0], r, lay.tie_x), ties[1])
        parts = [(name, (meshgen.curve_map(v, r, lay.tie_x), t)) for name, (v, t) in parts]
        holes = (meshgen.curve_map(holes[0], r, lay.tie_x), holes[1])
        inner = r - lay.rail_y - lay.summary["connector_width"] / 2  # tightest connector edge
        cv, ct = meshgen.bars(lay.connectors, meshgen.bend_step(inner))
        connectors = (meshgen.curve_map(cv, r), ct)
    else:
        connectors = meshgen.boxes(lay.connectors)
    parts.insert(0, ("Connectors", connectors))

    set_scene_millimetres(scene)
    coll = context.collection or scene.collection
    # Everything is built at the origin, so the Boolean operands line up;
    # the finished strip is moved to the 3D cursor at the end.
    base = _new_object(RESULT_NAME, *ties, coll)
    adds = [_new_object(f"_ts_{name}", *arrays, coll) for name, arrays in parts if len(arrays[0])]
    cutters = [_new_object("_ts_Holes", *holes, coll)] if len(holes[0]) else []
    for helper in adds + cutters:
        helper.hide_render = True
        helper.display_type = "WIRE"

    # Manifold needs closed inputs; the boxes and cutters always are.
    solver = "MANIFOLD" if meshgen.open_edges(ties[1]) == 0 else "EXACT"
    try:
        verts, tris = _boolean(base, adds, cutters, solver)
        if solver == "MANIFOLD" and (len(tris) == 0 or meshgen.open_edges(tris) > 0):
            solver = "EXACT"
            verts, tris = _boolean(base, adds, cutters, solver)
    finally:
        for helper in adds + cutters:
            mesh = helper.data
            bpy.data.objects.remove(helper)
            bpy.data.meshes.remove(mesh)

    old = base.data
    base.data = wb_bridge.mesh_from_arrays(RESULT_NAME, verts, tris)
    bpy.data.meshes.remove(old)
    open_edges = _clean(base.data)

    # ---- report ----
    warnings = list(lay.warnings)
    p = prefs.get(context)
    limit = p.grain_limit if p else 20.0
    grain = layout.grain_warning(top_cut, lay.tie_height, s.board_preset, limit)
    if grain:
        warnings.append(grain)
    thresholds = p.thresholds(s.printer) if p else None
    warnings += layout.printability(spec, lay, s.printer, thresholds)
    if open_edges:
        warnings.append(f"The strip has {open_edges} open edges and may not slice cleanly.")
    info = {
        "triangles": len(base.data.polygons), "open_edges": open_edges, "solver": solver,
        "seconds": time.perf_counter() - started, "top_cut": top_cut, "side_cut": side_cut,
        "boards": count,
    }
    if s.seed != seed:
        from .properties import quiet
        with quiet():  # record the seed used without marking a strip preset modified
            s.seed = seed
    s.last_report = (f"{base.name} (seed {seed}): {n} ties, {info['triangles']:,} triangles, "
                     f"{info['seconds']:.1f} s. Grain: top {top_cut:.2f} mm, sides {side_cut:.2f} mm.")
    base[TAG] = True
    base[SETTINGS_KEY] = json.dumps(s.strip_values(), default=str)
    if s.rail_on:
        rails, rail_warning = add_rails(s, spec, lay, base, coll)
        if rail_warning:
            warnings.append(rail_warning)
        info["rails"] = len(rails)
        if rails:
            s.last_report += " Rail added."
    base.location = scene.cursor.location.copy()
    # As in Weathered Board: select the new strip and make it active,
    # without touching earlier strips or the rest of the selection.
    base.select_set(True)
    context.view_layer.objects.active = base
    return BuildResult(base, warnings, info)


def file_name(s) -> str:
    """The default STL file name from the settings' template."""
    from .scales import scale_label
    kind = {"STRAIGHT": "straight", "FLEX": "flex", "CURVED": "curved"}.get(s.strip_type, "strip")
    name = s.export_template.format(scale=scale_label(s.scale, s.scale_custom), type=kind,
                                    n=s.ties())
    return name if name.lower().endswith(".stl") else name + ".stl"


def export_stl(context, objects, path: str) -> None:
    """Write exactly ``objects`` to one STL file in millimetres, restoring the selection after."""
    before = list(context.selected_objects)
    active = context.view_layer.objects.active
    for o in before:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    try:
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                              use_scene_unit=False, ascii_format=False, apply_modifiers=True)
    finally:
        for o in objects:
            o.select_set(False)
        for o in before:
            o.select_set(True)
        context.view_layer.objects.active = active
