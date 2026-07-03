"""
upload_to_supabase.py — embed the corpus and push it to the Supabase knowledge DB.

Fills `documents` + `document_chunks` (with pgvector embeddings) in the `oa-sourcing-brain`
project, so the deployed app can do live semantic search via the `match_chunks` RPC.

DEFAULT EMBEDDER = LOCAL (BAAI/bge-base-en-v1.5, via fastembed, $0, fully offline). The LIVE
corpus in Supabase was embedded with this model — Gemini/OpenAI vectors are NOT interchangeable
with it even at the same 768 dimensions (different embedding SPACES, not just different sizes),
so running this with a non-local provider silently writes semantically incompatible vectors
into the same table and degrades retrieval with no error at write time (Code Review 2026-07-02,
Finding B7 — this used to default to "gemini," which one forgetful run could trigger). Gemini/
OpenAI require an explicit `--force-provider` flag as an intentional "I know what I'm doing and
I'm about to re-embed the WHOLE corpus with a different model" acknowledgement.

Run AFTER `ingest.py`:
    pip install requests fastembed
    set SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co
    set SUPABASE_SERVICE_KEY=...        # dashboard -> Settings -> API -> service_role (secret)
    python upload_to_supabase.py
"""
import json
import math
import os
import random
import sys
import time
import requests

SUPA = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PROVIDER = os.environ.get("EMBED_PROVIDER", "local").lower()
FORCE_PROVIDER = "--force-provider" in sys.argv
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
# gemini-embedding-001 is Google's current GA embedding model (text-embedding-004 was shut
# down Jan 14 2026). It defaults to 3072 dims; we request 768 via outputDimensionality so the
# vectors fit the document_chunks.embedding vector(768) column.
GEMINI_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_DIM = int(os.environ.get("GEMINI_EMBED_DIM", "768"))
LOCAL_MODEL_NAME = os.environ.get("LOCAL_EMBED_MODEL", "BAAI/bge-base-en-v1.5")  # 768-dim, runs fully offline
_LOCAL_MODEL = None
OPENAI_MODEL = "text-embedding-3-small"                                     # 1536 dims
HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = int(os.environ.get("EMBED_BATCH", "50"))           # chunks per embed request
PACE = float(os.environ.get("EMBED_PACE", "20"))           # seconds between requests (Dec-2025 free tier is throttled)

if not (SUPA and KEY):
    sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first (see header).")
if PROVIDER in ("gemini", "openai") and not FORCE_PROVIDER:
    sys.exit(
        f"Refusing to run with EMBED_PROVIDER={PROVIDER} without --force-provider.\n"
        f"The live Supabase corpus was embedded with the LOCAL model (BAAI/bge-base-en-v1.5, "
        f"768-dim) — {PROVIDER}'s vectors are a DIFFERENT embedding space even at the same "
        f"768 dimensions, so mixing them into document_chunks silently corrupts retrieval with "
        f"no error at write time (Code Review 2026-07-02, Finding B7).\n"
        f"If you genuinely intend to re-embed the WHOLE corpus with {PROVIDER} (and update "
        f"every existing row, not just new ones), re-run with --force-provider."
    )
if PROVIDER == "gemini" and not GEMINI_KEY:
    sys.exit("Set GEMINI_API_KEY (free at aistudio.google.com), or unset EMBED_PROVIDER to use the free local default.")
if PROVIDER == "openai" and not OPENAI_KEY:
    sys.exit("Set OPENAI_API_KEY, or unset EMBED_PROVIDER to use the free local default.")
if PROVIDER == "local":
    try:
        import fastembed  # noqa: F401
    except ImportError:
        sys.exit("EMBED_PROVIDER=local needs fastembed — run:  pip install fastembed")

SB = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def _normalize(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _post_with_retry(url, **kw):
    """POST with exponential backoff + jitter on rate limits / transient server errors."""
    for attempt in range(7):
        r = requests.post(url, timeout=180, **kw)
        if r.status_code in (429, 500, 503):
            wait = min(120, 8 * 2 ** attempt) + random.uniform(0, 5)
            print(f"  rate-limited ({r.status_code}); waiting {wait:.0f}s then retrying...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def embed(texts, task_type="RETRIEVAL_DOCUMENT"):
    """Return a list of unit-normalized embedding vectors (provider-agnostic)."""
    if PROVIDER == "local":
        global _LOCAL_MODEL
        if _LOCAL_MODEL is None:
            from fastembed import TextEmbedding
            print(f"loading local model {LOCAL_MODEL_NAME} (first run downloads it once, ~200MB)...")
            _LOCAL_MODEL = TextEmbedding(model_name=LOCAL_MODEL_NAME)
        return [_normalize([float(x) for x in v]) for v in _LOCAL_MODEL.embed(list(texts))]
    if PROVIDER == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:batchEmbedContents?key={GEMINI_KEY}"
        body = {"requests": [{"model": f"models/{GEMINI_MODEL}",
                              "content": {"parts": [{"text": t}]},
                              "taskType": task_type,
                              "outputDimensionality": GEMINI_DIM} for t in texts]}
        r = _post_with_retry(url, json=body)
        return [_normalize(e["values"]) for e in r.json()["embeddings"]]
    # openai
    r = _post_with_retry("https://api.openai.com/v1/embeddings",
                         headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                         json={"model": OPENAI_MODEL, "input": texts})
    return [_normalize(d["embedding"]) for d in r.json()["data"]]


def upsert(table, rows):
    r = requests.post(f"{SUPA}/rest/v1/{table}",
                      headers={**SB, "Prefer": "resolution=merge-duplicates,return=minimal"},
                      json=rows, timeout=60)
    r.raise_for_status()


def existing_chunk_ids():
    """Ids already stored, so re-runs resume instead of re-embedding (and re-burning quota)."""
    ids, step, off = set(), 1000, 0
    while True:
        r = requests.get(f"{SUPA}/rest/v1/document_chunks?select=id&limit={step}&offset={off}",
                         headers=SB, timeout=60)
        r.raise_for_status()
        rows = r.json()
        ids.update(row["id"] for row in rows)
        if len(rows) < step:
            return ids
        off += step


def main():
    docs = [json.loads(l) for l in open(os.path.join(HERE, "corpus", "documents.jsonl"), encoding="utf-8")]
    chunks = [json.loads(l) for l in open(os.path.join(HERE, "corpus", "chunks.jsonl"), encoding="utf-8")]
    cols = ("id", "title", "source_type", "category", "source_path", "source_url", "content_hash", "version", "status")
    upsert("documents", [{k: d.get(k) for k in cols} for d in docs])
    print(f"upserted {len(docs)} documents")
    done = existing_chunk_ids()
    todo = [c for c in chunks if c["id"] not in done]
    pace_note = "no rate limit" if PROVIDER == "local" else f"~{PACE:.0f}s between requests"
    print(f"{len(done)} chunks already embedded; {len(todo)} remaining of {len(chunks)}. "
          f"(provider={PROVIDER}, batch={BATCH}, {pace_note})")
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        vecs = embed([c["chunk_text"] for c in batch])
        rows = [{"id": c["id"], "document_id": c["document_id"], "chunk_text": c["chunk_text"],
                 "heading_path": c.get("heading_path"), "chunk_index": c.get("chunk_index"),
                 "token_count": c.get("token_count"), "citation": c.get("citation"), "category": c.get("category"),
                 "embedding": "[" + ",".join(format(x, ".6f") for x in v) + "]"}
                for c, v in zip(batch, vecs)]
        upsert("document_chunks", rows)
        print(f"embedded {len(done) + i + len(batch)}/{len(chunks)} chunks")
        if PROVIDER != "local":
            time.sleep(PACE)
    print("done — knowledge DB filled. Test with ask('your question').")


def ask(question, k=6, category=None):
    qv = embed([question], task_type="RETRIEVAL_QUERY")[0]
    r = requests.post(f"{SUPA}/rest/v1/rpc/match_chunks", headers=SB,
                      json={"query_embedding": "[" + ",".join(map(str, qv)) + "]",
                            "match_count": k, "filter_category": category}, timeout=60)
    r.raise_for_status()
    for row in r.json():
        print(f"[{row['similarity']:.3f}] {row['citation']}\n  {row['chunk_text'][:200]}\n")


if __name__ == "__main__":
    main()
