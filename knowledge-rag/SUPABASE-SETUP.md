# Supabase "sourcing brain" — it's live AND filled

Your two-database backend is **created, schema'd, and the knowledge DB is now FULLY LOADED** on Supabase (free tier, $0/mo). This is the database the AI videos push: a real place to store knowledge + remember every lead and outcome.

## Status (2026-06-26)
- **Knowledge DB: ✅ filled** — 78 documents, **1,224 chunks**, every one embedded (`vector(768)`). Semantic search verified working (`match_chunks` self-similarity test = 1.0).
- **Business DB: ready, empty** — turns on when you add the Supabase key to the scout (below).

## Project
- **Name:** `oa-sourcing-brain`  ·  **Ref:** `cakbzcvtqhdtxfjuxstd`  ·  **Region:** us-east-1
- **URL:** `https://cakbzcvtqhdtxfjuxstd.supabase.co`
- **Publishable (public) key:** `sb_publishable_ffk3LRYbpHh_H6jfeChCKA_4RGkzAeh` (safe for the frontend / read-only search)
- **Service key (secret):** Supabase → your project → **Settings → API → `service_role`**. Server-side only — never put it in the browser. *(If you pasted it anywhere, rotate it.)*

## Tables (all created, RLS on)
**Knowledge DB (vector search):** `documents`, `document_chunks` (`embedding vector(768)` + an HNSW index) and a `match_chunks(query_embedding, match_count, filter_category)` function for semantic search. `anon` can EXECUTE `match_chunks` (read-only), so a frontend or the local `ask.py` can search with the publishable key.
**Business DB (the memory + learning loop):** `leads`, `keepa_snapshots`, `discounts`, `decisions`, `outcomes`, `storefronts` — **private** (RLS): the public key can't read them; only the `service_role` key (the scout) can.

## Embeddings = a FREE LOCAL model (no API, no rate limit)
The DB was filled with **`BAAI/bge-base-en-v1.5` (768-dim), run locally via `fastembed`** — fully offline, $0, no quotas.

Why not Gemini? Google **retired `text-embedding-004` on 2026-01-14**, and its replacement `gemini-embedding-001` has a free tier so throttled (post-Dec-2025 cuts) that bulk embedding hits `429` and won't recover — unusable for 1,224 chunks. The local model sidesteps all of that.

**Golden rule:** whatever model fills the DB must also embed the *queries*. Everything here uses `bge-base-en-v1.5`, so keep it consistent (`ask.py` and any deployed search must use the same model).

### Re-fill or top up (after you add documents)
```bat
cd "Amazon FBA\knowledge-rag"
python -m pip install fastembed requests
set "SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co"
set "SUPABASE_SERVICE_KEY=<your service_role key>"
set "EMBED_PROVIDER=local"
python ingest.py                 :: rebuild corpus from your docs (only if you changed docs)
python upload_to_supabase.py     :: embeds + uploads; resumable, $0, no rate limit
```
`upload_to_supabase.py` is **resumable** — it skips chunks already in the DB, so a re-run only does new/changed ones. Or just **double-click `run_upload.bat`**. (It still supports `EMBED_PROVIDER=gemini` / `openai` if you ever want an API embedder — those add pacing + retry for rate limits.)

## Ask the brain (live semantic search, right now)
```bat
cd "Amazon FBA\knowledge-rag"
python -m pip install fastembed requests
set "SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co"
python ask.py how do I get ungated in a brand?
```
It embeds your question with the same local model, calls `match_chunks`, and prints the most relevant **cited** passages. Uses the publishable key by default — no secret needed.

## The scout logs to the business DB automatically
Add the two Supabase vars to `scout/.env`. `scout/pipeline.py` now records every
evaluated candidate from a real run through `scout/db.py`: high-scoring candidates are
stored as `review`, while hard rejects and below-threshold candidates are stored as
`pass`. The scout never marks its own recommendation as a human-approved buy. Dry runs
do not write externally. Decisions and realized outcomes are added later through
`db.log_decision(...)` and `db.log_outcome(...)` once the human decision/result exists.

If the Supabase vars aren't set, every database call is a silent no-op — the scout runs
exactly as before. The service-role key stays only in the private `.env`, never in the
browser control center.

## Why this matters
- **Knowledge DB** → semantic search over your whole corpus (Keepa, sourcing, policy, SOPs). Scales past the dashboard's inlined copy and is ready for a deployed app.
- **Business DB** → every lead/decision/outcome is remembered, so the **rebuy agent** and the **mistake/learning loop** become possible once you've logged real buys.
