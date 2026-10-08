"""The Tie Strip tab in the 3D Viewport sidebar (N panel)."""

import bpy

from . import layout, operators, plates, preset_store, wb_bridge


def _s(context):
    """The scene's Tie Strip settings."""
    return context.scene.tie_strip


def _u(s):
    """Short label for the prototype units, for property labels: "in" or "mm"."""
    return "in" if s.proto_units == "IN" else "mm"


# ---- menus ----

class TIESTRIP_MT_board_presets(bpy.types.Menu):
    """Choose the Weathered Board preset that sets the ties' look and size"""

    bl_label = "Weathered Board Presets"
    bl_idname = "TIESTRIP_MT_board_presets"

    def draw(self, context):
        """One item per Weathered Board preset, or why there are none."""
        names = wb_bridge.preset_names()
        if not names:
            self.layout.label(text=wb_bridge.available() or "No presets found", icon="ERROR")
        for name, _desc in names:
            self.layout.operator("tie_strip.set_board_preset", text=name).name = name


class TIESTRIP_MT_plate_presets(bpy.types.Menu):
    """Built-in tie plate presets by era, then your saved ones"""

    bl_label = "Tie Plate Presets"
    bl_idname = "TIESTRIP_MT_plate_presets"

    def draw(self, context):
        """Built-in presets, then saved presets each with a delete button."""
        col = self.layout
        for p in plates.BUILTIN_PLATES:
            col.operator("tie_strip.apply_plate_preset", text=p.name).name = p.name
        saved = preset_store.saved_names(preset_store.PLATE)
        if saved:
            col.separator()
            for name in saved:
                row = col.row(align=True)
                row.operator("tie_strip.apply_plate_preset", text=name).name = name
                row.operator("tie_strip.remove_plate_preset", text="", icon="X").name = name


class TIESTRIP_MT_strip_presets(bpy.types.Menu):
    """Your saved strip presets"""

    bl_label = "Strip Presets"
    bl_idname = "TIESTRIP_MT_strip_presets"

    def draw(self, context):
        """Saved strip presets, each with a delete button."""
        saved = preset_store.saved_names(preset_store.STRIP)
        if not saved:
            self.layout.label(text="No strip presets saved yet")
        for name in saved:
            row = self.layout.row(align=True)
            row.operator("tie_strip.apply_strip_preset", text=name).name = name
            row.operator("tie_strip.remove_strip_preset", text="", icon="X").name = name


def _preset_row(layout, menu, label, current, modified, save_op):
    """A preset menu showing the current preset (marked if modified), plus a save button."""
    row = layout.row(align=True)
    text = (current or label) + (" (modified)" if current and modified else "")
    row.menu(menu, text=text)
    row.operator(save_op, text="", icon="ADD")


# ---- panels ----

class _Panel:
    """Shared placement: the Tie Strip tab in the 3D Viewport sidebar."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tie Strip"


class TIESTRIP_PT_main(_Panel, bpy.types.Panel):
    """Generate and export the tie strip, and check its printed size"""

    bl_label = "Tie Strip"

    def draw(self, context):
        """Presets, Generate and Export, then a live summary or the layout errors."""
        s = _s(context)
        col = self.layout.column()
        _preset_row(col, "TIESTRIP_MT_strip_presets", "Strip Presets", s.strip_preset,
                    s.strip_modified, "tie_strip.save_strip_preset")
        missing = wb_bridge.available()
        if missing:
            box = col.box()
            box.alert = True
            box.label(text=missing, icon="ERROR")
        row = col.row(align=True)
        row.scale_y = 1.4
        if operators.is_busy():
            row.alert = True
            row.label(text="Generating tie strip, please wait...", icon="SORTTIME")
        else:
            row.enabled = not missing
            row.operator("tie_strip.generate", icon="MESH_GRID")
        col.operator("tie_strip.export_stl", icon="EXPORT")
        if s.last_report:
            col.label(text=s.last_report)

        lay = layout.compute(s.to_spec())
        box = col.box()
        if lay.errors:
            box.alert = True
            for e in lay.errors:
                box.label(text=e, icon="ERROR")
            return
        m = lay.summary
        box.label(text="Model size", icon="INFO")
        box.label(text=f"Gap between ties {m['gap']:.2f} mm")
        box.label(text=f"Printed size {m['overall_length']:.1f} x {m['overall_width']:.1f} x "
                       f"{m['top']:.2f} mm ({len(lay.tie_x)} ties)")
        box.label(text=f"Rail centres at +/-{m['rail_centre']:.2f} mm")
        box.label(text=f"Outer hole edge at +/-{m['outer_hole']:.2f} mm")
        for w in lay.warnings:
            box.label(text=w, icon="ERROR")


class TIESTRIP_PT_track(_Panel, bpy.types.Panel):
    """Model scale, gauge and the rail measurements"""

    bl_label = "Scale and Track"
    bl_parent_id = "TIESTRIP_PT_main"

    def draw(self, context):
        """Scale (and custom ratio), then gauge and rail sizes in mm."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "scale")
        if s.scale == "CUSTOM":
            col.prop(s, "scale_custom")
        col.label(text="Measured on your rail (mm):")
        col.prop(s, "gauge", text="Gauge (mm)")
        col.prop(s, "rail_foot", text="Foot Width (mm)")
        col.prop(s, "rail_head", text="Head Width (mm)")


def _inches(v_mm: float) -> str:
    """Full-size mm as feet and inches when 12 in or more, e.g. 8' 6\"."""
    inches = v_mm / 25.4
    if inches >= 12:
        feet, rest = divmod(round(inches * 8) / 8, 12)
        return f"{int(feet)}' {rest:g}\"" if rest else f"{int(feet)}'"
    return f"{round(inches * 8) / 8:g}\""


class TIESTRIP_PT_ties(_Panel, bpy.types.Panel):
    """Tie preset, spacing, how many ties, printer and seed"""

    bl_label = "Ties"
    bl_parent_id = "TIESTRIP_PT_main"

    def draw(self, context):
        """Tie preset and its sizes, spacing, count or max length, printer and seed."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        col.label(text="Tie preset (from Weathered Board):")
        col.menu("TIESTRIP_MT_board_presets", text=s.board_preset or "Choose a tie preset",
                 icon="MESH_PLANE")
        (tl, tw, th), units, err = s.tie_size()
        box = col.box()
        if err:
            box.alert = True
            box.label(text=err, icon="ERROR")
        else:
            if units == "IN":
                box.label(text=f"{_inches(tl)} x {_inches(tw)} x {_inches(th)}  (L x W x H)")
            else:
                box.label(text=f"{tl:g} x {tw:g} x {th:g} mm  (L x W x H)")
            n = s.scale_n()
            box.label(text=f"Model: {tl / n:.2f} x {tw / n:.2f} x {th / n:.2f} mm")
        hint = col.column()
        hint.scale_y = 0.8
        hint.label(text="To change the tie size or look, edit and save", icon="INFO")
        hint.label(text="the preset in the Weathered Board panel.")
        col.separator()
        col.prop(s, "proto_units")
        col.prop(s, "tie_spacing", text=f"Spacing ({u})")
        col.prop(s, "size_mode", expand=True)
        if s.size_mode == "LENGTH":
            col.prop(s, "max_length", text="Max Length (mm)")
            n = s.ties()
            row = col.row()
            row.alert = n < 2
            row.label(text=f"{n} ties fit" if n >= 2 else "Not even 2 ties fit",
                      icon="INFO" if n >= 2 else "ERROR")
        else:
            col.prop(s, "tie_count")
        col.separator()
        col.prop(s, "printer", expand=True)
        row = col.row(align=True)
        row.prop(s, "seed")
        row.operator("tie_strip.new_seed", text="", icon="FILE_REFRESH")


class TIESTRIP_PT_strip(_Panel, bpy.types.Panel):
    """Straight or flexible strip, the connectors and rail seats"""

    bl_label = "Strip"
    bl_parent_id = "TIESTRIP_PT_main"

    def draw(self, context):
        """Strip type, first connector side for flex, connector size, rail seats."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "strip_type", expand=True)
        if s.strip_type == "FLEX":
            col.prop(s, "flex_first")
        col.prop(s, "connector_width", text="Connector Width (mm)")
        col.prop(s, "connector_height")
        col.prop(s, "seat_pad")


class TIESTRIP_PT_build(_Panel, bpy.types.Panel):
    """Mesh detail and board reuse, trading build time for variety"""

    bl_label = "Build Options"
    bl_parent_id = "TIESTRIP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Triangle limit and pool settings; Pool Size only matters for long strips."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "max_triangles")
        col.prop(s, "pool_threshold")
        sub = col.column()
        sub.enabled = s.ties() > s.pool_threshold
        sub.prop(s, "pool_size")


class TIESTRIP_PT_variation(_Panel, bpy.types.Panel):
    """Random differences in tie length, position and angle"""

    bl_label = "Variation"
    bl_parent_id = "TIESTRIP_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Length, end offset and angle variation, and random turning."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        col.prop(s, "length_jitter", text=f"Length +/- ({u})")
        col.prop(s, "end_jitter", text=f"End Offset +/- ({u})")
        col.prop(s, "yaw_jitter", text="Angle +/- (degrees)")
        col.prop(s, "random_turn")


class TIESTRIP_PT_holes(_Panel, bpy.types.Panel):
    """Size and placement of the spike holes"""

    bl_label = "Spike Holes"
    bl_parent_id = "TIESTRIP_PT_main"

    def draw(self, context):
        """Hole diameter, clearance from the rail foot and stagger."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        col.prop(s, "hole_diameter", text="Diameter (mm)")
        col.prop(s, "hole_clearance", text="Clearance from Foot (mm)")
        col.prop(s, "use_stagger")
        sub = col.column()
        sub.enabled = s.use_stagger
        sub.prop(s, "stagger", text=f"Stagger ({u})")


class TIESTRIP_PT_plates(_Panel, bpy.types.Panel):
    """Tie plates and shoulders under the rails"""

    bl_label = "Tie Plates"
    bl_parent_id = "TIESTRIP_PT_main"

    def draw_header(self, context):
        """The on/off checkbox in the panel header."""
        self.layout.prop(_s(context), "plates_on", text="")

    def draw(self, context):
        """Plate presets, then plate and shoulder sizes (greyed out when plates are off)."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        _preset_row(col, "TIESTRIP_MT_plate_presets", "Plate Presets", s.plate_preset,
                    s.plate_modified, "tie_strip.save_plate_preset")
        body = col.column()
        body.enabled = s.plates_on
        body.prop(s, "plate_length", text=f"Length ({u})")
        body.prop(s, "plate_width", text=f"Width ({u})")
        body.prop(s, "plate_thickness", text=f"Thickness ({u})")
        body.prop(s, "plate_bias", text=f"Field-Side Bias ({u})")
        body.prop(s, "shoulders")
        sub = body.column()
        sub.enabled = s.shoulders != "NONE"
        sub.prop(s, "shoulder_height", text=f"Shoulder Height ({u})")
        sub.prop(s, "shoulder_width", text=f"Shoulder Width ({u})")
        sub.prop(s, "shoulder_clearance", text="Shoulder Clearance (mm)")


classes = (
    TIESTRIP_MT_board_presets, TIESTRIP_MT_plate_presets, TIESTRIP_MT_strip_presets,
    TIESTRIP_PT_main, TIESTRIP_PT_track, TIESTRIP_PT_ties, TIESTRIP_PT_strip,
    TIESTRIP_PT_variation, TIESTRIP_PT_holes, TIESTRIP_PT_plates, TIESTRIP_PT_build,
)
