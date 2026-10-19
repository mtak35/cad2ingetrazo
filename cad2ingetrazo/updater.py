# SPDX-License-Identifier: GPL-3.0-or-later
"""«Update the extension»: the newest CAD2IngeTrazo from its GitHub
repository (https://github.com/mtak35/cad2ingetrazo) — its version read
first; when it is newer, the package downloaded and put in place of this
one (the old one kept beside it as a backup), to load at the next start
of IngeTrazo."""
from __future__ import annotations

import io
import re
import shutil
import ssl
import urllib.request
import zipfile
from pathlib import Path

REPO = "mtak35/cad2ingetrazo"
BRANCH = "main"
PAGE = f"https://github.com/{REPO}"
RAW_INIT = (f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
            "cad2ingetrazo/__init__.py")
ZIP = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
PKG = "cad2ingetrazo"


def _get(url: str, timeout: float = 25.0) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "CAD2IngeTrazo-updater", "Cache-Control": "no-cache"})
    try:
        ctx = ssl.create_default_context()
    except Exception:  # noqa: BLE001
        ctx = None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def latest_version() -> str:
    """The version on GitHub's main branch («3.18.0»), or raises."""
    txt = _get(RAW_INIT).decode("utf-8", "replace")
    m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", txt)
    if not m:
        raise RuntimeError("no version found on GitHub")
    return m.group(1)


def newer(remote: str, local: str) -> bool:
    return _vt(remote) > _vt(local)


def install(dest: Path | None = None) -> Path:
    """The main branch's package downloaded and put in ``dest`` (this
    package's folder); the old files moved to ``<dest>_backup``. The
    backup's path."""
    dest = Path(dest or Path(__file__).resolve().parent)
    data = _get(ZIP, timeout=90.0)
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    root = next((n for n in names if re.match(
        rf"^[^/]+/{PKG}/__init__\.py$", n)), None)
    if root is None:
        raise RuntimeError("the download holds no cad2ingetrazo package")
    pre = root[:-len("__init__.py")]
    tmp = dest.with_name(dest.name + "_new")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for n in names:
        if not n.startswith(pre) or n.endswith("/"):
            continue
        rel = n[len(pre):]
        if ".." in Path(rel).parts:
            continue
        out = tmp / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zf.read(n))
    if not (tmp / "__init__.py").exists():
        raise RuntimeError("the download is incomplete")
    bak = dest.with_name(dest.name + "_backup")
    if bak.exists():
        shutil.rmtree(bak, ignore_errors=True)
    shutil.copytree(dest, bak, ignore=shutil.ignore_patterns("__pycache__"))
    for p in tmp.rglob("*"):             # over the old files, in place
        rel = p.relative_to(tmp)
        q = dest / rel
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
        else:
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
    shutil.rmtree(tmp, ignore_errors=True)
    for c in dest.rglob("__pycache__"):
        shutil.rmtree(c, ignore_errors=True)
    return bak
