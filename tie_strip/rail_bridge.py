"""Rail presets from the Model Rail Generator add-on (optional).

Model Rail Generator (1.1 or later, API version 1) publishes its public API
as ``sys.modules["model_rail_api"]`` while it is enabled. Tie Strip uses
only ``list_builtin_presets``, ``list_user_presets`` and ``get_preset``, and
copies the values it needs into its own settings, so a strip still builds
when the rail add-on is later disabled.

All values are model millimetres.
"""

from __future__ import annotations

import importlib
import sys

API_ALIAS = "model_rail_api"

# Tie Strip setting <- RailProfile field.
FIELDS = {
    "rail_foot": "base_width",
    "rail_head": "head_width",
    "rail_edge": "base_edge_thickness",
    "rail_foot_web": "base_thickness",
    "rail_web": "web_thickness",
}


def find_api():
    """Model Rail Generator's api module, or None when it isn't enabled or is incompatible."""
    api = sys.modules.get(API_ALIAS)
    if api is None:
        try:
            import bpy
            names = list(bpy.context.preferences.addons.keys())
        except (ImportError, AttributeError):
            names = []
        for name in names:
            if name == "model_rail_generator" or name.endswith(".model_rail_generator"):
                try:
                    api = importlib.import_module(name + ".api")
                except ImportError:
                    api = None
                break
    if api is None or tuple(getattr(api, "API_VERSION", (0,)))[0] != 1:
        return None
    return api


def available() -> bool:
    """True when rail presets can be read."""
    return find_api() is not None


def preset_names() -> tuple[list[str], list[str]]:
    """(built-in preset names, your saved preset names); both empty without the add-on."""
    api = find_api()
    if api is None:
        return [], []
    try:
        return list(api.list_builtin_presets()), list(api.list_user_presets())
    except Exception:  # a broken preset file must not break the panel
        return [], []


def is_builtin(name: str) -> bool:
    """True when ``name`` is one of Model Rail Generator's built-in (typical-size) presets."""
    api = find_api()
    try:
        return bool(api and api.is_builtin_preset(name))
    except Exception:
        return False


def preset_values(name: str) -> dict[str, float]:
    """The rail preset's sizes, keyed by Tie Strip setting. Raises KeyError if not found."""
    api = find_api()
    if api is None:
        raise KeyError("Model Rail Generator isn't enabled.")
    profile = api.get_preset(name)
    return {key: float(getattr(profile, field)) for key, field in FIELDS.items()}
