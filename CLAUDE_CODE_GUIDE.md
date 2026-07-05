# Claude Code Guide — Amazon FBA project

**Read this first, every session.** This file tells you (Claude Code, running in VS Code) what this
project is, what already exists, and — most importantly — **how to use the `fba-` skill team while you
code.** These skills encode the rules the code itself must obey, so using them keeps the scout, the
control-center, the RAG, and the trackers consistent instead of drifting apart.

Also read, as the project already requires: `CLAUDE.md`, `AI_COLLABORATION_JOURNAL.md`, and
`learning-hub/tracking/session-archive.md`. Append a dated journal entry every working session.

---

## 0. EVERY DAY: the research pipeline needs you to pull transcripts

A scheduled Cowork task (`fba-daily-research`, ~7 AM daily) automatically finds new Amazon FBA/OA and
system-building material and ingests text sources — **but it cannot transcribe YouTube** (the Cowork app
can't call the transcript API; you can). So there is a standing daily job for you:

**At the start of each session, read `research-inbox/CLAUDE_CODE_HANDOFF.md`** — the task rewrites it every
run with what's pending and what it found. Then:

1. If it lists queued videos, run `python knowledge-rag/fetch_transcripts.py` (uses the key in
   `knowledge-rag/.env`; writes transcripts to `research-inbox/transcripts/`).
2. Ingest each new transcript with `fba-transcript-ingest`: distilled, cited takeaways →
   `research-inbox/research-insights.md`, a line in `research-inbox/corpus-staging.jsonl`, a record in
   `research-inbox/research-manifest.json`, then move the file to `research-inbox/transcripts/processed/`.
3. When staged material has built up and been eyeballed, **merge the reviewed insights into `learning-hub/`
   and run the real `knowledge-rag` ingestion/embedding** so `Ask`, the scout, and the control-center get
   smarter. This is the "feed it into the AI / use it as knowledge" step — a reviewed merge, never an auto-dump.

Never print or commit `knowledge-rag/.env` or any key. The handoff file has the full standing checklist.

---

## 1. The hard rule: use the skills, don't wing it

There is a plugin in this repo, **`amazon-fba-oa/`**, containing 24 expert skills (`fba-*`). Each is a
`SKILL.md` instruction file under `amazon-fba-oa/skills/<name>/`. They share one rulebook in
`amazon-fba-oa/references/` (`oa-criteria.md`, `guardrails.md`, `stack-map.md`, `sourcing-methods.md`).

**Before doing a task that matches a skill below, open that skill's `SKILL.md` and follow it.** If the
plugin is installed (see §5) you can invoke skills natively; if not, just read the file directly — they
are plain markdown and work either way. Do not re-derive the project's rules from memory when a skill
already encodes them.

When a task spans several skills, use them in sequence (e.g. design → implement → review → test):
`fba-architect` → `fba-coder` → `fba-code-reviewer` / `fba-qa-tester`.

---

## 2. Which skill for which task (engineering)

| You are about to… | Use this skill first |
|---|---|
| Decide structure/approach, "should we build X this way", refactor, anything cross-cutting | `fba-architect` |
| Write or change Python (scout/scout_pro/knowledge-rag) or TS/Next.js (control-center) or SQL | `fba-coder` |
| Review a diff before it ships (read-only findings) | `fba-code-reviewer` |
| Diagnose a bug / error / "it worked yesterday" | `fba-debugger` |
| Design a table/schema, RLS, the vector search, a migration | `fba-database-expert` |
| Write/run tests, add a regression test | `fba-qa-tester` |
| Design or improve a control-center screen/component | `fba-designer` (pair with `ui-ux-pro-max`) |
| Catch up on project state / decode shorthand / "where are we" | `fba-context-keeper` |
| Get honest critique of a plan or design | `fba-feedback-giver` |
| Brainstorm what to build next / roadmap | `fba-innovator` |
| Analyze the operation's own numbers/outcomes | `fba-data-analyst` |
| Write the mandatory session journal entry | `fba-session-journal` |
| Change a buying threshold / brand list / any `ai-brain.json` value | `fba-brain-updater` |
| Add a transcript/doc to the knowledge base (RAG) | `fba-transcript-ingest` |
| Record a researched product lead into the trackers | `fba-lead-capture` |

The sourcing/analysis skills (`fba-deal-analyst`, `fba-keepa-analyst`, `fba-selleramp-analyst`,
`fba-chart-reader`, `fba-compliance-checker`, `fba-deal-calculator`, `fba-sourcing-scout`,
`fba-market-analyst`, `fba-listing-optimizer`) are the **business logic in human form**. When you write
code that automates any of that logic, open the matching skill and keep the code faithful to it.

---

## 3. How the skills FEED the systems (this is the part that matters)

The skills are not separate from the code — they are the spec the code implements, and several of them
write directly into the files the code reads:

- **`ai-brain.json` is the single source of truth.** `scout/config.py` loads the gates/guards from
  `learning-hub/data/ai-brain.json`; the control-center reads it too. **`fba-brain-updater`** is the only
  safe way to edit it. When you code scout scoring (`scout/scoring.py`), it must match
  `fba-deal-analyst` + `references/oa-criteria.md` — the scout is the *automated version of that skill's
  gates*. If they diverge, that's a bug.
- **The scout → `fba-deal-analyst` / `fba-keepa-analyst` / `fba-selleramp-analyst` / `fba-compliance-checker`.**
  Those skills define the buy/no-buy gates, the Keepa red flags, the SellerAmp math, and the
  allowed-vs-profitable split. Scout code (gates, scoring, features) should be written *from* them.
- **The control-center → `fba-designer` + `fba-deal-calculator` + `fba-context-keeper`.** The deal
  analyzer UI computes the same fee math as `fba-deal-calculator`; the dashboard's honest-status design
  comes from `fba-designer`; "what's live vs estimated vs disconnected" must stay truthful.
- **The knowledge RAG → `fba-transcript-ingest`.** New sources enter the corpus through that skill's
  pipeline (`knowledge-rag/`), keeping `documents.jsonl` / `chunks.jsonl` / `sources/manifest.json` and
  `insights.md` consistent and citable.
- **The trackers / future scout training → `fba-lead-capture`.** Real leads, decisions, and outcomes are
  captured into `learning-hub/tracking/` (and `leads.json`). These become the ground-truth labels the
  scout learns from. Until they exist, model-improvement claims are architectural, not proven
  (`fba-data-analyst` enforces that honesty).
- **Supabase → `fba-database-expert`.** Key separation (publishable read-only vs service-role) and RLS are
  the security boundary that must never break.

So the data flow is: **`fba-brain-updater` edits `ai-brain.json` → scout + control-center pick it up;
`fba-transcript-ingest` feeds the RAG → Ask; `fba-lead-capture` feeds the trackers → scout training.**
The engineering skills (`fba-architect`/`fba-coder`/etc.) are how you build and maintain all of it
without violating the rules below.

---

## 4. Non-negotiables (from `references/stack-map.md` + `guardrails.md`)

These have bitten the project before — every code change must respect them:

1. **No secrets in source or browser.** Keys live only in untracked `.env`. The browser may call only
   same-origin routes; never expose a service-role key to client JS.
2. **No ML target leakage.** Only pre-decision features train models; realized outcomes are labels.
   Never log the scout's own verdict as its success label (self-confirmation).
3. **Hard compliance/safety gates stay outside ML** (eligibility, IP, Amazon-Buy-Box rejects are rules).
4. **Single source of truth:** read thresholds from `ai-brain.json`; never hardcode a second copy.
5. **Honest status words:** implemented ≠ tested ≠ configured ≠ deployed ≠ planned. Honest empty states
   are correct; fabricated "live" data is a defect.
6. **No auto-buy / no money movement.** Code recommends and explains; humans approve purchases.

**Verification expectations:** Python — `pytest`/`unittest` + `py_compile`. control-center —
`npm run typecheck`, `npm run build`, `npm audit --audit-level=moderate` (target 0). Report what you
actually ran vs only intended to run, and log it in the journal.

---

## 5. How to make the skills available in Claude Code (one-time)

**Option A — install the plugin (native auto-invocation, no file duplication):**

```
# from the project root, inside Claude Code:
/plugin marketplace add ./amazon-fba-oa
/plugin install amazon-fba-oa@amazon-fba-oa
```

(CLI equivalents: `claude plugin marketplace add ./amazon-fba-oa` then `claude plugin install
amazon-fba-oa@amazon-fba-oa`.) After this, the `fba-*` skills load automatically when relevant.

**Option B — no install needed:** because this guide is loaded via `CLAUDE.md`, you already know the
skills exist and where they are. For any task in §2/§3, open `amazon-fba-oa/skills/<name>/SKILL.md` and
follow it. This always works, even without installing the plugin.

Either way, the skills' shared rulebook is `amazon-fba-oa/references/`.

---

## 6. What already exists (so you don't redo it)

- **`amazon-fba-oa/`** — the 24-skill plugin (sourcing/analysis, project rituals, engineering crew),
  built and validated; 5 skills (`fba-deal-analyst`, `fba-compliance-checker`, `fba-keepa-analyst`,
  `fba-selleramp-analyst`, `fba-sourcing-scout`) are eval-hardened. Installable package +
  test artifacts are in **`fba-skill-evals/`**.
- **`scout/`** — Python OA discovery + scoring/gates (loads `ai-brain.json`); 382 tests pass
  (`python run_all_tests.py` runs this + scout_pro + knowledge-rag together); live discovery
  needs a paid `KEEPA_KEY`.
- **`scout_pro/`** — advanced ML variant; SP-API/Ads are stubs; 36 tests pass (`test_gates_scoring.py` + `test_discord_config.py`).
- **`knowledge-rag/`** — zero-cost RAG (local `BAAI/bge-base-en-v1.5`, read-only Supabase); live
  corpus count changes with every research-pipeline run — check `ai-brain.json`'s
  `knowledge.ragCorpus` rather than trusting a number pinned here.
- **`control-center/`** — Next.js 15 operator dashboard; `app/api/knowledge-search` shells `ask.py`.
- **`learning-hub/`** — knowledge base + `data/ai-brain.json` (source of truth) + trackers (honest empty states).

Known drift to be aware of (see the journal): some README chunk-counts and bundled `control-center/hub-data/`
snapshots lag the live corpus — prefer live data and `ai-brain.json` over stale docs.

---

## 7. Folder map

```
Amazon FBA/
├── CLAUDE.md, AI_COLLABORATION_JOURNAL.md   (read first; journal every session)
├── CLAUDE_CODE_GUIDE.md                      (this file)
├── amazon-fba-oa/        skills/ (24 fba-*) + references/ (the rulebook) + .claude-plugin/
├── fba-skill-evals/      eval runs, review pages, scripts, installable .plugin
├── scout/  scout_pro/  knowledge-rag/  control-center/   (the systems you code)
└── learning-hub/         data/ai-brain.json, playbooks, tracking, transcripts
```

Keep new work inside `Amazon FBA/`. When in doubt about state or terminology, use `fba-context-keeper`.
