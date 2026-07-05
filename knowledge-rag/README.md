# knowledge-rag — the Amazon FBA / arbitrage knowledge base (RAG)

A **retrieval-augmented** knowledge base so the assistant answers Amazon policy / FBA /
listing / fee / arbitrage questions from **cited source passages** instead of memory.
It does **not** fine-tune on the docs (that goes stale and can't cite) — it searches the
corpus every time it answers. This is the build of the plan in the two uploaded PDFs.

## What's ingested now
`ingest.py` chunks **every document we legitimately own** into a section-aware corpus:

| Category | Source |
|---|---|
| Fundamentals | `learning-hub/fundamentals/*`, course-slide notes |
| Arbitrage decision rules | sourcing + brands playbooks, `transcripts/insights.md` |
| Listing rules | ungating playbook |
| FBA operations | operations playbook |
| Transcripts | all 45 unique video transcripts |
| APIs and data | the 2 uploaded PDFs + our design docs |

Current corpus (live Supabase, verified 2026-07-03): **99 documents → 1,340 chunks** (~800-token
chunks, 100-token overlap, each carrying its `heading_path`, `category`, and a `citation` back to
the exact file/section). This count grows with every research-pipeline run — check
`learning-hub/data/ai-brain.json`'s `knowledge.ragCorpus` or query Supabase directly for the
current number rather than trusting this one to stay fresh.

## Amazon's own docs (the "every single document" part)
Amazon's ToS forbids automated logged-in scraping and bulk re-utilization, so Amazon pages
are tracked as a **coverage program**, not a one-time scrape:

- `sources/manifest.json` — every target Amazon source (Seller University, FBA, fees,
  SP-API, policy pages) with `category`, `access` (public / api / login), and `status`
  (collected / index_only / pending).
- Amazon publishes an **AI-agent index** at `developer-docs.amazon.com/llms.txt` — the
  machine-readable list of *all* SP-API doc pages (each as Markdown). That's the sanctioned
  way to cover the API surface; pages are fetched **on demand under your own access**.
- Login-gated Seller Central policy pages are **manual export only** — download them and drop
  the text into `sources/` and they get chunked + cited like everything else.

See `update_job.md` for the daily/weekly refresh cadence + change-versioning, and
`system_instruction.md` / `answer_flow.md` for how the assistant retrieves, cites, and
separates **"can I profit?"** from **"am I allowed?"**.

## Run
```bash
cd "Amazon FBA/knowledge-rag"
pip install -r requirements.txt
python ingest.py                              # (re)build corpus/chunks.jsonl  (no deps)
python build_index.py build                   # embed the corpus (downloads bge-small once)
python build_index.py ask "how do I get ungated?"
python build_index.py ask "fee rules" --category Policy
python ask.py --json --limit 6 "what are Keepa red flags?"  # live Supabase retrieval
python evaluate.py                                          # live answer quality gate
```

## Warm knowledge server (THIS_WEEK.md Prompt W1)

`ask.py` runs as a cold subprocess by default — every single call re-loads the
`BAAI/bge-base-en-v1.5` model from scratch. `server.py` loads that model **once** and keeps it
warm in memory, so repeated calls skip the load entirely. Measured on this machine (2026-07-04,
model already disk-cached): **cold subprocess ~1.1s per call, warm server ~350-650ms** — a real
speedup, and the gap widens further on a machine where the model isn't already cached locally
(a fresh cold start also pays a one-time download).

Everything that talks to the knowledge base tries the warm server FIRST and silently falls back
to the cold path if it's not running — nothing breaks if you never start it, it's purely an
optional speed boost:
- `ask.py`'s own CLI (`server_available()` / `ask_via_server()`) — same output either way.
- `control-center/app/api/knowledge-search/route.ts` — tries `http://127.0.0.1:8787` (3s
  timeout) before shelling out to `ask.py` as a subprocess; the response's `latency_source`
  field (`"server"` / `"subprocess"` / `"cache"`) honestly records which path actually answered.

**Start it:**
```bash
cd "Amazon FBA/knowledge-rag"
python server.py                 # foreground; Ctrl+C to stop
# or just double-click start-server.bat
```
Check it's up: `curl http://127.0.0.1:8787/health` (reports `model_loaded`, cached corpus
counts from `ai-brain.json`, and uptime).

**Keep it running automatically (Windows Task Scheduler, ONSTART trigger):**
```
schtasks /Create /TN "FBA Knowledge Server" /TR "python C:\path\to\knowledge-rag\server.py" ^
  /SC ONSTART /RL LIMITED /F
```
This starts the server once, at every login, instead of you remembering to double-click
`start-server.bat` each session. It's a plain long-running process (no console window closing
it), so `taskkill /F /IM python.exe` will also stop it — use `netstat -ano | findstr 8787` to
find its specific PID if you need to stop just this one process among other Python processes.

**Security:** binds `127.0.0.1` ONLY (see `server.py`'s `HOST` constant) — never `0.0.0.0`.
There is no authentication on `/embed`/`/ask`/`/health` because nothing outside this machine
can ever reach them. If you ever need to bind a non-loopback address, add real auth first;
don't just flip `HOST`.

**Port:** override with `KNOWLEDGE_SERVER_PORT` (both `server.py` and the two callers above
read the same env var — default `8787`).

## Files
| File | Role |
|---|---|
| `ingest.py` | Chunk every owned doc → `corpus/documents.jsonl` + `corpus/chunks.jsonl` (Postgres-ready schema). Pure stdlib. |
| `build_index.py` | Embed the corpus into FAISS + retrieve with citations. |
| `ask.py` | Embed a query locally, search Supabase, prefer maintained sources, deduplicate/rerank, and build a concise cited answer without a paid model. Tries the warm server first (see above), falls back to a cold in-process run — CLI behavior/output is identical either way. |
| `server.py` | The warm knowledge server (see above) — loads the embedding model once, exposes `/embed`, `/ask`, `/health` on loopback only. Reuses `ask.py`'s functions directly (no forked logic). |
| `start-server.bat` | Double-click to run `server.py` in the foreground. |
| `evaluate.py` | Run maintained fact/citation expectations against live retrieval; currently 5 core OA cases. |
| `evals/questions.json` | Versioned answer-quality cases. Add a case whenever a bad answer is found. |
| `sources/manifest.json` | The Amazon-docs coverage program (URLs, category, access, status). |
| `sources/pdfs/` | The uploaded PDFs as Markdown source docs. |
| `system_instruction.md` | The assistant's system prompt (retrieve-first, cite, refuse policy violations). |
| `answer_flow.md` | The 8-step retrieval + decision pipeline. |
| `update_job.md` | Refresh cadence + `source_events` versioning + compliance guardrails. |
| `corpus/` | Generated chunk corpus (the single chunking source of truth). |

## How this fits the system
The **scout** answers *"can I profit?"* (BSR/ROI/offers/Buy-Box + the spike/offers-rising/
Amazon-share guards). This corpus answers *"am I allowed?"* — gating, IP, restricted
products, invoices, FBA eligibility — the half Keepa can't see. The **control center** is
where both meet. The corpus is live in Supabase pgvector using 768-dimensional
`BAAI/bge-base-en-v1.5` embeddings; the local FAISS build remains an offline fallback.
High-frequency, high-risk OA questions use maintained project rules read from the current
brain and cite their source files. Other questions use extractive synthesis from reranked
passages. This is intentionally less fluent than a paid generative model but is auditable,
fast on repeated queries, and cannot fabricate unsupported prose.
