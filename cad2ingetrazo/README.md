# CAD2IngeTrazo 2.0

CAD floor plans (DXF / DWG) to a BIM model in IngeTrazo, level by level,
with drawings on sheets. Runs as a **CAD2IngeTrazo** tab in the side tray
(also *Extensions ▸ CAD2IngeTrazo*).

## Install
Copy the `cad2ingetrazo` folder into `%APPDATA%\ingetrazo\plugins\`
(Linux: `~/.local/share/ingetrazo/plugins/`) and restart IngeTrazo.
An older single-file `cad2ingetrazo.py` in that folder must be removed or
renamed (same plugin name — the first one found wins).

## Workflow (the panel, top to bottom)
| Part | What it does |
|---|---|
| Level · 3D · Plan · Sheets | The level the buttons work on; a clean uncut 3D, this level's plan (cut, with its notes), the sheets |
| 1 Import CAD plan — level by level | File; **Select floor on drawing…** opens the CAD file: drag a box round one floor, click its reference point (grid A/1 or a corner, snaps to line ends and crossings). Units, insert X,Y, rotation, wall thickness range, layer wildcards; **Import to «Level n»** builds walls, doors, windows, columns, beams, slab + holes, rooms, texts. After an import of the top level, **＋ Level n+1 (new)** is selected at once: select its part of the same file and import. Floors taken already show as dashed boxes. |
| | **Detect layers automatically** (on by default): walls, doors, windows, columns, beams, slab, texts, plot boundary and footings found from layer names (English, Spanish, Portuguese, French, German, Italian, AIA codes like A-WALL / A-DOOR / A-GLAZ / S-FNDN), from block names (DOOR…, PUERTA…, WINDOW…, VENTANA…) and, when no name says «wall», from the line pairs. Door and window **blocks** are placed in the wall they stand in (also where the wall lines run through without a gap). The layers found are written into the Layers fields so you can check or change them. |
| | Level list also offers **＋ Basement (new, below)** and **Foundation**: import a basement plan or a foundation plan (pads from closed outlines and circles, strips from line pairs on the footing layers) from the same file. |
| 2 Overlap floors | **Show greyed out**: in a plan view the floor below (grey), the floor above (dashed blue), both, or all other floors, drawn under the current plan. **Overlap**: lay the level picked at the top over another — best fit (the move that makes most wall corners meet), lower-left corners, or centres; or move it by X, Y. Everything on the level moves; a later re-import lands in the same place. |
| 3 Project and levels | Name, client, author, location; levels table (name, storey height), + Above / + Basement / Remove |
| 4 Plot (site) | **Boundary wall and gates** (ground level — shown in the ground floor plan, the site plan and 3D): a wall on the plot's edge (outer face on the property line), height and thickness, pillars at corners and gate jambs; gates on any side — double swing, single swing or sliding — with their swings in the site plan. The Level list's **Site · ground** entry: Plan shows the site plan. ArchXQ-style plot demarcation: from the drawing (click the corners, or click inside the boundary polyline), a rectangle, or found automatically on a «PLOT / SITE / BOUNDARY» layer. Front side, setbacks front / back / sides, plinth; plot area, perimeter, buildable area and a check that the building keeps the setbacks. Green ground plate in 3D; site plan sheet A-001 with side dimensions and the dashed setback line. |
| 5 Openings | Import heights/sill; add a door / window / void to the selected wall |
| 6 Structure and foundation | Slab on import, **Auto slab on every floor** (round the outside of each level's walls, stair holes kept; optionally replacing the slabs there), corner columns, beams on walls; **foundation level** (footings' bottom) and footings under the lowest level — foundation plan sheet A-100 |
| 7 Stairs, terraces and balconies | **Stairs on all floors** follow the plan: the tread lines on the stair layer give each flight's width, number of risers, going and turn (UP / DN marks set the direction), landings between flights; when the plan shows only the lower flight, a half landing and a return flight beside it complete the storey. Without tread lines: a stair well outline or a room named STAIR… gets a standard stair; a level with neither takes the floor below's. Every stair cuts its well in the slab above. **Terraces over the floors below** (every upper floor): the open roof of the floor below gets the floor's slab and a parapet on its open edges. **Balcony** on a selected outside wall of an upper floor: depth, width, railing. |
| 8 Roof | Hip, gable, flat with parapet, or none — over the top level; or a **Roof level** (also in the Level list: «＋ Roof level»): a terrace slab round the outside of the top floor's walls and a parapet wall on its edge (height, thickness), with its own plan and sheet |
| 9 Rooms | Names (editable) and areas, net and gross |
| 10 Selected element | Click any wall / opening / column / beam / slab / footing / roof: edit its sizes, flip a door, delete |
| 11 Plans, sheets and export | **Column grid** in every plan: axes 1, 2, 3… / A, B, C… with bubbles, from the columns, the wall corners, or the bays you type; Dimensions, room labels, CAD texts (plan views only); paper, scale, cut height; elevations and sections; Make sheets, PDF, DXF |

**Plan texts follow the zoom**: room names, areas and CAD texts are drawn at their real size in the plan view — larger as you zoom in, faded out when too small to read; the dimension chains hide when zoomed out too far for their figures and come back when you zoom in. Sheets keep them at paper size.

Every action is one **Ctrl+Z**. Upper plans sit over the lower ones by
their base points; each plan shows only its own level, its own notes and
door swings; the 3D view never shows 2D notes and leaves a plan cut as
soon as you orbit.

## Credits
Modelling engine (walls, openings, structure, roofs, rooms) from
*ArchXQ IT Lite* © Orlando Souza / XQ. GPL-3.0-or-later.

## 2.8 additions
- **Units from the CAD plan**: «Model units: Auto» takes the drawing's units (inches/feet → feet-inches, mm, cm, m); every length field, dimension and area (ft² / m²) follows; can be set by hand.
- **Stairs**: real treads and risers with nosing; type: monolithic RCC (waist slab, 6" by default), solid / masonry, open riser on stringers, cantilever.
- **Openings**: the door's hinge and the side it opens to are read from the CAD swing; openings drawn with nothing in them (down to the floor) come in as glass sliding doors; window types casement, sliding, fixed, top-hung, louvre (import default + per window); door types hinged, double, sliding; doors and windows move along their wall (◀ 0.1 / 0.1 ▶) with their opening.
- **Columns**: read from the CAD's column layers; when a plan has none you are asked whether to add them at the wall corners.
- **Clean wall joints**: wall ends are brought onto the walls they meet, so L and T joints are mitred and joined in plan.
- **Column grid from the CAD**: axes on GRID / AXIS layers with their labels (or numbered 1, 2, 3 / A, B, C).
- **Curved plots**: «Click the boundary line (curves too)» follows lines and arcs round.
- **Layers and materials (finishes)**: the CAD layers with the role each plays (editable), and a material name and colour per element type.
- **Update from CAD**: a warning when the CAD file changed since its import, and one button to read every level again.

## 2.9
- **Doors by their symbol only**: a door is made where the CAD shows a door — a door block (its name or a DOOR layer) or a swing arc; a block named SD / SLIDING makes a sliding door, DOUBLE a double door.
- **Every other opening down to the floor** — nothing drawn in it, or no door / window symbol — is a **glass sliding door**.
- **Windows by their symbol**: window blocks / glazing lines; their type from the block's name (SDG / SLIDING → sliding, FIX → fixed, LOUVRE, TOP-HUNG), else the import default.
- Layer detection: «FIXTURE» is no longer read as a door layer, note layers (…TEXT) never make elements, the boundary wall is not a building wall, «GIRD» is read as the grid.
- **Door sizes, as built**: a hinged door is one leaf up to 4'-0", two leaves (double shutter) up to 7'-0"; any wider opening is a glass sliding door. Double doors show both leaves' swings in plan.
- **Glass sliding doors in panels**: 4'-0" panels at most, on two tracks; a door higher than 7'-0" gets 7' panels with a fixed glass light above them (transom bar between).

## 3.0
- Hinged doors stand open 90° in the model (wooden leaf toward the room the door opens into), so plan cuts show the leaf and swing instead of a thin wall; double doors open both leaves.
- Lift cores: lines on LIFT / ELEVATOR / CORE layers become RCC core walls like the columns (same material, full height per level), with steel centre-opening landing doors; the shafts cut the slabs.
- Doors and windows moved with IngeTrazo's Move tool take their opening along: the move is projected on the wall, the opening's position updated and the wall rebuilt (one more Ctrl+Z step). The panel's ◀ ▶ nudge buttons still work too.

## 3.1
- Project north: read on import from the CAD's north arrow (a NORTH/COMPASS block, or a compass drawn in lines with an «N» at the needle's tip), turned with the import's rotation. Panel ▸ Project and levels ▸ North: type the angle (clockwise from the plan's up), «From CAD», «↻ 90°». Stored as one Ctrl+Z step without rebuilding the model.
- A compass in the viewport's top-right corner (true in plan, turns with the orbit in 3D); «Show the compass in the view» turns it off.
- «Make sheets»: a north arrow on the plan, foundation and site sheets; the elevations are named North / East / South / West from it.
- A CAD2IngeTrazo toolbar in IngeTrazo's window: the plugin's icon opens the panel, plus 3D / Plan / Sheets buttons; the icon also marks the Extensions menu entry.

## 3.2
- Car parking from the CAD: bay lines (PARKING layers) and car blocks (CAR layers) — the CAD's own symbols in the plan, white bay paint and simple car masses in 3D ("Cars in the parking (3D)" in part 11).
- Car ramps from the RAMP layers: striped ramps follow their stripes (straight or curved), side-line ramps run between their two edges. Climb from the note beside it (CLIMB HEIGHT, or GRADIENT 1:n × length); up / down from "RAMP UP / DN" and the arrow on it. Built in 3D as a sloped RC slab (IfcRamp); in plan as outline, stripes and an UP/DN arrow with "RAMP UP 9'-0"". A ramp down cuts a well in its own floor's slab, a ramp up in the slab of the floor above. Select a ramp: change its climb or thickness, or Flip (start at the other end).
- Floor level marks: the CAD's "LEV. +4'-0"" / "FFL" notes drawn as level symbols in the plan; a level with none gets "FFL +x'-x"" beside its biggest room ("Floor level marks" in part 11).
- New layer roles: Parking bays, Cars, Car ramps.

## 3.3
- Shafts and slab openings: boxes crossed by an X, and closed outlines, on the slab-hole layers (SHAFT, DUCT, OPENING, VOID…) are cut through the floor slab and drawn with their outline and X in the plans.
- Slabs from walls: every building block gets its slab (door / window gaps closed up to 2.5 m); a parking floor's slab also covers the drive and the ramps (a close hull round walls, bays and ramp lines), so the down ramps' wells are cut.

## 3.4
- Stairs: traced on every floor, the top floor too (one storey high), and built straight after an import / Update from CAD; side-by-side flights of a U stair are split and joined right.
- Car ramps: the turning pads at their bends and entries are built (3D and plan).
- Parking: a car in every bay — IngeTrazo's own library models (SUV, pickup or mixed; Properties ▸ Components), placed as instances along each bay, scaled down to fit; bays numbered P1… with the car count.
- Column grid: the CAD's grid bubble texts are no longer imported as plan texts (no double labels).
- Doors: types like the windows' — single hinged (flush), main entrance (panelled), frameless glass, double, French (glazed double), sliding glass, pocket, bi-fold, rolling shutter, garage; a type for one-leaf and for two-leaf doors at import, and «Apply to this level».
- Door handles on every door: levers on hinged leaves, pull bars on glass, main and sliding doors, flush pulls on pocket doors, knobs on bi-folds, lift handles on shutters.
- Heads: flat, transom (fixed light over, mullioned when wide) or arch top (semicircle, segmental when wide) for doors and windows; the wall is cut round the arch; a door with a transom / arch is raised to keep a 2.1 m leaf.
- Plan views: the CAD's own linework drawn with its line weights and line types (by entity, layer or block; LTSCALE), layers off / frozen in the CAD left out; a switch in part 11.
- Floor levels from the CAD's level notes (LEV. +4'-0", FFL …): the most common note on a floor is its level, in plan and 3D (absolute RL notes keep their spacing).
- Landscape: areas round LANDSCAPE / LAWN / GARDEN texts, and closed outlines on landscape layers, laid in green.
- Lifts: a car (with its counterweight) drawn in each shaft in the plans only; the lift wells hollow through every slab, the lowest too.
- Export the model to SketchUp (.skp) from part 11 and the toolbar (a Collada .dae for SketchUp's importer when this IngeTrazo has no SKP writer).

## 3.5
- Car ramps as routes: the striped pieces, their turns (round the arc the plan draws) and the entry / exit lanes are ONE continuous ramp from floor to floor, climbing evenly by the climbs its notes give (a note drawn twice counts once).
- Ramp wells cut exactly to the ramp (never widened to a hull): the slab behind the lift core stays.
- Lift cores and their lobby (a gap up to 5 m to the building) are under the floor slab.
- An X drawn in a hidden / dashed line type cuts the slab there (any layer but ceilings, grid, furniture, fittings, projections…).
- Stairs: an arrival landing at the floor above, past the last riser (kept out of the upper slab's well).
- Doors: two leaves up to 8'-0"; a louvred door type (stiles, rails, angled slats); a frame material for every door and window — wood (chowkat), aluminium, steel or uPVC — auto: wood for hinged-type doors, aluminium for sliding doors and windows, steel for shutters; set at import or per element.
- Parking markings painted as one clean joined shape (square ends, closed corners).
- Floor height at import (floor to floor), 9'-10" by default.
- A DWG the converter cannot read (some AutoCAD saves): the same-name DXF beside it is read instead, and the message says how to make it.

## 3.6
- Ramps reach the walls round them: each section's edges pushed out to the nearest wall face (further at the turns), so no strip of floor is left beside a bend.
- One floor at several levels: every level note on a floor (relative, and RL notes through a pair noted side by side, e.g. «LEV. 75.50» = «LEV.+3'-6"») sets its zone — each room its own noted level, the open floor round the rooms (drive, parking) the level most noted there; the slab is cut in pieces at those heights, and the parking, cars, ramps and landscape stand on the open floor's level.
- Right-click an element: «Edit properties…» (all its fields in a dialog), and quick changes — a door's or window's type, leaves, head and frame, flip the hinge, the side it opens to, move it; a wall to a curtain wall and back; delete.
- Curtain walls: any wall (straight or curved) as glass on an aluminium grid — mullion and transom spacing set per wall; from the right-click menu or the panel.
- Doors: single or double leaf is its own option for every hinged door type (flush, main entrance, louvred, frameless glass, glazed / French) and pocket doors (bi-parting); the import types are set for single- and double-leaf doors apart.

## 3.7
- Louvred door: an aluminium panel door (aluminium stiles, rails and slats; aluminium frame).
- Hinged glass door in an aluminium frame (single or double leaf), beside the frameless one.
- A wall made a curtain wall loses its windows (the glass is the wall); its doors are fitted 4'-0" to 8'-0" wide (one leaf to 4', two above), hinged glass in aluminium frames.
- Curtain wall: a lower and an upper panel, their heights and their infill (glass or an opaque spandrel) in its edit dialog; the vision glass between on the transom grid.
- Ramp: its slope (%) in the edit dialog — the climb follows from the ramp's length.

## 3.7.1
- Fix: `lift_cores` returned 2 values on a floor with no lift lines → import crashed ("not enough values to unpack"). Now always (cores, shafts, doors).
- DWG fallback chain: LibreDWG → same-name .dxf beside the DWG → ODA File Converter (if installed, writes <name>.dxf beside the DWG) → clear error.
- THE COURT HEIGHT.dwg (AC1027, 17 Sep): file-header map at 0x80 is zeros — LibreDWG gives a truncated DXF with no entities, ezdwg fails "section map page not found". Needs AutoCAD SAVEAS DXF (or RECOVER + SAVE).

## 3.7.2
- Windows default to **Sliding** (import option, settings and fallbacks).
- Overlap floors: own «Level to move» picker (default: level picked at the top if real, else the last floor imported); «Over level» = the floor below it. Before, a «＋ new level» pick at the top made Overlap silently do nothing.
- Curtain walls keep each door's own type and frame (the default door option) — only width (4'–8') and leaves are fitted.

## 3.7.3
- Overlap floors: **Rotate the level** (angle °, anticlockwise +) and quick turns ↺90° / ↻90° / 180°, about the middle of the level's walls. `PJ.rotate_level` updates the import (insert point + rotation) so a re-import lands the same way.
- `transform_level` (generic point/vector/angle walk) now drives both move and rotate — moving a level also carries its parking, ramps, level marks and landscape (before only walls/structure/rooms/texts/stairs moved).

## 3.7.4
- Rotate has its own **Level to rotate** picker (under «Rotate a floor:»), independent of «Level to move».
- Sliding doors/windows: pulls only on the jamb side of the two end panels — never on the meeting edges; inner panels of 3–4 panel sets have none.

## 3.8
- **Slab over each floor** (default, «6 Structure ▸ Slab position»): every level's main slab is cast on top of its walls (`top` flag, built at level top + next floor's open-floor offset; walls/cores stop under it); top floor gets its roof slab, ground floor stands on the ground. «Under each floor» = old behaviour. `apply_slab_pos` runs on every commit; `recut_wells` re-cuts stair wells (own level when on top) and ramp wells (up: own level, down: level below).
- Next floor's CAD level zones and sunk/raised parts are cut out of the slab below them (`floor_parts`).
- **Sunk / raised floor**: «6 Structure ▸ Level ± / Sunk / raise selected» — on selected room finishes (sets room `fz`) or on a rectangle drawn with the Rectangle tool and selected (`sunk_area` → user slab part). Room `fz` → slab part re-made from the room outline each commit (`sync_room_floors`).
- **Floor finishes per room**: «9 Rooms» table: Name · Area · Finish · Floor ± (typed lengths), default finish 2" (on/off), «Default finish → all rooms». Built as a solid per room on its floor (tag type `room`, material «Floor finishes (rooms)»); click one in the model → «Selected element» / right-click: name, finish thickness, floor sunk/raised.

## 3.8.1
- Terraces: parapets made as joined chains (`parapet_runs`: the terrace inset by t/2, mitred, minus the run along the upper floor) — corners close clean, ends run into the upper floor's wall face, outer face flush with the floor below.
- With slabs over each floor, a terrace adds no slab: it stands on the slab over the floor below, and the upper level's own slab is cut back off the terrace area (bottom mode keeps the old grown slab).

## 3.8.2
- DWGs LibreDWG cannot read (e.g. THE COURT HEIGHT.dwg, AC1027 with a zeroed header map) are converted automatically by **AutoCAD's console engine** (`accoreconsole.exe`, no window): `DXFOUT` R2018 into `%LOCALAPPDATA%\ingetrazo\c2i_dxf\<name>_<hash>.dxf`, cached until the DWG changes. Fallback chain: LibreDWG → AutoCAD → ODA → sibling DXF → error. THE COURT HEIGHT: 8 s convert, 489k segments.

## THE COURT HEIGHT — full tower import (7 Oct)
- 13 plans side by side in one DWG (titles at y≈-379000): Column layout, Basement, Ground, 1st, 2nd, 3rd, 4-6, 7-8, 9th, 10/13/16/19, 11/12/14/15/17/18/20, 21st, Roof. Sections/elevations below at y≈-383000.
- Every plan shares grid line 1/A: first vertical GIRD line x (per plan) and first horizontal GIRD y = -378450.434 → used as custom base point, so floors stack exactly. Region per plan: [gx-700, -378900, gx+4700, -376000] (drawing inches).
- Script `c2i_tower.py` (QTimer chain, log `c2i_tower_log.txt`): 24 levels (Basement, Ground Floor, 1st…21st Floor, Roof), floor height 10'6". Imports 4–13 s each (≈4.5 min), stairs 46 traced, commit (3D build) 996 s.
- Typical floor: ~206–215 walls, ~140–148 doors/windows, 59 columns, 60 rooms. Basement 47 bays/3 ramps, Ground 31 bays/4 ramps, 1st 36 bays/2 ramps.
- Perf: commit of a 24-storey model ≈ 16.6 min in IngeTrazo — a candidate for optimisation (per-group mesh building).

## 3.9 — components
- `components.py`: every element has a **component type** — mark + name from its parameters: doors `D-nn` (style, leaves, head, frame, w×h), windows `W-nn` (style, head, frame, w×h, sill), voids `V`, columns `C` (shape, w×d), beams `B`, walls `WL` (thickness; parapets apart), curtain walls `CW`, slabs `SL`, lift cores `LC`, footings `F`, roofs `R`, floor finishes `FF`. Marks persist in `doc["comp_names"]` (new types take the next number; a type edited keeps its mark); names can be renamed.
- Model built as **real components**: each element taken into its own frame (opening: its wall line at its centre; column: its point + angle; others: plan origin at level z) and hashed to the mm — identical geometry shares ONE prototype mesh placed by `xform` instances (`g.component = True`). Group name = «mark · name». Tag carries `ctype` + `mark`. Room finishes too (typical floors share).
- Test (5 floors of THE COURT HEIGHT): 1,669 elements → 548 meshes, 1,450 instances; placement check 1,664/1,664 exact.
- Panel «12 Components (types)»: list by level/kind with counts; **Select in model** (every instance); **Edit type…** (fields of the first element; changes applied to all of the type); rename + **Save names**. Right-click an element: «Select all «D-04» (n)», «Edit type «D-04» — all n…».

## 3.10 — curtain-wall doors, railings
- **Doors in curtain walls**: `PJ.add_cw_door(doc, wall, style, width, pos, leaves)` — set into the glazing grid (one bay, two when a bay < 3'-0"; 4'–8' unless typed; centred on a bay / mullion nearest `pos`; first place free of other doors). Styles `CW_DOOR_STYLES`: alu_glass hinged, frameless glass, sliding. Right-click a curtain wall ▸ «Add door in this curtain wall…» (type, leaves, width, position); «5 Openings ▸ Add to selected wall» on a curtain wall routes here.
- `curtain_wall()` now cuts mullions, transoms and glass round each door (`free()` box subtraction) and adds a transom over each door head.
- **Railings** `engine/railings.py`: `faces(path, height, kind)` along any 3D path (level or sloped). Types: solid parapet, SS vertical balusters, MS grill, frameless glass + handrail, glass panels between posts, steel pipe rails, timber, low wall + steel railing.
- **Stair railings**: settings `stair_rail` (default ss_bars), `stair_rail_h` (3'-0"), `stair_rail_sides` (inner = by the well, joined across landings; both). Built in `stairs.build` along the nosing line. Panel «7 ▸ Stair railing / height / sides ▸ Apply stair type and railing».
- **Parapets as railings**: wall field `rail` (any wall can be built as a railing — Edit properties ▸ «Build as railing»). Terrace parapets, roof parapets («Roof parapet n») and balcony railings take `settings.parapet_rail`; «7 ▸ Parapet / railing type ▸ Apply to every parapet and balcony» (`apply_parapet_rail`). Components: railing walls typed `RL-nn`.

## 3.10.1 — staircases and stair railings as components
- Each stair builds TWO groups: the stair (tag `stair`) and its railing (tag `stairrail`, same stair id), each typed and instanced (same stair on typical floors = one shared definition; frame = level z).
- Types: `ST-nn` «Dog-leg stair, RCC · 18 risers of 7" · 4'8" wide» (stype, flights, risers, rise, width); stair railings typed under Railings `RL-nn` «Stair railing · SS balusters · 3'0" · well side» (rail, height, sides).
- Per-stair own values `stairs.OWN` = stype, rail, rail_h, rail_sides (`ST.eff` falls back to the panel defaults); kept through `ST.auto` re-makes (matched by level + well centre).
- Editable: right-click a stair / its railing ▸ Edit properties, Select all «ST-03», Edit type «ST-03» — all n (FIELDS `stair`, `stairrail`); delete a stair railing = rail «none». Components list «Staircases».
- Test (5 floors): 10 stairs → 7 stair types, 20 groups, 14 meshes; override survives re-make.
- Choice fields show plain names (`CHOICE_LABELS`: railing types, stair types, sides, door styles, heads); right-click submenu reads «Stair» / «Stair railing».

## 3.11 — plan lines, stairs, detection, partial walls, ramps, excavation, library
- **CAD lines on/off**: «CAD lines» checkbox at the panel top and a checkable «CAD lines» button on the CAD2IngeTrazo toolbar; both and section 11's checkbox kept as one (`Panel.set_cad_lines`, setting `cad_lines`, read by `linework.draw`).
- **Stair landings**: designed U-stairs now put the first flight's last riser on the half landing's edge (`as_flights`: `s1 = L − dl − (n1−1)·g`; it used to start at the wall and stop short). Monolithic flights run their waist on under the landing until the soffits meet (one kink line, landing thickness = waist); a flight from a landing kinks into the landing's soffit — no step under landing edges.
- **Adjustable stair railing**: sides inner / outer (wall side, turns round the landings) / both / none; inset from the flight edge (`rail_off`), baluster spacing (`rail_gap`, 0 = the type's; posts for glass_post/pipe), run-on past the first and last step (`rail_ext`). Panel defaults (7 ▸ Railing inset / spacing / run-on) and per stair (Edit properties / Edit type); `railings.faces(..., gap=)`; types keyed with them.
- **Columns**: `columns_from()` — closed outlines, loose lines polygonised, circles; rectangles to 15 m (shear walls), other shapes as `shape: "poly"` columns (`pts` about the centre); layers naming a floor range («S-CONC-4 FOUNDATION TO 6TH») are columns, not footings. TCH Level 1: 6 → 321 columns; HEIGHT ground 107, 2nd 66.
- **Lift cores**: a bank drawn as one U of wall (no walls between cars, front only piers) now closes over its hull → its shaft and landing doors (TCH 3-lift bank); `lift_wells_by_text()` — a «LIFT» / «LIFT WELL» / «ELEVATOR» text inside a space closed by walls/columns/lift lines (1–40 m²) gives a shaft cut in the slab (TCH: 2 wells with no lift layer).
- **Partial wall edit**: right-click a straight wall ▸ «Edit part of this wall…» — from / to along it; the part becomes its own wall (same type, height, thickness; openings re-homed; a cut through an opening moves to clear it, END_GAP kept), then edit its properties / make it curtain wall / make it a railing (`PJ.split_wall`).
- **Ramps**: stripes picked by how many lines lie parallel (the chevrons of an arrow pattern no longer taken as the ramp's width — TCH ramps were 3.67 m wide and off-centre, now 5.49 m on the lines); `to_walls` drops a corner push made by one section alone (spikes past outer walls); `fit_ends()` cuts an end along a slanted line the plan draws.
- **Excavation / fill** (4 Plot ▸ Excavation / fill, ArchXQ's `arch["digs"]` format): outline from the building footprint + working space, the buildable area, the plot inset, a rectangle, or a selected slab/room/ramp; bottom under the lowest level (− margin), a depth, an elevation (fills: a height); side angle (90° vertical, 45° batter). The plot plate opens over cuts; pit floor + sloped sides (earth colours), fills with sloped sides; volumes by the prismoid rule, «Cut / fill / to cart away» totals; labels on the site plan; IFC IfcEarthworksCut/Fill; select + delete in the model. Module `excavation.py`.
- **Replace with a library component**: Components ▸ «Replace with library…» or right-click ▸ «Replace «D-01» with a library component…» — any IngeTrazo `resources/components/*.igz` (names from `components.json`, searchable), stretched to each element's box / kept in proportion / native size, turned 0/90/180/270; stored on the type (`comp_names[key]["lib"]`), the element stays the record (wall opening, schedules). Back to CAD2IngeTrazo's model from the same list. Module `library.py`; walls, openings, structure, stairs and stair railings.

## 3.11.1 — the whole IngeTrazo library; columns by floor range
- **Replace with library…** now lists IngeTrazo's whole online catalogue (Component library ▸ More components…, ~1,500 models by category: Doors and windows, Kitchen, Bathroom, Bedroom, Living room, Office, Lights, Staircases, Exterior, People, Vehicles, Miscellaneous) besides the bundled models — category filter, search, previews. Online models download once (IngeTrazo's own cache, `core.library`) and arrive at the catalogue's declared size before fitting. The choice stores the catalogue record on the type (`lib.entry`), so rebuilds need no index lookup.
- **Columns by floor range**: a column layer naming a run of floors («S-CONC-4 FOUNDATION TO 6TH», «COL 3RD TO 6TH», «6TH TO ROOF») is used only on the floors it names (`floor_range`, `level_floor_no`: ground 0, floors 1…, basements −1…; FOUNDATION/BASE = below all, ROOF = top).
- **Columns from the CAD (all levels / this level)** (section 6): re-reads only the columns of imported levels from their CAD plans — walls, openings and edits stay (`PJ.redetect_columns`). TCH Level 1: 6 → 313.

## 3.12 — bay numbers, mirror, shaft openings, real .skp export
- **Bay numbers in plan views**: P1, P2… drawn by the plan overlay along each bay (to scale, bold) with «CAR PARKING: n CARS»; the host's fixed-size copies stayed hidden before, so none showed. The CAD's own bay numbers are dropped while numbering is on (`labels._bay_number`: a parking-number layer — «TEXT-PARKING NO.», «BAY NO», «P.NO» — or a short number inside a bay). TCH: the 163 «99» texts (one CAD layer, every one «99») replaced by P1…P148.
- **Mirror a component type**: right-click ▸ «Mirror «D-01» — all n» ▸ Left ↔ right / Front ↔ back (checkable), or the Mirror checkboxes in Edit type. Stored on the type (`comp_names[key]["mirror"]`), faces flipped about the element's own box with loops reversed (`components.mirror_lf`); library models by a mirrored placement; stairs and stair railings too.
- **Loader keeps `lib` and `mirror`** on component types (3.11 dropped `lib` at the next load — a library replacement vanished on the next rebuild).
- **Shaft / slab openings by hand**: right-click a slab ▸ «Add shaft / opening in this slab…» (W × D at X, Y, angle — or the rectangle drawn and selected), on that floor or through every floor; «Remove an opening drawn here». Section 6 ▸ «Shaft / slab opening on this level…». Kept in `doc["man_shafts"]`, cut again at every rebuild (`apply_man_shafts`, idempotent; floor of a level = the slab cast over the level below when slabs sit over floors), drawn with the shaft X in plans.
- **SketchUp export writes ONE .skp**: IngeTrazo 0.5.7's installer has `openskp` but not `formats.skp_out`, so 3.11 always fell back to Collada (.dae + .jpg). New `skpwriter.py` writes the .skp with `openskp.create` itself: components → definitions + instances (mirrored kept), other groups → groups, face colours → materials (opacity), layers → tags; holes kept (older writers: triangles). TCH Level 1: 27 definitions, 190 instances, 119 groups, 10,100 faces, 2.8 MB, read back by IngeTrazo's own .skp reader.

## 3.12.1 — the wheel no longer changes values
- Scrolling the panel over a spin box, list or slider that hasn't been clicked into scrolls the panel instead of changing its value (`_WheelGuard`, an application event filter; a field you click into still takes the wheel).

## 3.13 — slab edges, basements, plan editing, motorbikes
- **SketchUp export**: the .skp now writes on IngeTrazo installs that lack openskp's scaffold file (bundled `_skp/blank_v17.skp`, MIT, checked by hash). No more .dae + .jpg.
- **Levels**: «Level 1» is now **Ground Floor** (then 1st Floor…, Basement 1…). The ground floor's F.F.L. above the road can be set from +1'-0" to +4'-0" in the Level section (0 = as the CAD's level note says).
- **Windows**: a glass type in edit mode (clear, double, low-E, tinted grey / bronze / green, reflective blue / silver, frosted), also for curtain walls. Right-click ▸ «Replace with wall» (or every window of that mark).
- **Stairs**: the tread (11") and riser (7") and the number of steps are editable; the railing on both sides now runs round the landings too.
- **Structure**: beams 8" × 24" by default, each its own component («Beams on the walls», this level or all). **Basements**: the outer walls become RCC retaining walls with no doors or windows (at least 12", on import, or «Basement outer walls → RCC»); **shoring** along the plot limits: contiguous or secant bored piles with a capping beam, or steel sheet piles, down past the lowest basement by an embedment.
- **Roof ▸ false ceilings**: gypsum, 2'×2' acoustic tiles on a T-grid, POP, timber, PVC, metal strips — 8'-0" over the floor by default; per room in the room's dialog.
- **Rooms**: the dialog shows the room's size (width × length) and a ceiling choice; right-click ▸ «Add furniture from the library…» (IngeTrazo's whole catalogue). Moved furniture stays where it was put.
- **Motorbike parking**: motorbike blocks and small bays on the bike / parking layers are found like the cars; a motorbike in every space, numbered M1, M2… with «MOTORBIKE PARKING: n BIKES».
- **Slab edges**: lines on the rail layers (`*RAIL*`, `*GRILL*`, misspelt «RALL», balustrade…) become railings, and the slab is carried out to them; hidden (dashed) lines round the building extend the slab as projections. Right-click a slab ▸ «Edges, railing, sun shades, close openings…»: extend the slab to its walls, a railing of any type on its free edges (or take them off), **sun shades (chajja)** over the floor's outer windows (2'-0" × 4", 6" past the jambs), and tick openings to close them. «Extend slab to the walls» is in the menu too.
- **Floor finish** goes out to the slab's edge (balconies, the slab out to the railings); **granite thresholds** in every door opening, as thick as the floor finish.
- **In the viewport**: double-click a slab in a floor plan for a level mark «▽ +1'-0" F.F.L.» (plan only; double-click it again to remove). Click a wall: drag its square end handles to stretch it along its line (Ctrl: anywhere, snapping to other walls' ends), the round middle handle to move it (Shift: square to the wall only); joined walls follow and its doors and windows keep their places. Esc cancels a drag.

## 3.13.1 — IngeTrazo no longer closes; the wheel never changes a value
- **Crash fixed**: 3.12.1–3.13's wheel guard sent the wheel event on to the panel's scroll bar, whose own wheel came back through the guard — an endless loop until the stack overflowed and IngeTrazo closed (IngeTrazo's crash log: «stack overflow … panel.py eventFilter»). The guard now scrolls the panel itself and never re-sends the event; a hot install takes the older guards off.
- **The wheel never changes a value in the panel**, even in a field clicked into: over a spin box, list or slider it scrolls the panel. Values change by typing, the arrows or picking from the list. (Dialogs keep the normal wheel.)
- **Motorbikes from IngeTrazo's library**, like the cars: the first motorbike / scooter in the online catalogue, or the one picked with «Pick…» in section 11 (beside the car model); «Auto» goes back to the first found. Offline: the simple built-in motorbike.

## 3.13.2
- **Motorbikes**: the Vehicles' «Scooter» of IngeTrazo's online catalogue is found first (3.13.1 skipped any name with «motorcycle» in it by mistake).
- **Floor finishes cut at the slab's openings** (shafts, stair / ramp / lift wells, openings drawn by hand), as the slab is.
- **1 Import CAD plan**: «Analyse / Import to …» right under «Select floor on drawing…»; the drawing and model units, base point, insert point, rotation, wall thickness, level options and floor height fold into «Import settings…» (closed), beside «Layers».
- **Door thresholds flush with the floor finish**: the granite's top is the finished floor of the rooms either side (the higher one when they differ — a sunk bath, a thicker finish), down to the slab; before, it stood on the level's open-floor height.

## 3.13.3
- **Extend a slab to the walls you pick**: right-click a slab ▸ «Extend slab to walls I pick…» (also in the slab's Edit properties and its Edges dialog), select the walls (Ctrl+click for several; on any floor, standing on the slab or off it up to 12 m), right-click one ▸ «Extend the slab to the selected walls». Selecting the slab and the walls together and right-clicking works too. The slab takes in each wall and the strip between it and the slab.
- **Beams column to column** (section 6 ▸ «Beams run: Column to column»): each column joined to the nearest column in each of its four grid directions (its own angle and square to it, within the longest span, 10 m by default), the beam between the two columns' faces; each beam its own element. «Over the walls» keeps the old way; a level with no columns says so.

## 3.13.4
- **Slab ▸ Edit properties ▸ Floor finish**: «In the rooms and out to the slab edge» (as before), «Over the whole slab» (one finish over all of it, less its openings, walls, columns and cores) or «No floor finish»; and «Finish thickness» (0 = the default) — the rooms on that slab without a finish of their own take it too.
- **Beams: trim / extend** — select a beam: square handles at its ends (drag along its line to trim or extend; joined beams follow), a round one in the middle to move it. Right-click a beam ▸ «Trim / extend this beam…» (which end: to the face of the nearest column in its line, to the nearest beam / wall, by a length + / −, or to a point clicked in the model) or «Trim / extend to a point I click» (its nearer end goes there).
- **Beams column to column** is also on the right-click menu of any beam or column («Beams column to column on this level»), besides section 6 ▸ «Beams run: Column to column» ▸ «Beams (this level)» / «All levels».

## 3.14.0
- **Slab ▸ «Extend slab up to the beams»** (right-click a slab, or its Edit properties): the slab carried out to the outer faces of the beams round it (within 4 m), the gap between filled.
- **Isolate level / Show all / Select level** (under 3D · Plan · Sheets): 3D with only the level picked at the top (every other floor, the plot and site hidden), and back; the whole level selected at once. Each level is one layer «C2I · <level>».
- **Car ramps**: a wall a ramp passes over stops under the ramp's soffit (and a wall over a ramp going down stands on it), following the slope — rebuilt with the ramp, so a changed slope changes the walls' heights; beams are cut round the ramp. Doors and windows in such a wall keep their piece.
- **Stairs**: the well in the slab above is cut only over the steps that need it — 7'-0" clear over every step and landing (`stair_head`); the lower steps stay under the slab.
- **Foundation type** (section 6): isolated pads + strips (as before), isolated footings, strip footings, combined footings (columns whose pads would touch or come within 1'-0" share one rectangular footing), or a raft (2'-0" thick, 2'-0" past the walls by default). The foundation plan's note counts each kind.
- **Ground floor level and floor height** sit right under «Select floor on drawing…»; defaults +2'-0" and 10'-0" (projects from before take the ground floor at +2'-0" too; 0 = as the CAD's level note).
- **Overlap floors: «Plot + shoring (site)»** in «Level to move» / «Level to rotate»: the plot (its setbacks, boundary wall, the shoring along it) and the excavations moved, laid over a level (centres or lower-left corners together) or turned.
- Fix: a slab cast over a floor crashed «Edges, railing, sun shades…» and the shaft dialog (levels' heights read wrongly).

## 3.14.1
- **Isolate level works**: IngeTrazo draws a group whatever its layer's visibility, so 3.14.0's hidden layers changed nothing. Now the other floors' elements (and the plot, site, other floors' slabs) are hidden themselves; the level stands on its floor slab and the slab cast over it is taken off so it can be seen into. «Show all» shows everything again.
- **Floors as groups** (checkbox beside Select level): each floor's whole 3D model one group «Level · Ground Floor» — move, hide, copy or export a floor as one; double-click a floor group to reach its elements. Off: the elements loose, as before.
- **Align beams with the columns**: right-click a beam (or a column: all its beams) ▸ «Align beam(s) with the columns» ▸ left / top face, centre, or right / bottom face of the columns at its ends.
- **Update floors and levels (all levels)** under Floor height: every storey set to the floor height typed and the ground floor to the level typed (the CAD's level notes still applied when that option is on), then the model, stairs and ramps made again — like Update from CAD, for the levels.
- **Shoring along**: the plot limits, or round the basement's outer (RCC) walls (one shoring all the way round, just outside them).
- **Sliding windows**: no pulls on the panels (doors keep theirs).
- **Shafts on a drawn rectangle**: draw a rectangle on a slab (Rectangle tool), select it, right-click ▸ «CAD2IngeTrazo · Shaft» ▸ «Open a shaft here», «… through every floor», or «Close the shaft / opening here» (the openings it covers closed again).
- Fix: the panel's buttons are called with no arguments — «Isolate level» ran as «Show all» and «Basement outer walls → RCC» as «Undo RCC» (Qt's «checked» flag landed in their first argument).

## 3.14.2
- **Walls attached / detached** (Edit properties ▸ Top / Bottom, or right-click ▸ Attach / detach for every wall selected): top attached = up to the slab over its floor (follows the storey), detached = its own height (the clear height it had); bottom attached = standing on its floor slab (base 0), detached = its own base.
- **Shaft open / close by drawing a rectangle**: right-click a slab ▸ «Open a shaft — draw a rectangle on this slab» (or «… through every floor», «Close a shaft / opening — draw a rectangle round it»), then click two opposite corners on it — a dashed rectangle follows the mouse, Esc cancels. Also in section 6 (select a slab first). 3.14.1's way needed IngeTrazo's Rectangle tool and selecting a face lying on the slab, which picks the slab instead.
- **Stair opening in the slab above** (section 7): following the railing (each flight that needs headroom opened its whole length, so the opening's edge runs along its railing — the default), only over the steps short of 7'-0", or the whole stair outline.
- **Isolate level**: works from a plan view too (the 3D view's scene no longer puts the hidden floors back a moment later); with Floors as groups, the other floors' groups are hidden whole.

## 3.14.3
- **Corner windows** found on import: glazing drawn outside the walls, double lines turning a corner — square or with a 45° chamfer — from one wall to another (door leaves at an angle and single lines left out). Each leg becomes a window wall «Corner window n»: a curtain wall with an opaque panel under the sill and over the head, glass between, so the glass turns the corner. Mr. Zahid's ground floor: 3 corner windows (8 legs). Section 1 ▸ «Find corner windows (this level)» adds them to a level already imported (rooms and edits kept); a new import finds them by itself.
- **False ceilings**: a ceiling set only on rooms (the room's Edit properties) was never built — only a level's ceiling was looked for. Fixed.
- **Shafts**: a shaft drawn by hand was cut again into the slab at every rebuild (the slab forgot which holes were hand cuts), so the same hole stacked up — three times over in your plan — and a slab with holes on top of each other is not drawn with them. Now each hand cut is made once; the same shaft added twice counts once; holes that overlap (a shaft over a stair well) are joined.
- Fix: a stair whose opening came out in two parts crashed the stair making on import («'MultiPolygon' object is not iterable»).

## 3.14.4
- **Corner windows in the wall line**: a corner window now closes the building's outline where a corner has no wall — glazing drawn double (the wall's two faces) that turns the corner and carries on the walls at both its ends. Each leg is put on that wall's centre line, made as thick as it (9" walls → 9" window wall) and run up to the wall's end, the two legs meeting at the corner. A bay window standing out from a wall is still found.
- **Covered by the slab / roof**: the slab over the floor (and the roof of that level) is carried out over the corner windows; a small block closed by them (a guard room) gets its own slab.
- **Glass inside the building is left alone**: shower screens and glass partitions (glazing that meets a wall square-on, inside the outline) are no longer taken for corner windows. Single lines, door leaves and stair rails are left out too.
- Mr. Zahid's ground floor: the entrance corner (by the living room) and the guard room corner — found; the two shower screens taken in 3.14.3 — gone. «Find corner windows (this level)» replaces the corner windows made before.

## 3.14.5
- **Corner windows are windows in a wall** (not a curtain wall): each leg is a wall like the one it continues (same type, thickness, height, finish) with a window in it — the import's window type, sill and height. The two windows meet at a small corner post. «Find corner windows (this level)» removes the old corner walls and their windows before adding the new ones.

## 3.14.6
- **Corner window = one aluminium window**: the glass turns the corner with no wall between — an aluminium frame (jambs at its two ends, sill and head running round the corner), a slim aluminium corner post (80 mm) where the legs meet, fixed glass panes with mullions at most 1.2 m apart. One element «Corner window n» in the model; its legs are walls «Corner window n · leg k» standing only under the sill and over the head (the window's sill and height: the import's window settings).
- **Doors stand on the threshold**: a door's frame and leaf now start at the top of its granite threshold (the finished floor) — not at the slab, where the threshold covered their foot. The hole in the wall still goes down to the slab, under the threshold.

## 3.15.0
- **Slab / roof edges tidied**: the outline loses the slivers the wall joints left and the points on a straight run (your ground floor slab: 107 → 51 corners), so far fewer edges on the slab. Right-click a slab ▸ «Tidy the slab's edges» for one slab; done on import.
- **Slab carried out to the columns**: a column or free-standing pier off the slab (up to 4 m) gets the slab over it — a pier in a corner pocket fills the pocket, a pier off one straight face pushes that whole face out to the column line (your porch: out to the front pillar). A column another slab holds is left to it; no slab grows over another. On import, and right-click a slab ▸ «Extend slab up to the columns».
- **Doors: jamb lining and architraves**: every hinged-type door gets a jamb lining over the reveal (both jambs and the head, the wall's full thickness) and an architrave on both faces of the wall (two legs and a head, 75 mm × 18 mm), in the frame's material. Sliding, rolling, garage and pocket doors and doors in curtain walls stay without.
- **Curtains at windows** (section 9 Rooms ▸ «Curtains at windows»): a rod with brackets over each window and two pleated curtains drawn open, on the room side; colour (cream, white sheer, grey, beige, blue, maroon) and length (to the floor / under the sill). Windows between two rooms are left bare.
- **Section box** (top ▸ «Section box», as Revit's): the 3D model cut to a box — six faces typed (X, Y, Z from / to), or «Whole model», «This level», «Selection» to set it, «Apply», «Off». What lies outside is not shown; what crosses it is cut at its faces. Saved with the project and undoable; its edges are drawn dashed orange in 3D.
- **Stair railings**: the inner railing of an L-shaped stair ran diagonally across the landing on the wrong side (the side nearest the stair's middle was taken — wrong for a long flight); now the side towards the next flight, turning at the inside corner. No more vertical jump at a landing (the rail runs on into the next flight). Posts are fixed down onto the tread under them (they stood on the pitch line, in the air between nosings).
- **Openings with no door drawn**: an opening the CAD shows empty (no swing, no glazing, no door block) is now an opening with no door — not a glass sliding door. Wider doors need a swing at each jamb with its leaf drawn (chairs and trees beside a gap were taken for door swings). Section 1 ▸ «Openings with no door drawn → no door (this level)» fixes a level already imported.

## 3.15.1
- **Section box grips**: the box now opens at once round the whole model with a grip on each of its six faces in 3D (an orange dot with an arrow pointing out) — drag a grip to move that face (it turns blue while you drag; 5 cm steps); the dialog's fields follow. The dialog still takes typed faces, «This level», «Selection», «Off».
- **Openings section**: «Find corner windows (this level)» and «Openings with no door drawn → no door (this level)» moved from section 1 to section 5 Openings.
- **Stair railing on the side away from the wall**: a flight with a wall along one side gets its railing on the open side (your 1st floor stair had it against the wall); sides open on both or walled on both keep the side towards the next flight.
- **Door frame and panel** (door's Edit properties): Frame width (its face, 0 = the frame material's), Frame thickness (its depth through the wall), and Door panel — flush, 2 / 4 / 6 raised panels, half glazed, fully glazed, louvred, ledged (vertical boards).
- **Terrace railings stay railings**: glazing-layer lines round a terrace drawn as just two lines, thinner than the walls they meet (the railing's outline, no glass), were taken for a corner window and built as a wall — your 1st floor terrace over the porch. Now a railing «Terrace railing n» (the parapet railing type; steel bars when that is «solid»).

## 3.15.2
- **Terrace railings all round**: every terrace of a level (the slab under it out past its walls) gets railings — along the railing lines the CAD plan draws there (window or rail layers, single or double lines), the terrace slab cut back to them (nothing beyond the railing), and on every other open edge. Each stands on a 3" × 6" upstand that runs down over the slab's edge. On import, and section 7 ▸ «Terrace railings from the CAD (this level)». Your 1st floor: 13 railings round the four terraces.
- **Wall plaster**: every wall gets a ½" plaster coat on both faces, carried up over the slab's edge — the slab no longer shows as a band on the elevations (section 9 ▸ «Wall plaster (each face)», 0 = none).
- **Stair railings in pieces**: each straight run of a stair railing (a flight, a landing edge) is its own component in the model — select one and Delete removes that piece only; right-click ▸ «Put back the railing's deleted pieces». Upstairs, a railing now guards the stair's opening in the floor (where no wall stands and not where the stair arrives).
- **Doors**: Edit properties shows the frame's real width and thickness (not 0). Door handle types: lever on a rose, lever on a back plate with lock, round knob, pull bar, D pull, flush pull, none — the handles' geometry redrawn (rose, neck, lever with turned end, plates, standoffs).
- **Curtains**: on by default (they were off in your model); section 9 turns them off.
- **Section box**: the cut walls, slabs, frames and railings show solid cut faces in their material's colour (a shade darker), not hollow shells.

## 3.15.3
- **Walls attached to the slab's underside** (by default): a wall stops under the slab over it; its ½" plaster carries on up over the slab's edge, and the slab's free edges (a porch, a cantilever, a terrace) are plastered too — no slab line on the elevations.
- **Terrace railing corners**: railings meeting at a corner run to the same point, with ONE common post on the corner, and their handrails and upstands carried on to meet full — clean edges.
- **Door ↔ window ↔ plain opening**: changing an opening's type (Edit properties ▸ Type, or right-click ▸ «Make it a…» door / window / plain opening, for every opening selected) gives it that type's own height, sill and kind (section 5's import values); its width and place stay. A plain opening (void) can be made a door or a window the same way.
- **Stray elements** (top ▸ «Stray elements…»): elements the CAD draws on a floor they are not on (no floor slab under them) are found and can be kept out of the 3D model — or put back; right-click any element ▸ «Not on this floor — keep out of 3D». A kept-out wall's doors and windows go with it.
- **Roof terrace** (section 7 ▸ «Selected slab → roof terrace floor», or right-click a slab): the slab becomes a roof terrace floor — a «Roof terrace» level over it when there is none, railings on 3" upstands along its open edges (one per straight run, corners joined), terrace tiles and rain-water outlets.
- **Materials from IngeTrazo's library**: a room's Edit properties take a Floor material, a Walls material (its walls' faces looking into it) and a Ceiling material from IngeTrazo's own material library (the Materials tray's swatches) — for every room selected; section 7 ▸ «Terrace floor material» for the terraces' floors.

## 3.15.4
- **Plaster inside the wall's width**: a wall's thickness is its total width with the plaster: the ½" coats are its outer ½" on each face, no longer added on top.
- **Every slab edge plastered**: all slabs (floors, slabs over, terraces, porches, roof) carry a plaster band all round — their outline AND their openings (stair wells, shafts) — flush with the walls' faces under them: no slab line anywhere on the elevations.
- **Sheet dimensions aligned**: on each side of a plan ONE straight chain — every corner and opening jamb seen from that side, on one line parallel to the side — and the overall size outside it; short extension lines; stations too close to read merged; the frame holds the dimensions, so the drawing's title sits under them. (They no longer re-snap to nearby points, which had pulled them out of line — «Make sheets» draws them again from the model.)
- **Zoom in the sheet view**: the mouse wheel zooms round the cursor (Shift + wheel scrolls), and a bar at the top right: − / + / Fit / fit width / 100 %.
- **Line weights of the sheets**: Sheets ▸ Line weights — cut, profile, edge, dimension (mm on paper); «Apply line weights to the sheets» changes the sheets already made; «Make sheets» uses them.
- **Model edges on / off**: top of the panel ▸ «Model edges» (and «Profiles») — the 3D view's edge lines shown or hidden (the host's Style menu follows).

## 3.15.5
- **Clean wall junctions**: where walls meet — a T, a butt joint, a corner, the joint across their tops — the line between them is hidden, in the 3D view and on the sheets; only the real corners of the walls show. The joint between a wall and the plastered slab edge over or under it, flush, is hidden too: no slab line on the elevations.
- **Terrace edges as a 3" wall** (default): the terraces' railings are built as a 3" thick plastered wall, the railing's height, corners mitred clean (section 7 ▸ «Terrace edge»: 3" wall, or railing on a 3" upstand).
- **Sheet units**: Sheets ▸ «Sheet units» — Metric (m, m², the default) or Imperial (ft-in, ft²), whatever unit the model is drawn in: the room areas, the schedules and the dimensions follow it.
- **Floors as groups** now sits beside «Model edges» / «Profiles» at the top of the panel.

## 3.15.7
- **Line weights in the sheet window**: the bar at the top right of the sheet window now carries Cut / Profile / Edge / Dim line weights (mm on paper), live on every CAD2IngeTrazo sheet; the panel's Sheets ▸ Line weights follow. (On screen a line never draws thinner than one pixel: zoom in, or print / PDF, to see thin weights.)
- **Slab commands with «Floors as groups»**: a whole floor selected, the element under the mouse is the one CAD2IngeTrazo works on — right-click a slab ▸ Extend slab…, Open / close a shaft by a rectangle, Edit properties… work without opening the floor group.
- **Terrace and roof-terrace edges**: the 3" parapet walls are solid plastered walls (they had come out as glass).

## 3.15.8
- **Handles on slabs** (and walls) to stretch them: select a slab — square handles on its corners (drag one to move the corner; Shift keeps it square) and on the middle of each edge (drag to push / pull that edge, square to itself; Ctrl: free). The corners and edges snap to the wall faces, columns and other slabs near them. Walls keep their end / middle handles. One Ctrl+Z each.
- **Inside «Floors as groups»**: a click on a floor picks the slab / wall under the mouse for CAD2IngeTrazo (our own ray cast through the floor), so its handles, its right-click commands (extend, shafts by rectangle, edit) and Edit properties work without opening the floor group.
- **Sheet units as the drawing** (default): the sheets write the drawing's own units — feet-inches and ft² for a drawing in inches / feet, m and m² for a metric one; Sheets ▸ «Sheet units» can still force Metric or Imperial.
- **Line weights in the sheet window**: the bar at the top right of the sheet window (zoom − / + / Fit / ↔ / 100 %, then Cut / Profile / Edge / Dim line weights) — an older bar left by 3.15.4 is replaced.

## 3.16.0
- **Handles on slab openings and shafts**: a selected slab shows blue handles on the corners and edge middles of its openings too (stair wells, shafts drawn by hand or from the CAD): drag to reshape the opening; a hand-drawn shaft follows on every floor it goes through. The opening stays inside the slab.
- **Handles on doors and windows**: a selected wall shows violet handles on each of its openings — the two jambs (width / position), the head (height) and the sill — dragged on the wall's own plane in 3D, the new size shown as you drag.
- **Object snap as AutoCAD's OSNAP** while dragging any handle: Endpoint □, Midpoint △, Intersection ×, Centre ○, Perpendicular ⊥, Nearest ⧗ on wall faces and centre lines, slab edges and openings, columns, cores, beams, shafts and door / window jambs — the marker and its name at the cursor. Top ▸ «Snaps…» switches each mode, the aperture and the whole snap on / off (kept for you); hold Alt to drag without snapping.
- **Shapes → openings**: a rectangle, circle or any closed shape drawn (Rectangle / Circle / Line tools) on the face of a wall becomes an opening there at once — a round hole for a circle; drawn on a slab's top, a shaft through it. The drawn shape is taken away; Ctrl+Z puts it back. Top ▸ «Shapes → openings» turns it off.
- **Floor finishes follow the slab**: a room's floor finish stops where its slab stops — a slab cut back, opened or reshaped takes the finish with it (and the finish carried out to the slab's edge follows a slab stretched out).
- **Stairs as the CAD plan draws them**: the stair's tread lines on any layer round the stair layer (the upper flight drawn on another layer) are traced with it, and no return flight or landing is invented when the plan's own treads climb the storey at 8" a riser at most — the stair keeps the plan's shape.
- **Furniture and fixtures from the CAD**: the plan's blocks — beds, WCs, washbasins, showers, bathtubs, sofas, armchairs, chairs, dining tables, desks, wardrobes, kitchen sinks, stoves, fridges, plants, trees — recognised by their names (English, Spanish, the usual CAD shorthands) or by their size and the room they stand in, set as the IngeTrazo library model of that kind nearest in size, at the block's place and turn, fitted to its footprint. On import, and section 9 ▸ «Furniture & fixtures from the CAD» / «Remove» (the pieces placed by hand stay).

## 3.16.1
- **Close an opening with its handles**: drag a slab opening's edge onto the edge facing it (or its corners together) and release — the opening is closed, the slab filled there (a hand-drawn shaft forgotten; a hole from the CAD kept closed when the CAD is read again). The same on a wall: a jamb dragged onto the other one, or the head onto the sill, closes the door / window ("release to CLOSE" shows while dragging).
- **Shapes → openings on slabs**: a shape drawn on a slab's top, its floor finish, or the floor under a slab cuts a shaft through that slab.
- **A model that will not build**: a face whose openings touch, overlap or close to nothing is now built with its openings cleaned (it stopped the whole rebuild before).
- **Stairs**: a stair's flights stop where the plan's next turn lands on another stair's treads (the stair down to the basement drawn beside it), and a stair drawn as an L (the plan cut above it) gets its third flight turning the same way again — a three-flight U as built.
- **Shafts named on the plan**: «GEN SHAFT», «IT SHAFT», «DUCT»… drawn as a box with an X on any layer are cut through the slab.
- **Furniture**: the library model for each fixture chosen better (a WC is a toilet unit, not a Turkish toilet; a hob a cooker…); blocks on window, column, AC, pipe… layers left alone; kitchen base cabinets along the walls the sink and hob stand on; and the bedrooms, living / drawing rooms and dining rooms the plan leaves empty furnished — a bed and a wardrobe, a sofa and a coffee table, a table and chairs — against the walls no door opens on (section 9 ▸ «Furniture & fixtures from the CAD»).
- **Plan views in the CAD's line weights**: with «The CAD's linework» on, a plan view shows the CAD's own line weights and types, the model's thin edge lines left out under them (back in 3D).

## 3.16.2
- The panel's title shows the version installed (it had stayed at 3.15.3).

## 3.16.3
- **Faster**: an edit (a handle dragged, a field changed) rebuilds in about half the time — the wall joins are worked out once per set of walls and kept, the hidden-seam pass skips elements nowhere near the edge it tests, and wall corners only test the walls within reach. The panel's refresh after an edit is ~30× quicker (the floor's gross area kept), and plan views draw about 3× faster (the CAD linework no longer re-reads the project on every frame; the room labels placed in one go). The model built is unchanged.
- **Furniture & fixtures from the CAD** moved to section 12 «Components (types)» as a checkbox, **off by default**: tick it to place the CAD's furniture and fixtures as library models (and on every import / update after), untick it to take them out (pieces placed by hand stay). «Place again» reads them again.

## 3.16.4
- **Stairs laid out by hand** (section 10 «Selected element», a stair selected ▸ «Flights and landings»): where the CAD plan was read wrong, set the number of flights, the risers in each, and how each flight turns off the landing before it — straight on, left / right 90°, U-turn left / right (seen walking up) — and turn the whole stair round its first step (⟲ / ⟳ 90°, or any angle). The landings are made again to fit every turn (a square at a 90° turn, both flights' width at a U, a flight's width straight on, and the arrival landing at the top), the storey height stays (the riser height follows), and the slab's well is cut again. «Mirror turns» swaps left and right; «Back to the CAD» forgets the hand layout. The layout set by hand is kept when the stairs are made again from the CAD.

## 3.16.5
- **Flights, rotation and landings…** is now easy to reach: right-click a stair ▸ CAD2IngeTrazo ▸ «Flights, rotation and landings…», the «Edit properties…» dialog of a stair, section 7 (the selected stair, else this level's), and at the top of section 10 when a stair is selected. Each flight's rotation (how it turns off the landing before it) and the whole stair's rotation are set there.
- **Railings locked to the flights**: the stair's railings are rebuilt on the new flights and landings, and the slab's old opening over the stair (a stair hole from the CAD merged into it too) is closed before the new one is cut — so the railing round the opening upstairs moves with the stair instead of staying on the old hole.

## 3.16.6
- **Stair railings on the right side**: the well (inner) side of each flight is now taken from the stair's own turns — a flight that turns left at its landing has its railing on its left, a right turn on its right, a straight run keeps the side before — so the railing no longer jumps to the outer edge or cuts diagonally across a landing after the stair is laid out or turned by hand. (Stairs read from the CAD still leave a side running along a wall open.)
- **The total number of steps kept**: in «Flights, rotation and landings…», raising one flight's risers takes them from the next flight (from the one before for the last flight), lowering gives them back — the storey's risers stay the same.

## 3.16.7
- **Stair finish follows the slab's floor finish** (section 7 ▸ «Follow the slab's floor finish», on by default): the stair climbs from the finished floor below to the finished floor of the slab it arrives at — each taken from the floor finish there (the room's own, the slab's own, else the default) — with all risers equal between them, and its tread and landing finish takes that slab's finish thickness. No more short step at the top or a first riser half buried in the floor finish.
- **Finish and nosing per stair in «Flights, rotation and landings…»**: the tread / riser / landing finish (marble, granite, terrazzo, porcelain, timber, bare) and the nosing type (square, bullnose, pencil round, chamfered, flush, square with anti-slip strip) of that stair. (The defaults for every stair stay in section 7.)

## 3.17.0
- **Slabs as floors** (new default, section 6 ▸ «Slab position: Under each floor»): each floor's slab is that floor — its top at the floor level, that floor's finishes on it (not on the floor above). The floor's walls run down to the slab's bottom, over its edge, so the slab sits flush inside the external walls and the outer face runs on in one plane; a thicker or thinner slab and the walls follow by themselves. Default slab thickness **4"**.
- **Ground floor on the ground**: no concrete slab under the ground floor by default (section 6 ▸ «Ground floor slab» to add one) — its floor finish covers the whole slab outline: every room, the verandah, the entrance lobby and the car porch (a ground floor with parking was left unfinished outside its rooms before).
- **«Update floors and levels»** also re-spaces each stair's risers to its storey height, so the stairs still land on the floor above when the ground floor level or a floor height changes.
- **Stair landings**: the step up onto a landing gets the same nosing as every tread — the chosen type (square, bullnose, pencil, chamfer, anti-slip strip…) — instead of a plain square edge.

## 3.17.1
- **Winders**: a turning landing the plan splits with a diagonal from corner to corner (on any layer but walls, doors, windows, grid, columns) is made two triangular winder treads, a riser apart, with the riser and the nosing along the diagonal — the stair's risers re-spaced to the storey (re-made with «Stairs on all floors»).
- **Ground floor finishes edited with handles**: on the ground (no slab), click the floor finish outside the rooms — the verandah, lobby, car porch — and its outline's handles appear on the finish: drag corners and edges, extend or open it as a slab's; the finish follows.
- **Floor slab flush with the floor below**: with slabs as floors, an upper floor's slab is carried out flush with the outer faces of the walls and columns of the floor under it — it caps that floor as its roof too (on import, and when a project is turned to slabs as floors).
- **4" slab thickness by default**: the panel no longer brings back a slab thickness saved before 3.17.

## 3.17.2
- **Each floor's slab is its own**: the floor slab reaches out to that floor's external walls, columns and terrace railings (as drawn on that floor's plan) — no longer carried out over the floor below (3.17.1 undone).
- **Terraces and balconies railed all round on a 1'-0" upstand**: the default terrace edge is now the railing on a 3" thick upstand wall, 1'-0" high (section 7 ▸ «Upstand under the railing»), run down over the slab's edge; the «3" wall» stays as the other choice. Changing either restyles the railings already made. A ground floor on the ground gets no terrace railings.
- **Winders' soffit**: the two winder treads of a turning landing share one flat soffit (the lower one's), and the flight leaving them starts its waist from it — no more stepped, folded underside.

## 3.17.3
- **The roof over the top floor is a slab like the floors**: with slabs as floors, the top floor gets its roof slab (flush with the outer faces of its walls) — or section 8 ▸ «Flat with parapet» ▸ «Roof over the top level» makes it, its thickness and parapet height as set there. It has a **floor finish** layer on top, the slab **handles** (click its finish), **openings drawn on it** (a rectangle / circle / any shape drawn on the roof cuts it), an opening over each stair coming up from the top floor, and a **parapet round its edge** in the terrace style (railing on the 1'-0" × 3" upstand, or the 3" wall).
- **A parapet round every drawn opening**: each opening drawn on a floor or the roof gets the terrace parapet round it, standing on the slab beside the hole — it follows the opening's handles and goes when the opening is closed.
- **Face → slab**: a flat face drawn in the model (Rectangle / Line tools) — right-click ▸ «CAD2IngeTrazo · Face → slab», or section 10 ▸ «Selected face → slab» — becomes a slab of the floor it lies at (raised / sunk by the difference), or of the roof over the top floor; the drawn face goes.

## 3.17.4
- **The roof slab only when asked**: the roof slab over the top floor is made only by section 8 ▸ «Flat with parapet» ▸ «Roof over the top level» (3.17.3 made it on every project by itself). Delete it and it stays deleted; a hip / gable roof or «No roof» takes it away too. Once asked for, it moves up with the top floor when a floor is added.

## 3.17.5
- **Terraces over the floor below, as before**: where the floor below reaches out past a floor (its outer walls, columns and its own outline — porch, verandah), that floor's slab is carried out over it, flush with them — a terrace — then cut back to the railing lines drawn on that floor's plan and railed round its open edges (railing on the 1'-0" × 3" upstand). Made on import of a floor; the roof slab over the top floor still only when asked.

## 3.17.6
- **Walls attached to the slab, always**: a floor's depth — where the walls of the floor below stop and where this floor's walls reach down to — is now its main slab's (the largest one). A small slab piece sunk or raised on a floor (a toilet, a drawn slab) no longer set it for the whole floor, which left the walls below short of the slab's underside.

## 3.17.7
- **Railings edited with handles, like walls**: the roof-edge railings and the railings round drawn openings keep a handle edit (moved, stretched, trimmed) — they are made again only when what they follow changes (the roof's outline, an opening, the railing settings). Terrace railings had the wall handles already.
- **A face made a slab: its finish on it**: a face drawn above or below a floor becomes a raised / sunk slab part whose floor finish sits on it (it hung at the floor's level before); a face drawn on a floor or its finish becomes level with the floor.
- **A railing edited by hand stays as edited**: once a roof-edge railing or an opening's railing is moved or stretched with its handles (or changed in its fields), that set is kept as plain railings — the roof's edge (or that opening) is no longer railed again by itself.
- **Ground floor outside finishes: a drop option** (section 9 ▸ «Ground floor outside finishes lower by»): the verandah, entrance lobby and car porch finish set lower than the rooms' — a step down at the doors (0 = level, the default).

## 3.18.0
- **Language** — the 🌐 box beside the extension's name: the panel in the world's ten most spoken languages (English, 中文, हिन्दी, Español, Français, العربية, বাংলা, Português, Русский, اردو) — section titles, buttons, check boxes and field labels; tooltips stay English. Remembered.
- **Newer version?** — the ⟳ button beside the name reads the version in the IngeTrazo extension catalogue and tells you when it is newer; install it from the Extension Manager.
- **Numbered sections, closed on every launch** — 1 Import … 13 Plans, sheets and export (1.1 / 1.2 the import settings and layers).
- **Ground floor outside finishes 1'-0" lower by default** — also in section 6 under «Ground floor slab» («Ground floor outside finishes drop»), and still in section 9.
- **Foundation platform** (section 6, on by default): with slabs as floors and no ground slab, the ground floor stands on a filled platform (PCC) from the natural ground up under its finishes — the ground F.F.L. (2'-0", with the 2" finish) under the rooms, 1'-0" lower under the verandah / lobby / porch; the ground floor's walls run down to N.G.L. With a basement it becomes a slab like the other floors' (the ground floor slab turns on by itself).
- **Entrance steps and the porch ramp** (section 6): every door out of the ground floor (main, side, back) gets steps from the platform's edge down to the ground in line with it (risers ≤ 7", treads 11", the door's width + 1'-0"); the car porch a ramp from its open edge towards the gate / road (1 : 6). The CAD's level notes (LEV. +x'-y", FFL …) still set the floor's parts' levels — the platform and steps follow them.
- **Gate from the IngeTrazo library**, moved as a block: each gate is the library's Gate model (two mirrored leaves on a wide gate) grouped with its two gate pillars — «Gate n (with its pillars)». Move the block with the Move tool along its wall: the gate's place in the boundary wall follows (its opening, the pillars, the swing).
- **The CAD as AutoCAD shows it in «Select floor on drawing…»**: every line in its colour, line weight and line type (by entity, layer or block, LTSCALE applied) — the walls, windows and hatches told apart; layers turned off stay hidden.
- **The CAD's linework on the sheets' plans**: «Make sheets» lays the level's CAD linework over each plan, at its plotted line weights and line types (300 dpi, as in the plan view).
- **Parking marks on the finished floor**: the bay lines, car numbers and cars stand on the floor finish (on the porch: the lowered outside finish), no longer hidden under it.
- **Stairs: faces the right way out** — finish pieces that came out inside-out (dark from outside) are turned outward; and a stair marked only DN on a floor's plan (the stair from the floor below, seen going down) no longer makes a second stair climbing from that floor.
- **Glazing that is the wall, with a door drawn in it**: where the window layer draws the wall (a corner / bay glazing with no wall lines) and the plan draws a door in it, that glass becomes a curtain wall with the door set into its grid where drawn.
- **Kitchen cabinets with «IngeTrazo Kitchen Maker»** (section 9, needs that extension): each room named KITCHEN gets Kitchen Maker's parametric cabinets — base run with worktop along the longest free wall and the wall turning off it, the sink under the window, the hob apart, a tall fridge unit at the end of a long run, wall cabinets where there is no window — fronts to the room, backs to the walls, doors and their swings kept clear. They stay Kitchen Maker's cabinets (select one: Edit, Add next, Finishes…); fitted again, they are replaced.

## 3.19.0
- **The main entrance at the rooms' floor level, its steps as the CAD draws them**: the entrance steps drawn on the plan's stair / step layers outside the rooms (a short run — too few to be a stair) are built where drawn, as many risers as lines, from the floor down to the ground; the lobby / landing at their top is at the internal floor level (the rest of the outside — porch, verandahs — keeps the 1'-0" drop). No steps are added by a door the CAD already draws steps for.
- **Low-poly furniture, fixtures and cars by default** — a light model to work in (each library model reduced to a few hundred faces, its shape and colours kept); **High poly (render)** beside «Profiles» puts the full models back for rendering.
- **Furniture facing the rooms**: beds, WCs, basins, sofas, wardrobes, cabinets, fridges, cookers, sinks, desks, TVs, showers and baths stand with their back to the nearest wall, facing into the room — the CAD block's place and size kept; the beds, wardrobes and sofas placed in empty rooms likewise.
- **«Select floor on drawing» as AutoCAD shows it**: each line in its layer / entity colour, its line type and line weight (AutoCAD's lineweight display — thicker as you zoom in, as plotted). The plot style table the drawing names (e.g. monochrome.ctb) is read from AutoCAD's Plot Styles folder: a pen weight it sets is used. A drawing read before is read again (an old read in memory no longer stands in).
- **Sheets**: the CAD linework over each plan at its plotted weights (made again with «Make sheets» — sheets made before 3.18 are outdated).
- **What the hidden (dashed) lines mean**, read on import (and once on the project now):
  - across an opening with no door or window drawn in it: a plain opening (no door, no window — door height); crossing it (an X): an arch, no door;
  - in a window's opening, with its glazing: a high window (6'-0" sill, 2'-0" high — a ventilator);
  - outside an outer wall by a window: its sun shade (chajja), as deep as drawn; longer runs: the slab's projection (the slab follows them, as before);
  - in a stair: the flight going up (not built twice);
  - crossing in open floor: the slab cut there (as before).

## 3.20.0
- **Hidden-line rules always applied**: every opening is read against the plan's hidden lines once — at import, on «Update from CAD», and on the next rebuild for openings not read yet (a project imported before) — so plain openings, arches and high windows no longer come back as sliding windows; an opening changed by hand stays as changed.
- **Stairs as the plan draws them**: a floor whose plan has its own import but draws no stair gets none (no stair copied up from the floor below, none designed in a room named STAIR on the top floor); a stair whose first step is outside (a verandah, the back passage) starts at that floor's level there — its risers spread over the extra height.
- **Cars on the porch's own floor**: placed on the finished floor where the bays are (the porch's lowered level), also when the parking has no bay lines.
- **Sheets**: the model's cut lines on a plan take the CAD's wall line weight (its heaviest pen with many lines), and the CAD linework is drawn in black at its plotted weights (0.00 mm as the thinnest pen, 0.05 mm).
- **Boundary wall designs** (section 4): plain, with coping, plinth band + coping, low wall + MS grille over it, piers along the sides + coping (pier spacing); finishes: plaster cream / white, exposed brick, stone cladding, fair-faced concrete; caps on the pillars.
- **Solid parapet designs** (section 7 ▸ «Solid parapet design»): plain, coping, coping + a band under it, coping + a 1'-0" MS grille — on every solid terrace, roof, balcony and opening parapet.
- Low-poly trees and plants keep their leaves green (the texture's colour taken from its opaque, coloured pixels).

## 3.20.1
- The ⟳ update keeps the current version as a dated copy beside it (`cad2ingetrazo_backup_<date>_<time>`) and writes the new files over the old ones — it never deletes a folder.

## 3.21.0
- **Steps and stairs apart**: the STEP layer (its own role, «Steps» in 1.2) is steps — a few risers to another level of the same floor (to a raised hall, a mimber, a verandah), inside or outside the rooms — built like the stairs' treads (concrete, the stair finish with its nosing over the riser, the riser's finish) and **without railings**; only the STAIR layers make staircases. Each run of steps goes from the level at its foot to the level at its top (a U of steps round a porch: each side its own run); with no level difference noted (a mimber), up from the floor, a riser per line, the top at the wall.
- **The LINE layer by where it lies** («Lines» in 1.2): a line in a wall's thickness, along it — a **CNC grille (jali)** in that opening (a wall with no opening there gets one); an area its lines close round — a **low platform** at the level its LEV. note gives (several notes: each part at the nearest), else 1'-6" over the floor; a closed strip under 0.4 m wide, or any other line outside the walls (two faces paired) — a **low wall** (2'-0"; both heights in section 6).
- **Doors and windows from their symbols**: a door swing (an arc on the door layers with its leaf; a pair of leaves meeting = a double door) or a window's glazing band standing between two walls / piers / columns, with no wall line drawn along it, gets a wall of its own exactly as wide, holding it; a gap read as «nothing drawn» under a swing becomes the door. Piers drawn as closed boxes on the wall layers become solid piers.
- **Floor levels from the level texts**: the floor's level is the note in its big hall / rooms (a note counts by the room it stands in; a stair's «MID LANDING / LEV. 14'-0"» never counts) and sets the ground F.F.L. field; the floor round the rooms is cut by the walls into its areas (hall, lobby, ablution, verandah…), each at the level noted in it — an area noted at several levels shared out to the nearest note; the platform, the steps and the entrance steps follow those levels. Text layers named TEX are read.
- **Round columns from the library**: a circle on the column layers (two round one centre: one column, its shaft the smaller) is a round column, built with the IngeTrazo library's round porch column — its shaft as thick as the circle, base and capital wider.
- **Arch shapes** (section 5 ▸ «Arch shape», and right-click ▸ Head ▸ Arch top): semicircular, segmental, elliptical, **pointed (Islamic / Gothic)**, **ogee (Mughal)**, **horseshoe (Moorish)**, **multifoil (cusped)**, **trefoil**, **four-centred (Persian / Tudor)** — for arch-top doors and windows and for the arches over openings with no door; «Openings with no door / window: arched» arches the plain openings.

## 3.22.0
- **Rooms close as the plan draws them**: walls that stop short of one another across a column, a pier or a window band still close a room (gaps up to 0.5 m, the columns counted with the walls) — a prayer hall bounded by piers and glazing is a room, with its floor finish and its level; two walls facing each other on one line across columns / an arch opening are joined, the open spans becoming plain openings (the hidden lines then make them arches); a wall end stopping short of a wall ahead is carried into it. Rooms are named by their text, not by a level note or UP / DN.
- **Steps round their corners**: the STEP layer's riser lines are read whole (an L or a U of steps round a porch is one riser each), every tread swept on round the corners (mitred) with its nosing and riser finish following; each run goes up to the floor it climbs to, and the landing between the top step and that floor (a porch round its columns) is built at the top level.
- **Arched windows from their blocks**: a door / window block named ARCH (MEHRAB, KAMAN) arches the opening under it.
- **Arch any opening**: section 5 — «Arch the selected openings», «Arch every plain opening of this level», «Flat heads again»; «Selected element» shows the arch shape and the grille of an opening.
- **Lobby fins**: a row of short wall ends with wide empty gaps between them is no longer read as one wall with openings.
- **Domes** (section 8 ▸ Domes): hemispherical, onion (Mughal), pointed / ogival, bulbous (Persian), shallow saucer (Ottoman), ribbed (melon), conical — any diameter (or as big as the room allows), height over diameter, a drum under it, a gold finial, finishes (white, gold, green or blue tiles, copper, sandstone); over the room clicked (else the level's biggest) or at an X, Y; each can be changed or removed from the list.

## 3.23.0
- **Minarets** (section 8): a square shaft, an octagonal then fluted round shafts between one to three corbelled galleries with their red balustrades, an open lantern, a bulbous / onion / conical cupola and a gold crescent finial — any height and base; at the selected columns or at X, Y.
- **Chhatris**: small domed kiosks on four posts, spread along the selected walls on the parapet, or at their corners.
- **Domes on a raised base**: a square block and stepped tiers under the dome (the elevations' «Y» detail); a dome can stand higher than the roof (its base offset).
- **Arch voussoirs**: ablaq (dark / light stones in turn) or a plain stone band round an arched opening, on both faces («Selected element» ▸ Arch voussoirs; section 5 for the import).
- **Arcade over the selected columns** (section 5): a wall standing on a row of columns (pairs count as one pier), an arched opening of the chosen shape in each bay — a portico, a riwaq.
- **Rows of small arched openings in the selected walls** (section 5): a clerestory / attic band, in groups, with CNC grilles.
- The roof level's parapet follows the building's main body when its outline pinches.

## 3.23.3
- **The ⟳ button only checks for a newer version.** It reads the version listed in the IngeTrazo extension catalogue and tells you when it is newer than yours; you install it from IngeTrazo's Extension Manager, which checks the download against the catalogue's SHA-256. The extension no longer downloads its own code or writes over its folder. (Earlier versions' update copies, `cad2ingetrazo_backup_…`, are still renamed `_cad2ingetrazo_backup_…`, so IngeTrazo never loads them as a second extension.)
