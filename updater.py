# SPDX-License-Identifier: GPL-3.0-or-later
"""«Is there a newer CAD2IngeTrazo?» — the version listed in the IngeTrazo
extension catalogue (ingelibre/ingetrazo-extensions) read and compared with
this one. Nothing is downloaded or installed here: updates come from the
Extension Manager, checked against the catalogue's SHA-256."""
from __future__ import annotations

import re
import ssl
import urllib.request
from pathlib import Path

PAGE = "https://github.com/mtak35/cad2ingetrazo"
CATALOGUE = ("https://raw.githubusercontent.com/ingelibre/"
             "ingetrazo-extensions/main/extensions/cad2ingetrazo.toml")


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "CAD2IngeTrazo", "Cache-Control": "no-cache"})
    try:
        ctx = ssl.create_default_context()
    except Exception:  # noqa: BLE001
        ctx = None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def latest_version() -> str:
    """The version the extension catalogue lists («3.23.3»), or raises."""
    txt = _get(CATALOGUE).decode("utf-8", "replace")
    m = re.search(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']", txt, re.M)
    if not m:
        raise RuntimeError("no version in the extension catalogue")
    return m.group(1)


def newer(remote: str, local: str) -> bool:
    return _vt(remote) > _vt(local)


def hide_backups(here: Path | None = None) -> int:
    """Copies the 3.20.1 updater left beside this package as
    ``cad2ingetrazo_backup_…`` — IngeTrazo loads them as a second
    CAD2IngeTrazo — renamed ``_cad2ingetrazo_backup_…`` (kept, never
    loaded). How many."""
    here = Path(here or Path(__file__).resolve().parent)
    n = 0
    try:
        for p in here.parent.iterdir():
            if p.is_dir() and p.name.startswith(f"{here.name}_backup"):
                q = p.with_name("_" + p.name)
                if not q.exists():
                    p.rename(q)
                    n += 1
    except OSError:
        pass
    return n
