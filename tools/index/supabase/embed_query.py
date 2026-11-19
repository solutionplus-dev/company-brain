#!/usr/bin/env python3
"""Embed one search question for brain_search. Run inside tools/index/.venv (supabase_sync.py does).

Reads the question on stdin, prints one line:  EMBED_QUERY_JSON:{"bin": "<768 chars 0/1>", "full": [768 floats]}
Uses tools/index/embed/embed.py (same model, query prefix and sign-bit order as the stored vectors:
character i of bin is dimension i, 1 when the value is > 0).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "embed"))
import embed  # noqa: E402

question = sys.stdin.read().strip()
if not question:
    sys.exit(1)
vec = embed.embed_query(question)
vals = [float(x) for x in vec]
print("EMBED_QUERY_JSON:" + json.dumps({"bin": "".join("1" if x > 0 else "0" for x in vals),
                                         "full": [round(x, 6) for x in vals]}))
