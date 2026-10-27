# CAD2IngeTrazo — User Manual

Version 3.11 · M. Tariq · October 2026

## 1. Introduction

CAD2IngeTrazo turns your AutoCAD floor plans (DWG or DXF) into a complete, editable BIM model inside IngeTrazo — walls, doors, windows, columns, slabs, lift cores, stairs, ramps, parking, rooms and finishes — one level at a time, stacked into a building.

It is built for architects and BIM teams who already draw plans in CAD and want a 3D model, plans, sheets and a SketchUp export without remodelling by hand. You keep working in CAD; when a plan changes, **Update from CAD** reads it again and the model follows.

What it does for you:

- **Reads the CAD plan by its layers** — walls, doors, windows, columns, stairs, lifts, parking, ramps, text and level notes are recognised automatically (you can correct any layer's role).
- **Builds every floor** at its true height, with the slab cast over each floor, lift wells and shafts open through every slab, and stairs and ramps running floor to floor.
- **Names every element as a component type** (D-01 doors, W-01 windows, C-01 columns…), so you select and change a whole type at once.
- **Lets you edit anything** with a right-click: its type, size, frame, head, leaves, or turn a wall into a curtain wall.
- **Produces plans and sheets** with the CAD's own line weights and line types, and exports to DXF and SketchUp.

This manual covers version 3.9 and later. Lengths follow the model's units: feet-inches (6'0") in an imperial project, metres otherwise; you can type either.

## 2. Installing and opening the plugin

Install once by extracting the package into IngeTrazo's plugins folder; restart IngeTrazo and the plugin is there.

1. Close IngeTrazo.
2. Extract `cad2ingetrazo_<version>.zip` into `%APPDATA%\ingetrazo\plugins\` so that you get the folder `%APPDATA%\ingetrazo\plugins\cad2ingetrazo\`. Replace the old folder when you update.
3. Start IngeTrazo. The **CAD2IngeTrazo** panel opens on the right, with the version number beside its name.

Where to find things:

| Item | Where | What it does |
| --- | --- | --- |
| CAD2IngeTrazo panel | Right-hand dock | All plugin settings, in numbered sections that fold open |
| Level list | Top of the panel | The level you are working on; **＋ Level (new, above)** and **＋ Basement (new, below)** add one |
| 3D / Plan / Sheets | Under the level list | Switch the view of the picked level |
| Plugin toolbar | Second toolbar row | Plugin icon, 3D, Plan, Sheets, SketchUp export |
| North arrow | Top-right of the 3D view | Shows the project north; set it in **3 Project and levels** |
| Python console | `Ctrl + Shift + P` | For support scripts only — you do not need it for normal work |

Units: the plugin follows the model's units. An imperial project shows and accepts feet-inches (`9'10"`, `6"`); a metric one shows metres. You can type either kind in any length box (`3.0`, `300cm`, `9'10"`).

Undo: every plugin action is **one Ctrl+Z**, however much it rebuilt.

## 3. Quick start: from a CAD plan to a 3D building

A two-floor house takes about ten minutes; a tower takes longer only because of its size.

1. **Pick the file.** In **1 Import CAD plan**, click **…** beside *File* and choose the DWG or DXF.
2. **Check the floor height.** *Floor height (floor to floor)* is 9'10" by default; type yours.
3. **Pick the floor on the drawing.** If the file holds several plans side by side, click **Select floor on drawing…**, drag a box round the ground floor plan, then click a reference point you can find on every plan (a grid intersection or a building corner), and **Use this floor**. One plan per file: skip this step.
4. **Import.** With *Level 1* picked at the top of the panel, click **Import to «Level 1»**. The report under the button lists what was found: walls, doors, windows, columns, slab, stairs, parking.
5. **Next floor.** Pick **＋ Level (new, above)** in the level list, select the first floor's plan on the drawing (same reference point), and import. Repeat for each floor; basements use **＋ Basement (new, below)**.
6. **Stairs, terraces, roof.** In **7 Stairs, terraces and balconies**, click **Stairs on all floors**, then **Terraces over the floors below** if upper floors step back. Add a roof level from the level list if you want parapets on the top.
7. **Look and adjust.** Orbit the 3D view; right-click any element to change it (see section 10). Use **3D / Plan / Sheets** at the top of the panel to switch views.
8. **Save** with *File ▸ Save*. The plugin's data is saved inside the IngeTrazo file.

When the CAD plan changes later, save it in AutoCAD and click **Update from CAD (all levels)**: every level is read again with the settings it was imported with.

## 4. Importing CAD plans

Each level is read from its own plan: a whole file, or one part of a drawing that holds several plans. The plugin remembers, per level, the file, the part, the base point and the settings, so **Update from CAD** can read it again later.

### Files the plugin reads

- **DXF** — read directly.
- **DWG** — converted first. If IngeTrazo's own converter cannot read a DWG (some AutoCAD 2013+ files), the plugin asks **AutoCAD's console engine** on your PC to convert it in the background (no window opens). It keeps the converted copy in `%LOCALAPPDATA%\ingetrazo\c2i_dxf` and converts again only when the DWG changes. Without AutoCAD it tries the free ODA File Converter, then a DXF of the same name beside the DWG. The diagram at the end of this section shows the order.

### The import options (section 1)

| Option | What it sets | Default |
| --- | --- | --- |
| Drawing units | The CAD's unit (mm, cm, m, inch, foot) | Auto: from the file's header, checked against the wall sizes |
| Model units | The units the model shows | As the CAD plan |
| Base point | Which drawing point becomes the model's 0,0 | Drawing origin; *Select floor on drawing* sets your reference point |
| Insert at X, Y / Rotation | Where and how the plan lands in the model | 0, 0, 0° |
| Wall thickness min / max | The range of parallel lines read as walls | 3" to 18" |
| Detect layers automatically | Reads every layer's role from its name | On |
| Floor levels from the CAD's level notes | Reads notes such as `LEV. +4'-0"`, `FFL`, `RL 102.50` | On |
| Floor height | Floor-to-floor height of the level being imported | 9'10" |

### Layers and what they make

With *Detect layers automatically* on, each layer's role comes from its name: `*WALL*` walls, `*DOOR*` doors, `*WIN*` windows, `*COL*` columns, `*STAIR*` stairs, `*LIFT*` lift cores, `*PARK*` parking bays, `*CAR*` cars, `*RAMP*` ramps, `*GRID*` the column grid, text layers for room names and notes. To correct a role, open **Layers and materials (finishes)**, click **Read layers**, change the *Makes* column, click **Use these roles**, then **Update from CAD**.

### What a plan can tell the plugin

- **Level notes** (`LEV. +4'-0"`): the floor's own level, and areas of the floor at other levels (sunk toilets, a raised lobby).
- **A dashed (hidden-line) X** over an area: an opening cut through the slab there.
- **Doors drawn without a swing** and openings down to the floor: glass sliding doors.
- **Parking bays, car blocks and ramp lines**: parking with library cars, numbered bays and continuous ramps.

### Multi-floor drawings

When one drawing holds every plan side by side, use **Select floor on drawing…** for each level. Drag a box round that floor's plan, then click the same reference point on each plan, such as a grid intersection. All floors then stack exactly.

The first way that reads the DWG wins. AutoCAD's conversion is cached, so a large drawing is converted only once until you save it again.

## 5. Levels: adding, overlapping and rotating floors

Levels stack from the ground floor up, each at the height of the one below plus its floor height. Basements go below the ground floor.

- **Add a floor:** pick **＋ Level (new, above)** in the level list, then import its plan.
- **Add a basement:** pick **＋ Basement (new, below)**, then import.
- **Names and heights:** edit them in **3 Project and levels**. With *Floor levels from the CAD's level notes* on, a plan's `LEV.` notes set its level.

### 2 Overlap floors

Use this when two plans were imported but don't sit over each other. That happens when the plans were drawn side by side without a common reference point.

1. **Level to move:** the floor that moves. It defaults to the level picked at the top, or the last floor imported.
2. **Over level:** the floor it lays over (by default the one below).
3. **How:**
   - **Best fit** moves the floor so the most wall corners meet. It is the most accurate.
   - **Lower-left corners together** and **Centres together** are quick alternatives.
4. Click **Overlap**. Or type an X, Y distance and click **Move the level**.

### Rotating a floor

Under *Rotate a floor*, pick the **Level to rotate**, type an angle (positive = anticlockwise) and click **Rotate the level**. Or use the quick turns **↺ 90°**, **↻ 90°** and **180°**.

The floor turns about the middle of its walls, with everything on it: walls, openings, columns, stairs, parking, ramps, rooms and texts. A later re-import of that plan lands at the same angle. If plans were drawn at different angles, rotate first, then overlap with *Best fit*.

**Show greyed out** (at the top of section 2) draws the floor below and/or above greyed under the plan you are looking at. It's useful for checking alignment, and it doesn't change the model.

## 6. Walls, doors and windows

Walls come from the plan's parallel wall lines, and their thickness is read from the drawing. Doors and windows come from the door and window symbols and are set into their walls.

### Door and window types

Set the defaults for an import in **5 Openings**, then change any single one by right-clicking it.

| Setting | Choices | Default |
| --- | --- | --- |
| Window type | Sliding, casement, fixed glass, louvre, top-hung | Sliding |
| Door type, single leaf | Hinged (flush), main door, glazed, hinged glass, glass door with aluminium frame, louvred aluminium, pocket, folding | Hinged |
| Door type, double leaf | The same hinged types, two leaves | Hinged |
| Leaves | Single up to 4'-0" wide, double up to 8'-0", sliding above (or set per door: single / double) | By width |
| Head | Flat, transom light, arch top | Flat |
| Frame | Wood (chowkat), aluminium, steel, uPVC | Wood for hinged doors; aluminium for sliding doors and windows |

Other door types: sliding glass doors, rolling shutters and garage doors. Every door has handles. Sliding doors and windows have their pulls on the frame side of the end panels, never where panels meet. A door with a transom or arch is raised so its leaf stays a full 7'-0".

### Moving and adding openings

- **Move** a door or window with IngeTrazo's Move tool along its wall: the hole follows.
- **Add** one: select a wall, then in **5 Openings ▸ Add one to the selected wall** choose its type, width and position, and click **Add to selected wall**.

### Curtain walls

To make a curtain wall, right-click a wall ▸ *Convert*, or select walls and click **Selected walls → curtain wall** in **10 Selected element**. The wall becomes glass on an aluminium grid. Its windows are removed, and its doors are fitted 4'-0" to 8'-0" wide, keeping their own door type.

In a curtain wall's edit dialog you set:

- the mullion spacing
- the transom spacing
- the lower and upper panel heights
- whether those panels are glass or spandrel

**Doors in a curtain wall:** right-click the curtain wall ▸ **Add door in this curtain wall…**.

- **Door type:** glass door in an aluminium frame (hinged), frameless glass door with patch fittings, or sliding glass door.
- **Leaves:** by width, single or double.
- **Width:** 0 = one bay of the grid (two bays when a bay is under 3'-0").
- **Centre from the wall's start:** where along the wall it goes.

The door snaps to the grid, centred on a bay or a mullion. It takes the nearest place free of other doors. The mullions, transoms and glass stop around it, and a transom closes its head. **Add to selected wall** in section 5 does the same when the selected wall is a curtain wall.

### Turning a wall into a railing

Any wall can be built as a railing instead of masonry. Right-click it ▸ *Edit properties…* ▸ **Build as railing**, and pick a type (see section 8). Use this for a balcony edge or a terrace parapet you drew yourself.

### Editing part of a wall

To change only a stretch of a wall (a glazed part, a lower part, a railing at a balcony), right-click the wall ▸ **Edit part of this wall…** and give **From** and **To** in metres from the wall's start (the dialog shows the start and end points). That stretch becomes a wall of its own, with the same type, height and thickness. Doors and windows go with the part they stand in. If a cut would fall through an opening, it moves to clear it. Then pick what happens next:

- **Edit its properties** opens the new part's fields.
- **Make it a curtain wall** converts only that part.
- **Make it a railing** builds it as a 1 m railing of the parapet type.
- **Just split it** leaves the part as it is.

Only straight walls can be split.

## 7. Structure: slabs, sunk floors, columns, cores

Each floor's slab is cast **over** it, on its walls, as on site. The top floor gets its roof slab, and the ground floor stands on the ground. You set this in **6 Structure and foundation ▸ Slab position**; *Under each floor* is the older way.

### Slabs

- **Outline:** the plan's slab layer, else the outside of the walls (blocks a few feet apart get one slab each). Use **Auto slab on every floor** to remake them, with *Replace* ticked to overwrite.
- **Thickness:** *Slab thickness* (default 6").
- **Openings:** stair wells, ramp wells, lift shafts, duct shafts and areas under a dashed X are cut through the right slab automatically. Lift shafts stay open on every floor.
- **Several levels in one floor:** with level notes in the plan, rooms at other levels get their own slab piece at that level.

### Sunk or raised floor in one area

1. Type the difference in **Level ±**: minus sinks (a toilet, a pool), plus raises (a platform).
2. Select the area. Either click the rooms' floor finishes in the model, or draw a rectangle on the floor with the Rectangle tool and select it.
3. Click **Sunk / raise selected**.

That part of the floor is built at its own level and cut out of the slab that carries it. A room's sunk floor follows the room if its walls move. Delete the rectangle you drew afterwards.

### Columns, beams, cores, footings

- **Columns** are read from the plan's column layer, at their true size and angle. A floor without columns offers to add them at the wall corners. **Columns at wall corners (this level)** adds them later.
- **Beams:** **Beams on the walls (this level)**, with the width and depth you type.
- **Lift cores** are the RCC walls round each lift shaft. They are built like columns, with landing-door openings on each floor and a cabin drawn in plan.
- **Footings:** **Footings under the lowest level** puts pads under the columns and strips under the walls, down to the *Foundation level* (default −5'-0").
- **Roof:** pick **＋ Roof level (terrace, parapet)** in the level list for a flat roof with a parapet. Section **8 Roof** builds pitched (gable or hip) roofs.

**What is detected.** Columns are read from closed outlines, from loose lines that close a shape, and from circles on the column layers. Rectangles up to 15 m long (shear walls) become rectangular columns; L, T and C sections keep their own shape. A structural layer that names a run of floors, such as «S-CONC-4 FOUNDATION TO 6TH», is read as columns, not footings. Lift cores are found on the lift layers, and two cases are now covered:

- **A bank of lifts drawn as one U of wall** (no walls between the cars, only piers at the front) gets its shaft and a landing door at each gap.
- **A lift well drawn only with walls or columns** gets its shaft cut through the slab when a «LIFT», «LIFT WELL» or «ELEVATOR» text stands inside it.

## 8. Stairs, terraces, balconies and railings

Everything here is in **7 Stairs, terraces and balconies**.

### Stairs

**Stairs on all floors** builds a stair up to the next level on every floor and cuts its well in the slab. It reads the stairs from the plan's stair layer (treads, landings, dog-leg or straight). Without one it uses a room named STAIR…, else the floor below's stair. Risers fit the floor height exactly, and an arrival landing is added at the top.

| Stair type | What it builds |
| --- | --- |
| Monolithic RCC | Steps on a waist slab (default 6"), with nosings |
| Solid / masonry | Filled steps down to the floor |
| Open riser | Steel or timber treads on two steel stringers |
| Cantilever | Floating treads |

### Stair railings

Pick the **Stair railing** type, its **height** (default 3'-0") and its **sides**, then click **Apply stair type and railing**.

- **Inner side:** by the well, one continuous railing from bottom to top, joined across each landing.
- **Both sides:** a railing on each side of every flight.
- A single straight flight gets both sides.

Each stair and its railing are also **components** of their own (section 10). Right-click a stair, or its railing, ▸ *Edit properties…* to give that one stair its own stair type, railing type, railing height or sides. Right-click ▸ **Edit type «ST-03»** (or «RL-01») changes every stair, or every stair railing, of that type at once. What a stair sets for itself is kept when **Stairs on all floors** or **Update from CAD** makes the stairs again. Deleting a stair railing leaves the stair without one.

**Adjusting the railing.** Under **Railing height / sides** and **Railing inset / spacing / run-on** in section 7 you set the defaults for every stair. Edit properties on one stair (or Edit type for all stairs of a type) overrides them:

- **Sides:** inner (by the well, joined across the landings), outer (by the wall, turning round the landings), both, or none.
- **Inset:** how far in from the flight's edge the railing stands (default 50 mm).
- **Baluster spacing:** 0 keeps the railing type's own. For glass panels and pipe rails it is the post spacing.
- **Run-on:** the handrail continued level past the first and the last step.

**Landings.** The landing is always flush with the flights: the first flight's last riser is the landing's edge, and the waist slab runs on under the landing until the two soffits meet in one clean line.

### Railing types

The same types serve stairs, parapets, balconies and any wall built as a railing.

| Railing type | Made of |
| --- | --- |
| Solid parapet | Masonry upstand, plastered, with a coping |
| Stainless steel — vertical balusters | SS posts every 5'-0", balusters at about 4", SS handrail |
| MS grill | Painted mild-steel bars between a top and a bottom rail |
| Frameless glass + steel handrail | 15 mm glass in a floor channel, SS handrail |
| Glass panels between steel posts | Glass panels between posts every 4'-0", handrail on top |
| Steel pipe rails | Three horizontal SS pipes on posts |
| Timber | Timber handrail, posts and balusters |
| Low wall + steel railing | A 2'-0" masonry wall with SS balusters and handrail over it |

### Terraces and parapets

**Terraces over the floors below** finds the part of the floor below's roof that this floor leaves open. It runs a parapet along its open edges, joined cleanly at the corners and into this floor's walls. With slabs over each floor, the terrace is the slab below, and no extra slab is added over it. Set the parapet's height and thickness first.

To choose what the parapets are made of, pick **Parapet / railing type** and click **Apply to every parapet and balcony**. That covers terrace parapets, roof parapets and balcony railings on all levels; new ones take the same type.

### Balconies

Select a wall, set the **depth** and **width** (0 = the whole wall) and the railing height, then click **Balcony on the selected wall**. You get a cantilevered slab with a railing of the parapet type.

## 9. Rooms, floor finishes, parking and landscape

### Rooms and floor finishes

A room is any space the walls enclose. It takes its name from the plan's text inside it, with its area shown in plan. **9 Rooms** lists the picked level's rooms with four columns: Name, Area, Finish and Floor ±.

- **Finish:** the floor finish's thickness (tiles, screed). It is built as a layer on the room's floor. Type a length (`2"`, `50mm`) per room.
- **Floor ±:** sinks (−) or raises (+) that room's floor (see section 7).
- **Floor finishes / default:** switches finishes on or off and sets the default thickness (2"). **Default finish → all rooms** resets the level's rooms to it.
- Click **Save rooms** to keep names, finishes and levels.

You can also click a room's finish in the model, or right-click it, to edit that one room.

### Parking, ramps and cars

- **Parking bays** come from the plan's parking layer. Their lines are painted on the floor with clean joined edges, and the bays are numbered P1, P2… with a car count per floor.
- **Cars:** each bay gets a car from IngeTrazo's component library (SUV, pickup, or mixed), oriented in its bay.
- **Ramps** come from the plan's ramp lines and slope notes. Each one is a single continuous sloped slab from floor to floor, turns included, widened to the walls around it, with its well cut in the slab.
- To edit a ramp, right-click it: slope %, climb and slab thickness.

Ramps take their width from the cross stripes drawn on them, never from the chevron arrows. An end drawn on a slanted line is cut along that line. A turn is no longer pushed out through an outer wall. If a ramp still looks wrong, check that its lines are on the ramp layer and run **Update from CAD** for that level.

### Landscape

Soft areas in the plan (lawn, planting layers) are built in green on their floor. **4 Plot (site)** sets the plot, its boundary wall and the ground around the building.

### Excavation and fill

Under **4 Plot (site) ▸ Excavation / fill** (the same idea as ArchXQ's terrain cuts):

1. **Make**: Excavation (cut) or Fill (raise the ground).
2. **Outline**: one of the following.
   - The building footprint plus the **working space**.
   - The buildable area inside the setbacks.
   - The whole plot inset by the margin.
   - A rectangle (the plot's W × D, X, Y fields).
   - The outline of a slab, room or ramp you selected in the model.
3. **Bottom**: under the lowest level (by the value, default 0.30 m below its floor), a depth below the ground, or an elevation. For a fill, a height above the ground.
4. **Side angle**: 90° for vertical (shored) sides, 45° for a 1:1 batter.
5. Click **Add**.

The ground plate opens over the cut, and the pit is drawn with its floor and sloped sides. The list shows each excavation's depth and volume, plus the total cut, fill and earth to cart away. The site plan labels each one with its bottom level and volume. Remove one from the list, or select it in the model and delete it.

## 10. Components and editing any element

Every element belongs to a **component type** with a mark and a name built from its sizes. Elements with the same geometry share one IngeTrazo component definition, so you can select or change a whole type at once.

| Mark | Kind | Type set by | Example |
| --- | --- | --- | --- |
| D-nn | Doors | Type, leaves, head, frame, width × height | D-05 · Hinged door, single · 2'9" × 7'0" · Wood frame |
| W-nn | Windows | Type, head, frame, width × height, sill | W-03 · Sliding window · 6'0" × 4'5" · sill 3'4" |
| C-nn | Columns | Shape, width × depth | C-02 · Column 9" × 18" |
| B-nn | Beams | Width × depth | B-01 · Beam 9" × 18" |
| WL / CW | Walls / curtain walls | Thickness (parapets apart) | WL-03 · Wall 9" |
| RL-nn | Railings | Railing type, height | RL-01 · Glass panels between steel posts · 3'0" high |
| SL / LC / F / R | Slabs, lift cores, footings, roofs | Thickness, kind | SL-01 · Slab 6" |
| FF-nn | Floor finishes | Thickness | FF-01 · Floor finish 2" |

A mark, once given, stays with its type. A new type takes the next number.

**Staircases** are typed too: `ST-nn` by stair type, number of flights, risers, riser height and width (*ST-01 · Dog-leg stair, RCC · 18 risers of 7" · 4'8" wide*). Each stair's **railing** is a separate component listed under Railings (*RL-01 · Stair railing · Stainless steel · 3'0" · well side*). Identical stairs on typical floors share one definition. Edit a stair type for its stair type and railing; edit a stair-railing type for the railing type, height and sides.

### Replacing a type with an IngeTrazo library component

Any component type can be drawn as a model from IngeTrazo's own library (Properties ▸ Components). In **12 Components** pick the type and click **Replace with library…**, or right-click an element ▸ **Replace «D-01» with a library component…**. Then:

1. Search and pick the model.
2. Choose its **Size**: stretch to each element, keep its proportions inside the element, or its own size.
3. Choose a **Turn** of 0°, 90°, 180° or 270°.

Every element of the type changes at once. The element itself stays: a replaced door keeps its opening in the wall, its sizes and its place in the schedules. To go back, pick **CAD2IngeTrazo's own model** at the top of the list. The choices depend on the components installed with your IngeTrazo.

### 12 Components (types)

- **List:** every type with its count. Filter by *All levels* / *This level* and by kind.
- **Select in model:** selects every element of the types picked in the list. Double-clicking a row does the same.
- **Edit type…:** opens the type's fields (width, height, door type, frame, head, thickness…). What you change goes to **every** element of that type, and the type keeps its mark.
- **Rename:** type a new name in the *Name* column and click **Save names**. An empty name goes back to the one made from the sizes.

### Right-click any element

Select an element in the model and right-click: the **CAD2IngeTrazo** submenu offers:

- **Edit properties…:** a small dialog with the element's own fields.
- **Select all «D-05» (n)** and **Edit type «D-05» — all n…**.
- **Quick changes:**
  - doors: type, head, frame, single / double, flip hinge;
  - walls: convert to curtain wall, *Add door in this curtain wall…*;
  - every element: delete.

The same fields show in **10 Selected element** for the element you click.

If you double-click into a component and edit its geometry by hand, every copy changes, as in SketchUp. The next plugin rebuild replaces such hand edits, so make lasting changes through the plugin.

## 11. Plans, sheets and export

Everything here is in **11 Plans, sheets and export**. The plan views and sheets are made from the model, so they follow every change.

### Plan views

Click **Plan** at the top of the panel to see the picked level from above, cut at the *Plan cut height*. These options add to the plan views only, never to 3D:

**Hiding the CAD lines.** The **CAD lines** checkbox at the top of the panel and the **CAD lines** button on the CAD2IngeTrazo toolbar show or hide the CAD plan's own linework in the plan views in one click. The model and its notes stay.

- Dimensions, room names with areas, and the CAD's texts.
- **The CAD's linework**, with its line weights and line types (dashed, hidden).
- Floor level marks (FFL, or the CAD's `LEV.` notes).
- Parking bay numbers and car count, and a car in every bay.
- **Column grid** (1, 2, 3 / A, B, C), taken from:
  - the columns,
  - the wall corners,
  - bays you type,
  - or the CAD's own grid.

Click **Update plans** after changing these.

### Sheets

**Make sheets** draws, on title-blocked sheets:

- a plan per level,
- four elevations and sections A-A and B-B (if ticked),
- dimensions and room schedules.

Making them again replaces only the plugin's own sheets. Export them with **PDF…** or **DXF…**.

### SketchUp

**Export the model to SketchUp (.skp)…** (also on the plugin toolbar) writes the whole 3D model:

- walls, slabs, doors and windows, stairs and railings,
- ramps, cars and landscape.

Component types come through as SketchUp components. If IngeTrazo's SKP writer is missing, it writes a Collada `.dae` that SketchUp imports.

## 12. Troubleshooting and tips

Most problems come from the CAD file or its layers. The report under **Import** and the error log say which.

| Problem | What to do |
| --- | --- |
| “This DWG could not be read” | Neither IngeTrazo's converter nor AutoCAD could read it. In AutoCAD run `RECOVER`, then `SAVEAS` ▸ *AutoCAD 2018 DXF* with the same name beside the DWG, and import again. Or install the free ODA File Converter. |
| “No walls found” | The wall layer has another name. Click **Analyse** to list the layers, then set the wall role in **Layers and materials** («Use these roles»). |
| Walls too thin or missing | Check *Wall thickness min / max* (3" to 18") and the *Drawing units*. |
| Floors don't sit over each other | Use **2 Overlap floors ▸ Best fit**. Next time, pick the same reference point on every plan. |
| A floor is turned | **2 Overlap floors ▸ Rotate a floor**, then overlap. |
| Doors “don't fit in that wall” | The door is wider than its wall, or overlaps another opening. It is listed in the report and left out; add it by hand if needed. |
| Slab missing or extra | Check **6 ▸ Slab position**. Then use **Auto slab on every floor** with *Replace* ticked. |
| Overlap does nothing | Both floors need walls. Check *Level to move* and *Over level*. |
| A big building is slow to build | A 24-storey tower takes several minutes. Components make repeated floors much quicker; keep working on one level, and save often. |

### Good habits

- **Save often.** The plugin's data lives inside the IngeTrazo file.
- **Undo** is one Ctrl+Z per plugin action.
- **Keep your CAD layers named consistently** (WALL, DOOR, WIN, COL, STAIR, LIFT…). Detection then needs no correcting.
- **One reference point** (a grid intersection) on every plan, picked the same way for each level.
- **Change things through the plugin** (right-click, Edit type, the panel), not by editing geometry by hand: the next rebuild keeps plugin changes and replaces hand edits.
- **When the CAD changes,** save it and click **Update from CAD (all levels)**.

### Error log

If something goes wrong without a clear message, the details are written to `%APPDATA%\ingetrazo\plugins\cad2ingetrazo_errors.log`. Send that file with your question.

## 13. What's new since 3.11 (3.12 – 3.30)

The full list, version by version, is in the README. In short:

**Importing and reading the CAD**
- DWGs that LibreDWG cannot read are converted by AutoCAD's own engine when it is installed (no window opens), else ODA, else a DXF beside the DWG.
- «Select floor on drawing» shows the drawing as AutoCAD does: each line in its colour, line type and line weight; the plot style table the drawing names (e.g. monochrome.ctb) is read from AutoCAD's Plot Styles folder.
- **Hidden (dashed) lines are read as drafted**: across an opening with no door / window drawn → a plain opening; crossing it (an X) → an arch; in a window's opening with its glazing → a high window (ventilator, 6'-0" sill); outside an outer wall by a window → its sun shade (chajja); longer runs → the slab's projection; in a stair → the flight going up; crossing in open floor → a slab cut.
- Stairs follow the plan: UP / DN marks set the direction; a floor whose plan draws no stair (or only the stair from below, marked DN) gets none; a stair starting outside (a verandah, the ground) starts at that lower level.
- Corner / bay windows, glazing that is the wall (made a curtain wall with its door where drawn), railings, motorbike bays, landscape, level notes.

**Building the model**
- Slabs as floors (4" by default): the ground floor on a **foundation platform** (2'-0" incl. the 2" finish), its walls down to the ground; outside finishes (verandah, porch) 1'-0" lower; the main entrance at the floor level with its **steps as the CAD draws them**; steps at the other doors and a porch ramp made by themselves. With a basement the platform becomes a slab.
- Terraces over the floors below with railings on a 1'-0" × 3" upstand; roof slab with finishes, handles and openings (railed round); any face made a slab; sunk / raised parts.
- Stairs: flights, rotation and landings editable, winders, finishes on treads and risers with six nosing types, railing locked to the flights, faces always outward.
- Walls attached to the slab bottoms; slab edges, sun shades, thresholds; basements with RCC walls and shoring; false ceilings; partial wall edits; handles to stretch / move walls and railings in plan.
- **Boundary wall designs** (plain, coping, plinth band + coping, low wall + MS grille, piers along it) and finishes (plaster, brick, stone, concrete); gates from the IngeTrazo library, each gate a block with its pillars that slides along the wall with the Move tool.
- **Solid parapet designs** (plain, coping, coping + band, coping + short grille) on every terrace, roof, balcony and opening parapet.

**Furniture, kitchens, parking**
- Furniture and fixtures from the CAD blocks as IngeTrazo library models, facing the rooms (backs to the walls); empty bedrooms / living / dining rooms furnished; **low-poly by default** for speed, «High poly (render)» for rendering.
- Kitchens fitted with the «IngeTrazo Kitchen Maker» extension's parametric cabinets (sink under the window, hob, tall fridge unit, wall cabinets).
- Cars (library models) in every bay, on the finished floor (the porch's own level).

**Sheets and export**
- Sheets with the CAD's own linework over each plan at its plotted line weights; dimensions, room schedule, north arrow, line weights in the sheet window; PDF, DXF, a real SketchUp .skp.

**3.21 — reading the plan like a draughtsman**
- **STEP and STAIR layers apart**: the STEP layer is steps to another level of the same floor (a raised hall, a mimber, a verandah) — the stairs' finish and nosing, no railing; only the STAIR layers make staircases.
- **The LINE layer by where it lies**: in a wall's opening → a CNC grille (jali); closing round an area → a low platform at its noted level; outside the walls → a low wall.
- **Doors and windows from their symbols** even where no wall line runs along them (doors between fins, glazing from pier to pier): each gets a wall of its own.
- **Floor levels from the level texts** (LEV. +4'-0", LEVEL 163.00…): the floor's level from the note in its hall / rooms, each area at its own noted level; the ground F.F.L. field set from it.
- **Round columns** as the IngeTrazo library's round column; **arch shapes** — semicircular, segmental, elliptical, pointed (Islamic), ogee (Mughal), horseshoe (Moorish), multifoil, trefoil, four-centred (Persian).

**3.22 — closer to the drawing, and domes**
- Rooms close across columns, piers and window bands (the prayer hall is a room: its floor finish and level); walls stopping short are joined; rooms take their names, stair halls «STAIRCASE».
- Steps run on round their corners (an L / U of steps), up to the floor they climb to, with the landing built; floors noted by the CAD get no made-up outside drop.
- Blocks named ARCH arch their openings; any selected opening can be arched (section 5).
- **Domes** (section 8): hemispherical, onion, pointed, bulbous, saucer, ribbed, conical — any size, on a drum, with a finial, over a room or at a point.

**3.23 — the masjid as its elevations draw it**
- Minarets (square, octagonal and fluted shafts, corbelled galleries, lantern, cupola, crescent) and chhatris on the parapet (section 8).
- Domes on a square block with stepped tiers, raised over the roof.
- Arcades over the selected columns, rows of small arched openings (a clerestory / attic band) and ablaq voussoirs on any arch (section 5).

**3.24 — stairs, basements, levels and railings by the CAD**
- Section 7 split into «7.1 Stairs and steps» and «7.2 Terraces and balconies».
- At most 14 steps in a flight, with a landing between the parts; a floor added later gets its stair made again for its height, with landings and railings.
- Basement windows kept between the natural ground and the ground floor.
- A level written on the plan holds until a dividing line and the next level text.
- Terrace and balcony railings only where the CAD writes RAIL or BALCONY.

**3.25 — cleaner plans**
- U-turn standard stairs, their landings out to the stair hall's walls; floor steps 6" / 12".
- Floors stop where the plan and its level texts end.
- Walls broken at the column faces, their corners joined cleanly; the LINE layer never read as a wall.
- Hatched / filled walls taken as RCC structure; an X of hidden lines between columns is an (Islamic, pointed) arch.

**3.26 — jali, arches, stairs, structure**
- CNC jali in six patterns (diamonds, squares, round, hexagons, 8-point stars, lattice), fixed on the wall's outer face by default (or middle / inner): per opening in «Selected element», or for the selected openings / walls and a whole level in section 5.
- Arch shape and voussoirs applied to the selected walls' openings, or to every opening of a level; an arch shape picked for an opening arches its head.
- A U stair needing more risers than drawn turns back and forth inside its hall, a landing at each turn.
- Square-cornered hatches (boxes, L, T) in walls become RCC columns of their shape; arrow heads never do.
- Wall ends short of a column face or a wall are met; outside platforms only where a level text is written, never the plot's open ground; platforms cut round the entrance steps.

**3.26.1 — fixes from the Court Masjid ground floor**
- No runaway wall at near-straight joins; openings cut even in walls whose faces a join turned slightly.
- Crossed hidden lines: pointed (Islamic) arches by default, cut into a wall already across the gap.
- Duplicate walls (a window band over a drawn wall) merged; railings beside steps / inside the building kept, none on a wall.
- A landing at the top of traced stairs; the entrance porch floored; square pedestals for twin columns between planters.

**3.27 — railings, floors, steps and openings by the CAD**
- Terraces named on the plan (TERRACE, BALCONY…) are railed along the RAIL layer's lines as drawn, corners met; the 7.2 switch remakes them at once; no railing over a stair.
- Upper floors' slabs stop at their walls and terrace railings; the roof follows the top floor's walls.
- Thresholds in doorways without doors; CAD entrance steps read riser by riser from the outermost line, down to the porch they land on.
- Right-click an opening ▸ «Make it a…» door / window / opening / curtain wall; right-click a curtain wall ▸ «Glass door in the panel here».

**3.28 — curtain walls, arches, stairs, columns**
- Curtain walls on the finished floor (a solid base under them), mullions each side of their doors, a transom at the door head; corner windows → curtain wall or a glass door in a panel (right-click).
- Arch types in the Head field of doors and windows.
- Stairs start on the ground / platform at their foot; ground-floor columns run down to the ground.

**3.29 — fit-out from the CAD**
- VOID / CUT OUT texts cut the floor slab; DUCT / SHAFT / O.T.S / OPEN TO SKY cut it and every floor over it, the roof too.
- GLASS layer in a bathroom → glass shower partition with its door; CLADDING / ACP layer → aluminium panels on the wall; LIFT room → library elevator and its door.
- WCs → «Toilet unit», basins → «Vanity» (also oval basins drawn loose); LIGHT / ELE layers → ceiling lamps and AC layers → diffusers in the false ceiling (made when missing); DRESS rooms / layer → library wardrobes.
- The stair cut symbol (slant break line) is ignored when tracing stairs.
- 3.29.1: ducts drawn as crossed boxes cut the slab (no false arches); shower glass no longer makes walls; the slab runs under corridors open to balconies; one lift per LIFT text with its door to the lobby; 45° fixtures read correctly.

**3.30 — floor, ceilings, lift lobby, columns**
- The floor slab follows the plan's closed lines (balconies to their railings, no pockets); missed and single-line walls are made.
- False ceilings over halls and corridors too; a False ceiling toolbar menu with more types (cove, coffered, baffles, slats, open-cell, stretch, ACP, mineral tiles).
- Round LED panel lights and stepped 4-way diffusers; two-leaf lift doors with the cladding carried over them.
- Column type: structural / architectural.

**The panel**
- Numbered sections (1 – 13), closed on every launch; a language box (English, 中文, हिन्दी, Español, Français, العربية, বাংলা, Português, Русский, اردو); a ⟳ button that tells you when the extension catalogue lists a newer version (install it from IngeTrazo's Extension Manager).

## 3.31.0
- **False ceiling has its own section** in the panel (**8A  False ceiling**, below Roof): pick the type, then apply it to the rooms selected in the model, the level picked, or every level; Remove takes them off. The toolbar **False ceiling…** menu offers the same types.
- **Ceiling types as built on site**, each with its own form: Gypsum (plain board); POP (a tray: border band, raised centre, cornice and a hidden cove LED glow); Wooden planks; PVC panels; Metal 600×600 tiles; Glass (back-lit panels in a gypsum frame); Fabric / cloth (draped folds inside a gypsum border); Mineral fibre 600×600 with flush light panels; Combination (gypsum border, wooden centre). The earlier types stay (2×2 / 2×4 grid, cove, coffered, baffles, slats, open-cell, stretch, ACP, metal linear strips).
- **Architectural columns are their own object**, not a renamed RCC column: plinth, moulded base, shaft and capital, in four styles (Selected element ▸ Architectural style): round smooth, round fluted, fluted with Corinthian capital, square smooth (plinth and cap). Finished in white plaster, no load (IFC), no footing. **Structural columns** stay plain RCC prisms (rectangular or circular) in concrete grey, labelled "RCC column".

## 3.32.0
- **Structural columns as cast RCC**: every column is structural unless set otherwise, built as bare reinforced concrete — plain rectangular section with chamfered arrises (or round), shuttering joints every 1.2 m and a kicker at the foot, concrete grey, no base or capital. Architectural columns keep their classical form (plinth, base, shaft, capital): round smooth, round fluted, Corinthian, square smooth, or the IngeTrazo library column (Selected element ▸ Column type / Architectural style). Round columns are no longer given the decorative library column by default.
- **No column in a duct**: crossed boxes of ducts / shafts are not read as columns, and a box drawn out in the open (off the floor and its walls) is left out.
- **False ceiling from the right-click menu**: right-click in the model ▸ «False ceiling type» — the rooms / ceilings selected (or the level picked) take the type chosen; the current type is ticked; «No false ceiling» too.
- **Railings continuous**: a balcony railing that stopped short of the wall, a column or the next railing is carried on along the slab edge to meet it (the balcony corners and pointed ends included); pieces of one curved railing a few cm apart are joined.
- **Bath fixtures and beds as in the CAD**: blocks drawn turned inside their definition (a plan at 45°) are measured on their true sides, so WCs, vanities and beds get their real size and turn. A WC has its cistern to the wall behind it, a vanity its long side to the wall, always square with the block as drawn (also in bathrooms the plan leaves unnamed). Beds head between their bedside tables, the tables square with the bed.
- **Walkthrough** (Extensions ▸ CAD2IngeTrazo ▸ Walkthrough): pick a room (or the biggest room of a level): the eye goes inside at eye height looking along the room, the floors above are hidden, and First Person takes over (W/A/S/D or arrows to walk, mouse to look). Next / Previous room; «End walkthrough» puts the floors and the camera back.

## 3.33.0
- **Balconies get a false ceiling** (under the floor above) with a **periphery beam** along their open sides — the railing side and every edge no wall closes: 9" wide, from the soffit of the slab above down to the false-ceiling level, the ceiling inside it. Balconies open to the sky (the top floor without a roof) get neither. Settings: `balcony_ceiling` (on), `balcony_ceiling_type` (the level's type unless set); a balcony set to «No false ceiling» keeps none.
- **Toolbar: Walkthrough** in place of the False ceiling button (the false ceiling stays in panel section 8A and the right-click menu). A click walks into the biggest room of the level picked; its arrow lists the rooms, the other levels, «Wide angle», next / previous room.
- **Walkthrough is its own mode until Esc**: W/A/S/D or the arrows walk and turn (Shift faster), a mouse drag looks round, the wheel sets the angle of view (35°–120°, keys 1–4 = 60/75/90/110°, «Wide angle» = 100°), PgUp/PgDn go to the floor above / below at the same place. Walls are no obstacle (walk through them room to room); the eye stays fixed at eye level; zoom, orbit and the view buttons cannot take the camera out — only Esc ends it, putting the floors and the camera back.

## 3.34.0
- **Walkthrough**: walls stop you, but doors, openings, French windows and lift doors let you through into the next room («Walk through walls» in its menu lets you go anywhere). The view stays the normal one (the camera's own angle) until «Wide angle» is ticked.
- **Doors: architrave width** (Selected element ▸ Door architrave width; 0 = none).
- **Windows: curtain** per window (As the project setting / Curtain on this window / No curtain on this window).
- **Columns, as on the reference plates**: architectural columns in the five orders — **Doric** (fluted, no base, cushion capital), **Ionic** (scroll volutes), **Corinthian** (acanthus leaves, corner helices), **Composite** (big volutes over the leaves), **Tuscan** (plain shaft, simple capital) — besides round smooth / fluted, square smooth and the library column. **Structural** columns are bare RCC (rectangular / round, one clean pour, no lines); «Structural columns: show the reinforcement» (section 6) shows their main bars and links / helix through see-through concrete.
- **Clean wall junctions**: L corners that stopped short of each other (a notch the CAD does not draw, e.g. the lift lobby) are closed to the outer faces; small stubs past a wall's far face are cut back.
- **No slab / floor-finish lines on the elevations**: the floor finish stops at the walls and 20 mm short of the slab edge; structural columns no longer show joint or kicker lines.

## 3.34.1
- **No band at the floor line on the elevations**: a floor slab standing a little proud of the outside walls above it (the CAD outline drawn a couple of cm out) is trimmed back flush with the walls' outer face, so the walls running down over its edge cover it; balconies and canopies stay.

## 3.35.0
- **Walkthrough keeps every edit tool**: the left mouse button selects and edits as ever (the panel, Move, every tool work while you walk); drag with the right (or middle) button to look round; a right click still opens the menu. Doorways stay open their full width — every door, opening, French window and lift door lets you through; walls stop you («Walk through walls» in its menu to go anywhere). Esc ends it.
- **Slab to the inner face of the outside walls**: the floor slab stops at the inside face of the outside walls (and of the piers in them); the outside walls run on floor to floor over its edge — no slab or floor-finish line on the elevations. Balconies and canopies keep the slab running out past their wall. Setting `slab_inner_face` (on).
- **No CNC jali by mistake**: «None» picked for a window's jali (e.g. while taking its curtain off) now means no jali; models saved that way are cleaned when opened.
- **Square / rectangular architectural columns** (piers, pilasters) keep their own section in every order — base, fluted shaft (Tuscan plain), capital (Ionic volutes, Corinthian / Composite leaves).
