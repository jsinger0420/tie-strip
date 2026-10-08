"""Operators: the buttons in the Tie Strip panel. Each docstring is its tooltip."""

import os

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper

from . import build, plates, preset_store, wb_bridge
from .preset_store import PresetError


def _settings(context):
    """The scene's Tie Strip settings."""
    return context.scene.tie_strip


_busy = False


def is_busy() -> bool:
    """True while a strip is being generated (the panel shows a wait message)."""
    return _busy


def _redraw(context):
    """Ask every area on the screen to redraw, so the panel shows the busy state."""
    screen = context.screen
    if screen:
        for area in screen.areas:
            area.tag_redraw()


class TIESTRIP_OT_generate(bpy.types.Operator):
    """Build the tie strip from these settings, replacing the previous one"""

    bl_idname = "tie_strip.generate"
    bl_label = "Generate Tie Strip"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None

    def _run(self, context, progress=None):
        """Build the strip and report errors, warnings and the summary line."""
        try:
            result = build.generate(context, progress)
        except (build.BuildError, wb_bridge.BridgeError) as err:
            for line in str(err).splitlines():
                self.report({"ERROR"}, line)
            _settings(context).last_report = str(err).splitlines()[0]
            return {"CANCELLED"}
        for w in result.warnings:
            self.report({"WARNING"}, w)
        self.report({"INFO"}, _settings(context).last_report)
        return {"FINISHED"}

    def execute(self, context):
        """Build straight away, with no wait message (scripts and the redo panel)."""
        return self._run(context)

    def invoke(self, context, event):
        """Show the wait message and busy cursor first, then build on the next timer tick.

        Blender doesn't redraw while an operator runs, so the build waits one
        tick to let the panel show "please wait".
        """
        global _busy
        if _busy:
            return {"CANCELLED"}
        _busy = True
        wm = context.window_manager
        context.window.cursor_modal_set("WAIT")
        if context.workspace:
            context.workspace.status_text_set("Generating tie strip, please wait...")
        _redraw(context)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """On the first timer tick, build with a progress bar, then restore the cursor."""
        global _busy
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}  # ignore clicks and keys until the build is done
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_begin(0, 1)
        try:
            return self._run(context, lambda done, total: wm.progress_update(done / total))
        finally:
            wm.progress_end()
            context.window.cursor_modal_restore()
            if context.workspace:
                context.workspace.status_text_set(None)
            _busy = False
            _redraw(context)


class TIESTRIP_OT_new_seed(bpy.types.Operator):
    """Pick a new random seed for a different-looking strip"""

    bl_idname = "tie_strip.new_seed"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Set a random seed."""
        import random
        _settings(context).seed = random.randrange(1, 2**31 - 1)
        return {"FINISHED"}


class TIESTRIP_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the generated tie strip as an STL file in millimetres, ready for a slicer"""

    bl_idname = "tie_strip.export_stl"
    bl_label = "Export STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        """Only available once a strip has been generated."""
        return bpy.data.objects.get(build.RESULT_NAME) is not None

    def invoke(self, context, event):
        """Open the file browser on the default file name, next to the .blend file."""
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(folder, build.file_name(_settings(context)))
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        """Write the strip to the chosen file."""
        obj = bpy.data.objects.get(build.RESULT_NAME)
        try:
            build.export_stl(context, obj, self.filepath)
        except RuntimeError as err:
            self.report({"ERROR"}, f"Export failed: {err}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {os.path.basename(self.filepath)}")
        return {"FINISHED"}


class TIESTRIP_OT_set_board_preset(bpy.types.Operator):
    """Use this Weathered Board preset for the ties"""

    bl_idname = "tie_strip.set_board_preset"
    bl_label = "Board Preset"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    name: StringProperty()

    def execute(self, context):
        """Store the chosen preset name in the settings."""
        _settings(context).board_preset = self.name
        return {"FINISHED"}


# ---- tie plate presets ----

class TIESTRIP_OT_apply_plate_preset(bpy.types.Operator):
    """Fill in every tie plate setting from this preset"""

    bl_idname = "tie_strip.apply_plate_preset"
    bl_label = "Apply Plate Preset"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    name: StringProperty()

    @classmethod
    def description(cls, context, properties):
        """Tooltip: the built-in preset's description, or a generic one for a saved preset."""
        preset = plates.get_builtin(properties.name)
        return preset.description if preset else f"Apply your saved plate preset '{properties.name}'"

    def execute(self, context):
        """Load the built-in or saved preset's values into the settings."""
        preset = plates.get_builtin(self.name)
        try:
            values = dict(preset.values) if preset else preset_store.load(preset_store.PLATE, self.name)
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        _settings(context).apply_plate_values(values, self.name)
        return {"FINISHED"}


class TIESTRIP_OT_save_plate_preset(bpy.types.Operator):
    """Save the current tie plate settings as a preset of your own"""

    bl_idname = "tie_strip.save_plate_preset"
    bl_label = "Save Plate Preset"
    name: StringProperty(name="Name", description="Saving under an existing name replaces it")

    def invoke(self, context, event):
        """Ask for a name, suggesting the current saved preset (not a built-in one)."""
        current = _settings(context).plate_preset
        self.name = "" if plates.is_builtin(current) else current
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Save the plate settings under the name, refusing built-in names."""
        name = preset_store.clean_name(self.name)
        if not name:
            self.report({"ERROR"}, "Give the preset a name.")
            return {"CANCELLED"}
        if plates.is_builtin(name):
            self.report({"ERROR"}, f"'{name}' is a built-in preset. Pick another name.")
            return {"CANCELLED"}
        s = _settings(context)
        try:
            preset_store.save(preset_store.PLATE, name, s.plate_values())
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s.plate_preset, s.plate_modified = name, False
        self.report({"INFO"}, f"Saved plate preset '{name}'.")
        return {"FINISHED"}


class TIESTRIP_OT_remove_plate_preset(bpy.types.Operator):
    """Delete one of your saved plate presets"""

    bl_idname = "tie_strip.remove_plate_preset"
    bl_label = "Delete Plate Preset"
    bl_options = {"INTERNAL"}
    name: StringProperty()

    def invoke(self, context, event):
        """Ask before deleting."""
        return context.window_manager.invoke_confirm(
            self, event, title=f"Delete plate preset '{self.name}'?", confirm_text="Delete")

    def execute(self, context):
        """Delete the preset file, and clear the panel's preset name if it was this one."""
        try:
            preset_store.remove(preset_store.PLATE, self.name)
        except (PresetError, OSError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s = _settings(context)
        if s.plate_preset == self.name:
            s.plate_preset = ""
        return {"FINISHED"}


# ---- strip presets ----

class TIESTRIP_OT_apply_strip_preset(bpy.types.Operator):
    """Fill in every setting from this saved strip preset"""

    bl_idname = "tie_strip.apply_strip_preset"
    bl_label = "Apply Strip Preset"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    name: StringProperty()

    def execute(self, context):
        """Load the saved preset's values into the settings."""
        try:
            values = preset_store.load(preset_store.STRIP, self.name)
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        _settings(context).apply_strip_values(values, self.name)
        return {"FINISHED"}


class TIESTRIP_OT_save_strip_preset(bpy.types.Operator):
    """Save every current setting as a strip preset, for example 'HO Code 83 branch line'"""

    bl_idname = "tie_strip.save_strip_preset"
    bl_label = "Save Strip Preset"
    name: StringProperty(name="Name", description="Saving under an existing name replaces it")

    def invoke(self, context, event):
        """Ask for a name, suggesting the current strip preset."""
        self.name = _settings(context).strip_preset
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Save every setting under the name."""
        name = preset_store.clean_name(self.name)
        if not name:
            self.report({"ERROR"}, "Give the preset a name.")
            return {"CANCELLED"}
        s = _settings(context)
        try:
            preset_store.save(preset_store.STRIP, name, s.strip_values())
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s.strip_preset, s.strip_modified = name, False
        self.report({"INFO"}, f"Saved strip preset '{name}'.")
        return {"FINISHED"}


class TIESTRIP_OT_remove_strip_preset(bpy.types.Operator):
    """Delete one of your saved strip presets"""

    bl_idname = "tie_strip.remove_strip_preset"
    bl_label = "Delete Strip Preset"
    bl_options = {"INTERNAL"}
    name: StringProperty()

    def invoke(self, context, event):
        """Ask before deleting."""
        return context.window_manager.invoke_confirm(
            self, event, title=f"Delete strip preset '{self.name}'?", confirm_text="Delete")

    def execute(self, context):
        """Delete the preset file, and clear the panel's preset name if it was this one."""
        try:
            preset_store.remove(preset_store.STRIP, self.name)
        except (PresetError, OSError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s = _settings(context)
        if s.strip_preset == self.name:
            s.strip_preset = ""
        return {"FINISHED"}


classes = (
    TIESTRIP_OT_generate, TIESTRIP_OT_new_seed, TIESTRIP_OT_export_stl,
    TIESTRIP_OT_set_board_preset,
    TIESTRIP_OT_apply_plate_preset, TIESTRIP_OT_save_plate_preset, TIESTRIP_OT_remove_plate_preset,
    TIESTRIP_OT_apply_strip_preset, TIESTRIP_OT_save_strip_preset, TIESTRIP_OT_remove_strip_preset,
)
