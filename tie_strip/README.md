# Tie Strip Generator

A Blender 4.5+ add-on that builds 3D-printable model railroad tie strips: weathered ties joined by low connectors under the rails, four spike holes per tie, optional tie plates with shoulders, exported as an STL in millimetres.

Design doc: https://claude.ai/code/artifact/546738a1-5a4c-43b3-ad10-bbe6330be406

## Requirements

- Blender 4.5 or later.
- Weathered Board 0.1.5 or later, installed and enabled. It makes the ties.

## Install

1. In Blender, open Edit > Preferences > Get Extensions, choose "Install from Disk" in the menu at the top right, and pick `tie_strip-0.2.0.zip`.
2. Open the 3D Viewport sidebar (N) and the **Tie Strip** tab.

## Use

1. **Scale and Track:** pick the scale, which pre-fills the gauge. Enter your rail's foot width and head width in model mm.
2. **Ties:** pick a tie preset. Tie presets are Weathered Board presets: in the Weathered Board panel, set the tie's prototype length, width and thickness and its look, then save it as a preset (for example "Tie 8' 6\" x 9\" x 7\""). Tie Strip shows the preset's size, full size and in model mm. Then enter the tie spacing (inches by default) and either the number of ties, or switch Size By to Max Length and enter the longest strip your printer takes (model mm); the add-on fits as many ties as it can. Pick the printer type; the seed changes the look.
3. **Strip:** Straight (two connectors per gap) or Flexible (one per gap, alternating sides, so the strip bends).
4. **Variation**, and **Build Options** for triangle count and long strips, if needed.
5. **Spike Holes** and **Tie Plates** as needed. Plate presets cover eras from no plates to modern heavy track, and you can save your own with the + button.
6. **Generate Tie Strip**. The cursor shows busy and the panel says "please wait" until it's done. Check the Summary box (it shows the printed size, including tie variation) and any warnings, then **Export STL**.

The first build of a strip takes a while (about 2.5 s per HO tie on resin settings) because each tie is a separate weathered board. Later builds reuse the boards, so changing spacing, count, holes or plates takes a second or two. Larger scales take longer per tie.

Whole setups can be saved as strip presets from the menu at the top of the panel. Preset files live in the extension's user folder and can be copied to share.

## Warnings

- **Grain too deep:** grain depth comes from the Weathered Board preset. If it cuts more than 20 % into the tie (changeable in the add-on preferences), lower Depth or turn off Auto Detail in that preset.
- **Too small to print:** holes, connectors, gaps, plates and shoulders are checked against resin or FDM thresholds, which you can change in the add-on preferences.

## Files

| File | What it does |
| --- | --- |
| `layout.py` | Where everything goes, in model mm. Plain Python, no Blender |
| `meshgen.py` | Boxes, hole cutters and tie placement as numpy arrays. Plain Python |
| `plates.py` | Built-in tie plate presets by era. Plain Python |
| `scales.py` | Scales and unit conversion. Plain Python |
| `wb_bridge.py` | Finds Weathered Board's API, builds, simplifies and caches boards |
| `build.py` | Builds the strip object (Manifold booleans) and exports the STL |
| `properties.py` | All settings, stored on the scene |
| `operators.py`, `ui.py`, `prefs.py` | Buttons, the sidebar panel and the preferences |
| `preset_store.py` | Saved plate and strip presets (JSON) |
| `tests/test_layout.py` | Unit tests for the plain-Python parts |

Run the tests without Blender from the folder that contains `tie_strip`:

```
python -m unittest discover -s tie_strip/tests -t .
```
