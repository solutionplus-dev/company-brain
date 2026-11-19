#!/usr/bin/env python3
"""Vault size budgets and duplicate-media report.  Stdlib only.  Always exits 0.

Reads tools/vault_health/budgets.json:
  * registers  - per-file KB budgets (OPEN_LOOPS, EMAIL_BACKLOG, DEADLINES, TODO, CALENDAR, ...)
  * generic    - any .md/.json/.csv above `kb` outside the excluded directories
  * media      - extensions hashed (sha256) to find duplicates added since the last run

Status per file: OK (< 80 % of budget) / WARN (>= 80 %) / OVER (>= 100 %).
Generic files that are verbatim raw sources or generated files (info_globs) are INFO, never OVER.

Read-only except for ONE state file (.index/size_check_state.json: the media paths and hashes seen
by the last run). It never moves, trims, deletes or rewrites a vault file.

Usage:
  python3 tools/vault_health/size_check.py                 # markdown table, then JSON after a marker line
  python3 tools/vault_health/size_check.py --json          # JSON only
  python3 tools/vault_health/size_check.py --md            # markdown only
  python3 tools/vault_health/size_check.py --candidates    # + draft Recommend-candidate lines for OVER registers / new duplicates
  python3 tools/vault_health/size_check.py --no-state      # do not update the duplicate-media state file
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = Path(os.environ.get("BRAIN_ROOT") or HERE.parents[1])
KB = 1024


def kb(n: int) -> float:
    return round(n / KB, 1)


def load_budgets(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------- walking
def is_excluded_dir(rel_dir: str, name: str, abs_dir: Path, g: dict) -> bool:
    """rel_dir = vault-relative path of the directory itself (posix)."""
    if name in g.get("exclude_dirs", []):
        return True
    for p in g.get("exclude_dir_prefixes", []):
        if name.startswith(p):
            return True
    if name in g.get("exclude_components", []):
        return True
    for frag in g.get("exclude_if_contains", []):
        if frag in rel_dir:
            return True
    for pth in g.get("exclude_paths", []):
        if rel_dir == pth or rel_dir.startswith(pth + "/"):
            return True
    # any virtual environment
    if name in (".venv", "venv") or (abs_dir / "pyvenv.cfg").is_file():
        return True
    return False


def walk(root: Path, g: dict):
    """Yield (rel_posix, abs_path) for every regular file outside the excluded directories."""
    for dp, dn, fn in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dp, root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        keep = []
        for d in sorted(dn):
            rd = f"{rel_dir}/{d}" if rel_dir else d
            if is_excluded_dir(rd, d, Path(dp) / d, g):
                continue
            keep.append(d)
        dn[:] = keep
        for f in sorted(fn):
            p = Path(dp) / f
            if p.is_symlink() or not p.is_file():
                continue
            rel = f"{rel_dir}/{f}" if rel_dir else f
            yield rel, p


def matches_any(rel: str, globs: list[str]) -> bool:
    for gl in globs:
        pat = gl.replace("**/", "*/").replace("/**", "/*")
        if fnmatch.fnmatch(rel, gl) or fnmatch.fnmatch(rel, pat):
            return True
        # '**' in fnmatch already crosses '/', so a plain fnmatch on the original pattern is enough
    return False


def status_for(size: int, budget_kb: float, warn_ratio: float) -> tuple[str, float]:
    ratio = size / (budget_kb * KB) if budget_kb else 0.0
    if ratio >= 1.0:
        return "OVER", ratio
    if ratio >= warn_ratio:
        return "WARN", ratio
    return "OK", ratio


# ----------------------------------------------------------------------------- registers + generic
def check_registers(root: Path, b: dict) -> list[dict]:
    out = []
    wr = float(b.get("warn_ratio", 0.8))
    for r in b.get("registers", []):
        base = root.parent if r.get("base") == "documents" else root
        p = base / r["path"]
        label = ("~/Documents/" + r["path"]) if r.get("base") == "documents" else r["path"]
        rec = {"path": label, "budget_kb": r["kb"], "rollover": r.get("rollover", "manual"), "note": r.get("note", "")}
        if r.get("level"):
            rec["level"] = r["level"]
        try:
            size = p.stat().st_size
        except OSError:
            rec.update({"size_bytes": None, "size_kb": None, "pct": None, "status": "MISSING"})
            out.append(rec)
            continue
        st, ratio = status_for(size, r["kb"], wr)
        rec.update({"size_bytes": size, "size_kb": kb(size), "pct": round(ratio * 100), "status": st, "abs_path": str(p)})
        out.append(rec)
    return out


def check_generic(root: Path, b: dict, register_paths: set[str]) -> list[dict]:
    g = b.get("generic", {})
    limit_kb = float(g.get("kb", 100))
    wr = float(b.get("warn_ratio", 0.8))
    exts = tuple(e.lower() for e in g.get("exts", [".md", ".json", ".csv"]))
    info = g.get("info_globs", [])
    out = []
    for rel, p in walk(root, g):
        if not rel.lower().endswith(exts):
            continue
        if rel in register_paths:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        st, ratio = status_for(size, limit_kb, wr)
        if st == "OK":
            continue
        if matches_any(rel, info):
            st = "INFO"
        out.append({"path": rel, "size_bytes": size, "size_kb": kb(size), "budget_kb": limit_kb,
                    "pct": round(ratio * 100), "status": st})
    out.sort(key=lambda r: -r["size_bytes"])
    return out


# ----------------------------------------------------------------------------- duplicate media
def sha256_file(p: Path) -> str | None:
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            while True:
                blk = f.read(1024 * 1024)
                if not blk:
                    break
                h.update(blk)
    except OSError:
        return None
    return h.hexdigest()


def media_report(root: Path, b: dict, update_state: bool) -> dict:
    m = b.get("media", {})
    g = b.get("generic", {})
    exts = tuple(e.lower() for e in m.get("exts", []))
    max_hash = int(m.get("max_hash_mb", 2048)) * 1024 * 1024
    state_path = root / m.get("state_file", ".index/size_check_state.json")
    prev = {}
    had_state = False
    try:
        with state_path.open(encoding="utf-8") as f:
            data = json.load(f)
        prev = data.get("media", {})
        had_state = True
    except (OSError, json.JSONDecodeError):
        prev = {}

    files = []
    for rel, p in walk(root, g):
        if rel.lower().endswith(exts):
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((rel, p, st.st_size, int(st.st_mtime)))

    by_size: dict[int, list] = {}
    for rec in files:
        by_size.setdefault(rec[2], []).append(rec)

    hashes: dict[str, str] = {}
    skipped_big = []
    for size, group in by_size.items():
        if size == 0:
            continue
        need = len(group) >= 2
        for rel, p, sz, mt in group:
            old = prev.get(rel)
            if old and old.get("size") == sz and old.get("mtime") == mt and old.get("sha256"):
                hashes[rel] = old["sha256"]
            elif need:
                if sz > max_hash:
                    skipped_big.append(rel)
                    continue
                h = sha256_file(p)
                if h:
                    hashes[rel] = h

    groups: dict[str, list[str]] = {}
    for rel, h in hashes.items():
        groups.setdefault(h, []).append(rel)
    dup_groups = {h: sorted(v) for h, v in groups.items() if len(v) >= 2}
    new_groups = []
    for h, paths in dup_groups.items():
        if had_state and any(pth not in prev for pth in paths):
            new_groups.append({"sha256": h, "size_kb": kb(next(sz for r, _, sz, _ in files if r == paths[0])),
                               "paths": paths, "paths_new_since_last_run": [x for x in paths if x not in prev]})
    new_groups.sort(key=lambda r: r["paths"][0])

    if update_state:
        state = {"run_at": datetime.now().replace(microsecond=0).isoformat(),
                 "media": {rel: {"size": sz, "mtime": mt, "sha256": hashes.get(rel)} for rel, _, sz, mt in files}}
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(state_path)
        except OSError as e:
            skipped_big.append(f"(state not written: {e})")

    return {
        "baseline": not had_state,
        "media_files": len(files),
        "duplicate_groups_total": len(dup_groups),
        "new_duplicate_groups": new_groups,
        "duplicate_groups_all": [{"sha256": h, "paths": v} for h, v in sorted(dup_groups.items(), key=lambda kv: kv[1][0])],
        "skipped_too_big_to_hash": skipped_big,
        "state_file": str(state_path),
    }


# ----------------------------------------------------------------------------- output
def md_table(rows: list[dict]) -> list[str]:
    lines = ["| File | Size (KB) | Budget (KB) | % | Status |", "|---|---:|---:|---:|---|"]
    for r in rows:
        sz = "—" if r.get("size_kb") is None else f"{r['size_kb']:.1f}"
        pct = "—" if r.get("pct") is None else f"{r['pct']}"
        lines.append(f"| `{r['path']}` | {sz} | {r['budget_kb']:g} | {pct} | {r['status']} |")
    return lines


def counts(rows: list[dict]) -> dict:
    c: dict[str, int] = {}
    for r in rows:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c


def build_markdown(rep: dict, top_n: int) -> str:
    s = rep["summary"]
    out = [f"# Vault size check — {rep['generated_at']}", ""]
    fmt = lambda d: " · ".join(f"{v} {k}" for k, v in sorted(d.items())) or "none"
    out.append(f"Registers: {fmt(s['registers'])} · other large text files: {fmt(s['generic'])} · duplicate media groups: "
               f"{rep['media']['duplicate_groups_total']} ({len(rep['media']['new_duplicate_groups'])} new since the last run"
               f"{', baseline run' if rep['media']['baseline'] else ''}).")
    out.append("")
    out += md_table(rep["registers"])
    gen = rep["generic"]
    if gen:
        out.append("")
        shown = [r for r in gen if r["status"] in ("OVER", "WARN")][:top_n]
        n_over = sum(1 for r in gen if r["status"] == "OVER")
        n_info = sum(1 for r in gen if r["status"] == "INFO")
        out.append(f"Other text files above the generic budget (OVER {n_over}, INFO raw/generated {n_info}; top {len(shown)} OVER/WARN shown, all in the JSON):")
        out.append("")
        out += md_table(shown) if shown else ["_none_"]
    out.append("")
    med = rep["media"]
    if med["new_duplicate_groups"]:
        out.append("New duplicate media since the last run (list only, nothing is moved):")
        for gp in med["new_duplicate_groups"]:
            out.append(f"- `{gp['sha256'][:12]}…` {gp['size_kb']} KB: " + " = ".join(f"`{p}`" for p in gp["paths"]))
    elif med["baseline"]:
        out.append(f"Duplicate media: baseline recorded ({med['media_files']} media files, {med['duplicate_groups_total']} duplicate groups already present; listed in the JSON). New ones are reported from the next run.")
    else:
        out.append("New duplicate media since the last run: none.")
    if med["skipped_too_big_to_hash"]:
        out.append(f"Not hashed (too big): {len(med['skipped_too_big_to_hash'])} file(s).")
    return "\n".join(out)


def candidates(rep: dict, skill: str) -> list[str]:
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for r in rep["registers"]:
        if r["status"] != "OVER":
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", r["path"].replace("~/Documents/", "").lower().rsplit(".", 1)[0]).strip("-")
        how = {"sections": f"stage a proposal with `python3 tools/vault_health/rollover.py stage {r['path']}` (never writes the live file), then the owner reviews it",
               "changelog": f"stage a proposal with `python3 tools/vault_health/rollover.py stage {r['path']}`, then the owner reviews it",
               }.get(r["rollover"], "slim it by judgement (no tool method); the owner reviews the proposal")
        out.append(
            f"- {today} · {skill} · key=vault-size-{slug} · U2·S2 · both · process · WHAT: Review the archive-rollover proposal for {r['path']}: "
            f"{r['size_kb']} KB against a {r['budget_kb']:g} KB budget ({r['pct']} %). · WHY: an over-budget register is read in full by every daily run and "
            f"by the owner's page; {how}. [`{r['path']}`, `tools/vault_health/budgets.json`] · IMPACT: slower, truncated or skipped reads (calculated) · "
            f"EFFORT: M · BY: none · CONF: high · WHO: owner")
    for gp in rep["media"]["new_duplicate_groups"][:3]:
        out.append(
            f"- {today} · {skill} · key=vault-dup-media-{gp['sha256'][:8]} · U3·S2 · both · process · WHAT: Decide which copy of a duplicated media file stays "
            f"({' = '.join(gp['paths'])}). · WHY: identical sha256 ({gp['size_kb']} KB each); the owner runs any removal (give the `mv … ~/.Trash/` command, never `rm`). "
            f"[`tools/vault_health/size_check.py` output] · IMPACT: disk and search noise · EFFORT: S · BY: none · CONF: medium · WHO: owner")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Vault size budgets + duplicate media (always exits 0)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--budgets", default=str(HERE / "budgets.json"))
    ap.add_argument("--json", action="store_true", help="JSON only")
    ap.add_argument("--md", action="store_true", help="markdown only")
    ap.add_argument("--candidates", action="store_true", help="also print draft candidate lines")
    ap.add_argument("--skill", default="brain-daily", help="skill name written into candidate lines")
    ap.add_argument("--no-state", action="store_true", help="do not update the duplicate-media state file")
    ap.add_argument("--top", type=int, default=12, help="how many generic OVER/WARN rows to show in markdown")
    args = ap.parse_args()
    t0 = time.time()
    try:
        root = Path(args.root).resolve()
        b = load_budgets(Path(args.budgets))
        regs = check_registers(root, b)
        reg_paths = {r["path"] for r in regs if not r["path"].startswith("~/")}
        gen = check_generic(root, b, reg_paths)
        med = media_report(root, b, update_state=not args.no_state)
        rep = {
            "generated_at": datetime.now().replace(microsecond=0).isoformat(),
            "root": str(root),
            "budgets_file": str(Path(args.budgets)),
            "summary": {"registers": counts(regs), "generic": counts(gen)},
            "registers": regs,
            "generic": gen,
            "media": med,
            "seconds": round(time.time() - t0, 1),
        }
        if args.candidates:
            rep["candidate_lines"] = candidates(rep, args.skill)
    except Exception as e:  # never fail the run
        rep = {"error": f"{type(e).__name__}: {e}", "generated_at": datetime.now().replace(microsecond=0).isoformat()}
        if args.md or not args.json:
            print(f"size_check failed (exit 0 anyway): {rep['error']}")
        if args.json or not args.md:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        sys.exit(0)

    want_md = args.md or not args.json
    want_json = args.json or not args.md
    if want_md:
        print(build_markdown(rep, args.top))
        if args.candidates and rep.get("candidate_lines"):
            print("\nCandidate lines (draft; a run decides which of them reach the owner's page):")
            for ln in rep["candidate_lines"]:
                print(ln)
    if want_md and want_json:
        print("\n---JSON---")
    if want_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
