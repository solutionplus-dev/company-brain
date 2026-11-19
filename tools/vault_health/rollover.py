#!/usr/bin/env python3
"""Archive-rollover PROPOSAL for an over-budget register.  Stdlib only.

The rollover method for registers (OPEN_LOOPS, EMAIL_BACKLOG, CALENDAR, DEADLINES, a JSON changelog), as a tool:

  * the register is split into dated sections (a section is "old" when the FIRST date in its header is
    earlier than the cutoff = the first day of the previous month; undated sections and the preamble stay);
  * the old sections are copied VERBATIM, in order, to   00_Brain/ARCHIVE/<NAME>_<period>.md   (with a header
    that records the source sha256 and the cutoff);
  * a slimmed proposal   00_Brain/ARCHIVE/_proposed/<NAME>.proposed.md   keeps the preamble and the kept
    sections and puts ONE placeholder "Carried forward from before <cutoff>" section where the first old
    section stood. THE AGENT fills that block by judgement (what is still open or unsettled); this tool does not;
  * a worklist   _proposed/<NAME>.worklist.json   lists every item of the old sections (checkbox, bullet,
    table row) for the agent's classification;
  * a manifest   _proposed/<NAME>.rollover.json   records source path, sha256, cutoff, level and the order
    of old/keep sections, so that  `verify`  can rebuild the original from archive + proposal and compare
    its sha256 with the source.

HARD RULES (enforced in code): the live register is NEVER written; no existing file is overwritten (a name
that exists gets a _v2, _v3 ... suffix); outputs go only under 00_Brain/ARCHIVE/. Applying a proposal
(replacing the live file) needs the owner's OK and is done by the owner or on the owner's instruction.

A changelog-style JSON ({"_note":..., "entries":[{"when":...}]}) is split by `when`.
todos.json and other shapes are not handled (manual).

Usage:
  rollover.py plan  [FILE ...] [--over] [--cutoff D] [--today D]      what would move (no writes)
  rollover.py stage FILE [FILE ...] | --all-over [--cutoff D] [--level 1|2] [--force-new]
  rollover.py verify FILE                                              rebuild-from-disk check (sha256)
FILE: vault-relative path, ~/Documents/<name>, or absolute.
Exit code 0 unless the arguments are invalid; refusals are reported in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ in the vault
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import size_check as sc  # noqa: E402

ROOT = Path(os.environ.get("BRAIN_ROOT") or os.environ.get("VAULT_ROOT") or HERE.parents[1]).resolve()  # VAULT_ROOT: testing on a copy
ARCH = ROOT / "00_Brain" / "ARCHIVE"
PROP = ARCH / "_proposed"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ARCHIVE_MARK = "<!-- ARCHIVE-HEADER-END -->"
CF_WORD = "Carried forward from before"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def split_lines(text: str) -> list[str]:
    return re.findall(r"[^\n]*\n|[^\n]+", text)


# ----------------------------------------------------------------------------- paths
def resolve(arg: str) -> Path:
    if arg.startswith("~/Documents/"):
        return ROOT.parent / arg[len("~/Documents/"):]
    p = Path(arg)
    return p if p.is_absolute() else ROOT / p


def label_of(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace(os.sep, "/")
    except ValueError:
        try:
            return "~/Documents/" + str(p.relative_to(ROOT.parent)).replace(os.sep, "/")
        except ValueError:
            return str(p)


def name_of(p: Path) -> str:
    """NAME used in the output file names; unique per source."""
    stem = p.stem
    try:
        rel = p.relative_to(ROOT)
    except ValueError:
        return stem  # ~/Documents/<name>
    parts = list(rel.parts[:-1])
    if parts == ["00_Brain"]:
        return stem
    if not parts:
        return "ROOT_" + stem
    return "_".join(parts) + "_" + stem


def under_archive(p: Path) -> bool:
    try:
        p.resolve().relative_to(ARCH.resolve())
        return True
    except ValueError:
        return False


def unique(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    n = 2
    while True:
        q = p.with_name(f"{stem}_v{n}{suf}")
        if not q.exists():
            return q
        n += 1


def safe_write(path: Path, data: bytes) -> None:
    assert under_archive(path), f"refusing to write outside 00_Brain/ARCHIVE: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:  # 'x' = never overwrite
        f.write(data)


def default_cutoff(today: date) -> date:
    first_this = today.replace(day=1)
    prev_last = first_this - timedelta(days=1)
    return prev_last.replace(day=1)


# ----------------------------------------------------------------------------- markdown sections
def split_sections(text: str, level: int) -> tuple[str, list[str]]:
    mark = "#" * level + " "
    pre: list[str] = []
    secs: list[str] = []
    cur: list[str] | None = None
    fence = False
    for ln in split_lines(text):
        if ln.startswith("```"):
            fence = not fence
        if (not fence) and ln.startswith(mark):
            if cur is not None:
                secs.append("".join(cur))
            cur = [ln]
        elif cur is None:
            pre.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        secs.append("".join(cur))
    return "".join(pre), secs


def header_of(sec: str) -> str:
    return sec.split("\n", 1)[0]


def classify(sec: str, cutoff: str) -> tuple[str, str | None]:
    ds = DATE_RE.findall(header_of(sec))
    if not ds:
        return "keep", None
    return ("old" if ds[0] < cutoff else "keep"), ds[0]


def pick_level(text: str, hint: int | None) -> int:
    if hint in (1, 2):
        return hint
    best, best_n = 2, -1
    for lv in (1, 2):
        _, secs = split_sections(text, lv)
        n = sum(1 for s in secs if DATE_RE.search(header_of(s)))
        if n > best_n:
            best, best_n = lv, n
    return best


ITEM_CB = re.compile(r"^- \[(.)\] ")
SEP_ROW = re.compile(r"^\|[\s:\-|]+\|\s*$")


def extract_items(sections: list[tuple[str, int]]) -> list[dict]:
    """sections: [(section_text, first_line_number_1based)] for the OLD sections."""
    items = []
    for sec, base in sections:
        hdr = header_of(sec)
        sd = (DATE_RE.findall(hdr) or [None])[0]
        lines = split_lines(sec)
        i = 0
        tbl_hdr = None
        while i < len(lines):
            ln = lines[i].rstrip("\n")
            no = base + i
            if ln.startswith("|"):
                nxt = lines[i + 1].rstrip("\n") if i + 1 < len(lines) else ""
                if SEP_ROW.match(nxt) and not SEP_ROW.match(ln):
                    tbl_hdr = ln
                    i += 2
                    continue
                if SEP_ROW.match(ln):
                    i += 1
                    continue
                items.append({"id": f"L{no}", "section": hdr, "date": sd, "kind": "row", "table_header": tbl_hdr, "text": ln})
                i += 1
                continue
            is_cb = bool(ITEM_CB.match(ln))
            is_b = ln.startswith("- ") and not is_cb
            if is_cb or is_b:
                j = i + 1
                while j < len(lines) and lines[j].strip() != "" and lines[j][0] in " \t":
                    j += 1
                kind = ({"x": "cb-done", "X": "cb-done", " ": "cb-open"}.get(ln[3], "cb-other")) if is_cb else "bullet"
                items.append({"id": f"L{no}", "section": hdr, "date": sd, "kind": kind, "text": "".join(lines[i:j]).rstrip("\n")})
                i = j
                continue
            if ln.startswith("#"):
                tbl_hdr = None
            i += 1
    return items


# ----------------------------------------------------------------------------- planning
def period_label(dates: list[str]) -> str:
    months = sorted({d[:7] for d in dates if d})
    if not months:
        return "old"
    return months[0] if len(months) == 1 else f"{months[0]}_to_{months[-1]}"


def analyse_md(p: Path, cutoff: str, level_hint: int | None) -> dict:
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    level = pick_level(text, level_hint)
    pre, secs = split_sections(text, level)
    meta = []
    ln = len(split_lines(pre)) + 1
    for i, s in enumerate(secs):
        cls, d = classify(s, cutoff)
        n = len(split_lines(s))
        meta.append({"idx": i, "cls": cls, "date": d, "start": ln, "bytes": len(s.encode("utf-8"))})
        ln += n
    old = [m for m in meta if m["cls"] == "old"]
    return {"raw": raw, "text": text, "level": level, "pre": pre, "secs": secs, "meta": meta,
            "n_old": len(old), "old_bytes": sum(m["bytes"] for m in old),
            "dates": [m["date"] for m in old]}


def entries_of(obj) -> tuple[list, str]:
    if isinstance(obj, dict) and isinstance(obj.get("entries"), list):
        return obj["entries"], "dict"
    if isinstance(obj, list):
        return obj, "list"
    raise ValueError("unsupported JSON shape (needs a list or {'entries': [...]})")


def entry_date(e) -> str | None:
    w = e.get("when") if isinstance(e, dict) else None
    return w[:10] if isinstance(w, str) and DATE_RE.fullmatch(w[:10]) else None


def canon(entries: list) -> bytes:
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def pending(name: str, stem: str | None = None) -> bool:
    """A proposal is pending when _proposed/ holds <NAME>.proposed* (also the bare file stem."""
    if not PROP.is_dir():
        return False
    return any(PROP.glob(f"{name}.proposed*")) or bool(stem and any(PROP.glob(f"{stem}.proposed*")))


def plan_one(arg: str, cutoff: str, level_hint: int | None, budgets: dict | None, force_new: bool = False) -> dict:
    p = resolve(arg)
    rec = {"file": label_of(p), "cutoff": cutoff}
    if not p.is_file():
        rec.update({"can_stage": False, "reason": "file not found"})
        return rec
    rec["size_kb"] = sc.kb(p.stat().st_size)
    name = name_of(p)
    rec["name"] = name
    rec["pending_proposal"] = pending(name, p.stem)
    for r in (budgets or {}).get("registers", []):
        if label_of(resolve(r["path"] if r.get("base") != "documents" else "~/Documents/" + r["path"])) == rec["file"]:
            rec["budget_kb"] = r["kb"]
            rec["rollover"] = r.get("rollover", "manual")
            if r.get("level"):
                level_hint = level_hint or r["level"]
    try:
        if p.suffix.lower() == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            ents, _shape = entries_of(obj)
            old = [e for e in ents if (entry_date(e) or "9999") < cutoff]
            rec.update({"kind": "changelog", "n_old": len(old), "n_entries": len(ents),
                        "old_kb": sc.kb(len(canon(old))), "dates": sorted({entry_date(e)[:7] for e in old if entry_date(e)})})
        else:
            a = analyse_md(p, cutoff, level_hint)
            rec.update({"kind": "sections", "level": a["level"], "n_sections": len(a["secs"]), "n_old": a["n_old"],
                        "old_kb": sc.kb(a["old_bytes"]), "dates": sorted({d[:7] for d in a["dates"] if d})})
    except ValueError as e:
        rec.update({"can_stage": False, "reason": f"manual: no tool method for this shape ({e})"})
        return rec
    except Exception as e:  # noqa: BLE001
        rec.update({"can_stage": False, "reason": f"{type(e).__name__}: {e}"})
        return rec
    if rec["n_old"] == 0:
        rec.update({"can_stage": False, "reason": f"nothing dated before {cutoff}"})
    elif rec["pending_proposal"] and not force_new:
        rec.update({"can_stage": False, "reason": "a proposal already exists in 00_Brain/ARCHIVE/_proposed (owner review pending); use --force-new to stage another"})
    else:
        rec.update({"can_stage": True, "reason": "ok"})
    return rec


# ----------------------------------------------------------------------------- stage
def stage_md(p: Path, cutoff: str, level_hint: int | None, force_new: bool, today: date) -> dict:
    name = name_of(p)
    a = analyse_md(p, cutoff, level_hint)
    level, secs, meta, pre, raw = a["level"], a["secs"], a["meta"], a["pre"], a["raw"]
    old_idx = [m["idx"] for m in meta if m["cls"] == "old"]
    period = period_label(a["dates"])
    arch_path = unique(ARCH / f"{name}_{period}.md")
    prop_path = PROP / f"{name}.proposed.md"
    if force_new:
        prop_path = unique(prop_path)
    man_path = PROP / f"{name}.rollover.json"
    wl_path = PROP / f"{name}.worklist.json"
    if force_new:
        man_path, wl_path = unique(man_path), unique(wl_path)
    arch_rel = label_of(arch_path)
    src_label = label_of(p)
    src_sha = sha(raw)
    mark = "#" * level
    hdr = (f"# Archive — {p.name}, sections dated before {cutoff}\n\n"
           f"**What this is:** the {len(old_idx)} sections of `{src_label}` whose header date is earlier than {cutoff}, copied here verbatim, in their original order.\n"
           f"**Source file:** `{src_label}` (state of {today.isoformat()}, sha256 of the source `{src_sha}`).\n"
           f"**Cutoff:** {cutoff} (the first day of the previous month). A section is old when the first date in its header is earlier than the cutoff; undated sections and the preamble are not archived. Section level: {'#' * level}.\n"
           f"**Archived on:** {today.isoformat()}. **Verbatim — do not edit.**\n"
           f"**Status:** a copy only, written by `tools/vault_health/rollover.py`. The live file `{src_label}` is unchanged pending the owner's review. "
           f"The slimmed version is the proposal `{label_of(prop_path)}`.\n\n"
           f"{ARCHIVE_MARK}\n\n")
    old_text = "".join(secs[i] for i in old_idx)
    archive = hdr + old_text
    cf_head = f"{mark} {CF_WORD} {cutoff} (archive: {arch_rel})\n\n"
    cf_body = (f"<!-- ROLLOVER-CARRY-FORWARD-PLACEHOLDER: the agent has not classified the archived items yet -->\n"
               f"**PLACEHOLDER — written {today.isoformat()} by `tools/vault_health/rollover.py`.** The {len(old_idx)} sections dated before {cutoff} were moved to "
               f"`{arch_rel}` verbatim. The agent must now list here, in the register's own shape, only what is still open or unsettled in them "
               f"(original wording, prefixed with its original date) — worklist: `{label_of(wl_path)}` — and then remove this placeholder line and the marker above. "
               f"The owner applies the proposal only after that.\n\n")
    parts = [pre]
    first_old = old_idx[0]
    for m, s in zip(meta, secs):
        if m["cls"] == "keep":
            parts.append(s)
        elif m["idx"] == first_old:
            parts.append(cf_head + cf_body)
    proposal = "".join(parts)
    # worklist
    old_secs = [(secs[m["idx"]], m["start"]) for m in meta if m["cls"] == "old"]
    worklist = extract_items(old_secs)
    manifest = {
        "tool": "tools/vault_health/rollover.py", "version": 1, "kind": "sections", "created": datetime.now().replace(microsecond=0).isoformat(),
        "source": src_label, "source_sha256": src_sha, "source_bytes": len(raw), "cutoff": cutoff, "level": level,
        "order": [m["cls"] for m in meta], "n_old": len(old_idx), "n_keep": len(meta) - len(old_idx),
        "archive": arch_rel, "proposal": label_of(prop_path), "worklist": label_of(wl_path),
        "carry_forward_header_prefix": f"{mark} {CF_WORD}",
    }
    safe_write(arch_path, archive.encode("utf-8"))
    safe_write(prop_path, proposal.encode("utf-8"))
    safe_write(wl_path, (json.dumps(worklist, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    safe_write(man_path, (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    res = verify_manifest(man_path)
    res.update({"archive_kb": sc.kb(len(archive.encode())), "proposal_kb": sc.kb(len(proposal.encode())), "source_kb": sc.kb(len(raw)),
                "worklist_items": len(worklist), "manifest": label_of(man_path)})
    return res


def stage_json(p: Path, cutoff: str, force_new: bool, today: date) -> dict:
    name = name_of(p)
    raw = p.read_bytes()
    obj = json.loads(raw.decode("utf-8"))
    ents, shape = entries_of(obj)
    order = ["old" if (entry_date(e) or "9999") < cutoff else "keep" for e in ents]
    old = [e for e, o in zip(ents, order) if o == "old"]
    keep = [e for e, o in zip(ents, order) if o == "keep"]
    period = period_label([entry_date(e) for e in old if entry_date(e)])
    arch_path = unique(ARCH / f"{name}_{period}.json")
    prop_path = PROP / f"{name}.proposed.json"
    man_path = PROP / f"{name}.rollover.json"
    if force_new:
        prop_path, man_path = unique(prop_path), unique(man_path)
    src_label = label_of(p)
    note = (f"Archive of {src_label}: entries whose `when` is before {cutoff} (cutoff = first day of the previous month), archived {today.isoformat()} by "
            f"tools/vault_health/rollover.py; original order kept; same shape as the live file. Source sha256 {sha(raw)}. Copy only: the live file is unchanged pending the owner's review.")
    if shape == "dict":
        arch_obj = {"_note": note, "entries": old}
        prop_obj = {k: v for k, v in obj.items() if k != "entries"}
        if isinstance(prop_obj.get("_note"), str):
            prop_obj["_note"] += f" Entries dated before {cutoff} were moved to {label_of(arch_path)}."
        prop_obj["entries"] = keep
    else:
        arch_obj, prop_obj = old, keep
    manifest = {
        "tool": "tools/vault_health/rollover.py", "version": 1, "kind": "changelog", "shape": shape,
        "created": datetime.now().replace(microsecond=0).isoformat(), "source": src_label, "source_sha256": sha(raw),
        "source_bytes": len(raw), "entries_sha256": sha(canon(ents)), "cutoff": cutoff, "order": order,
        "n_old": len(old), "n_keep": len(keep), "archive": label_of(arch_path), "proposal": label_of(prop_path),
    }
    safe_write(arch_path, (json.dumps(arch_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    safe_write(prop_path, (json.dumps(prop_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    safe_write(man_path, (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    res = verify_manifest(man_path)
    res.update({"archive_kb": sc.kb(arch_path.stat().st_size), "proposal_kb": sc.kb(prop_path.stat().st_size), "source_kb": sc.kb(len(raw)),
                "manifest": label_of(man_path)})
    return res


# ----------------------------------------------------------------------------- verify
def verify_manifest(man_path: Path) -> dict:
    m = json.loads(man_path.read_text(encoding="utf-8"))
    src = resolve(m["source"])
    arch = resolve(m["archive"])
    prop = resolve(m["proposal"])
    out = {"source": m["source"], "archive": m["archive"], "proposal": m["proposal"], "n_old": m["n_old"], "n_keep": m["n_keep"]}
    try:
        live = src.read_bytes()
    except OSError as e:
        out.update({"ok": False, "error": f"source unreadable: {e}"})
        return out
    out["live_unchanged_since_snapshot"] = (sha(live) == m["source_sha256"]) if m["kind"] == "sections" else (sha(canon(entries_of(json.loads(live))[0])) == m["entries_sha256"])
    if m["kind"] == "sections":
        a_txt = arch.read_bytes().decode("utf-8")
        p_txt = prop.read_bytes().decode("utf-8")
        if ARCHIVE_MARK + "\n\n" not in a_txt:
            out.update({"ok": False, "error": "archive header marker missing"})
            return out
        a_body = a_txt.split(ARCHIVE_MARK + "\n\n", 1)[1]
        level = m["level"]
        _, a_secs = split_sections(a_body, level)
        p_pre, p_secs = split_sections(p_txt, level)
        pref = m["carry_forward_header_prefix"]
        cf = [k for k, s in enumerate(p_secs) if header_of(s).startswith(pref)]
        if len(cf) != 1:
            out.update({"ok": False, "error": f"expected exactly one carry-forward section in the proposal, found {len(cf)}"})
            return out
        kept = [s for k, s in enumerate(p_secs) if k != cf[0]]
        rebuilt = [p_pre]
        ia = ik = 0
        for o in m["order"]:
            if o == "old":
                if ia >= len(a_secs):
                    out.update({"ok": False, "error": "archive has fewer sections than recorded"})
                    return out
                rebuilt.append(a_secs[ia]); ia += 1
            else:
                if ik >= len(kept):
                    out.update({"ok": False, "error": "proposal has fewer kept sections than recorded"})
                    return out
                rebuilt.append(kept[ik]); ik += 1
        if ia != len(a_secs) or ik != len(kept):
            out.update({"ok": False, "error": "section counts differ from the manifest"})
            return out
        got = sha("".join(rebuilt).encode("utf-8"))
        out.update({"ok": got == m["source_sha256"], "sha256_source": m["source_sha256"], "sha256_rebuilt": got})
        out["placeholder_still_present"] = "ROLLOVER-CARRY-FORWARD-PLACEHOLDER" in p_txt
    else:
        a_obj = json.loads(arch.read_text(encoding="utf-8"))
        p_obj = json.loads(prop.read_text(encoding="utf-8"))
        a_ents, _ = entries_of(a_obj)
        p_ents, _ = entries_of(p_obj)
        rebuilt = []
        ia = ik = 0
        for o in m["order"]:
            if o == "old":
                rebuilt.append(a_ents[ia]); ia += 1
            else:
                rebuilt.append(p_ents[ik]); ik += 1
        ok = ia == len(a_ents) and ik == len(p_ents) and sha(canon(rebuilt)) == m["entries_sha256"]
        out.update({"ok": ok, "sha256_source_entries": m["entries_sha256"], "sha256_rebuilt_entries": sha(canon(rebuilt))})
    return out


def find_manifest(arg: str) -> Path | None:
    p = resolve(arg)
    if ".rollover" in p.name and p.suffix == ".json" and p.is_file():
        return p  # a manifest given directly (e.g. 00_Brain/ARCHIVE/_proposed/X.rollover_v2.json)
    name = name_of(p)
    cands = sorted(PROP.glob(f"{name}.rollover*.json")) if PROP.is_dir() else []
    return cands[-1] if cands else None


# ----------------------------------------------------------------------------- cli
def main() -> None:
    ap = argparse.ArgumentParser(description="Archive-rollover proposal (never writes the live file)")
    ap.add_argument("cmd", choices=["plan", "stage", "verify"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--over", action="store_true", help="plan: only registers that are OVER budget")
    ap.add_argument("--all-over", action="store_true", help="stage: every OVER register marked sections/changelog in budgets.json")
    ap.add_argument("--cutoff", help="YYYY-MM-DD; default = first day of the previous month")
    ap.add_argument("--today", help="YYYY-MM-DD; default = today (testing)")
    ap.add_argument("--level", type=int, choices=[1, 2], help="heading level of the dated sections (default: auto)")
    ap.add_argument("--force-new", action="store_true", help="stage another proposal even if one is pending (suffix _v2)")
    ap.add_argument("--budgets", default=str(HERE / "budgets.json"))
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    cutoff = args.cutoff or default_cutoff(today).isoformat()
    budgets = sc.load_budgets(Path(args.budgets))
    results: list[dict] = []

    if args.cmd == "verify":
        if not args.files:
            sys.exit("verify needs FILE")
        for f in args.files:
            man = find_manifest(f)
            if not man:
                results.append({"file": f, "ok": False, "error": "no manifest in 00_Brain/ARCHIVE/_proposed"})
            else:
                results.append(verify_manifest(man))
    else:
        targets = list(args.files)
        if args.over or args.all_over:
            regs = sc.check_registers(ROOT, budgets)
            for r in regs:
                if r["status"] != "OVER":
                    continue
                if args.all_over and r["rollover"] not in ("sections", "changelog"):
                    continue
                targets.append(r["path"])
        seen = set()
        targets = [t for t in targets if not (t in seen or seen.add(t))]
        if not targets:
            print(json.dumps({"cmd": args.cmd, "cutoff": cutoff, "results": [], "note": "no target (no OVER register of a supported kind)"}, ensure_ascii=False, indent=2))
            return
        for t in targets:
            pl = plan_one(t, cutoff, args.level, budgets, args.force_new)
            if args.cmd == "plan":
                results.append(pl)
                continue
            if not pl.get("can_stage"):
                results.append({**pl, "staged": False})
                continue
            p = resolve(t)
            try:
                if p.suffix.lower() == ".json":
                    r = stage_json(p, cutoff, args.force_new, today)
                else:
                    r = stage_md(p, cutoff, args.level or pl.get("level"), args.force_new, today)
                results.append({"file": pl["file"], "staged": True, **r})
            except Exception as e:  # noqa: BLE001
                results.append({**pl, "staged": False, "error": f"{type(e).__name__}: {e}"})

    print(json.dumps({"cmd": args.cmd, "cutoff": cutoff, "live_files_written": 0, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
