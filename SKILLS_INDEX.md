# SKILLS INDEX — check the team before you act

**Who this is for:** every AI working in this project — Cowork/Claude (desktop), the scheduled task
(`fba-daily-research`), and Claude Code (VS Code). Read it and follow the rule below.

## The governing rule

Before doing any non-trivial task, do this quick check:

1. **Does the action match the goal?** State (to yourself) what we're trying to accomplish, and confirm the
   step you're about to take actually serves it.
2. **Does a skill/agent cover it?** Scan the index below. If the task **matches or is even related** to a
   skill, **use that skill** — open `amazon-fba-oa/skills/<name>/SKILL.md` and follow it. Don't re-derive
   what a specialist already encodes.
3. **When several apply, chain them** (e.g. design → build → review → test). Only improvise when nothing in
   the index fits — and if you find yourself repeatedly improvising something, that's a signal to propose a
   new skill.

The skills live in the single-source plugin `amazon-fba-oa/` (installed in Cowork via Settings, and in
Claude Code via `/plugin marketplace add ./amazon-fba-oa` — or just read the `SKILL.md` files directly).
They share one rulebook: `amazon-fba-oa/references/` (`oa-criteria.md`, `guardrails.md`, `stack-map.md`,
`sourcing-methods.md`). If a reference and `learning-hub/data/ai-brain.json` disagree, `ai-brain.json` wins.

---

## The 35 skills — use when…

### Sourcing & product analysis (the business logic)

| Skill | Use when the task is… |
|---|---|
| `fba-deal-analyst` | judging a specific product to buy/pass (ASIN, numbers, screenshot) → BUY/NO-BUY/REVIEW |
| `fba-sourcing-scout` | finding products/leads to source today (storefront stalking, Keepa Finder, deal-first) |
| `fba-compliance-checker` | "am I allowed to sell it?" — gating, IP/brand risk, hazmat, meltable, eligibility |
| `fba-keepa-analyst` | reading Keepa data/history (BSR, price, offers, Buy Box, red flags) from numbers/text |
| `fba-selleramp-analyst` | SellerAmp settings or reading the SAS panel / Max Cost |
| `fba-chart-reader` | decoding a **screenshot/image** of a Keepa graph or SAS panel |
| `fba-market-analyst` | bigger-than-one-ASIN strategy: category/trend/seasonality/budget |
| `fba-deal-calculator` | exact ROI / fee / breakeven / max-cost math (runs a script) |
| `fba-listing-optimizer` | writing/optimizing an Amazon listing you control (title, bullets, A+, keywords) |

### Project rituals (maintain the system's data)

| Skill | Use when the task is… |
|---|---|
| `fba-session-journal` | writing the mandatory `AI_COLLABORATION_JOURNAL.md` session entry |
| `fba-brain-updater` | changing any value in `ai-brain.json` (thresholds, guards, brand lists) |
| `fba-transcript-ingest` | adding a transcript/doc to the knowledge base (distill → insights + RAG corpus) |
| `fba-lead-capture` | recording a researched product lead into the trackers |

### Engineering crew (build & maintain scout / RAG / control-center / Supabase)

| Skill | Use when the task is… |
|---|---|
| `fba-architect` | deciding structure/approach, "how should we build X", refactor, cross-cutting design |
| `fba-coder` | writing/changing code (Python scout/RAG or TS/Next.js control-center or SQL) |
| `fba-code-reviewer` | reviewing a diff before it ships (read-only findings) |
| `fba-debugger` | diagnosing a bug/error/"it worked yesterday" |
| `fba-database-expert` | Supabase/Postgres schema, RLS, vector search, migrations |
| `fba-designer` | designing/improving a control-center screen or component |
| `fba-context-keeper` | catching up on project state / decoding shorthand / "where are we" |
| `fba-feedback-giver` | honest critique of a plan/design/decision (non-code) |
| `fba-innovator` | generating ideas / roadmap / "what should we build next" |
| `fba-qa-tester` | writing/running tests, regression coverage |
| `fba-data-analyst` | analyzing the operation's own numbers/outcomes once real data exists |

### ML crew (the learning system — the ranker + item finder). MANDATE: every ML / command-center learning task routes through these — now and for all future builds/upgrades. Read `amazon-fba-oa/references/ml-doctrine.md`.

| Skill | Use when the task is… |
|---|---|
| `fba-ml-lead` | anything spanning >1 ML component, "is the ML healthy / going right", plan/coordinate the ML build — use FIRST |
| `fba-scout-strategist` | the item finder / what ASIN universe we sample, breadth, "are we only collecting certain brands", coverage |
| `fba-ml-data-engineer` | collection→dataset, the data lake, dedupe, stratification, `backtest_rows`, label tiers, class balance |
| `fba-feature-engineer` | designing/changing features, point-in-time snapshots, missing→NaN + stale flags, dead/constant features |
| `fba-ranker-architect` | the model itself — LightGBM/LambdaRank, groups, champion/challenger, serving/utilization, promotion gate |
| `fba-ml-trainer` | running/scheduling training, cadence, fingerprint, minimum-rows refuse, artifact registry/versioning |
| `fba-leakage-auditor` | checking for target/temporal/train-test leakage — **sign-off required before any promotion** |
| `fba-ml-evaluator` | "is the model actually accurate", metrics, calibration, offline-vs-online, bias slices, promotion evidence |
| `fba-ml-guardian` | ML safety/guardrails, shadow-vs-live, no-auto-promote/buy, rollback/kill-switch — **final safety gate** |
| `fba-ml-debugger` | ML pipeline broken/stuck/"too good"/silent bug (corpus not growing, trainer skips, model unused, telemetry off) |
| `fba-ml-ops` | the unattended automation layer — GitHub Actions schedules/dispatch/concurrency, cross-run Supabase Storage state (cursors/fingerprints/artifacts), token-budget partitioning, CI dependency pins, "the cron didn't fire" |

---

## Common chains

- **Evaluate a product:** `fba-chart-reader` (if image) → `fba-keepa-analyst` + `fba-selleramp-analyst` +
  `fba-deal-calculator` → `fba-compliance-checker` → `fba-deal-analyst` (verdict) → `fba-lead-capture`.
- **Build a feature:** `fba-context-keeper` → `fba-architect` → `fba-coder` → `fba-code-reviewer` /
  `fba-qa-tester` → `fba-session-journal`.
- **Ingest research (daily task / Claude Code):** `fba-transcript-ingest` for every new transcript/doc;
  `fba-brain-updater` if a finding should change a buying threshold.
- **Any ML / learning work (data, features, ranker, training, serving):** `fba-ml-lead` plans →
  `fba-scout-strategist` / `fba-ml-data-engineer` / `fba-feature-engineer` / `fba-ranker-architect` /
  `fba-ml-trainer` implement → `fba-leakage-auditor` + `fba-ml-evaluator` + `fba-ml-guardian` **sign off
  before any promotion or ship** → `fba-ml-debugger` when something's wrong. This chain is mandatory.

## Non-negotiables that always apply (from `references/guardrails.md` + `references/ml-doctrine.md`)

Separate "am I allowed?" from "can it profit?"; humans approve purchases (no auto-buy/money movement);
no secrets in source/browser/outputs; honest status words (implemented ≠ tested ≠ deployed); single source of
truth in `ai-brain.json`; cite sources. **For ML specifically:** collect as much and as varied data as possible
(brand-agnostic, category-diverse — no friendly-brand skew); no leakage (pre-decision features only, missing=NaN,
point-in-time); hard gates stay outside ML; the model only ranks (never buys); shadow-by-default and no
auto-promotion (a human flips `scoring.rankingChampion`). These hold regardless of which skill is in use, for
every current component and every future build/upgrade.
