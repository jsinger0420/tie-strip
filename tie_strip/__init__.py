"""Tie Strip Generator: 3D-printable model railroad tie strips.

Builds a strip of weathered ties (made by the Weathered Board add-on,
0.1.5 or later) joined by low connectors under the rails, with spike holes
and optional tie plates, scaled for a model railroad scale and exported
as an STL in millimetres.

The layout, shapes and plate presets (layout.py, meshgen.py, plates.py,
scales.py) are plain Python with no bpy, so they can be tested outside
Blender. Blender modules are only imported in ``register``.
"""

_modules = None


def _load():
    from . import build, operators, prefs, properties, ui  # noqa: F401
    return prefs, properties, operators, ui


def _classes():
    prefs, properties, operators, ui = _load()
    return (prefs.TIESTRIP_Preferences, properties.TIESTRIP_Settings) + operators.classes + ui.classes


def register():
    import bpy
    for cls in _classes():
        bpy.utils.register_class(cls)
    _load()[1].register()


def unregister():
    import bpy
    from . import wb_bridge
    _load()[1].unregister()
    for cls in reversed(_classes()):
        bpy.utils.unregister_class(cls)
    wb_bridge.clear_cache()
