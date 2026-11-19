#!/usr/bin/env python3
"""The one place the tools learn who the company is. Stdlib only.

Reads brain.config.json at the brain's root (the repository root, or the folder named by the
BRAIN_ROOT environment variable). Nothing about a company is hard-coded anywhere else: the legal
entities, their folders and their short codes all come from that file.

  entities   list of {"code": "DE", "name": "...", "folder": "Entity_DE", "currency": "EUR"}
             code    short label used in registers ("DE: pay the insurance"), record rows and the store
             folder  top-level folder that holds this entity's legal and finance records
  not_our_entity   phrases that contain an entity code but mean somebody else (a client called
             "Something DE"), so they are not counted as a mention of our entity
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BASE_AREAS = {
    "finance": "finance",
    "01_Clients": "clients",
    "02_Meetings": "meetings",
    "03_Sales": "sales",
    "04_Marketing": "marketing",
    "05_Operations": "operations",
    "00_Brain": "brain",
    "tools": "system",
    "scripts": "system",
}
BASE_LABELS = {
    "00_Brain": "Brain",
    "01_Clients": "Clients",
    "02_Meetings": "Meetings",
    "03_Sales": "Sales",
    "04_Marketing": "Marketing",
    "05_Operations": "Operations",
    "finance": "Finance",
    "tools": "Tools",
    "scripts": "Tools",
}
CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")


def root() -> Path:
    return Path(os.environ.get("BRAIN_ROOT") or REPO_ROOT).resolve()


def load(at: Path | None = None) -> dict:
    path = (at or root()) / "brain.config.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"company": "", "entities": [], "not_our_entity": []}
    cfg.setdefault("entities", [])
    cfg.setdefault("not_our_entity", [])
    for ent in cfg["entities"]:
        if not CODE.match(str(ent.get("code", ""))):
            raise SystemExit(f"brain.config.json: entity code {ent.get('code')!r} must be 1-16 letters, digits, _ or -")
    return cfg


def entities(at: Path | None = None) -> list:
    return load(at)["entities"]


def codes(at: Path | None = None) -> tuple:
    return tuple(e["code"] for e in entities(at))


def area_by_top(at: Path | None = None) -> dict:
    out = dict(BASE_AREAS)
    for e in entities(at):
        if e.get("folder"):
            out[e["folder"]] = "finance-" + e["code"].lower()
    return out


def label_by_top(at: Path | None = None) -> dict:
    out = dict(BASE_LABELS)
    for e in entities(at):
        if e.get("folder"):
            out[e["folder"]] = e["code"]
    return out


def prefixes(at: Path | None = None) -> list:
    """Top-level folders the catalogue walks."""
    return list(BASE_AREAS) + [e["folder"] for e in entities(at) if e.get("folder")]


def not_our_entity(at: Path | None = None) -> list:
    return [str(x) for x in load(at)["not_our_entity"] if str(x).strip()]


_IGNORE_CACHE: dict = {}


def ignore_patterns(at: Path | None = None) -> list:
    """The lines of `.brainignore` at the brain's root (gitignore-like; `#` comments; `!` is not supported)."""
    base = at or root()
    key = str(base)
    if key not in _IGNORE_CACHE:
        try:
            lines = (base / ".brainignore").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        _IGNORE_CACHE[key] = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith(("#", "!"))]
    return _IGNORE_CACHE[key]


def ignored(rel: str, at: Path | None = None) -> bool:
    """True when a path relative to the brain's root is matched by `.brainignore`. Such a path is not
    catalogued, not searched, not embedded and never uploaded. Matching is case-insensitive.
      name/        a folder of that name anywhere        dir/sub/     that folder, from the root
      *.ext        a file name pattern anywhere          dir/*.csv    a path pattern, from the root
      name         a file or folder of that name anywhere"""
    import fnmatch
    low = rel.replace("\\", "/").lower().strip("/")
    parts = low.split("/")
    for raw in ignore_patterns(at):
        pat = raw.lower()
        if pat.endswith("/"):
            pat = pat.strip("/")
            if "/" in pat:
                if low == pat or low.startswith(pat + "/"):
                    return True
            elif pat in parts[:-1] or any(fnmatch.fnmatch(seg, pat) for seg in parts[:-1]):
                return True
            continue
        pat = pat.lstrip("/")
        if "/" in pat:
            if fnmatch.fnmatch(low, pat) or low.startswith(pat + "/"):
                return True
        elif any(fnmatch.fnmatch(seg, pat) for seg in parts):
            return True
    return False
