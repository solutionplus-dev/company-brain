#!/usr/bin/env python3
"""Quality check for the vault embedding lane.

1. Bit search + re-score (what search() does) against exact search over the full vectors,
   for the 20 questions in eval_queries.json: overlap of the top 10 documents, and how many
   of the exact top 10 chunks survive the 300-candidate Hamming shortlist.
2. Language: share of top-10 documents in the other language (EN query -> DE docs, DE -> EN).
   Cross-lingual pair overlap: top 10 of an English question against its German translation.
3. Storage format: on a random sample of chunks re-embedded in fp32, cosine of the stored
   'full' vector, of float16 and of int8 (with scale) round trips, and sign-bit agreement;
   then the top-10 overlap of fp32 vs int8 vs float16 on the sample, for the 20 questions.

Writes .index/embed_eval.json and prints a summary. Run with the venv python:
  tools/index/.venv/bin/python tools/index/embed/evaluate.py
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import embed as E  # noqa: E402

if not E._heavy_ready():
    if not E.VENV_PY.exists():
        sys.exit("venv missing: run tools/index/embed/setup.sh")
    os.environ[E.CHILD_ENV] = "1"
    os.execv(str(E.VENV_PY), [str(E.VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:])

import numpy as np  # noqa: E402

OUT = E.INDEX_DIR / "embed_eval.json"
K = 10
SHORTLIST = 300
SAMPLE = int(os.environ.get("EVAL_SAMPLE", "500"))
EN_SW = {"the", "and", "of", "to", "is", "are", "with", "for", "this", "that", "from", "invoice", "bank"}
DE_SW = {"der", "die", "das", "und", "ist", "mit", "für", "von", "zu", "den", "nicht", "auf", "dem",
         "ein", "eine", "rechnung", "bank"}


def lang_of(text: str) -> str:
    words = re.findall(r"[a-zäöüß]+", text.lower())
    en = sum(1 for w in words if w in EN_SW)
    de = sum(1 for w in words if w in DE_SW)
    if en == de:
        return "unclear"
    return "de" if de > en else "en"


def main() -> None:
    queries = json.loads((HERE / "eval_queries.json").read_text(encoding="utf-8"))["pairs"]
    vdb = E._open_vectors()
    rows = vdb.execute("SELECT sha256, ord, bin, full FROM vectors ORDER BY sha256, ord").fetchall()
    n = len(rows)
    if n == 0:
        sys.exit("no vectors yet: run embed.py pending first")
    keys = [r[0] for r in rows]
    ords = [r[1] for r in rows]
    bmat = np.frombuffer(b"".join(r[2] for r in rows), dtype=np.uint8).reshape(n, E.BIN_BYTES)
    t0 = time.time()
    fmat = np.stack([E.unpack_full(r[3]) for r in rows])
    load_s = time.time() - t0
    fmap: dict[str, list[str]] = {}
    for path, sha in vdb.execute("SELECT path, sha256 FROM file_map"):
        fmap.setdefault(sha, []).append(path)
    pop = E._popcount_table()

    def chunk_text(i: int) -> str:
        r = vdb.execute("SELECT text FROM chunks WHERE sha256=? AND ord=?", (keys[i], ords[i])).fetchone()
        return r[0] if r else ""

    def docs_from(order: np.ndarray, k: int = K) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for i in order:
            for p in sorted(fmap.get(keys[i], [])):
                if p not in seen:
                    seen.add(p)
                    out.append(p)
                    if len(out) >= k:
                        return out
        return out

    def run_query(text: str, mat: np.ndarray = fmat):
        t = time.time()
        qv = E.embed_query(text)
        t_embed = time.time() - t
        t = time.time()
        full = mat @ qv
        exact_order = np.argsort(-full)
        t_exact = time.time() - t
        qbits = np.packbits(qv > 0)
        t = time.time()
        ham = pop[bmat ^ qbits].sum(axis=1)
        pool = np.argpartition(ham, SHORTLIST - 1)[:SHORTLIST]
        fast_order = pool[np.argsort(-full[pool])]
        t_fast = time.time() - t
        exact_top_chunks = set(exact_order[:K].tolist())
        recall_pool = len(exact_top_chunks & set(pool.tolist())) / K
        return {
            "qv": qv,
            "exact_docs": docs_from(exact_order),
            "fast_docs": docs_from(fast_order),
            "fast_top_chunks": fast_order[:K].tolist(),
            "exact_top_chunks": exact_order[:K].tolist(),
            "shortlist_recall_top10_chunks": recall_pool,
            "ms_embed_query": round(t_embed * 1000, 1),
            "ms_exact_scan": round(t_exact * 1000, 2),
            "ms_bit_plus_rescore": round(t_fast * 1000, 2),
            "exact_order": exact_order,
            "fast_order": fast_order,
        }

    per_pair = []
    overlaps = []
    shortlist_recalls = []
    cross_pair = []
    lang_rows = []
    for pi, pair in enumerate(queries, 1):
        res_en = run_query(pair["en"])
        res_de = run_query(pair["de"])
        for lang, res, text in (("en", res_en, pair["en"]), ("de", res_de, pair["de"])):
            ov = len(set(res["fast_docs"]) & set(res["exact_docs"])) / K
            overlaps.append(ov)
            shortlist_recalls.append(res["shortlist_recall_top10_chunks"])
            # language of the documents returned (from the bit+rescore top 10)
            langs = [lang_of(chunk_text(i)) for i in res["fast_top_chunks"]]
            other = "de" if lang == "en" else "en"
            lang_rows.append({"pair": pi, "query_lang": lang,
                              "top10_other_language": sum(1 for x in langs if x == other),
                              "top10_same_language": sum(1 for x in langs if x == lang),
                              "top10_unclear": sum(1 for x in langs if x == "unclear")})
        cx = len(set(res_en["exact_docs"]) & set(res_de["exact_docs"])) / K
        cross_pair.append(cx)
        per_pair.append({"pair": pi, "theme": pair["theme"], "en": pair["en"], "de": pair["de"],
                         "overlap_en": overlaps[-2], "overlap_de": overlaps[-1],
                         "en_de_top10_overlap": cx,
                         "en_top3_exact": res_en["exact_docs"][:3],
                         "de_top3_exact": res_de["exact_docs"][:3]})
        print(f"pair {pi:2d} {pair['theme']:<26} overlap en={overlaps[-2]:.1f} de={overlaps[-1]:.1f} "
              f"en-de={cx:.1f}", flush=True)

    # -- storage format on a sample ------------------------------------------------
    rng = random.Random(7)
    sample_idx = rng.sample(range(n), min(SAMPLE, n))
    sample_texts = [chunk_text(i) for i in sample_idx]
    t = time.time()
    fp32 = E.embed_documents(sample_texts)  # unit fp32 vectors from the model
    embed_s = time.time() - t
    stored = np.stack([E.unpack_full(rows[i][3]) for i in sample_idx])
    stored_bits = np.stack([np.unpackbits(np.frombuffer(rows[i][2], dtype=np.uint8)) for i in sample_idx])
    fp32_bits = np.unpackbits(np.packbits(fp32 > 0, axis=1), axis=1)
    bit_agree = float((stored_bits == fp32_bits).mean())
    f16 = fp32.astype(np.float16).astype(np.float32)
    scale = np.max(np.abs(fp32), axis=1, keepdims=True)
    q = np.clip(np.round(fp32 / scale * 127), -127, 127)
    i8 = q * (scale / 127.0)
    cos = lambda a, b: np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    fmt = {
        "stored_format": CFG_FORMAT(),
        "cos_stored_vs_fp32_min": float(cos(stored, fp32).min()),
        "cos_stored_vs_fp32_mean": float(cos(stored, fp32).mean()),
        "cos_float16_vs_fp32_min": float(cos(f16, fp32).min()),
        "cos_int8_scaled_vs_fp32_min": float(cos(i8, fp32).min()),
        "cos_int8_scaled_vs_fp32_mean": float(cos(i8, fp32).mean()),
        "sign_bit_agreement_stored_vs_fp32": bit_agree,
        "sample_chunks": len(sample_idx),
        "sample_embed_seconds": round(embed_s, 1),
    }
    # top-10 over the sample mini-corpus, fp32 vs int8 vs float16, for the 20 questions
    mini = {"fp32": fp32, "int8": i8, "float16": f16}
    mini_sha = [keys[i] for i in sample_idx]
    mini_ord = [ords[i] for i in sample_idx]
    qvecs = []
    for pair in queries:
        qvecs.append(E.embed_query(pair["en"]))
        qvecs.append(E.embed_query(pair["de"]))
    fmt_overlap = {"int8": [], "float16": []}
    for qv in qvecs:
        top = {name: set(np.argsort(-(m @ qv))[:K].tolist()) for name, m in mini.items()}
        fmt_overlap["int8"].append(len(top["fp32"] & top["int8"]) / K)
        fmt_overlap["float16"].append(len(top["fp32"] & top["float16"]) / K)
    fmt["mini_corpus_top10_overlap_vs_fp32_int8"] = float(np.mean(fmt_overlap["int8"]))
    fmt["mini_corpus_top10_overlap_vs_fp32_float16"] = float(np.mean(fmt_overlap["float16"]))

    # -- language summary -----------------------------------------------------------
    def agg(lang):
        rows_l = [r for r in lang_rows if r["query_lang"] == lang]
        other = sum(r["top10_other_language"] for r in rows_l)
        same = sum(r["top10_same_language"] for r in rows_l)
        return {"queries": len(rows_l), "share_other_language_in_top10": round(other / (other + same), 3)
                if other + same else None}

    summary = {
        "chunks_in_db": n,
        "documents_mapped": len(fmap),
        "load_matrix_seconds": round(load_s, 2),
        "k": K,
        "shortlist": SHORTLIST,
        "questions": 2 * len(queries),
        "top10_overlap_bit_rescore_vs_exact_mean": round(float(np.mean(overlaps)), 4),
        "top10_overlap_min": round(float(np.min(overlaps)), 4),
        "top10_overlap_distribution": dict(sorted({str(round(x, 2)): overlaps.count(x) for x in set(overlaps)}.items())),
        "exact_top10_chunks_inside_300_shortlist_mean": round(float(np.mean(shortlist_recalls)), 4),
        "cross_lingual_pair_top10_overlap_mean": round(float(np.mean(cross_pair)), 4),
        "language_english_queries": agg("en"),
        "language_german_queries": agg("de"),
        "storage_format": fmt,
        "per_pair": per_pair,
        "timing_ms_mean": {
            "embed_query": round(float(np.mean([0.0])), 1),
        },
    }
    lat = {"embed_query_ms": [], "exact_scan_ms": [], "bit_plus_rescore_ms": []}
    for pair in queries[:5]:
        r = run_query(pair["en"])
        lat["embed_query_ms"].append(r["ms_embed_query"])
        lat["exact_scan_ms"].append(r["ms_exact_scan"])
        lat["bit_plus_rescore_ms"].append(r["ms_bit_plus_rescore"])
    summary["timing_ms_mean"] = {k: round(float(np.mean(v)), 2) for k, v in lat.items()}
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_pair"}, indent=2, ensure_ascii=False))
    print(f"written: {OUT}")


def CFG_FORMAT() -> str:
    return E.CFG["storage"]["full_format"]


if __name__ == "__main__":
    main()
