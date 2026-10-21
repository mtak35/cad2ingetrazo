# CAD2IngeTrazo 3.23 — The Court Masjid built from its CAD plans, then
# shaped as elevations E-01…E-04 draw it (c2i_masjid.py). One undo step
# per floor read and one for the elevations: Ctrl+Z undoes them.
import sys, copy, importlib, json
NAME = "ingetrazo_plugin_cad2ingetrazo"
P = sys.modules[NAME]._panel
PJ = sys.modules[NAME + ".project"]
M = importlib.import_module(NAME + ".engine.model")
D = r"C:\Users\kashi\Downloads\archxq-it-lite-main\archxq-it-lite-main\archxq_it"
DWG = r"C:/Users/kashi/OneDrive/Documents/The Court group Project/THE COURT MASJID for Ingetrazo.dwg"
FT = 0.3048
HOW = {'auto': True,
 'base': 'custom',
 'beams': '*BEAM*, S-BEAM*',
 'bikes': 'A Bike',
 'bx': 660003.647,
 'by': -284660.878,
 'cars': 'CAR',
 'columns': 'COL',
 'doors': 'DOOR',
 'file': 'C:/Users/kashi/OneDrive/Documents/The Court group Project/THE '
         'COURT MASJID for Ingetrazo.dwg',
 'footings': 'X-REF$0$FS-PUMP-FOUNDTAION',
 'grid': 'GRIDE',
 'holes': 'STAIR, STAIRE',
 'ix': 0.0,
 'iy': 0.0,
 'lift': 'DETAIL OF STAIR LIFT& FINESH$0$FINISH SH',
 'parking': 'PARKING',
 'plot': 'PLOT',
 'rails': 'RAIL, RALL',
 'ramps': 'RAMP',
 'region': [659187.6076, -286470.8115, 661160.3083, -284300.1581],
 'rot': 0.0,
 'slab': 'OPENING IN SLAB',
 'stairs': 'STAIR, STAIRE',
 'text': 'TEXT-1, TEXT.1',
 'tmax': 0.4354,
 'tmin': 0.1016,
 'unit': None,
 'unit_k': 0.0254,
 'unit_key': 'auto',
 'walls': 'WALL, WALL1',
 'windows': 'WIN'}
HOW["file"] = DWG
# the plans side by side in the drawing: each floor's offset from the
# ground floor plan (drawing units, inches)
FLOORS = [("Basement 1", "basement", -3364, 13 * FT),
          ("Ground Floor", "ground", 0, 20 * FT),
          ("1st Floor", "floor", 3364, 12 * FT),
          ("Roof", "floor", 6726, 8.5 * FT),
          ("Stair Roof", "floor", 10090, 3.0)]
d = P.doc()
a = d["arch"]
if a["walls"] or a["structure"]:
    ours = any("MASJID" in str((h or {}).get("file", "")).upper()
               for h in d.get("imports", {}).values() if isinstance(h, dict))
    if not ours:
        raise SystemExit("The model is not empty: open a new model (File > New) first")
    keep = dict(d["settings"])
    d = PJ.empty()                 # the masjid made before: made again
    d["settings"].update(keep)
    a = d["arch"]
lv = [{"name": n, "kind": k, "height": h, "id": ""} for n, k, dx, h in FLOORS]
lv[1]["id"] = next((l["id"] for l in a["levels"] if l.get("kind") == "ground"), "lv0")
a["levels"] = M.fix_levels(lv)
ids = {l["name"]: l["id"] for l in a["levels"]}
P.commit(d, "The masjid's floors")
REP = {}
for n, k, dx, h in FLOORS:
    d = P.doc()
    how = copy.deepcopy(HOW)
    r = how["region"]
    how["region"] = [r[0] + dx, r[1], r[2] + dx, r[3]]
    how["bx"] = HOW["bx"] + dx
    d["imports"][ids[n]] = how
    rep = PJ.import_level(d, ids[n], DWG, how)
    REP[n] = {x: rep.get(x) for x in ("walls", "openings", "columns", "rooms")}
    P.commit(d, "The masjid: " + n + " read from the CAD")
    print(n, REP[n])
exec(open(D + r"\c2i_masjid.py", encoding="utf-8").read())
REP["masjid"] = MASJID_REP
open(D + r"\c2i_build_log.txt", "w").write(json.dumps(REP, default=str, indent=1))
print("built")
