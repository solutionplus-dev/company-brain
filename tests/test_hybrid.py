#!/usr/bin/env python3
"""Hybrid search on a copy of the made-up company: exact codes, passages deep in a long file, the file named
for a topic, an honest "not found". Standard library only.  python3 tests/test_hybrid.py"""
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
sys.path.insert(0, str(REPO / "tools" / "index"))
sys.dont_write_bytecode = True
import hybrid  # noqa: E402

LONG = "# Supplier register\n\n" + "".join(f"Filler line number {i} about nothing in particular.\n" for i in range(700)) \
       + "\nThe contract reference is ZX-4471 and nothing else.\n"


def run(args, root):
    env = dict(os.environ, BRAIN_ROOT=str(root))
    res = subprocess.run([sys.executable] + [str(a) for a in args], cwd=str(REPO), env=env,
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise AssertionError(f"{args} failed:\n{res.stdout}\n{res.stderr}")
    return res


class HybridSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="brain-hybrid-"))
        cls.root = cls.tmp / "brain"
        shutil.copytree(EXAMPLE, cls.root, ignore=shutil.ignore_patterns(".index"))
        (cls.root / "05_Operations").mkdir(exist_ok=True)
        (cls.root / "05_Operations" / "SUPPLIERS.md").write_text(LONG, encoding="utf-8")
        run([REPO / "tools/index/refresh.py", "--full", "--no-embed"], cls.root)
        cls.vectors = cls.root / ".index" / "vectors.db"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ask(self, *words):
        out = run([REPO / "scripts/brain", "ask", "--json", "--explain", "--no-embed", "--limit", "5", *words], self.root)
        return json.loads(out.stdout)

    def add_passages(self):
        """A passage store as the embedder leaves it: the whole text, cut into pieces."""
        v = sqlite3.connect(str(self.vectors))
        v.executescript("CREATE TABLE IF NOT EXISTS chunks (sha256 TEXT NOT NULL, ord INTEGER NOT NULL, "
                        "text TEXT NOT NULL, n_chars INTEGER NOT NULL, PRIMARY KEY (sha256, ord));"
                        "CREATE TABLE IF NOT EXISTS file_map (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL);"
                        "DELETE FROM chunks; DELETE FROM file_map;")
        v.execute("INSERT INTO file_map VALUES (?,?)", ("05_Operations/SUPPLIERS.md", "sha-suppliers"))
        for o, start in enumerate(range(0, len(LONG), 1200)):
            piece = LONG[start:start + 1200]
            v.execute("INSERT INTO chunks VALUES (?,?,?,?)", ("sha-suppliers", o, piece, len(piece)))
        v.commit()
        v.close()
        return hybrid.ensure_passages(self.vectors)

    def test_1_question_words_are_read_as_a_question(self):
        an = hybrid.analyse("which deadlines are in the next weeks")
        self.assertEqual([t["text"] for t in an["terms"]], ["deadlines", "next", "weeks"])
        self.assertEqual((an["kind"], an["alpha"]), ("question", 0.5))
        self.assertEqual(hybrid.analyse("where is ZX-4471 mentioned")["kind"], "exact")
        self.assertEqual(hybrid.analyse("Deadlines")["alpha"], 0.4)

    def test_2_a_code_is_matched_exactly_and_explained(self):
        res = self.ask("where", "is", "DEC-2030-003", "decided")
        self.assertEqual(res["kind"], "exact")
        self.assertEqual(res["verdict"], "found")
        top = res["results"][0]
        self.assertEqual(top["confidence"], "strong")
        self.assertIn("keywords #", top["why"])
        self.assertIn("DEC-2030-003", top["snippet"].replace("[", "").replace("]", ""))

    def test_3_the_file_named_for_the_topic_comes_first(self):
        res = self.ask("which", "deadlines", "are", "coming", "up")
        self.assertEqual(res["results"][0]["path"], "00_Brain/DEADLINES.md")
        self.assertIn("file name", res["results"][0]["why"])

    def test_4_words_the_brain_does_not_hold_are_reported_as_not_found(self):
        res = self.ask("qqqzzz", "wwwyyy")
        self.assertEqual(res["results"], [])
        self.assertEqual(res["verdict"], "nothing found")

    def test_5_a_code_deep_in_a_long_file_needs_the_passages(self):
        before = self.ask("ZX-4471")
        self.assertNotIn("05_Operations/SUPPLIERS.md", [r["path"] for r in before["results"]])
        built = self.add_passages()
        self.assertTrue(built["rebuilt"])
        self.assertFalse(hybrid.ensure_passages(self.vectors)["rebuilt"])
        after = self.ask("where", "is", "ZX-4471", "mentioned")
        self.assertEqual(after["results"][0]["path"], "05_Operations/SUPPLIERS.md")
        self.assertIn("passage #1", after["results"][0]["why"])
        self.assertEqual(after["results"][0]["confidence"], "strong")


    def test_6_agents_get_the_passage_and_its_lines(self):
        self.add_passages()
        out = run([REPO / "scripts/brain", "find", "--json", "--no-embed", "--top", "2", "--budget", "800",
                   "where", "is", "ZX-4471", "mentioned"], self.root)
        res = json.loads(out.stdout)
        block = res["results"][0]
        self.assertEqual(block["path"], "05_Operations/SUPPLIERS.md")
        passage = block["passages"][0]
        self.assertIn("ZX-4471", passage["text"])
        first, last = passage["lines"]
        self.assertTrue(any("ZX-4471" in ln for ln in LONG.splitlines()[first - 1:last]))
        text = run([REPO / "scripts/brain", "find", "--no-embed", "where", "is", "DEC-2030-003", "decided"], self.root).stdout
        self.assertTrue(text.startswith("find: found"))
        self.assertIn("records:", text)
        self.assertIn("next: answer from these lines", text)


    def test_7_names_that_explain_nothing_are_listed_not_renamed(self):
        (self.root / "05_Operations" / "scan0001.md").write_text("# Scan\n\nSomething.\n", encoding="utf-8")
        run([REPO / "tools/index/refresh.py", "--no-embed"], self.root)
        out = run([REPO / "tools/vault_health/name_check.py", "--print"], self.root).stdout
        self.assertIn("05_Operations/scan0001.md", out)
        self.assertNotIn("DEADLINES.md", out)                       # a register's fixed name explains itself
        self.assertTrue((self.root / "05_Operations" / "scan0001.md").exists())


if __name__ == "__main__":
    unittest.main()
