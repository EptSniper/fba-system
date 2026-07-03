# Stack map — codebase orientation for the engineering crew

Shared context for the engineering skills (architect, coder, code-reviewer, debugger, database-expert,
designer, qa-tester, data-analyst). Read this before touching code so you understand what exists and the
non-negotiables. The durable record of every change is `AI_COLLABORATION_JOURNAL.md` — read it and append to it.

## Components

- **`scout/`** — Python OA discovery engine. Keepa → scoring/gates (`scoring.py`, `config.py` loads thresholds
  from `learning-hub/data/ai-brain.json`) → optional Discord alert → SQLite + optional Supabase logging
  (`db.py`, `pipeline.py`). Tests in `scout/tests/` (scorer 15/15, pipeline-memory 2/2). Live discovery needs a paid `KEEPA_KEY`.
- **`scout_pro/`** — advanced ML variant: snapshots, features, calibrated models, ranker, review queue,
  registry, drift (`models.py`, `gates.py`, `features.py`, `labels.py`, `db/schema.sql`). SP-API/Ads are stubs; no tests yet.
- **`knowledge-rag/`** — zero-cost RAG. Local embeddings `BAAI/bge-base-en-v1.5` (768-dim), read-only Supabase
  retrieval. `ask.py` exposes `retrieve()` + `--json` CLI; corpus is 78 docs / 1,224 chunks. Evals in `evals/`, `evaluate.py`.
- **`control-center/`** — canonical UI. Next.js 15.5.18, TypeScript, Tailwind. Read-only operator dashboard
  (Today, Find/deal-analyzer, Amazon Ops, Ask, Brain, Scout Intelligence). `app/api/knowledge-search/route.ts`
  is a Node-only dynamic POST route that shells `ask.py`. Bundled snapshots in `hub-data/` can go stale vs the live brain.
- **`learning-hub/`** — knowledge base + `data/ai-brain.json` (single source of truth for criteria).
- Static HTML prototypes (`fba-toolkit.html`, `oa-control-center.html`, `tracker/`, `oa-terminal-deploy/`) — older, some are byte-for-byte duplicates.

## Non-negotiables (these have bitten the project before)

1. **No secrets in source or browser.** Service-role keys, Keepa keys, webhooks live only in untracked `.env`.
   The browser may call only same-origin routes; never expose a service key to client JS.
2. **ML target-leakage prevention.** Only pre-decision features train the model; realized outcomes are labels.
   Never log the scout's own verdict as its success label — that is self-confirmation.
3. **Hard compliance/safety gates stay outside ML.** Eligibility, IP, Amazon-Buy-Box rejects are rules, not learned weights.
4. **`ai-brain.json` is the single source.** `scout/config.py` and the dashboard both load it; edit it through `fba-brain-updater`, preserving the `source:` provenance lines.
5. **Honest status words.** implemented ≠ tested ≠ configured ≠ deployed ≠ planned. Empty states are correct; fake live data is a defect.
6. **No auto-buy / no money movement.** Code recommends and explains; humans approve purchases and external writes.

## Verification expectations

Python: `python -m pytest` (or `unittest`) for scout; `py_compile` for syntax. control-center: `npm run typecheck`,
`npm run build` (Next.js), `npm audit --audit-level=moderate` (target 0). Capture results honestly in the journal,
and distinguish what you actually ran from what you only intended to run.
