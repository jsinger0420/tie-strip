# Tie Strip Generator

A Blender 4.5+ add-on that builds 3D-printable model railroad tie strips: weathered ties joined by low connectors under the rails, four spike holes or four printed spikes per tie, optional tie plates with shoulders, exported as an STL in millimetres.

Design doc: https://claude.ai/code/artifact/546738a1-5a4c-43b3-ad10-bbe6330be406

## Requirements

- Blender 4.5 or later.
- Weathered Board 0.1.5 or later, installed and enabled. It makes the ties.
- Optional: Model Rail Generator 1.1 or later, enabled, for rail presets.

## Install

1. In Blender, open Edit > Preferences > Get Extensions, choose "Install from Disk" in the menu at the top right, and pick `tie_strip-0.3.0.zip`.
2. Open the 3D Viewport sidebar (N) and the **Tie Strip** tab.

## Use

1. **Scale and Track:** pick the scale, which pre-fills the gauge. Pick a rail preset from Model Rail Generator, or Custom and enter your rail's foot width, head width and foot edge thickness in model mm. Built-in rail presets are typical sizes; for printed spikes, measure your rail and save it as a preset in Model Rail Generator.
2. **Ties:** pick a tie preset. Tie presets are Weathered Board presets: in the Weathered Board panel, set the tie's prototype length, width and thickness and its look, then save it as a preset (for example "Tie 8' 6\" x 9\" x 7\""). Tie Strip shows the preset's size, full size and in model mm. Then enter the tie spacing (inches by default) and either the number of ties, or switch Size By to Max Length and enter the longest strip your printer takes (model mm); the add-on fits as many ties as it can. Pick the printer type. Each Generate uses a new random seed, so every strip looks different; the seed it used appears in the Seed field. To repeat a strip, or to rebuild quickly while adjusting spacing, holes or spikes, turn on Lock Seed (the padlock) so the same ties are reused.
3. **Strip:** Straight (two connectors per gap) or Flexible (one per gap, alternating sides, so the strip bends).
4. **Variation**, and **Build Options** for triangle count and long strips, if needed.
5. **Spikes:** choose Spike Holes (you spike the rail down) or Printed Spikes (the rail slides in from a strip end under printed spike heads; no spiking). Printed spikes have their own sizes and clearances, a chamfer under each head (45 degrees by default, so the head doesn't overhang straight out from the shank), spike every Nth tie, and bare end ties so rail joiners fit. They are a resin feature at HO and smaller; keep slicer supports off the top face, or they fill the slot under the heads.
6. **Tie Plates** as needed. Plate presets cover eras from no plates to modern heavy track, and you can save your own with the + button.
7. **Generate Tie Strip**. The cursor shows busy and the panel says "please wait" until it's done. Like Weathered Board's Add button, each Generate adds a new strip (TieStrip, TieStrip.001, ...) at the 3D cursor in the active collection and selects it; strips made earlier are kept. Check the Summary box (it shows the printed size, including tie variation) and any warnings, then **Export STL**, which exports the selected strips: all in one file, or one file per strip.

The first build of a strip takes a while (about 2.5 s per HO tie on resin settings) because each tie is a separate weathered board. With Lock Seed on, later builds reuse the boards, so changing spacing, count, holes or plates takes a second or two; with it off, each Generate builds fresh ties. Larger scales take longer per tie.

Whole setups can be saved as strip presets from the menu at the top of the panel. Preset files live in the extension's user folder and can be copied to share.

## Warnings

- **Grain too deep:** grain depth comes from the Weathered Board preset. If it cuts more than 20 % into the tie (changeable in the add-on preferences), lower Depth or turn off Auto Detail in that preset.
- **Too small to print:** holes, connectors, gaps, plates and shoulders are checked against resin or FDM thresholds, which you can change in the add-on preferences.

## Files

| File | What it does |
| --- | --- |
| `layout.py` | Where everything goes, in model mm. Plain Python, no Blender |
| `meshgen.py` | Boxes, hole cutters, printed spikes and tie placement as numpy arrays. Plain Python |
| `plates.py` | Built-in tie plate presets by era. Plain Python |
| `scales.py` | Scales and unit conversion. Plain Python |
| `wb_bridge.py` | Finds Weathered Board's API, builds, simplifies and caches boards |
| `rail_bridge.py` | Reads rail presets from Model Rail Generator (optional) |
| `build.py` | Builds the strip object (Manifold booleans) and exports the STL |
| `properties.py` | All settings, stored on the scene |
| `operators.py`, `ui.py`, `prefs.py` | Buttons, the sidebar panel and the preferences |
| `preset_store.py` | Saved plate and strip presets (JSON) |
| `tests/test_layout.py` | Unit tests for the plain-Python parts |

Run the tests without Blender from the folder that contains `tie_strip`:

```
python -m unittest discover -s tie_strip/tests -t .
```
