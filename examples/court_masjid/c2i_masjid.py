# The Court Masjid as elevations E-01…E-04 draw it (CAD2IngeTrazo 3.23).
# Works on the model imported level by level from «THE COURT MASJID for
# Ingetrazo.dwg»: Basement −9'-0", GR +4'-0", 1ST FL +24'-0", ROOF +36'-0"
# (the «2ND FLOOR PLAN»: the attic band, the chhatris' and the dome's
# footprints), STAIR ROOF +44'-6" (the «3RD TO 8TH FLOOR PLAN»: the
# minarets' shafts).
import sys, math, importlib
NAME = "ingetrazo_plugin_cad2ingetrazo"
P = sys.modules[NAME]._panel
PJ = sys.modules[NAME + ".project"]
M = importlib.import_module(NAME + ".engine.model")
DM = importlib.import_module(NAME + ".domes")
MN = importlib.import_module(NAME + ".minarets")
ST = importlib.import_module(NAME + ".stairs")
SP = importlib.import_module(NAME + ".engine.spaces")
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
FT = 0.3048
d = P.doc()
arch = d["arch"]
rep = {}

# ---------------------------------------------------------------- levels
lv = arch["levels"]
gi = next(i for i, l in enumerate(lv) if l.get("kind") == "ground")
G = lv[gi]
UP = lv[gi + 1:]
F1 = UP[0] if len(UP) > 0 else None          # +24'-0"
RF = UP[1] if len(UP) > 1 else None          # +36'-0"  roof / attic
SR = UP[2] if len(UP) > 2 else None          # +44'-6"  stair roof
d["settings"]["ground_ffl"] = 4 * FT
G["height"] = 20 * FT
if F1: F1["height"] = 12 * FT
if RF: RF["height"] = 8.5 * FT
if SR: SR["height"] = max(float(SR["height"]), 3.0)
for l in lv[:gi]:
    l["height"] = 13 * FT                     # basement −9'-0" → +4'-0"
arch["levels"] = M.fix_levels(arch["levels"])
gid = G["id"]
rep["levels"] = [(l["name"], round(l["height"] / FT, 1)) for l in arch["levels"]]

rooms = SP.of_level(arch, gid)
hall = next((r for r in rooms if "PRAYER" in str(r["name"]).upper()),
            max(rooms, key=lambda r: r["area"]))
abl = next((r for r in rooms if "ABLUTION" in str(r["name"]).upper()), None)
lob = next((r for r in rooms if "LOBBY" in str(r["name"]).upper()), None)
hc = hall["poly"].centroid
fx, fy = ((lob["poly"].centroid.x - hc.x, lob["poly"].centroid.y - hc.y)
          if lob else (1.0, 0.0))
fl = math.hypot(fx, fy) or 1.0
fx, fy = fx / fl, fy / fl                    # towards the entrance (E-01)
wang = math.degrees(math.atan2(fy, fx))      # the building's axis


def ang(w):
    return math.degrees(math.atan2(w["b"][1] - w["a"][1], w["b"][0] - w["a"][0]))


def same_line(w, h, tol=0.45):
    if abs(((ang(w) - ang(h)) + 90) % 180 - 90) > 6:
        return False
    lh = LineString([h["a"], h["b"]])
    lw = LineString([w["a"], w["b"]])
    return lh.distance(lw.interpolate(0.5, normalized=True)) < tol and \
        lh.buffer(tol).intersection(lw).length > 0.5 * lw.length


def drop(ids):
    ids = set(ids)
    arch["walls"] = [w for w in arch["walls"] if w["id"] not in ids]
    arch["openings"] = [o for o in arch["openings"] if o["wall"] not in ids]


# ------------------------------------------------- the ablution: one storey
abl_z = abl["poly"].buffer(1.0) if abl is not None else None
abl_ids = set()
if abl is not None:
    for w in arch["walls"]:
        if w["level"] == gid and abl_z.contains(
                LineString([w["a"], w["b"]]).interpolate(0.5, normalized=True)):
            w["height"] = 12 * FT
            abl_ids.add(w["id"])
    ups = {l["id"] for l in UP}
    drop([w["id"] for w in arch["walls"] if w["level"] in ups and abl_z.contains(
        LineString([w["a"], w["b"]]).interpolate(0.5, normalized=True))])
    arch["structure"] = [e for e in arch["structure"] if not (
        e["level"] in ups and e["type"] in ("slab", "column") and (
            Polygon(e["corners"]).buffer(0).intersection(abl_z).area >
            0.6 * max(Polygon(e["corners"]).buffer(0).area, 1e-6)
            if e["type"] == "slab" else abl_z.contains(Point(e["x"], e["y"]))))]

# ------------------------------------- the facade: GR → +44'-0" in one wall
foot = unary_union([r["poly"].buffer(0.45, join_style=2) for r in rooms])
near = hall["poly"].buffer(6.0)
fac = []
for w in arch["walls"]:
    if w["level"] != gid or w["id"] in abl_ids or w.get("kind", "line") != "line":
        continue
    ln = LineString([w["a"], w["b"]])
    if ln.length < 0.6:
        continue
    m_ = ln.interpolate(0.5, normalized=True)
    ux, uy = (w["b"][0] - w["a"][0]) / ln.length, (w["b"][1] - w["a"][1]) / ln.length
    off = float(w.get("t", 0.23)) / 2 + 0.9
    sl, sr = Point(m_.x - uy * off, m_.y + ux * off), Point(m_.x + uy * off, m_.y - ux * off)
    inl, inr = foot.contains(sl), foot.contains(sr)
    if inl != inr and near.contains(m_):
        n_ = (-uy, ux) if not inl else (uy, -ux)          # outward
        w["height"] = 40 * FT
        w["_side"] = ("front" if n_[0] * fx + n_[1] * fy > 0.7 else
                      "rear" if n_[0] * fx + n_[1] * fy < -0.7 else "side")
        fac.append(w)
rep["facade_walls"] = len(fac)
# walls drawn twice on one line (a wall and the band a window was bridged
# into): one wall, holding both's openings
merged = 0
fac.sort(key=lambda w: -math.dist(w["a"], w["b"]))
gone_ = set()
for i, w in enumerate(fac):
    if w["id"] in gone_:
        continue
    lw = LineString([w["a"], w["b"]])
    for x in fac[i + 1:]:
        if x["id"] in gone_ or abs(((ang(x) - ang(w)) + 90) % 180 - 90) > 4:
            continue
        lx = LineString([x["a"], x["b"]])
        tol = max(float(w.get("t", 0.2)), float(x.get("t", 0.2))) / 2 + 0.02
        if lw.distance(lx.interpolate(0.5, normalized=True)) > tol or \
                lw.buffer(tol).intersection(lx).length < 0.6 * lx.length:
            continue
        for o in arch["openings"]:
            if o["wall"] != x["id"]:
                continue
            t_ = float(o["pos"]) / max(lx.length, 1e-6)
            pt = Point(x["a"][0] + (x["b"][0] - x["a"][0]) * t_,
                       x["a"][1] + (x["b"][1] - x["a"][1]) * t_)
            pos = lw.project(pt)
            if not any(q["wall"] == w["id"] and abs(float(q["pos"]) - pos) <
                       (float(q["w"]) + float(o["w"])) / 2 + 0.05
                       for q in arch["openings"]):
                o["wall"], o["pos"] = w["id"], round(pos, 4)
        if float(x.get("t", 0)) > float(w.get("t", 0)):
            w["t"] = x["t"]
        gone_.add(x["id"])
        merged += 1
fac = [w for w in fac if w["id"] not in gone_]
drop(gone_)
rep["facade_merged"] = merged
FAC = {w["id"]: w for w in fac}

# the upper floors' walls on the facade's lines go; the attic's small
# arched windows (the roof plan's) move onto the facade, at +36'-6"
moved = 0
upper = [w for w in arch["walls"] if w["level"] in {l["id"] for l in UP}]
gone = []
newo = []
for w in upper:
    h = next((f for f in fac if same_line(w, f)), None)
    if h is None:
        continue
    gone.append(w["id"])
    if RF is not None and w["level"] == RF["id"]:
        L = LineString([h["a"], h["b"]])
        for o in arch["openings"]:
            if o["wall"] != w["id"] or float(o["w"]) > 0.6:
                continue
            t = float(o["pos"]) / max(math.dist(w["a"], w["b"]), 1e-6)
            p = Point(w["a"][0] + (w["b"][0] - w["a"][0]) * t,
                      w["a"][1] + (w["b"][1] - w["a"][1]) * t)
            newo.append({"kind": "void", "wall": h["id"],
                         "pos": round(L.project(p), 4), "w": 0.46, "h": 1.2,
                         "sill": round(32.6 * FT, 4), "swing": "left", "face": 1,
                         "style": "", "head": "arch", "arch": "semi",
                         "grille": "cnc"})
drop(gone)
rep["upper_facade_walls_removed"] = len(gone)

# ---------------- the arcades: the portico (E-01) and the riwaqs (E-02/04)
# rows of paired round columns outside the hall: a wall to +36'-0" on them,
# a pointed ablaq arch to +34'-0" in each bay
def _uv(x, y):
    return ((x - hc.x) * fx + (y - hc.y) * fy, -(x - hc.x) * fy + (y - hc.y) * fx)


cols = [c for c in arch["structure"] if c["type"] == "column"
        and c["level"] == gid and c.get("shape") == "round"
        and not hall["poly"].buffer(0.2).contains(Point(c["x"], c["y"]))]
rows = {}
for c in cols:
    u, v = _uv(c["x"], c["y"])
    key = ("v", round(v)) if abs(v) > abs(u) else ("u", round(u))
    rows.setdefault(key, []).append(c)
arc = []
for key, row in rows.items():
    if len(row) < 4:
        continue
    before = {w["id"] for w in arch["walls"]}
    why = PJ.arcade_over_columns(d, [c["id"] for c in row], t=0.45, sill=0.0,
                                 top_gap=0.5, style="pointed", ring="ablaq")
    nw = [w for w in arch["walls"] if w["id"] not in before]
    for w in nw:
        w["height"] = 32 * FT
        for o in arch["openings"]:
            if o["wall"] == w["id"]:
                o["h"] = round(31.0 * FT, 4)
                o["sill"] = 0.0
    arc.append((key, len(row), why or "ok"))
rep["arcades"] = arc

# the facade's openings as the elevations draw them (distances from each
# end of a face, ft): the plan's windows on the facade give way to them
E_FRONT = [5.1, 16.5]                 # E-01: two tall windows each side
E_REAR = [5.1, 15.1, 25.0]            # E-03: three each side, the portal
E_SIDE = [5.0]                        # E-02 / E-04: the end bays
TALL_H = 37.5                         # GR → the arch's point (ft)
BAY_H = 27.0                          # behind the riwaq arches


def _face(w):
    (ua, va), (ub, vb) = _uv(*w["a"]), _uv(*w["b"])
    return ua, va, ub, vb


def _side_of(w):
    ua, va, ub, vb = _face(w)
    if abs(ub - ua) < abs(vb - va):            # runs along v: front / rear
        return "front" if (ua + ub) / 2 > 0 else "rear"
    return "left" if (va + vb) / 2 > 0 else "right"


uvs = [_uv(x, y) for w in fac for x, y in (w["a"], w["b"])]
UMIN, UMAX = min(p[0] for p in uvs), max(p[0] for p in uvs)
VMIN, VMAX = min(p[1] for p in uvs), max(p[1] for p in uvs)


MISS = []


def _place(side, s_m, rec):
    """An opening on the outermost facade wall of that side at s (m along
    the face, from its low end)."""
    best = None
    for w in fac:
        if _side_of(w) != side:
            continue
        ua, va, ub, vb = _face(w)
        a0, a1 = (va, vb) if side in ("front", "rear") else (ua, ub)
        lo, hi = min(a0, a1), max(a0, a1)
        if not (lo - 0.05 <= s_m <= hi + 0.05) or hi - lo < 0.75:
            continue
        out = {"front": (ua + ub) / 2, "rear": -(ua + ub) / 2,
               "left": (va + vb) / 2, "right": -(va + vb) / 2}[side]
        if best is None or out > best[0]:
            best = (out, w, a0, a1)
    if best is None:
        near_ = []
        for w in fac:
            if _side_of(w) != side:
                continue
            ua, va, ub, vb = _face(w)
            a0, a1 = (va, vb) if side in ("front", "rear") else (ua, ub)
            if min(a0, a1) - 0.5 <= s_m <= max(a0, a1) + 0.5:
                near_.append((round(min(a0, a1), 2), round(max(a0, a1), 2)))
        MISS.append((side, round(s_m, 2), rec["w"], near_))
        return False
    _o, w, a0, a1 = best
    L = math.dist(w["a"], w["b"])
    pos = (s_m - a0) / (a1 - a0) * L
    rec = dict(rec, w=round(min(rec["w"], L - 0.26), 3))
    pos = min(max(pos, rec["w"] / 2 + 0.12), L - rec["w"] / 2 - 0.12)
    for o in [o for o in arch["openings"] if o["wall"] == w["id"]]:
        if abs(float(o["pos"]) - pos) < (float(o["w"]) + rec["w"]) / 2 + 0.06:
            arch["openings"].remove(o)          # the plan's, in the way
    arch["openings"] += M.new_openings(arch["openings"], [dict(
        rec, wall=w["id"], pos=round(pos, 4))])
    return True


def _win(w_ft, h_ft, sill_ft=0.0, grille="cnc"):
    return {"kind": "window", "w": round(w_ft * FT, 3), "h": round(h_ft * FT, 3),
            "sill": round(sill_ft * FT, 3), "swing": "left", "face": 1,
            "style": "fixed", "head": "arch", "arch": "pointed",
            "ring": "ablaq", "grille": grille}


# the plan's windows on the facade go: the elevations' take their place
FID = {w["id"] for w in fac}
arch["openings"] = [o for o in arch["openings"]
                    if not (o["wall"] in FID and o["kind"] == "window")]
put = {"front": 0, "rear": 0, "left": 0, "right": 0, "missed": 0}
for side, lst in (("front", E_FRONT), ("rear", E_REAR)):
    for e_ in lst:
        for s_m in (VMIN + e_ * FT, VMAX - e_ * FT):
            ok = _place(side, s_m, _win(4.0, TALL_H))
            put[side if ok else "missed"] += 1
for side in ("left", "right"):
    for s_m in (UMIN + E_SIDE[0] * FT, UMAX - E_SIDE[0] * FT):
        ok = _place(side, s_m, _win(4.0, TALL_H))
        put[side if ok else "missed"] += 1
# E-03: the qibla wall's portal, 8'-10" wide, its pointed arch at 22'-6"
rec_ = _win(8.83, 22.5, 0.0, None)
rec_.update(kind="door", style="hinged", leaves=2)
rec_.pop("grille", None)
put["portal"] = _place("rear", (VMIN + VMAX) / 2, rec_)
# behind each riwaq arch (E-02 / E-04): a door with its jali over it
for w in arch["walls"]:
    if not str(w.get("name", "")).startswith("Arcade"):
        continue
    for o in [o for o in arch["openings"] if o["wall"] == w["id"]]:
        L = math.dist(w["a"], w["b"])
        t_ = float(o["pos"]) / L
        x = w["a"][0] + (w["b"][0] - w["a"][0]) * t_
        y = w["a"][1] + (w["b"][1] - w["a"][1]) * t_
        u, v = _uv(x, y)
        if abs(v) > abs(u):                    # a riwaq (not the portico)
            side = "left" if v > 0 else "right"
            ok = _place(side, u, _win(5.0, BAY_H))
            put["bays"] = put.get("bays", 0) + bool(ok)
rep["elevation_openings"] = put
rep["missed"] = MISS
# the doors and plain openings left on the facade: pointed, ablaq
for o in arch["openings"]:
    if o["wall"] in FID and o["kind"] in ("door", "void") and o.get("head") != "arch":
        o.update(head="arch", arch="pointed", ring="ablaq")
        o["h"] = round(max(float(o["h"]), 3.4), 3)
# the attic band's windows, where they do not cross a tall window
okn = []
for r_ in newo:
    clash = any(o["wall"] == r_["wall"] and abs(float(o["pos"]) - r_["pos"]) <
                (float(o["w"]) + r_["w"]) / 2 + 0.1 for o in arch["openings"])
    if not clash:
        okn.append(r_)
arch["openings"] += M.new_openings(arch["openings"], okn)
rep["attic_windows"] = len(okn)
for w in fac:
    w.pop("_side", None)

# the attic band over the arcades (+36'-0" → +44'-6"): the roof plan's wall
# on each arcade's line (made when the plan has none), with groups of three
# small arched jali windows (E-01, E-02, E-04)
att = []
if RF is not None:
    for w in [w for w in arch["walls"] if str(w.get("name", "")).startswith("Arcade")]:
        on = [x for x in arch["walls"] if x["level"] == RF["id"] and not x.get("rail")
              and same_line(x, w, 0.6)]
        if not on:
            on = M.new_walls(arch["walls"], [{
                "kind": "line", "a": list(w["a"]), "b": list(w["b"]), "t": w["t"],
                "align": "centre", "side": 1, "height": "level", "base": 0.0,
                "level": RF["id"]}])
            for x in on:
                x["name"] = "Attic " + x["name"].split()[-1]
            arch["walls"] += on
        for x in on:
            arch["openings"] = [o for o in arch["openings"] if o["wall"] != x["id"]]
            att.append(x["id"])
    rep["attic_band"] = PJ.openings_along(d, att, w=0.46, h=1.2, sill=0.35,
                                          pitch=0.62, group=3, gap=1.1,
                                          style="semi", grille="cnc")

# the upper floors' railings on the outside edge (balconies the
# elevations do not draw) go
fp0 = unary_union([LineString([w["a"], w["b"]]).buffer(float(w.get("t", 0.2)) / 2)
                   for w in fac]).convex_hull
upids = {l["id"] for l in UP}
rails = []
for w in arch["walls"]:
    if w["level"] in upids and w.get("rail"):
        m_ = LineString([w["a"], w["b"]]).interpolate(0.5, normalized=True)
        if not fp0.buffer(-0.5).contains(m_):
            rails.append(w["id"])
drop(rails)
rep["edge_rails_removed"] = len(rails)

# ------------------------- the roof plan's chhatri circles, the dome block
chh = []
if RF is not None:
    for e in list(arch["structure"]):
        if e["type"] == "column" and e["level"] in (RF["id"], SR["id"] if SR else "") \
                and e.get("shape") == "poly" and 0.9 < max(float(e["w"]), float(e["d"])) < 1.3:
            if e["level"] == RF["id"] and not any(math.dist((e["x"], e["y"]), c) < 0.5 for c in chh):
                chh.append((e["x"], e["y"]))
            arch["structure"].remove(e)
    # the big circle under one of them (a drawn ring) goes too
    arch["structure"] = [e for e in arch["structure"] if not (
        e["type"] == "column" and e["level"] in (RF["id"], SR["id"] if SR else "")
        and e.get("shape") == "poly" and any(math.dist((e["x"], e["y"]), c) < 0.5 for c in chh))]
d["chhatris"] = []
for x, y in chh:
    MN.new_chhatri(d, RF["id"], x, y, 1.9, wang, z=0.0)
rep["chhatris"] = len(d["chhatris"])

# the stair roof plan: only the stair towers' roofs and the minarets
mins = []
if SR is not None:
    sw = [w for w in arch["walls"] if w["level"] == SR["id"]]
    # the minarets' shafts: four walls ~1.7 m apart round a point
    segs = [w for w in sw if 0.14 < float(w.get("t", 0)) < 0.3
            and 1.2 < math.dist(w["a"], w["b"]) < 2.2]
    used = set()
    for w in segs:
        if w["id"] in used:
            continue
        grp = [x for x in segs if math.dist(((x["a"][0] + x["b"][0]) / 2, (x["a"][1] + x["b"][1]) / 2),
                                            ((w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2)) < 2.0]
        if len(grp) >= 3:
            pts = [p for x in grp for p in (x["a"], x["b"])]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            if not any(math.dist((cx, cy), m) < 2.0 for m in mins):
                mins.append((cx, cy))
            used |= {x["id"] for x in grp}
    drop([w["id"] for w in sw])
    keep = [r for r in SP.of_level(arch, RF["id"]) if "STAIR" in str(r["name"]).upper()] \
        if RF is not None else []
    arch["structure"] = [e for e in arch["structure"] if not (
        e["level"] == SR["id"] and (e["type"] != "slab" or not any(
            Polygon(e["corners"]).buffer(0).intersection(r["poly"]).area > 0.5 * r["poly"].area
            for r in keep)))]
    arch["rooms"] = [r for r in arch["rooms"] if r["level"] != SR["id"]]
d["minarets"] = []
# on the stair towers at the front corners: 5'-0" in from the front face
# and from the side face (E-01, E-02), 84'-0" from the stair roof
fp = unary_union([LineString([w["a"], w["b"]]).buffer(float(w.get("t", 0.2)) / 2)
                  for w in fac]).convex_hull
uv = [_uv(x, y) for x, y in fp.exterior.coords]
umax = max(p[0] for p in uv)
vmin, vmax = min(p[1] for p in uv), max(p[1] for p in uv)
for vv in (vmin + 5 * FT, vmax - 5 * FT):
    uu = umax - 5 * FT
    x = hc.x + uu * fx - vv * fy
    y = hc.y + uu * fy + vv * fx
    mins.append((x, y))
for cx, cy in mins[-2:]:
    MN.new_minaret(d, SR["id"] if SR else RF["id"], cx, cy, 6 * FT, 84 * FT,
                   17 * FT, 3, "bulbous", wang)
rep["minarets"] = [(round(x, 2), round(y, 2)) for x, y in mins[-2:]]

# the dome (E-03 «Y»): on the roof plan's STORE block, a 9'-0" block, three
# 1'-6" tiers, an onion Ø13'-9" 11'-6" high, from +44'-6"
d["domes"] = []
if RF is not None:
    rr = SP.of_level(arch, RF["id"])
    st_ = next((r for r in rr if "STORE" in str(r["name"]).upper()), None)
    c = st_["poly"].centroid if st_ is not None else hall["poly"].centroid
    DM.new(d, RF["id"], c.x, c.y, 13.75 * FT, "onion", 11.5 / 13.75, 0.0,
           True, "white")
    d["domes"][-1].update(base_h=round(9 * FT, 4), steps=3,
                          step_h=round(1.5 * FT, 4), base=0.0)
    rep["dome"] = (round(c.x, 2), round(c.y, 2))
try:
    rep["stairs"] = ST.auto(d)
except Exception as e:
    rep["stairs"] = repr(e)
def _arcades_again(d_):
    ids = {w["id"] for w in d_["arch"]["walls"]
           if str(w.get("name", "")).startswith("Arcade")}
    n_ = 0
    for o in d_["arch"]["openings"]:
        if o["wall"] in ids and abs(float(o["h"]) - 31.0 * FT) > 0.01:
            o.update(kind="void", h=round(31.0 * FT, 4), sill=0.0, head="arch",
                     arch="pointed", ring="ablaq")
            n_ += 1
    return n_


rep["arcade_fixed_before"] = _arcades_again(d)
P.commit(d, "The masjid as elevations E-01…E-04 draw it")
d2 = P.doc()
rep["arcade_fixed_after"] = _arcades_again(d2)
if rep["arcade_fixed_after"]:
    P.commit(d2, "The arcades' arches")
print("masjid", rep)
MASJID_REP = rep
