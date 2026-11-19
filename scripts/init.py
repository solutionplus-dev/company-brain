#!/usr/bin/env python3
"""Set the brain up for your company. Standard library only. Never overwrites a file that exists.

  python3 scripts/init.py                                   asks the questions
  python3 scripts/init.py --company "Example Studio" --timezone UTC \
          --entity "DE:Example Studio GmbH:EUR" --entity "UK:Example Studio Ltd:GBP"

It writes brain.config.json, creates Entity_<CODE>/ and finance/ledger/<CODE>/ for each legal entity,
and fills the entity table in AGENTS.md. Run it again to add an entity. The brain's root is this
repository, or the folder named by the BRAIN_ROOT environment variable.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("BRAIN_ROOT") or Path(__file__).resolve().parents[1]).resolve()
CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
JOURNAL_HEADER = "jnl,date,account,account_name,description,debit,credit,currency,counterparty,source,certainty\n"


def ask(question, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or default


def parse_entity(text):
    parts = [p.strip() for p in text.split(":")]
    if len(parts) != 3:
        sys.exit(f'entity must be "CODE:Legal name:CUR", got {text!r}')
    code, name, currency = parts
    if not CODE.match(code):
        sys.exit(f"entity code {code!r}: 1 to 16 letters, digits, _ or -, starting with a letter")
    if not CURRENCY.match(currency):
        sys.exit(f"currency {currency!r}: three capital letters, such as EUR")
    return {"code": code, "name": name, "folder": f"Entity_{code}", "currency": currency}


def write_new(path, text):
    """Create a file only if it is not there. Returns True when written."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--company")
    ap.add_argument("--timezone")
    ap.add_argument("--entity", action="append", default=[], help='"CODE:Legal name:CUR"; repeat per legal entity')
    args = ap.parse_args()

    config_path = ROOT / "brain.config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    config.setdefault("entities", [])
    config.setdefault("not_our_entity", [])
    config.setdefault("owner_role", "the owner")

    interactive = not (args.company or args.entity)
    if interactive:
        print(f"Setting up the brain in {ROOT}\n")
        config["company"] = ask("1. What is the company called (the everyday name)", config.get("company", ""))
        config["timezone"] = ask("2. Time zone for the routines", config.get("timezone") or "UTC")
        print("3. Legal entities. One per company you invoice from. Empty code to finish.")
        new = []
        while True:
            code = ask("   Short code (for example DE)")
            if not code:
                break
            name = ask("   Full legal name")
            currency = ask("   Main currency", "EUR").upper()
            new.append(parse_entity(f"{code}:{name}:{currency}"))
    else:
        if args.company:
            config["company"] = args.company
        if args.timezone:
            config["timezone"] = args.timezone
        new = [parse_entity(e) for e in args.entity]

    known = {e["code"] for e in config["entities"]}
    added = [e for e in new if e["code"] not in known]
    config["entities"].extend(added)
    config.pop("_help", None)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    created = []
    for ent in config["entities"]:
        code, folder = ent["code"], ROOT / ent["folder"]
        summary = (f"# {ent['name']} ({code}) — summary\n\n"
                   f"**Purpose.** Legal and finance records of this legal entity. Books in `finance/ledger/{code}/`. "
                   f"Never mixed with another entity; {ent['currency']} stays {ent['currency']}.\n\n"
                   "**Contents.** `Formation/` · `Contracts/` · `Correspondence/` · `Invoices/` · "
                   "`Expenses/<yyyy>/<yyyy-mm>/` · `Taxes/` · `Banking/` · `Insurance/`\n\n"
                   "**Latest update.**\n\n**Gaps and open items.**\n\nLast verified:\n")
        if write_new(folder / "SUMMARY.md", summary):
            created.append(f"{ent['folder']}/SUMMARY.md")
        for sub in ("Formation", "Contracts", "Correspondence", "Invoices", "Expenses", "Taxes", "Banking", "Insurance"):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        if write_new(ROOT / "finance" / "ledger" / code / "journal_template.csv", JOURNAL_HEADER):
            created.append(f"finance/ledger/{code}/journal_template.csv")

    agents = ROOT / "AGENTS.md"
    if agents.exists() and config["entities"]:
        text = agents.read_text(encoding="utf-8")
        rows = ["| Code | Legal entity | Folder | Books |", "|---|---|---|---|"]
        rows += [f"| `{e['code']}` | {e['name']} | `{e['folder']}/` | `finance/ledger/{e['code']}/` ({e['currency']}) |"
                 for e in config["entities"]]
        table = "<!-- entities:start -->\n" + "\n".join(rows) + "\n<!-- entities:end -->"
        text2, n = re.subn(r"<!-- entities:start -->.*?<!-- entities:end -->", lambda m: table, text, flags=re.S)
        if n:
            agents.write_text(text2, encoding="utf-8")

    print(f"\nbrain.config.json written: {config.get('company') or '(no name)'}, "
          f"{len(config['entities'])} legal entit{'y' if len(config['entities']) == 1 else 'ies'} "
          f"({len(added)} added).")
    for item in created:
        print("  created", item)
    print("\nNext: fill in 00_Brain/SOURCES.md, then run  python3 tools/index/refresh.py --full")
    return 0


if __name__ == "__main__":
    sys.exit(main())
