"""
ask.py — ask your Supabase knowledge brain a question (live, cited semantic search).

Embeds your question locally with the SAME model that filled the DB
(BAAI/bge-base-en-v1.5, 768-dim, via fastembed), calls the match_chunks RPC,
and prints the most relevant cited passages.

    python -m pip install fastembed requests
    set "SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co"
    python ask.py how do I get ungated in a brand?

Read-only: uses the PUBLISHABLE (public) key by default, so no secret is needed.
If you've rotated keys, set SUPABASE_KEY=...; it will also pick up SUPABASE_SERVICE_KEY
if that's already in your shell.
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SUPA = os.environ.get("SUPABASE_URL", "https://cakbzcvtqhdtxfjuxstd.supabase.co").rstrip("/")
# read-only publishable key is safe to keep here; SUPABASE_KEY / SUPABASE_SERVICE_KEY override it
KEY = (os.environ.get("SUPABASE_SERVICE_KEY")
       or os.environ.get("SUPABASE_KEY")
       or "sb_publishable_ffk3LRYbpHh_H6jfeChCKA_4RGkzAeh")
MODEL = os.environ.get("LOCAL_EMBED_MODEL", "BAAI/bge-base-en-v1.5")
_MODEL = None
ROOT = Path(__file__).resolve().parent

STOPWORDS = {
    "about", "after", "again", "also", "because", "before", "being",
    "could", "does", "from", "have", "into", "more", "should", "that", "their",
    "there", "these", "they", "this", "what", "when", "where", "which", "while",
    "with", "would", "your",
}

CONCEPTS = {
    "safe": {"eligibility", "gated", "restriction", "risk", "authenticity", "ip", "hazmat", "buybox"},
    "allowed": {"eligibility", "gated", "restriction", "policy", "condition", "invoice"},
    "profitable": {"roi", "profit", "margin", "fees", "cost", "price", "sales", "bsr", "offers"},
    "profit": {"roi", "margin", "fees", "cost", "price", "break-even"},
    "bad": {"reject", "avoid", "risk", "red", "flag", "spike", "cliff", "falling"},
    "buy": {"cost", "roi", "profit", "eligibility", "keepa", "offers", "buybox", "risk"},
    "accurate": {"outcomes", "labels", "calibration", "evaluation", "drift", "leakage"},
    "smarter": {"outcomes", "feedback", "labels", "evaluation", "evidence", "learning"},
    "keepa": {"price", "rank", "offers", "buybox", "history", "sales", "seasonality"},
}


def _terms(text):
    return {
        token for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def _query_terms(text):
    terms = _terms(text)
    expanded = set(terms)
    for concept, related in CONCEPTS.items():
        if concept in terms:
            expanded.update(related)
    return expanded


def _source_bonus(citation):
    """Prefer distilled/structured project knowledge over raw creator transcripts."""
    source = (citation or "").lower()
    if "playbooks/" in source:
        return 0.18
    if "ai-system/" in source:
        return 0.14
    if "fundamentals/" in source:
        return 0.07
    if "transcripts/insights.md" in source:
        return 0.06
    if "transcripts/" in source:
        return -0.08
    return 0.02


def _clean_text(text):
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text or "")
    text = re.sub(r"[`*_>#]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—:;")
    return text


def _canonical_points(question):
    """Return maintained expert rules for high-frequency OA intents."""
    terms = _terms(question)
    points = []
    if terms & {"accurate", "accuracy", "smarter", "improve", "learn", "learning"}:
        points = [
            ("Capture the human decision and the realized outcome for every reviewed lead: actual profit/ROI, sell-through time, returns, price movement, and whether it should be bought again.", "learning-hub/ai-system/ai-architecture.md"),
            ("Train only on information available before the decision; post-purchase performance is the label. This prevents target leakage and false confidence.", "learning-hub/ai-system/ai-upgrade-plan.md"),
            ("Keep compliance and margin gates outside machine learning, and promote a challenger only after it beats the current model on held-out outcomes and calibration.", "scout_pro/ARCHITECTURE.md"),
        ]
    elif "keepa" in terms or terms & {"chart", "graph", "buybox", "rank"}:
        points = [
            ("Read the 90-day and one-year views together: repeated rank drops support demand, while stable or rising Buy Box price is healthier than a temporary spike.", "learning-hub/playbooks/sourcing-playbook.md"),
            ("Prefer flat or falling offer count. Rising offers while price falls signals crowding and likely price compression; a sudden seller-count cliff can indicate IP enforcement.", "learning-hub/playbooks/sourcing-playbook.md"),
            ("Check Amazon's Buy Box share, variation-level history, seasonality, and the lowest historical price. The deal should at least break even in that downside case.", "learning-hub/ai-system/product-research-template.md"),
        ]
    elif terms & {"ungated", "gated", "approval", "eligible", "eligibility", "invoice", "restricted", "allowed"}:
        points = [
            ("Test the exact ASIN, condition, and marketplace in Seller Central first because approval is account-specific and can change.", "learning-hub/playbooks/ungating-playbook.md"),
            ("Prefer auto-ungated products while the account is new. If Amazon requests documents, follow the current request exactly and use authentic, unaltered supply-chain invoices from an accepted source.", "learning-hub/playbooks/ungating-playbook.md"),
            ("Eligibility does not prove profitability or low IP risk; verify both separately before buying inventory.", "learning-hub/ai-system/product-research-template.md"),
        ]
    elif terms & {"unit", "units", "quantity", "many"}:
        points = [
            ("Use a small 5–10 unit test for a new product rather than committing heavily before real sell-through is observed.", "learning-hub/playbooks/sourcing-playbook.md"),
            ("For a larger buy, estimate variation-level monthly sales per price-competitive seller, then reduce the result by 30–50% for uncertainty.", "learning-hub/ai-system/product-research-template.md"),
            ("Only scale after the product survives the lowest historical price, account-eligibility, IP/restriction, and concentration-risk checks.", "learning-hub/ai-system/product-research-template.md"),
        ]
    elif terms & {"buy", "product", "candidate", "profitable", "profit", "roi", "safe", "avoid", "bad", "deal"}:
        try:
            brain = json.loads((ROOT.parent / "learning-hub" / "data" / "ai-brain.json").read_text(encoding="utf-8"))
            criteria = brain.get("criteria", {})
        except (OSError, ValueError):
            criteria = {}
        bsr = int(criteria.get("bsrMax", 200000))
        sales = int(criteria.get("minMonthlySales", 50))
        min_offers = int(criteria.get("minOffers", 3))
        max_offers = int(criteria.get("maxOffers", 25))
        roi = round(float(criteria.get("minRoi", 0.30)) * 100)
        profit = float(criteria.get("minProfitPerUnit", 3))
        points = [
            (f"Use the current screening floors: BSR at or below {bsr:,}, at least {sales} estimated monthly sales, {min_offers}–{max_offers} competitive offers, at least {roi}% ROI, and at least ${profit:g} profit per unit after all landed costs and fees.", "learning-hub/data/ai-brain.json · learning-hub/ai-system/product-research-template.md"),
            ("Require stable price history, flat or falling offer count, and little or no Amazon Buy Box dominance. Reject price spikes, seller-count spikes, suspicious seller cliffs, and margins that fail at the historical low price.", "learning-hub/playbooks/sourcing-playbook.md"),
            ("Before buying, verify the exact UPC/model/size/count/variation and confirm account eligibility, condition, IP risk, FBA restrictions, hazmat/expiration rules, and current fees.", "learning-hub/ai-system/product-research-template.md"),
            ("Treat a passing score as a candidate, not authorization. Start with a small test order and record the realized outcome so future recommendations can improve.", "learning-hub/playbooks/field-sops.md · learning-hub/ai-system/ai-architecture.md"),
        ]
    return [
        {"text": text, "citation": citation, "category": "Maintained project rule", "similarity": 1.0}
        for text, citation in points
    ]


def _retrieval_question(question):
    expanded = _query_terms(question) - _terms(question)
    if not expanded:
        return question
    return f"{question} Relevant OA concepts: {' '.join(sorted(expanded))}."


def rerank(rows, question, limit=6):
    """Hybrid rerank: vector relevance + lexical coverage + source reliability."""
    query_terms = _query_terms(question)
    seen = set()
    ranked = []
    for row in rows:
        text = row.get("chunk_text") or ""
        fingerprint = re.sub(r"\W+", "", text.lower())[:260]
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        text_terms = _terms(text)
        coverage = len(query_terms & text_terms) / max(1, min(len(query_terms), 8))
        similarity = float(row.get("similarity", 0) or 0)
        enriched = dict(row)
        enriched["query_coverage"] = round(coverage, 4)
        enriched["relevance"] = round(similarity + (coverage * 0.16) + _source_bonus(row.get("citation")), 4)
        ranked.append(enriched)
    ranked.sort(key=lambda item: item["relevance"], reverse=True)
    return ranked[:limit]


def synthesize(question, rows):
    """Build a concise, cited extractive answer without a paid/generative model."""
    query_terms = _query_terms(question)
    canonical = _canonical_points(question)
    if canonical:
        policy_terms = {"allowed", "eligible", "eligibility", "gated", "policy", "restricted", "hazmat", "invoice"}
        return {
            "intro": "Here is the maintained project guidance, backed by the cited knowledge base.",
            "points": canonical,
            "evidence_strength": "strong",
            "caveat": (
                "This is project evidence, not account-specific authorization. Confirm the current ASIN and condition in Seller Central before acting."
                if query_terms & policy_terms
                else "Treat this as decision support. Verify current marketplace data, fees, restrictions, and account eligibility before buying."
            ),
            "method": "zero-cost extractive synthesis",
        }
    candidates = []
    for source_index, row in enumerate(rows):
        raw = row.get("chunk_text") or ""
        parts = re.split(r"(?:\n+|(?<=[.!?])\s+|\s+[•·]\s+)", raw)
        for part in parts:
            original = part.strip()
            sentence = _clean_text(part)
            if len(sentence) < 38:
                continue
            if len(sentence) > 380:
                continue
            if not re.match(r"^[A-Z0-9$]", sentence):
                continue
            if re.search(r"(?:\b(?:and|or|the|a|an|to|with|have|has|from|at|of|for|in)|[+→,:;])$", sentence, re.I):
                continue
            if not re.search(r"[.!?]$", original) and not re.match(r"^(?:[-*•]|\d+[.)])\s+", original):
                continue
            sentence_terms = _terms(sentence)
            hit_count = len(query_terms & sentence_terms)
            if hit_count == 0:
                continue
            score = float(row.get("relevance", row.get("similarity", 0)) or 0) + min(hit_count, 6) * 0.09
            if re.search(r"(?:\$|%|\b(?:roi|bsr|offers?|buy box|eligib|gated|ip risk|profit)\b)", sentence, re.I):
                score += 0.06
            if 65 <= len(sentence) <= 320:
                score += 0.04
            candidates.append((score, source_index, sentence, sentence_terms, row))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    used_citations = {}
    for _, _, sentence, sentence_terms, row in candidates:
        citation = row.get("citation") or "Project knowledge source"
        if used_citations.get(citation, 0) >= 2:
            continue
        duplicate = False
        for point in selected:
            previous_terms = _terms(point["text"])
            union = sentence_terms | previous_terms
            if union and len(sentence_terms & previous_terms) / len(union) > 0.72:
                duplicate = True
                break
        if duplicate:
            continue
        selected.append({
            "text": sentence,
            "citation": citation,
            "category": row.get("category") or "Knowledge base",
            "similarity": float(row.get("similarity", 0) or 0),
        })
        used_citations[citation] = used_citations.get(citation, 0) + 1
        if len(selected) >= 4:
            break

    top_similarity = max((float(row.get("similarity", 0) or 0) for row in rows), default=0)
    top_coverage = max((float(row.get("query_coverage", 0) or 0) for row in rows), default=0)
    if top_similarity >= 0.76 and top_coverage >= 0.45:
        strength = "strong"
    elif top_similarity >= 0.58 and selected:
        strength = "moderate"
    else:
        strength = "limited"

    policy_terms = {"allowed", "eligible", "gated", "policy", "restricted", "hazmat", "invoice"}
    caveat = (
        "This is project evidence, not account-specific authorization. Confirm the current ASIN and condition in Seller Central before acting."
        if query_terms & policy_terms
        else "Treat this as decision support. Verify current marketplace data, fees, restrictions, and account eligibility before buying."
    )
    return {
        "intro": "Here is the clearest answer supported by the current knowledge base.",
        "points": selected,
        "evidence_strength": strength,
        "caveat": caveat,
        "method": "zero-cost extractive synthesis",
    }


def health():
    """Return safe runtime diagnostics without exposing credentials."""
    fastembed_ready = importlib.util.find_spec("fastembed") is not None
    supabase_ready = False
    detail = "unreachable"
    try:
        response = requests.get(
            f"{SUPA}/rest/v1/document_chunks?select=id&limit=1",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
            timeout=8,
        )
        supabase_ready = response.status_code < 400
        detail = f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        detail = exc.__class__.__name__
    return {
        "ready": fastembed_ready and supabase_ready,
        "python": sys.version.split()[0],
        "fastembed": fastembed_ready,
        "supabase": supabase_ready,
        "supabase_status": detail,
        "model": MODEL,
        "auth_mode": "environment override" if os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") else "publishable read-only",
    }


def embed(text):
    """Local 768-dim embedding, unit-normalized — must match how the DB was filled."""
    global _MODEL
    if _MODEL is None:
        from fastembed import TextEmbedding
        print(f"(loading {MODEL} once...)", file=sys.stderr)
        try:
            _MODEL = TextEmbedding(model_name=MODEL)
        except Exception as e:
            # A cold download interrupted mid-write (e.g. a caller's subprocess timeout firing
            # before the ~217MB onnx file finishes downloading+linking) leaves blobs/metadata
            # present but the per-revision snapshot dir empty. fastembed's own local-files-only
            # fast path only logs a WARNING for this and returns the broken path anyway, so it
            # fails identically forever without self-healing (Full-crew audit, 2026-07-11 —
            # reproduced live, this is exactly how scout/propose_updates.py's knowledge-driven
            # check degraded 4 days straight). Clear this model's cache folder and retry once.
            print(f"(model load failed ({e}); clearing cache and retrying once)", file=sys.stderr)
            from fastembed.common.utils import define_cache_dir
            import shutil
            stale = define_cache_dir(None) / f"models--{MODEL.replace('/', '--')}"
            shutil.rmtree(stale, ignore_errors=True)
            _MODEL = TextEmbedding(model_name=MODEL)
    vec = [float(x) for x in next(iter(_MODEL.embed([text])))]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def retrieve(question, k=6, category=None):
    """Return cited semantic matches without formatting or exiting the process."""
    qv = embed(question)
    r = requests.post(
        f"{SUPA}/rest/v1/rpc/match_chunks",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json={"query_embedding": "[" + ",".join(map(str, qv)) + "]",
              "match_count": k, "filter_category": category},
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase error {r.status_code}: {r.text[:300]}")
    return r.json()


def ask(question, k=6, category=None):
    rows = retrieve(question, k=k, category=category)
    if not rows:
        print("No matches found.")
        return []
    print(f"\nTop {len(rows)} matches for: {question}\n" + "-" * 60)
    for row in rows:
        sim = float(row.get("similarity", 0) or 0)
        text = (row.get("chunk_text") or "").replace("\n", " ").strip()
        print(f"\n[{sim:.3f}]  {row.get('citation', '')}")
        print("   " + text[:400] + ("..." if len(text) > 400 else ""))
    return rows


# ----------------------------------------------------------------------------
# Warm-server delegation (THIS_WEEK.md Prompt W1). The cold path above pays a full model load
# every process start (~1s on this machine's already-disk-cached fastembed model, much worse
# on a fresh machine/model download); server.py keeps that model warm in memory. If it's
# running, delegate to it for a faster answer — completely optional, best-effort, and
# invisible to every caller: same JSON shape either way, and any failure (server not running,
# timeout, bad response) silently falls back to the cold path below. This CLI never raises
# just because the server happens to be down; that's the whole point of the fallback.
# ----------------------------------------------------------------------------
def _server_base_url() -> str:
    port = os.environ.get("KNOWLEDGE_SERVER_PORT", "8787")
    return f"http://127.0.0.1:{port}"


def server_available(timeout: float = 1.5) -> bool:
    """True if knowledge-rag/server.py is up and has the model warm. Short timeout on
    purpose — if nothing's listening (the common case until the server is started as a
    background process), this must fail fast so it never meaningfully delays the cold path."""
    try:
        r = requests.get(f"{_server_base_url()}/health", timeout=timeout)
        return r.status_code == 200 and bool(r.json().get("model_loaded"))
    except Exception:
        return False


def ask_via_server(question: str, limit: int = 6, category=None, timeout: float = 8.0):
    """POST to the local warm server's /ask endpoint. Returns the exact same
    {question, count, answer, matches} shape the cold path below produces, or None on ANY
    failure (caller falls back to cold — this must never raise)."""
    try:
        r = requests.post(
            f"{_server_base_url()}/ask",
            json={"question": question, "limit": limit, "category": category},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the live Supabase knowledge brain")
    parser.add_argument("question", nargs="*", help="question to retrieve evidence for")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit machine-readable JSON to stdout")
    parser.add_argument("--limit", type=int, default=6, help="number of matches (1-10)")
    parser.add_argument("--category", default=None, help="optional corpus category filter")
    parser.add_argument("--health", action="store_true", help="check local runtime and Supabase access")
    args = parser.parse_args()
    q = " ".join(args.question).strip()
    if args.health:
        payload = health()
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload["ready"] else 1)
    if not q and not args.as_json:
        q = input("Ask your brain: ").strip()
    if not q:
        parser.error("a non-empty question is required")
    try:
        limit = max(1, min(args.limit, 20))
        # Fast path: delegate to the warm server if it's up (THIS_WEEK.md Prompt W1) — same
        # output either way, so every existing caller of this CLI sees zero behavior change,
        # just a faster answer when server.py happens to be running.
        server_payload = ask_via_server(q, limit=limit, category=args.category) if server_available() else None
        if server_payload is not None:
            ranked = server_payload.get("matches", [])
            answer = server_payload.get("answer")
        else:
            rows = retrieve(_retrieval_question(q), k=limit, category=args.category)
            ranked = rerank(rows, q, limit=limit)
            answer = synthesize(q, ranked)
        if args.as_json:
            print(json.dumps({"question": q, "count": len(ranked), "answer": answer, "matches": ranked},
                             ensure_ascii=False))
        else:
            # Note: previously this branch printed pre-rerank `rows` while --json printed
            # post-rerank `ranked` (an existing drift between the two output modes) — now both
            # use `ranked` always, since the warm server only ever returns the reranked form
            # (there's no separate "raw rows" to fall back to when delegating to it) and this
            # keeps the human-readable text IDENTICAL whether the cold or warm path served it.
            if not ranked:
                print("No matches found.")
            else:
                print(f"\nTop {len(ranked)} matches for: {q}\n" + "-" * 60)
                for row in ranked:
                    sim = float(row.get("similarity", 0) or 0)
                    text = (row.get("chunk_text") or "").replace("\n", " ").strip()
                    print(f"\n[{sim:.3f}]  {row.get('citation', '')}")
                    print("   " + text[:400] + ("..." if len(text) > 400 else ""))
    except Exception as exc:
        if args.as_json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Knowledge search failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
