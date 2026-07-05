"""
eval_retrieval.py — RAG retrieval eval (DATA_ENGINE_PLAN.md V1, part 1).

Scores recall@5 and MRR on the question->expected-doc pairs in
learning-hub/evals/retrieval/pairs.jsonl, comparing:

  * bge (local)      — the SAME model production uses (BAAI/bge-base-en-v1.5, unit-normalized
                       cosine), embedded over the local corpus/chunks.jsonl. This needs no
                       Supabase, so it always runs when fastembed is installed and is the
                       apples-to-apples measure of the embedding model's retrieval quality.
  * bge (supabase)   — the ACTUAL production path (ask.retrieve -> match_chunks RPC). Runs only
                       when Supabase creds resolve and the corpus is embedded there; otherwise it
                       is reported "unavailable" honestly (never silently skipped).
  * BM25 (rank_bm25) — a plain lexical baseline over the same chunks. If bge LOSES to BM25 on any
                       category, the report flags CHUNKING as the first suspect, not the model
                       (the standard RAG-quality lesson from the corpus's own research docs).

recall@5 / MRR are computed at the retrieved-CHUNK level: a pair is a hit if any of the top-5
chunks belongs to an expected document; MRR uses the rank of the first such chunk.

Usage:
    python eval_retrieval.py                # runs every available system, writes the report
    python eval_retrieval.py --k 5          # cutoff (default 5)
    python eval_retrieval.py --no-supabase  # skip the production path even if creds exist
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
CORPUS = ROOT / "corpus" / "chunks.jsonl"
PAIRS = PROJECT / "learning-hub" / "evals" / "retrieval" / "pairs.jsonl"
REPORT = PROJECT / "learning-hub" / "evals" / "retrieval-report.md"
_VEC_CACHE = ROOT / "evals" / ".bge_vectors.jsonl"  # gitignored local cache (see below)


# --- IO ---------------------------------------------------------------------
def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def doc_id_of(row: Dict[str, Any]) -> Optional[str]:
    """Document id for a chunk row from either the corpus (has document_id) or the match_chunks
    RPC (may only carry the chunk id 'doc_xxx::N' or a citation). Degrades to None, never raises."""
    if row.get("document_id"):
        return row["document_id"]
    cid = row.get("id") or ""
    if "::" in cid:
        return cid.split("::", 1)[0]
    return cid or None


# --- metrics (pure, unit-testable) -----------------------------------------
def recall_at_k(ranked_doc_ids: List[Optional[str]], expected: List[str], k: int) -> float:
    exp = set(expected)
    return 1.0 if (set(ranked_doc_ids[:k]) & exp) else 0.0


def reciprocal_rank(ranked_doc_ids: List[Optional[str]], expected: List[str]) -> float:
    exp = set(expected)
    for i, d in enumerate(ranked_doc_ids, 1):
        if d in exp:
            return 1.0 / i
    return 0.0


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


# --- BM25 baseline ----------------------------------------------------------
def build_bm25(chunks: List[Dict[str, Any]]):
    from rank_bm25 import BM25Okapi
    return BM25Okapi([tokenize(c.get("chunk_text", "")) for c in chunks])


def bm25_rank(bm25, chunks: List[Dict[str, Any]], question: str, k: int) -> List[Optional[str]]:
    scores = bm25.get_scores(tokenize(question))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [doc_id_of(chunks[i]) for i in order]


# --- bge local --------------------------------------------------------------
_EMBED_MODEL: Dict[str, Any] = {"name": None, "model": None}


def _embed_texts(texts: List[str], model_name: str) -> List[List[float]]:
    # Module-level singleton: re-instantiating fastembed's ONNX model per call cost a full model
    # load per eval QUESTION — minutes of pure reloading per run (Review 2026-07-05).
    if _EMBED_MODEL["model"] is None or _EMBED_MODEL["name"] != model_name:
        from fastembed import TextEmbedding
        _EMBED_MODEL["model"] = TextEmbedding(model_name=model_name)
        _EMBED_MODEL["name"] = model_name
    out = []
    for vec in _EMBED_MODEL["model"].embed(list(texts)):
        v = [float(x) for x in vec]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


def _corpus_signature(chunks: List[Dict[str, Any]]) -> str:
    """Cache key for the chunk vectors. Includes CONTENT (not just count + boundary ids): a
    re-ingest that rewrites chunk_text while preserving ids/count must invalidate the cache, or
    the eval silently ranks against embeddings of text that no longer exists (Review 2026-07-05)."""
    import hashlib
    h = hashlib.sha256()
    h.update(str(len(chunks)).encode())
    if chunks:
        h.update((chunks[0].get("id", "") + chunks[-1].get("id", "")).encode())
        h.update(chunks[0].get("chunk_text", "")[:400].encode("utf-8", "replace"))
        h.update(chunks[-1].get("chunk_text", "")[:400].encode("utf-8", "replace"))
        total_chars = sum(len(c.get("chunk_text", "")) for c in chunks)
        h.update(str(total_chars).encode())
    return h.hexdigest()[:16]


def load_or_build_chunk_vectors(chunks: List[Dict[str, Any]], model_name: str) -> List[List[float]]:
    """Embed every chunk once with bge, caching to a local jsonl keyed by a corpus signature so
    re-runs are instant. The cache is derived (regenerable) — gitignored, never committed."""
    sig = _corpus_signature(chunks)
    if _VEC_CACHE.exists():
        try:
            cached = load_jsonl(_VEC_CACHE)
            if cached and cached[0].get("sig") == sig and len(cached) == len(chunks) + 1:
                return [row["v"] for row in cached[1:]]
        except Exception:
            pass
    vectors = _embed_texts([c.get("chunk_text", "") for c in chunks], model_name)
    try:
        _VEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(_VEC_CACHE, "w", encoding="utf-8") as f:
            f.write(json.dumps({"sig": sig}) + "\n")
            for v in vectors:
                f.write(json.dumps({"v": v}) + "\n")
    except Exception:
        pass
    return vectors


def bge_local_rank(vectors: List[List[float]], chunks: List[Dict[str, Any]],
                   query_vec: List[float], k: int) -> List[Optional[str]]:
    sims = [sum(a * b for a, b in zip(query_vec, v)) for v in vectors]
    order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:k]
    return [doc_id_of(chunks[i]) for i in order]


# --- evaluation core --------------------------------------------------------
def evaluate(pairs: List[Dict[str, Any]], rank_fn: Callable[[str, int], List[Optional[str]]],
             k: int) -> Dict[str, Any]:
    """Run one ranking system over every pair. rank_fn(question, k) -> list of doc_ids (chunk
    order). Returns overall + per-category recall@k and MRR."""
    per_cat: Dict[str, Dict[str, float]] = {}
    recalls, rrs = [], []
    for p in pairs:
        ranked = rank_fn(p["question"], k)
        r = recall_at_k(ranked, p["expected_doc_ids"], k)
        rr = reciprocal_rank(ranked, p["expected_doc_ids"])
        recalls.append(r)
        rrs.append(rr)
        cat = p.get("category", "Uncategorized")
        c = per_cat.setdefault(cat, {"recall": 0.0, "rr": 0.0, "n": 0})
        c["recall"] += r
        c["rr"] += rr
        c["n"] += 1
    for c in per_cat.values():
        c["recall"] = round(c["recall"] / c["n"], 3)
        c["rr"] = round(c["rr"] / c["n"], 3)
    n = len(pairs) or 1
    return {
        "recall_at_k": round(sum(recalls) / n, 3),
        "mrr": round(sum(rrs) / n, 3),
        "n": len(pairs),
        "per_category": per_cat,
    }


# --- report -----------------------------------------------------------------
def render_report(k: int, results: Dict[str, Dict[str, Any]],
                  unavailable: Dict[str, str], n_pairs: int) -> str:
    systems = list(results.keys())
    lines = [
        "# Retrieval eval — recall@%d + MRR (DATA_ENGINE_PLAN.md V1)" % k,
        "",
        f"**Pairs:** {n_pairs} (learning-hub/evals/retrieval/pairs.jsonl). "
        "Metrics are at the retrieved-chunk level: a pair is a hit if any of the top-%d chunks "
        "belongs to an expected document; MRR uses the first such chunk's rank." % k,
        "",
        "## Overall",
        "",
        "| System | recall@%d | MRR |" % k,
        "|---|---|---|",
    ]
    for s in systems:
        lines.append(f"| {s} | {results[s]['recall_at_k']:.3f} | {results[s]['mrr']:.3f} |")
    for s, reason in unavailable.items():
        lines.append(f"| {s} | _unavailable_ | {reason} |")
    lines += ["", "## Per-category recall@%d" % k, ""]
    cats = sorted({c for s in systems for c in results[s]["per_category"]})
    header = "| Category | " + " | ".join(systems) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(systems) + 1))
    for cat in cats:
        row = [cat]
        for s in systems:
            pc = results[s]["per_category"].get(cat)
            row.append(f"{pc['recall']:.2f} (n={pc['n']})" if pc else "—")
        lines.append("| " + " | ".join(row) + " |")

    # Honest chunking flag: where does BM25 beat bge?
    lines += ["", "## Honest read", ""]
    bge_key = next((s for s in systems if s.startswith("bge")), None)
    if bge_key and "BM25" in results:
        worse = []
        for cat in cats:
            b = results[bge_key]["per_category"].get(cat)
            m = results["BM25"]["per_category"].get(cat)
            if b and m and m["recall"] > b["recall"]:
                worse.append(f"{cat} (BM25 {m['recall']:.2f} > bge {b['recall']:.2f})")
        if worse:
            lines.append("⚠ BM25 beats bge in: " + "; ".join(worse) + ". Per the corpus's own RAG "
                         "research (rag-chunking-strategies-databricks, rag-best-practices), the FIRST "
                         "suspect is CHUNKING (chunks too small/large or split mid-idea), not the model.")
        else:
            lines.append("bge matches or beats BM25 in every category — no chunking red flag from this run.")
    for s, reason in unavailable.items():
        lines.append(f"- **{s}:** {reason}")
    lines.append("")
    lines.append("_Regenerate: `python knowledge-rag/eval_retrieval.py`._")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RAG retrieval eval (recall@k + MRR, bge vs BM25).")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--no-supabase", action="store_true", help="skip the production Supabase path")
    ap.add_argument("--no-bge", action="store_true", help="skip the local bge path (fast, BM25-only)")
    args = ap.parse_args(argv)

    pairs = load_jsonl(PAIRS)
    chunks = load_jsonl(CORPUS)
    results: Dict[str, Dict[str, Any]] = {}
    unavailable: Dict[str, str] = {}

    # BM25 (always available — rank_bm25 is a pure-python dep)
    try:
        bm25 = build_bm25(chunks)
        results["BM25"] = evaluate(pairs, lambda q, k: bm25_rank(bm25, chunks, q, k), args.k)
    except Exception as e:
        unavailable["BM25"] = f"rank_bm25 unavailable: {e}"

    # bge (local) — the same model, no DB needed
    if not args.no_bge:
        try:
            import ask  # for the model name
            model_name = getattr(ask, "MODEL", "BAAI/bge-base-en-v1.5")
            vectors = load_or_build_chunk_vectors(chunks, model_name)
            qcache: Dict[str, List[float]] = {}

            def _bge_rank(q, k):
                if q not in qcache:
                    qcache[q] = _embed_texts([q], model_name)[0]
                return bge_local_rank(vectors, chunks, qcache[q], k)

            results["bge (local)"] = evaluate(pairs, _bge_rank, args.k)
        except Exception as e:
            unavailable["bge (local)"] = f"fastembed unavailable: {e}"

    # bge (supabase) — the production path, only if it actually resolves
    if not args.no_supabase:
        try:
            import ask
            probe = ask.retrieve(pairs[0]["question"], k=args.k)
            _ = [doc_id_of(r) for r in probe]  # confirm shape
            results["bge (supabase)"] = evaluate(
                pairs, lambda q, k: [doc_id_of(r) for r in ask.retrieve(q, k=k)], args.k)
        except Exception as e:
            unavailable["bge (supabase)"] = f"production path not reachable here: {str(e)[:120]}"
    else:
        unavailable["bge (supabase)"] = "skipped (--no-supabase)"

    report = render_report(args.k, results, unavailable, len(pairs))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(f"wrote {REPORT}")
    for s, r in results.items():
        print(f"  {s:16} recall@{args.k}={r['recall_at_k']:.3f}  MRR={r['mrr']:.3f}")
    for s, reason in unavailable.items():
        print(f"  {s:16} UNAVAILABLE — {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
