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
