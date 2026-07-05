"""
server.py — the persistent warm knowledge-embedding worker (THIS_WEEK.md Prompt W1; the
long-planned "persistent warm embedding worker" from Codex Session 04's limitations note).

Problem: every Ask query and every future embedding consumer (the deal matcher's title path,
M3's exemplar index) pays the FULL BAAI/bge-base-en-v1.5 model load (~seconds) because ask.py
runs as a cold subprocess every single call. This process loads the model ONCE at startup and
keeps it warm in memory, so every subsequent call is just inference (milliseconds).

Reuses ask.py's OWN functions directly (embed/retrieve/rerank/synthesize/_retrieval_question/
health) — this file does NOT reimplement or fork any retrieval/embedding logic. That also means
ask.py's module-level `_MODEL` cache gets populated by THIS process at startup and stays warm
for the process's whole life; ask.py itself is completely unaware it's running inside a server
instead of a cold script.

SECURITY: binds 127.0.0.1 ONLY (HOST below) — never 0.0.0.0. This is a personal, single-
operator tool; the server carries no auth because nothing outside this machine can ever reach
it. Never change HOST to a non-loopback address without adding real authentication first.

Run it:
    python server.py                      # foreground, Ctrl+C to stop
    uvicorn server:app --host 127.0.0.1 --port 8787   # equivalent, explicit

See README.md's "Warm knowledge server" section for the Windows-friendly ways to keep it
running (start-server.bat, Task Scheduler ONSTART).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

import ask

HOST = "127.0.0.1"  # LOOPBACK ONLY — see the security note above. Never change this.
PORT = int(os.environ.get("KNOWLEDGE_SERVER_PORT", "8787"))

_START_TIME = time.time()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Load the bge model into ask.py's module-level cache immediately, so the FIRST real
    # request is fast too (not just the second one) and /health can honestly report
    # model_loaded=true right after boot instead of lying until the first query arrives.
    try:
        ask.embed("warm up the embedding model")
    except Exception:
        # ask.embed() already logs to stderr on load failure; /health's "ready" field will
        # honestly reflect fastembed being unavailable. Never crash server startup over this —
        # a degraded /health is still useful signal, a dead process is not.
        pass
    yield


app = FastAPI(title="FBA knowledge-rag warm server", docs_url=None, redoc_url=None, lifespan=_lifespan)


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedResponse(BaseModel):
    vectors: List[List[float]]


class AskRequest(BaseModel):
    question: str
    limit: Optional[int] = 6
    category: Optional[str] = None


_BRAIN_PATH = os.path.join(os.path.dirname(__file__), "..", "learning-hub", "data", "ai-brain.json")


def _corpus_counts() -> Dict[str, Any]:
    """Corpus size, read from `ai-brain.json`'s `knowledge.ragCorpus` - NOT a live Supabase
    count. Confirmed live (2026-07-04) that the read-only publishable key ask.py uses has no
    direct SELECT grant on `documents`/`document_chunks` (only the `match_chunks` RPC is
    granted to `anon` - see knowledge-rag/SUPABASE-SETUP.md); a direct-table count with this
    key always returns 0 regardless of real corpus size, which would be actively misleading
    reported as "live," not just stale. ai-brain.json's ragCorpus block is this project's own
    established single source for this exact number (synced by the ingestion pipeline,
    documented in CLAUDE_CODE_GUIDE.md) - reported here honestly labeled as cached, with its
    own sync date, rather than fabricating a fresher-looking live query that can't work.
    Plain ASCII in the returned string on purpose - this gets printed by ask.py's CLI on a
    Windows cp1252 console, and a real unicode dash crashed a similar print() before
    (Session 38's journal entry)."""
    try:
        with open(_BRAIN_PATH, "r", encoding="utf-8") as f:
            brain = json.load(f)
        rag = (brain.get("knowledge") or {}).get("ragCorpus") or {}
        return {
            "source": "cached (ai-brain.json knowledge.ragCorpus) - not a live Supabase count; "
                      "the read-only key this server uses has no direct table-select grant",
            "documents": rag.get("documents"),
            "chunks": rag.get("chunks"),
            "synced": brain.get("knowledge", {}).get("lastDistilled"),
        }
    except Exception:
        return {"source": "unavailable", "documents": None, "chunks": None, "synced": None}


@app.get("/health")
def health() -> Dict[str, Any]:
    base = ask.health()
    return {
        **base,
        "model_loaded": ask._MODEL is not None,
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "corpus": _corpus_counts(),
        "port": PORT,
    }


@app.post("/embed", response_model=EmbedResponse)
def embed_endpoint(body: EmbedRequest) -> EmbedResponse:
    return EmbedResponse(vectors=[ask.embed(t) for t in body.texts])


@app.post("/ask")
def ask_endpoint(body: AskRequest) -> Dict[str, Any]:
    """The EXACT same cited-matches JSON shape `python ask.py --json` produces — same
    functions, same output contract, just warm instead of cold."""
    limit = max(1, min(body.limit or 6, 20))
    rows = ask.retrieve(ask._retrieval_question(body.question), k=limit, category=body.category)
    ranked = ask.rerank(rows, body.question, limit=limit)
    return {
        "question": body.question,
        "count": len(ranked),
        "answer": ask.synthesize(body.question, ranked),
        "matches": ranked,
    }


def run_server() -> None:
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    run_server()
