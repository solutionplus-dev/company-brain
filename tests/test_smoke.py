#!/usr/bin/env python3
"""Smoke test: build the index on a copy of the made-up company and check what matters.
Standard library only.  python3 tests/test_smoke.py"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "harbour-pine"


def run(args, root, check=True):
    env = dict(os.environ, BRAIN_ROOT=str(root))
    res = subprocess.run([sys.executable] + [str(a) for a in args], cwd=str(REPO), env=env,
                         capture_output=True, text=True)
    if check and res.returncode != 0:
        raise AssertionError(f"{args} failed:\n{res.stdout}\n{res.stderr}")
    return res


class ExampleBrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="brain-smoke-"))
        cls.root = cls.tmp / "brain"
        shutil.copytree(EXAMPLE, cls.root, ignore=shutil.ignore_patterns(".index"))
        cls.refresh = run([REPO / "tools/index/refresh.py", "--full"], cls.root)
        cls.db = sqlite3.connect(str(cls.root / ".index" / "vault_index.db"))

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def kinds(self):
        return dict(self.db.execute("select kind, count(*) from records group by kind"))

    def test_catalogue_has_the_files(self):
        n = self.db.execute("select count(*) from files").fetchone()[0]
        self.assertGreaterEqual(n, 20)
        areas = {r[0] for r in self.db.execute("select distinct area from files")}
        self.assertTrue({"brain", "clients", "meetings", "finance", "finance-de", "finance-uk"} <= areas, areas)

    def test_records_of_every_kind(self):
        kinds = self.kinds()
        for kind in ("deadline", "todo", "decision", "meeting", "client", "person", "recommendation", "ledger_line"):
            self.assertGreater(kinds.get(kind, 0), 0, f"no {kind} records: {kinds}")

    def test_legal_entities_are_never_mixed_in_the_ledger(self):
        rows = self.db.execute("select company, currency, count(*) from records where kind='ledger_line' "
                               "group by company, currency").fetchall()
        self.assertEqual({(c, cur) for c, cur, _ in rows}, {("DE", "EUR"), ("UK", "GBP")})

    def test_a_client_name_that_contains_an_entity_code_is_not_our_entity(self):
        row = self.db.execute("select company from records where kind='client' and ref='brindlemoor-robotics'").fetchone()
        self.assertEqual(row[0], "UK")  # from billing_entity, which is stated
        row = self.db.execute("select company, extra from records where kind='decision' and ref='DEC-2030-003'").fetchone()
        self.assertEqual(row[0], "none")  # free text never sets the entity
        self.assertNotIn("UK", json.loads(row[1] or "{}").get("mentions", []))

    def test_an_unparsed_date_stays_text(self):
        row = self.db.execute("select due_date, extra from records where kind='deadline' and title like 'Office lease%'").fetchone()
        self.assertIsNone(row[0])
        self.assertIn("end of April", row[1])

    def test_no_private_contact_details_in_person_records(self):
        for (extra,) in self.db.execute("select coalesce(extra,'') from records where kind='person'"):
            self.assertNotIn("@", extra)

    def test_search_finds_english_and_german(self):
        out = run([REPO / "scripts/brain", "ask", "ordering app"], self.root).stdout
        self.assertIn("northlight-bookshop", out)
        out = run([REPO / "scripts/brain", "ask", "Festpreisvertrag"], self.root).stdout
        self.assertIn("contract.pdf.digest.md", out)

    def test_records_query_filters_by_entity(self):
        out = run([REPO / "scripts/brain", "records", "kind=ledger_line", "company=UK"], self.root).stdout
        self.assertIn("UK-2030-001", out)
        self.assertNotIn("DE-2030", out)

    def test_importer_check_and_journal_balance(self):
        out = run([REPO / "tools/index/importers/run_all.py", "--db", self.root / ".index/vault_index.db",
                   "--check"], self.root).stdout
        self.assertIn("entry not balanced: 0", out)

    def test_standing_questions_are_answered(self):
        out = run([REPO / "scripts/brain", "check"], self.root).stdout
        self.assertIn("5 of 5 standing questions", out)

    def test_size_check_runs(self):
        run([REPO / "tools/vault_health/size_check.py", "--md", "--no-state"], self.root)

    def test_refresh_is_incremental_and_stable(self):
        before = self.db.execute("select count(*) from files").fetchone()[0]
        run([REPO / "tools/index/refresh.py"], self.root)
        after = sqlite3.connect(str(self.root / ".index" / "vault_index.db")).execute("select count(*) from files").fetchone()[0]
        self.assertEqual(before, after)


class EmptyTemplate(unittest.TestCase):
    """The template as cloned, before init: it must index without a single legal entity."""

    def test_init_then_index(self):
        tmp = Path(tempfile.mkdtemp(prefix="brain-init-"))
        try:
            root = tmp / "brain"
            ignore = shutil.ignore_patterns(".git", ".index", "examples", "tools", "scripts", "tests", "docs", "__pycache__")
            shutil.copytree(REPO, root, ignore=ignore)
            run([REPO / "tools/index/refresh.py", "--full", "--no-embed"], root)
            run([REPO / "scripts/init.py", "--company", "Example Studio", "--timezone", "UTC",
                 "--entity", "DE:Example Studio GmbH:EUR"], root)
            self.assertTrue((root / "Entity_DE" / "SUMMARY.md").is_file())
            self.assertTrue((root / "finance" / "ledger" / "DE" / "journal_template.csv").is_file())
            self.assertIn("| `DE` | Example Studio GmbH |", (root / "AGENTS.md").read_text(encoding="utf-8"))
            run([REPO / "tools/index/refresh.py", "--full", "--no-embed"], root)
            db = sqlite3.connect(str(root / ".index" / "vault_index.db"))
            areas = {r[0] for r in db.execute("select distinct area from files")}
            self.assertIn("finance-de", areas)
            # running init again adds nothing and breaks nothing
            run([REPO / "scripts/init.py", "--entity", "DE:Example Studio GmbH:EUR"], root)
            cfg = json.loads((root / "brain.config.json").read_text(encoding="utf-8"))
            self.assertEqual([e["code"] for e in cfg["entities"]], ["DE"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Audit(unittest.TestCase):
    def test_audit_catches_a_planted_address_and_term(self):
        tmp = Path(tempfile.mkdtemp(prefix="brain-audit-"))
        try:
            (tmp / "note.md").write_text("Write to jane.roe@privatemail.net about Blue Heron Ltd.\n", encoding="utf-8")
            (tmp / "ok.md").write_text("Write to hello@example.com.\n", encoding="utf-8")
            terms = tmp.parent / (tmp.name + "-terms.txt")
            terms.write_text("Blue Heron\n", encoding="utf-8")
            res = run([REPO / "scripts/audit_public.py", "--root", tmp, "--terms", terms], REPO, check=False)
            terms.unlink()
            self.assertEqual(res.returncode, 1)
            self.assertIn("e-mail address", res.stdout)
            self.assertIn("private term", res.stdout)
            self.assertNotIn("ok.md", res.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_audit_sees_through_spelling_and_narrow_exceptions(self):
        tmp = Path(tempfile.mkdtemp(prefix="brain-audit-"))
        try:
            (tmp / "a.md").write_text("Invoice for BLUE-HÉRON, due Friday.\n", encoding="utf-8")
            (tmp / "b.svg").write_text("<text>Blue\nHeron</text>\n", encoding="utf-8")
            (tmp / "c.md").write_text("Licensed to Blue Heron. Call Grey Wren.\n", encoding="utf-8")
            (tmp / ".audit-allow").write_text("c.md:Blue Heron\n", encoding="utf-8")
            terms = tmp.parent / (tmp.name + "-terms.txt")
            terms.write_text("Blue Heron\nGrey Wren\n", encoding="utf-8")
            res = run([REPO / "scripts/audit_public.py", "--root", tmp, "--terms", terms], REPO, check=False)
            terms.unlink()
            self.assertEqual(res.returncode, 1)
            self.assertIn("a.md:1", res.stdout)                      # hyphen, capitals and accent
            self.assertIn("b.svg:0  private term across lines", res.stdout)   # any text file, name split over lines
            self.assertIn("c.md:1  private term  Grey Wren", res.stdout)      # the exception covers its own text only
            self.assertNotIn("c.md:1  private term  Blue Heron", res.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class IgnoreFile(unittest.TestCase):
    def test_an_ignored_folder_is_not_catalogued(self):
        sys.path.insert(0, str(REPO / "tools" / "index"))
        import brainconfig
        tmp = Path(tempfile.mkdtemp(prefix="brain-ignore-"))
        try:
            (tmp / ".brainignore").write_text("# comment\nsealed/\n*.key\n01_Clients/acme/raw/\n", encoding="utf-8")
            brainconfig._IGNORE_CACHE.clear()
            self.assertTrue(brainconfig.ignored("01_Clients/acme/Sealed/report.md", tmp))
            self.assertTrue(brainconfig.ignored("05_Operations/server.key", tmp))
            self.assertTrue(brainconfig.ignored("01_Clients/acme/raw/dump.csv", tmp))
            self.assertFalse(brainconfig.ignored("01_Clients/acme/STATUS.md", tmp))
            self.assertFalse(brainconfig.ignored("01_Clients/other/raw/notes.md", tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
