# Tie Strip Generator

A Blender 4.5+ add-on that builds 3D-printable model railroad tie strips (straight, flexible, or printed already curved): weathered ties joined by low connectors under the rails, four spike holes or four printed spikes per tie, optional tie plates with shoulders, exported as an STL in millimetres.

Design doc: https://claude.ai/code/artifact/546738a1-5a4c-43b3-ad10-bbe6330be406

## Requirements

- Blender 4.5 or later.
- Weathered Board 0.1.5 or later, installed and enabled. It makes the ties.
- Optional: Model Rail Generator 1.1 or later, enabled, for rail presets.

## Install

1. In Blender, open Edit > Preferences > Get Extensions, choose "Install from Disk" in the menu at the top right, and pick `tie_strip-0.6.0.zip`.
2. Open the 3D Viewport sidebar (N) and the **Tie Strip** tab.

## Use

1. **Scale and Track:** pick the scale, which pre-fills the gauge. Pick a **Rail Profile** (Model Rail Generator's rail presets), or Custom and enter your rail's foot width, head width, foot edge thickness and rail height in model mm (the height is only needed for Include Rail). Built-in rail profiles are typical sizes; for printed spikes, measure your rail and save it as a preset in Model Rail Generator. Tick **Include Rail** to lay two rail objects on the rail seats of each new strip, parented to it, to check the fit and for renders. Their shape is the rail profile's (the same shape Model Rail Generator draws), or for typed-in sizes typical proportions of the rail height. By default (**Half Tie Gap**) each rail ends half a tie gap past the end ties, so rail on strips laid end to end meets in the middle of the gap between them; turn it off to enter your own **End Overhang** (0 = flush with the end ties, negative stops short). On curved strips the rail follows the curve.
2. **Ties:** pick a tie preset. Tie presets are Weathered Board presets: in the Weathered Board panel, set the tie's prototype length, width and thickness and its look, then save it as a preset (for example "Tie 8' 6\" x 9\" x 7\""). Tie Strip shows the preset's size, full size and in model mm. Then enter the tie spacing (inches by default) and either the number of ties, or switch Size By to Max Length and enter the longest strip your printer takes (model mm); the add-on fits as many ties as it can. Pick the printer type. Each Generate uses a new random seed, so every strip looks different; the seed it used appears in the Seed field. To repeat a strip, or to rebuild quickly while adjusting spacing, holes or spikes, turn on Lock Seed (the padlock) so the same ties are reused.
3. **Strip:** Straight (two connectors per gap), Flexible (one per gap, alternating sides, so the strip bends), or Curved (printed already curved). For Curved, enter the radius to the track centreline in model inches or mm (22 in by default). The ties point at the centre of the curve, tie spacing is measured along the centreline, and the connectors under both rails follow the curve. A curved strip works for left- and right-hand curves: turn it end for end. To make the strip cover a set angle, tick **Set Length by Arc Angle** under the radius and enter, say, 30 degrees and the add-on works out the number of ties and adjusts the spacing slightly so the strip covers exactly that angle, so strips laid end to end add up (twelve 30 degree strips make a circle). The Summary shows the angle the strip covers and the gap between ties at their inner and outer ends. With printed spikes, bend the rail to the radius before sliding it in.
4. **Variation**, and **Build Options** for triangle count and long strips, if needed.
5. **Spikes:** choose Spike Holes (you spike the rail down) or Printed Spikes (the rail slides in from a strip end under printed spike heads; no spiking). Printed spikes have their own sizes and clearances, a chamfer under each head (45 degrees by default, so the head doesn't overhang straight out from the shank), spike every Nth tie, and bare end ties so rail joiners fit. They are a resin feature at HO and smaller; keep slicer supports off the top face, or they fill the slot under the heads.
6. **Tie Plates** as needed. Plate presets cover eras from no plates to modern heavy track, and you can save your own with the + button.
7. **Generate Tie Strip**. The cursor shows busy and the panel says "please wait" until it's done. Like Weathered Board's Add button, each Generate adds a new strip (TieStrip, TieStrip.001, ...) at the 3D cursor in the active collection and selects it; strips made earlier are kept. Check the Summary box (it shows the printed size, including tie variation) and any warnings, then pick what to export (**Entire Track**, **Tie Strip Only**, the default, for printing, or **Rail Only**) and click **Export STL**, which exports the selected strips, all in one file or one file per strip (the choice is also in the file browser's side panel). Selecting a strip's rail counts as selecting the strip.

The first build of a strip takes a while (about 2.5 s per HO tie on resin settings) because each tie is a separate weathered board. With Lock Seed on, later builds reuse the boards, so changing spacing, count, holes or plates takes a second or two; with it off, each Generate builds fresh ties. Larger scales take longer per tie.

**Changing a strip you already made.** Click the strip (or its rail) and press **Load Settings From Selected**: the panel takes the settings that strip was built with, including its seed. Adjust what you like, then press **Regenerate Selected** to rebuild the selected strips in place with the panel's settings. Each keeps its name, place, collection and materials; its rail is rebuilt if Include Rail is on. Like Generate, Regenerate uses a new random seed unless Lock Seed is on, so to keep a strip's look while changing it: Load, tick Lock Seed, adjust, Regenerate. Loading leaves Lock Seed and the Export choice as they are. Strips made before 0.3.0 have no stored settings.

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
| `rail.py` | The rail laid on the strip: cross-section, ends, sweep and bend. Plain Python |
| `build.py` | Builds the strip object (Manifold booleans) and exports the STL |
| `properties.py` | All settings, stored on the scene |
| `operators.py`, `ui.py`, `prefs.py` | Buttons, the sidebar panel and the preferences |
| `preset_store.py` | Saved plate and strip presets (JSON) |
| `tests/` | Unit tests for the plain-Python parts |

Run the tests without Blender from the folder that contains `tie_strip`:

```
python -m unittest discover -s tie_strip/tests -t .
```
