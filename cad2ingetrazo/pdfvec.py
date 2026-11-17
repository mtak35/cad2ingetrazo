"""3.64.44: the lines of a PDF page (a CAD plot), read without any PDF
library — only zlib from Python itself.

A PDF plotted from AutoCAD, Revit or SketchUp keeps its drawing as
vector paths: ``m`` / ``l`` / ``c`` / ``re`` operators in the page's
content streams (often inside form XObjects), under a transformation
matrix (``cm``). This reader walks those streams and returns the straight
segments and the curves (as their chords and as arcs' boxes), in page
points, y up, with the page's /Rotate applied. Text is skipped (its
fonts may be anything); images are skipped.

It is a small reader, not a PDF engine: encrypted files and exotic
filters give no lines (the caller then falls back to the page as a
picture).
"""
from __future__ import annotations

import re
import zlib

_OBJ_RX = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_REF_RX = re.compile(rb"(\d+)\s+(\d+)\s+R\b")


class _Pdf:
    def __init__(self, data: bytes):
        self.data = data
        self.objs: dict[int, bytes] = {}          # number → body (no stream)
        self.streams: dict[int, bytes] = {}       # number → raw stream bytes
        self._scan()

    # ---- objects ----------------------------------------------------------
    def _scan(self):
        d = self.data
        for m in _OBJ_RX.finditer(d):
            num = int(m.group(1))
            start = m.end()
            end = d.find(b"endobj", start)
            if end < 0:
                continue
            body = d[start:end]
            si = body.find(b"stream")
            if si >= 0 and (body[:si].rstrip().endswith(b">>")):
                head = body[:si]
                k = si + 6
                if body[k:k + 2] == b"\r\n":
                    k += 2
                elif body[k:k + 1] in (b"\n", b"\r"):
                    k += 1
                ei = body.rfind(b"endstream")
                raw = body[k:ei if ei > k else len(body)]
                self.objs[num] = head
                self.streams[num] = self._decode(head, raw)
            else:
                self.objs[num] = body
        # objects packed in object streams (PDF 1.5+)
        for num, head in list(self.objs.items()):
            if b"/ObjStm" not in head or num not in self.streams:
                continue
            st = self.streams[num]
            mN = re.search(rb"/N\s+(\d+)", head)
            mF = re.search(rb"/First\s+(\d+)", head)
            if not (mN and mF):
                continue
            n, first = int(mN.group(1)), int(mF.group(1))
            nums = [int(x) for x in st[:first].split()]
            pairs = list(zip(nums[0::2], nums[1::2]))[:n]
            for i, (on, off) in enumerate(pairs):
                a = first + off
                b = first + pairs[i + 1][1] if i + 1 < len(pairs) else len(st)
                self.objs.setdefault(on, st[a:b])

    @staticmethod
    def _decode(head: bytes, raw: bytes) -> bytes:
        if b"/FlateDecode" in head or b"/Fl " in head or b"/Fl]" in head:
            try:
                return zlib.decompressobj().decompress(raw)
            except zlib.error:
                try:
                    return zlib.decompress(raw.strip())
                except zlib.error:
                    return b""
        if b"/Filter" in head:
            return b""          # an unknown filter: nothing to read
        return raw

    def get(self, ref) -> bytes:
        return self.objs.get(ref, b"")

    def resolve(self, val: bytes) -> bytes:
        m = re.match(rb"\s*(\d+)\s+(\d+)\s+R", val)
        return self.get(int(m.group(1))) if m else val

    # ---- dictionaries (enough of them) --------------------------------------
    @staticmethod
    def entry(d: bytes, key: bytes) -> bytes | None:
        """The raw value after ``/key`` in a dictionary (a ref, a number, an
        array, a dict, a name)."""
        m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])\s*", d)
        if not m:
            return None
        i = m.end()
        if d[i:i + 2] == b"<<":
            depth, j = 0, i
            while j < len(d):
                if d[j:j + 2] == b"<<":
                    depth += 1
                    j += 2
                    continue
                if d[j:j + 2] == b">>":
                    depth -= 1
                    j += 2
                    if depth == 0:
                        return d[i:j]
                    continue
                j += 1
            return d[i:]
        if d[i:i + 1] == b"[":
            j = d.find(b"]", i)
            return d[i:j + 1]
        m2 = re.match(rb"(\d+\s+\d+\s+R|/[^\s/<>\[\]()]+|[-+.\d]+)", d[i:])
        return m2.group(1) if m2 else None

    def pages(self) -> list[int]:
        root = None
        for num, body in self.objs.items():
            if re.search(rb"/Type\s*/Catalog", body):
                v = self.entry(body, b"Pages")
                if v:
                    m = _REF_RX.match(v)
                    root = int(m.group(1)) if m else None
                break
        out = []

        def walk(n, depth=0):
            if depth > 30:
                return
            b = self.get(n)
            if re.search(rb"/Type\s*/Pages\b", b):
                kids = self.entry(b, b"Kids") or b""
                for m in _REF_RX.finditer(kids):
                    walk(int(m.group(1)), depth + 1)
            elif re.search(rb"/Type\s*/Page\b", b):
                out.append(n)
        if root is not None:
            walk(root)
        if not out:          # no tree found: every page object in order
            out = sorted(n for n, b in self.objs.items()
                         if re.search(rb"/Type\s*/Page\b", b))
        return out

    def inherited(self, page: int, key: bytes):
        n, seen = page, set()
        while n and n not in seen:
            seen.add(n)
            b = self.get(n)
            v = self.entry(b, key)
            if v is not None:
                return v
            p = self.entry(b, b"Parent")
            m = _REF_RX.match(p or b"")
            n = int(m.group(1)) if m else None
        return None


# ---- the content stream ------------------------------------------------------
_TOK = re.compile(
    rb"\s*(?:(%[^\r\n]*)|(\[)|(\])|(<<)|(>>)|(\((?:\\.|[^\\)])*\))|"
    rb"(<[0-9A-Fa-f\s]*>)|(/[^\s/<>\[\]()%{}]*)|([-+]?(?:\d+\.?\d*|\.\d+))|"
    rb"([A-Za-z'\"*]+[0-9]?\*?))", re.S)


def _tokens(data: bytes):
    i, n = 0, len(data)
    while i < n:
        m = _TOK.match(data, i)
        if not m or m.end() == i:
            i += 1
            continue
        i = m.end()
        g = m.lastindex
        if g == 1:
            continue
        if g == 6:                     # a string: its nesting may need more
            s = m.group(6)
            depth = s.count(b"(") - s.count(b")")
            while depth > 0 and i < n:
                c = data[i:i + 1]
                if c == b"\\":
                    i += 2
                    continue
                if c == b"(":
                    depth += 1
                elif c == b")":
                    depth -= 1
                i += 1
            yield ("s", None)
            continue
        if g == 9:
            yield ("n", float(m.group(9)))
        elif g == 8:
            yield ("name", m.group(8)[1:])
        elif g in (2, 3, 4, 5):
            yield ("p", m.group(g))
        elif g == 7:
            yield ("s", None)
        else:
            op = m.group(10)
            if op == b"BI":            # an inline image: skipped to EI
                j = data.find(b"EI", i)
                i = j + 2 if j >= 0 else n
                continue
            yield ("op", op)


def _mul(a, b):
    """Matrix product a·b (PDF matrices [a b c d e f])."""
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _xf(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def page_lines(path, page=1, max_segs=400_000):
    """{"w", "h", "segs": [(x1, y1, x2, y2)], "arcs": [(x0, y0, x1, y1)]}
    of the page (1-based), in points, y up, the page's rotation applied;
    None when the file cannot be read."""
    try:
        data = open(path, "rb").read()
    except OSError:
        return None
    if b"/Encrypt" in data[-4096:] or b"/Encrypt" in data[:4096]:
        return None
    pdf = _Pdf(data)
    pages = pdf.pages()
    if not pages:
        return None
    pnum = pages[min(max(page, 1), len(pages)) - 1]
    pb = pdf.get(pnum)
    box = pdf.inherited(pnum, b"CropBox") or pdf.inherited(pnum, b"MediaBox")
    try:
        bx = [float(v) for v in re.findall(rb"[-+]?\d*\.?\d+",
                                            pdf.resolve(box or b""))[:4]]
    except ValueError:
        bx = []
    if len(bx) != 4:
        bx = [0.0, 0.0, 612.0, 792.0]
    rot = pdf.inherited(pnum, b"Rotate")
    try:
        rot = int(float(rot)) % 360 if rot else 0
    except ValueError:
        rot = 0
    segs, arcs = [], []

    def run(content: bytes, ctm, res: bytes, depth=0):
        if depth > 12:
            return
        stack = []
        gs = []
        path = []          # list of subpaths: [(x, y), ...] with "c" flags
        cur = None
        start = None
        args = []
        xobjs = None
        for kind, val in _tokens(content):
            if kind != "op":
                if kind in ("n", "name"):
                    args.append(val)
                elif kind == "p" and val in (b"[", b"]"):
                    pass
                continue
            op = val
            try:
                if op == b"q":
                    gs.append(list(ctm))
                elif op == b"Q":
                    if gs:
                        ctm = gs.pop()
                elif op == b"cm" and len(args) >= 6:
                    ctm = _mul([float(a) for a in args[-6:]], ctm)
                elif op == b"m" and len(args) >= 2:
                    cur = start = (args[-2], args[-1])
                elif op == b"l" and len(args) >= 2 and cur is not None:
                    p = (args[-2], args[-1])
                    path.append(("l", cur, p))
                    cur = p
                elif op in (b"c", b"v", b"y") and cur is not None:
                    a = args[-6:] if op == b"c" else args[-4:]
                    if op == b"c" and len(a) == 6:
                        c1, c2, p = (a[0], a[1]), (a[2], a[3]), (a[4], a[5])
                    elif op == b"v" and len(a) == 4:
                        c1, c2, p = cur, (a[0], a[1]), (a[2], a[3])
                    elif len(a) == 4:
                        c1, c2, p = (a[0], a[1]), (a[2], a[3]), (a[2], a[3])
                    else:
                        args = []
                        continue
                    path.append(("c", cur, c1, c2, p))
                    cur = p
                elif op == b"h" and cur is not None and start is not None:
                    if cur != start:
                        path.append(("l", cur, start))
                    cur = start
                elif op == b"re" and len(args) >= 4:
                    x, y, w, h = args[-4:]
                    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                    for i in range(4):
                        path.append(("l", pts[i], pts[(i + 1) % 4]))
                    cur = start = (x, y)
                elif op in (b"S", b"s", b"f", b"F", b"f*", b"B", b"B*",
                            b"b", b"b*"):
                    if op in (b"s", b"b", b"b*") and cur is not None and \
                            start is not None and cur != start:
                        path.append(("l", cur, start))
                    for it in path:
                        if len(segs) >= max_segs:
                            break
                        if it[0] == "l":
                            a_ = _xf(ctm, *it[1])
                            b_ = _xf(ctm, *it[2])
                            segs.append((a_[0], a_[1], b_[0], b_[1]))
                        else:
                            p0, c1, c2, p3 = it[1:]
                            pts = []
                            for k in range(9):
                                t = k / 8
                                u = 1 - t
                                x = (u ** 3 * p0[0] + 3 * u * u * t * c1[0]
                                     + 3 * u * t * t * c2[0] + t ** 3 * p3[0])
                                y = (u ** 3 * p0[1] + 3 * u * u * t * c1[1]
                                     + 3 * u * t * t * c2[1] + t ** 3 * p3[1])
                                pts.append(_xf(ctm, x, y))
                            for a_, b_ in zip(pts, pts[1:]):
                                segs.append((a_[0], a_[1], b_[0], b_[1]))
                            xs = [p[0] for p in pts]
                            ys = [p[1] for p in pts]
                            arcs.append((min(xs), min(ys), max(xs), max(ys)))
                    path = []
                    cur = start = None
                elif op == b"n":
                    path = []
                    cur = start = None
                elif op == b"Do" and args and isinstance(args[-1], bytes):
                    if xobjs is None:
                        xobjs = pdf.entry(pdf.resolve(res or b""),
                                          b"XObject") or b""
                        xobjs = pdf.resolve(xobjs)
                    ref = pdf.entry(xobjs, args[-1])
                    m_ = _REF_RX.match(ref or b"")
                    if m_:
                        on = int(m_.group(1))
                        head = pdf.get(on)
                        if b"/Form" in head and on in pdf.streams:
                            mx = pdf.entry(head, b"Matrix")
                            mm = [float(v) for v in re.findall(
                                rb"[-+]?\d*\.?\d+", mx or b"")][:6]
                            sub = _mul(mm, ctm) if len(mm) == 6 else ctm
                            sres = pdf.entry(head, b"Resources") or res
                            run(pdf.streams[on], sub, sres, depth + 1)
            except (TypeError, ValueError, IndexError):
                pass
            args = []
        del stack

    cont = pdf.entry(pb, b"Contents") or b""
    streams = []
    if cont.startswith(b"["):
        for m in _REF_RX.finditer(cont):
            streams.append(pdf.streams.get(int(m.group(1)), b""))
    else:
        m = _REF_RX.match(cont)
        if m:
            n_ = int(m.group(1))
            if n_ in pdf.streams:
                streams.append(pdf.streams[n_])
            else:                         # an array held in an object
                for m2 in _REF_RX.finditer(pdf.get(n_)):
                    streams.append(pdf.streams.get(int(m2.group(1)), b""))
    res = pdf.inherited(pnum, b"Resources") or b""
    run(b"\n".join(streams), [1.0, 0.0, 0.0, 1.0, 0.0, 0.0], res)
    # the page box at the origin, then its rotation (clockwise on screen)
    x0, y0, x1, y1 = bx
    W, H = x1 - x0, y1 - y0

    def tr(x, y):
        x, y = x - x0, y - y0
        if rot == 90:
            return y, W - x
        if rot == 180:
            return W - x, H - y
        if rot == 270:
            return H - y, x
        return x, y
    out_s = []
    for a, b, c, d in segs:
        p, q = tr(a, b), tr(c, d)
        out_s.append((p[0], p[1], q[0], q[1]))
    out_a = []
    for a, b, c, d in arcs:
        p, q = tr(a, b), tr(c, d)
        out_a.append((min(p[0], q[0]), min(p[1], q[1]),
                      max(p[0], q[0]), max(p[1], q[1])))
    w_, h_ = (H, W) if rot in (90, 270) else (W, H)
    return {"w": w_, "h": h_, "segs": out_s, "arcs": out_a,
            "pages": len(pages)}
