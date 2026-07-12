# FBA Product Scout (that learns)

A small, runnable Python project that finds candidate Amazon products through the
**Keepa API** (sanctioned data — we never scrape Amazon), scores them against the
research criteria, posts the winners to **Discord**, logs everything to SQLite, and
**improves as you label which picks actually performed.**

> **Honesty up front.** This does not promise profits and it is not autonomous magic.
> With zero labels it runs on a transparent rule score. It only gets "smarter" when
> *you* feed it honest outcomes (see [The learning loop](#the-learning-loop-how-always-learning-actually-works)).
> A **paid Keepa key** is required for any real run. You must be **18+** to sell on Amazon.

---

## What's in here

| File | Role |
|---|---|
| `config.py` | Loads `.env`: credentials + all tunable thresholds. |
| `keepa_client.py` | Wraps the `keepa` package: `find_candidates`, `enrich`, `seller_catalog_signals`, `seller_asins`. Import-guarded. |
| `scoring.py` | Transparent rule score (0–100) + reason string + `risk_flags` + 2026 fee/margin estimate. **No ML.** |
| `model.py` | Optional scikit-learn layer: `predict_proba`, `train`, `blended_score`. Falls back to the rule score when untrained. |
| `storage.py` | SQLite: `candidates`, `picks`, `outcomes`. Dedupes by ASIN. |
| `db.py` | Optional Supabase business memory for evaluated leads, decisions, and realized outcomes. |
| `competitors.py` | Ranks a competitor's ASINs (or a seller's catalog) by Keepa velocity proxies → seed ideas. |
| `discord_router.py` | Multi-channel Discord routing — one webhook per notification stream. See its own section below. |
| `discord_notify.py` | Builds + posts scout-pick embeds via the router's "scout_picks" stream. |
| `smoke_test_discord.py` | LIVE script: posts one test message to every channel + reports real HTTP status. |
| `pipeline.py` | Orchestrates: (retrain) → find → enrich → score → filter → dedupe → post → log. |
| `run_scout.py` | CLI: `--once`, or `--loop --interval <min>`. |
| `train.py` | CLI: add an outcome label, and/or retrain the model. |
| `spapi.py` | SP-API wiring: Listings Restrictions (eligibility), Product Fees, Catalog Items. No-ops honestly without real credentials. |
| `deals/` | The Deal Finder — a second discovery source (retail feeds → matched ASIN → the same rater). See its own section below. |
| `search_log.py` | The brand-growth loop: due-date tracking for saved brand searches. See "Scout agent" section below. |
| `ops_report.py` | Weekly ops KPIs (sell-through, turns estimate, realized-vs-estimated ROI gap) from Supabase outcomes. |
| `analyst.py` | LLM second-opinion pass over gate-survivors (needs `ANTHROPIC_API_KEY`). See "Scout agent" section below. |
| `reflect.py` | Weekly brand-memory reflection; `memory_report.py` measures whether it helps. |
| `mcp_server.py` | Read-only MCP server over the scout's Supabase brain (Python 3.10+ only). See "Scout agent" section below. |
| `run_all_tests.py` | Discovers and runs every test file across `scout/`, `scout_pro/`, and `knowledge-rag/`, prints one aggregate pass/fail line. Requires `pytest`. |
| `requirements.txt`, `.env.example` | Dependencies and config template. |

**Tests, all of them:** `python run_all_tests.py` from this directory runs scout's + scout_pro's +
knowledge-rag's full suites in one shot (427 tests total as of 2026-07-04: 382 scout, 36
scout_pro, 9 knowledge-rag) and prints one aggregate line. Individual sections below also list
their own narrower `pytest` invocations for faster iteration on one area.

---

## Setup

```bash
cd scout
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env          # then edit .env
```

Fill in `.env`:

- **`KEEPA_KEY`** — your **paid** Keepa subscription key (Premium ~$19+/mo unlocks
  sales-rank data, Product Finder, and API). Get it at <https://keepa.com/#!api>.
  *This is required — the scout cannot pull data without it.*
- **`DISCORD_WEBHOOK_URL`** — Discord → *Server Settings → Integrations → Webhooks →
  New Webhook → Copy URL*. No bot token needed. *Optional:* without it the scout still
  finds, scores, and logs picks — it just won't post them.
- **`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`** — optional server-side business
  memory. When set, each real run records every evaluated candidate, including hard
  rejects and below-threshold passes. Keep the service-role key only in `.env`; never
  expose it in browser code. Dry runs do not write to Supabase.
- Thresholds (`PRICE_MIN`, `MIN_MONTHLY_SALES`, `MAX_REVIEWS`, …) and the margin
  assumptions (`COGS_FRACTION`, `PPC_FRACTION`, …) are all optional overrides.

### Run it

```bash
python run_scout.py --once --dry-run     # find + score + PRINT picks, post nothing
python run_scout.py --once               # find + score + POST top picks to Discord
python run_scout.py --loop --interval 360  # every 6 hours
```

Seed ideas from a competitor's catalog (velocity proxies only):

```bash
python competitors.py B0XXXXXXX1,B0XXXXXXX2     # by ASIN list
python competitors.py seller:A1B2C3D4E5F6G7     # by Keepa seller ID
```

---

## How scoring works (transparent first, model second)

1. **Rule score (always on).** `scoring.py` awards points for each criterion — price
   in $15–$50, est. monthly sales ≥ ~200 (from Keepa *Sales Rank Drops*), beatable
   review count, rating ≤ ~4.3, low weight, uncrowded offers, and a rough **net-margin
   estimate after 2026 Amazon fees** (referral + fulfillment + 3.5% fuel surcharge,
   minus your assumed COGS/PPC). It returns the score, the margin, and a human-readable
   reason — plus `risk_flags()` (offer crowding, review moat, stockout history, etc.).
2. **Model probability (optional).** Once trained, `model.py` predicts P(good pick) and
   `blended_score` mixes it with the rule score (`MODEL_BLEND_WEIGHT`). **No trained
   model → `predict_proba` returns `None` → the rule score is used unchanged.**

> The fee/margin numbers are **estimates** based on weight only. Always confirm a real
> SKU in Amazon's Revenue Calculator before committing money — actual fees depend on
> dimensions and size tier, not just weight.

### Online-Arbitrage mode (default: `SCOUT_MODE=OA`)

The scout now defaults to **OA mode**, scoring the way our research says to
(see `../learning-hub/playbooks/sourcing-playbook.md`). Instead of private-label
"weak incumbent" signals, OA mode scores each candidate on:

- **BSR ≤ 200,000** (sells fast enough) and **≥ ~50 sales/mo** (Keepa "yellow line").
- **Seller-count band** — at least a few sellers (so it's a real OA listing, not
  private-label/wholesale) but not a crowded price war.
- **ROI ≥ 30%** and **≥ $3 profit/unit** (estimated; buy cost assumed at
  `OA_COGS_FRACTION` of the sell price — **confirm the real ROI in SellerAmp**).
- **Buy Box** — a **hard reject** if Amazon holds the Buy Box (you can't compete).
- **Brand knowledge (`brands.py`)** — the search is **seeded toward known-good OA brands** (the videos'
  Keepa Product Finder method), **hard-gated/IP-risky brands** (Nike, Adidas, Jordan…) are **hard-rejected**,
  and known-good brands get a small score nudge. Seeded from
  `../learning-hub/playbooks/brands-and-sources.md` — keep the two in sync as the mentor/transcripts teach more.
- **Criteria + learned guards from the brain** — the OA thresholds (BSR, ROI, profit, offers, price band)
  *and* the red-flag guards load from `../learning-hub/data/ai-brain.json` (**single source** — update it, the
  rater updates). The rater now automatically detects three "the price is about to tank / you can't win"
  traps from Keepa stats:
  - **Price spike** — current price far above its 90-day average (likely to revert). Penalized + flagged.
  - **Rising offers** — new-offer count far above its 90-day average (a seller pile-in). Penalized + flagged.
  - **Amazon Buy-Box rotation** — Amazon's Buy-Box *win share* over the period (not just the current holder):
    **hard-reject** at ≥ `OA_AMAZON_SHARE_MAX` (default 20%), penalize + flag below that.

It still can't see gating/IP eligibility from these Keepa stats, so every Discord alert
reminds you to verify that by hand.

**Tune it in `.env`:** `SCOUT_MODE`, `OA_BSR_MAX`, `OA_MIN_SALES`, `OA_MIN_OFFERS`,
`OA_MAX_OFFERS`, `OA_MIN_ROI`, `OA_MIN_PROFIT`, `OA_PRICE_MIN/MAX`, `OA_COGS_FRACTION`,
`OA_PRICE_SPIKE_RATIO`, `OA_OFFERS_RISE_RATIO`, `OA_AMAZON_SHARE_MAX`,
`SCOUT_USE_BRAND_SEEDS` (0 to search broadly), `BRAND_SEED_LIMIT`.
Set `SCOUT_MODE=PL` to use the old private-label scorer.
(The guard thresholds also load from the brain's `guards` block — `.env` is just an override.)

**Tests:** `python tests/test_scoring.py` (no dependencies) or `python -m pytest tests/test_scoring.py` —
28 tests locking the profit/ROI math, the OA scorer, the hard gates, the brand logic, and the
price-spike / offers-rising / Amazon-Buy-Box-share guards. Run the WHOLE scout suite with
`python -m pytest tests/`, or every project's suite at once (scout + scout_pro + knowledge-rag)
with `python run_all_tests.py` from this directory — see "Tests, all of them" below.

**Confirmed + still open (from the processed transcripts):** the criteria above match what the courses teach,
and the offer-count-trend and Buy-Box-rotation upgrades the videos imply are now **implemented**
(offers-rising guard + Amazon Buy-Box share guard). One upgrade still needs an external integration:
an **ungating-eligibility check** — only surface what your account can actually sell (needs SP-API or a
Boxem-style checker; not visible from Keepa alone). A full **IP-complaint "cliff"** detector would also benefit
from Keepa *history* (the scout currently pulls current stats only). See `../learning-hub/playbooks/` for the
full criteria the scout is based on.

> **To actually search + post to Discord you still need:** a paid **`KEEPA_KEY`** and a
> **`DISCORD_WEBHOOK_URL`** in `.env`. Without them the scout can't pull data or post.

---

## The learning loop (how "always learning" actually works)

There is no autonomous magic — the scout improves through a **labeled feedback loop**:

1. Each run **logs its picks** to the local `picks` table (deduped by ASIN, so a
   product is never re-sent). If Supabase is configured, every evaluated lead is also
   written to the business database as `review` or `pass`; the scout never marks its
   own recommendation as a human-approved buy.
2. Later, you learn how a pick actually did and **record an honest label** — a row in
   `outcomes` (1 = good, 0 = bad):

   ```bash
   python train.py --label B0XXXXXXXX --good --notes "sold ~300/mo, held 30% margin"
   python train.py --label B0YYYYYYYY --bad  --notes "fees ate margin, returns high"
   python train.py --status            # see how many labels you have / picks awaiting a label
   ```

3. On the next run (or by running `python train.py`), the pipeline **retrains
   `model.py` on the accumulated labels**, so scoring shifts toward the features that
   correlated with *your* real winners.
4. With **zero labels**, it runs purely on the transparent rule score. With
   **more honest labels → a better model.** That's the whole deal: it learns your
   business, not generic theory.

A retrain needs at least `MIN_LABELS_TO_TRAIN` labels (default 20) with **both** good
and bad examples present; below that it stays on the rule score and tells you so.

### Deeper learning-loop pieces (System Blueprint Prompt 3.1 + G5)

Beyond the rule-score retrain above, three more scripts close the loop as real leads/decisions/
outcomes accumulate — all diagnostic, none of them auto-apply anything:

- **`python labels.py`** — assembles a leakage-safe training table from linked leads →
  decisions → outcomes (Supabase + the local `learning-hub/data/events.jsonl` ledger). Refuses
  to say "ready" below `ai-brain.json`'s `learning.minLabeledRows` (default 30) or with only one
  outcome class present.
- **`python calibration_report.py`** — appends a dated block to
  `learning-hub/tracking/calibration-report.md`: sample size, class balance, and (only once
  there's enough data) a diagnostic calibration fit. Explicitly states "NOT enough data to
  promote" until real numbers clear the bar — it never silently promotes a model.
- **`python tuning_report.py`** — appends to `learning-hub/tracking/threshold-tuning-report.md`:
  win/loss rates per named gate/adjustment from the scout's own explain-why output, flagging
  only genuinely lopsided patterns (≥4 samples, ≥75% loss rate) as **suggestions for you to
  review** — it never edits `ai-brain.json` itself.
- **`python propose_updates.py`** — runs automatically at the end of every `run_daily.py` cycle
  (System Blueprint Prompt G5). Appends dated, evidence-cited proposals to
  `learning-hub/tracking/brain-proposals.md` — outcome-driven (realized win/loss patterns,
  reported honestly even at n=1-3 as "too small to act"), data-driven (dead/toothless gates,
  brands repeatedly IP-cliff-flagged, Keepa token-cost drift), and knowledge-driven (a
  best-effort pointer to a fresh knowledge-base check, never auto-diffed against the brain —
  free-text answers are too unreliable to trust without a human reading them). **The daily
  Discord digest shows "N new brain proposals pending" whenever any exist.**

**Applying a proposal is always a separate, human-initiated step.** Read
`learning-hub/tracking/brain-proposals.md`, then tell Claude (any session) "apply proposal
&lt;describe it&gt;" — the `fba-brain-updater` skill makes the edit with provenance, bumps
`updated`, re-syncs `control-center/hub-data/`, and you should mark the proposal applied in the
file with today's date. No script in this repo has a write path to `ai-brain.json` except a
human-directed `fba-brain-updater` edit.

---

## Scheduling `run_daily.py` (System Blueprint Prompt G2)

`run_daily.py` is the single daily entry point: it orchestrates `pipeline.run_once()` (which
does the drip-scan → gate → enrich → score → idempotent Supabase upsert), checks for
brain drift between `learning-hub/data/ai-brain.json` and the bundled
`control-center/hub-data/ai-brain.json`, posts ONE batched Discord digest embed, and pings a
free [healthchecks.io](https://healthchecks.io) heartbeat on success or its `/fail` endpoint on
failure — a webhook alone can't tell you a machine never woke up; the heartbeat closes that gap.

```
python run_daily.py               # real run — needs KEEPA_KEY in .env
python run_daily.py --dry-run      # no external writes/posts, prints the summary
python run_daily.py --dry-run-live # THIS_WEEK.md Prompt W2 — no KEEPA_KEY yet? Keepa discovery
                                    # is honestly SKIPPED (status="skipped", never "failed"),
                                    # but deals collection, the runs row, the digest, and the
                                    # heartbeat all still run for real. Drop this flag once
                                    # KEEPA_KEY is configured (HUMAN_TODO.md item 2).
```

Set `HEALTHCHECK_URL` in `.env` (optional; the heartbeat step no-ops honestly without it) to a
check URL from your free healthchecks.io account.

**Windows Task Scheduler** — registered for real (2026-07-04, THIS_WEEK.md Prompt W2), task
name `"FBA Scout Daily"`, daily 07:30, running `run_daily.py --dry-run-live` (see the note
above about dropping that flag once a Keepa key exists). Registered via an XML definition
(`schtasks /Create /XML ...`) specifically so **"Run task as soon as possible after a scheduled
start is missed"** (`StartWhenAvailable`) could be set programmatically instead of left as a
manual GUI checkbox — verify it's still set with:
```
schtasks /Query /TN "FBA Scout Daily" /XML | findstr StartWhenAvailable
```
A from-scratch equivalent (e.g. on a new machine) via the plain CLI form (note this variant
does NOT set `StartWhenAvailable` — you'd still need the GUI checkbox afterward, Task
Scheduler → the task's Properties → **Settings** tab):
```
schtasks /Create /TN "FBA Scout Daily" /TR "python C:\path\to\scout\run_daily.py --dry-run-live" ^
  /SC DAILY /ST 07:30 /RL LIMITED /F
```
Without "run when missed" enabled, a sleeping/off PC silently skips the whole day — the
healthchecks heartbeat is your backstop for exactly that failure mode.

**Keepa collector dispatch fallback** — GitHub's scheduled workflow is best-effort and has
live-observed multi-hour gaps. The tracked dispatcher asks GitHub to run the existing
`keepa-collect.yml` workflow every 45 minutes, but only when no run is active and the latest run
is at least 40 minutes old. It embeds no credentials; `gh` uses the operator's existing login,
and the workflow's `concurrency` group serializes local dispatches with cloud cron runs.

```powershell
# Run from the repository root. Validate without dispatching or registering anything.
.\scripts\dispatch_keepa_collect.ps1 -MinimumGapMinutes 5 -DryRun
.\scripts\install_keepa_dispatch_task.ps1 -WhatIf

# Install/replace the real StartWhenAvailable task
.\scripts\install_keepa_dispatch_task.ps1

# Remove it cleanly
.\scripts\install_keepa_dispatch_task.ps1 -Remove
```

The task is named `FBA Keepa Collector Dispatch`, repeats every 45 minutes while Windows is
running, ignores overlapping local launches, and uses the GitHub cron as the always-on fallback
when the PC is sleeping/off. Its cadence and quiet-gap guard come directly from
`learning.sampling.corpusAcceleration.targetDispatchMinutes` and
`minimumDispatchGapMinutes`; re-run the installer after changing either brain value.

**Cron** (for a future ~$5/mo VPS, once the machine needs to stay always-on):

```
0 7 * * * cd /path/to/scout && /usr/bin/python3 run_daily.py >> run_daily.log 2>&1
```

---

## Git pre-commit guard (THIS_WEEK.md Prompt W2)

Every `git commit` runs `scripts/pre-commit.py` (via the `.git/hooks/pre-commit` stub git
actually invokes — hooks aren't tracked/synced by git itself, so the real logic lives in the
tracked script instead):

1. **Secrets scan** of every staged file's INDEX content (what's actually about to be
   committed) — reuses `redact.py`'s own patterns directly: real env-secret values (skipping
   template placeholders like `<FILL_ME>`), `key=`/`token=`/`secret=` query params, Discord
   webhook URLs, and JWT-shaped strings (Supabase keys).
2. **Fast tests** — `test_scoring.py` + `test_db_idempotency.py` + `test_discord_router.py`
   (~1s total).

Either failure blocks the commit with a clear message (never prints the actual secret value).
**Emergency bypass:** `git commit --no-verify` skips both checks — if you ever use it, run
`python scripts/pre-commit.py` manually right after and fix anything it flags; a skipped check
should never become a silently-never-checked one.

---

## Top-100 deal watch (`deals/run_watch.py`, TOP100_DEAL_WATCH_PLAN.md)

A SECOND, standalone job (separate from the scout's `run_daily.py`) that watches the 100 ranked
OA deal sources in `learning-hub/data/top100-sources.json` and writes two things to Supabase:
real `deals` rows, and brand-anchored `deal_hints` the scout reads as its FIRST discovery pass
("look where the deals are showing up"). It never edits `ai-brain.json` or the scout's config —
hints are DATA, not rules. AVOID-listed brands (Nike/adidas/Disney) are enforced twice as
signal-only: they can appear in the digest, but never become a hint or a buy.

```
python -m deals.run_watch             # real run: collect -> upsert deals -> derive+upsert hints -> #retail-deals digest
python -m deals.run_watch --dry-run   # collect + derive only; NO Supabase writes, NO Discord post
```

Needs only `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DISCORD_WEBHOOK_RETAIL_DEALS` (+ optional
`WOOT_API_KEY`, `BESTBUY_API_KEY`, `HEALTHCHECK_URL_DEALWATCH`) — no Keepa, no Anthropic. Tier
scheduling + concurrent per-store feeds keep a full run comfortably under 5 minutes.

**Where it runs:** the intended home is the FREE GitHub Actions cloud runner at 9 PM ET
(`.github/workflows/deal-watch.yml`; one-time repo/secrets setup is HUMAN_TODO.md §3e). Until
that's set up — and as a permanent fallback — it runs locally via Task Scheduler exactly like
the scout (a "FBA Deal Watch" task is registered). The two jobs share one brain through
Supabase and never need each other online.

---

## Discord notification routing (`discord_router.py`)

Every notification stream gets its own Discord channel webhook instead of one shared channel:

| Stream | Env var | Posted by |
|---|---|---|
| `daily_digest` | `DISCORD_WEBHOOK_DAILY_DIGEST` | `run_daily.py`'s one-per-cycle digest |
| `scout_picks` | `DISCORD_WEBHOOK_SCOUT_PICKS` | `pipeline.py` via `discord_notify.post_picks()` |
| `retail_deals` | `DISCORD_WEBHOOK_RETAIL_DEALS` | `deals/collect.py`'s per-source stats |
| `brain_proposals` | `DISCORD_WEBHOOK_BRAIN_PROPOSALS` | `propose_updates.py` (count + top finding only) |
| `system_health` | `DISCORD_WEBHOOK_SYSTEM_HEALTH` | `run_daily.py` — run failures, brain drift, low Keepa tokens |
| `review_queue` | `DISCORD_WEBHOOK_REVIEW_QUEUE` | stub — no caller yet (S1 disagreements / Deal Finder D2 gray-zone matches) |
| `outcomes` | `DISCORD_WEBHOOK_OUTCOMES` | stub — no caller yet (Phase 3) |

Resolution order per stream: its own env var → `DISCORD_WEBHOOK_FALLBACK` → an honest logged
skip (never crashes a run, never fakes a successful send). One retry on HTTP 429, honoring
Discord's `Retry-After`; multiple embeds batch into as few messages as Discord's 10-embeds-
per-message limit allows. The daily digest keeps a one-line cross-channel summary (e.g. "picks
→ #scout-picks (3), proposals → #brain-proposals (2)") so it remains the single place that
proves the whole run happened, even though those items now also post to their own channels.

`discord_notify.py`'s `post_pick(product, webhook_url=...)` still accepts an explicit webhook
URL as a legacy/manual override that bypasses stream resolution entirely.

**Verify the wiring:** `python smoke_test_discord.py` — a LIVE script (not part of the test
suite) that posts one labeled test message directly to each of the 7 channels + the fallback
and reports the real HTTP status per channel (expect `HTTP 204` on success). Run it after
rotating any webhook or adding a new stream.

**Tests:** `python tests/test_discord_router.py tests/test_discord_notify.py` — routing
resolution, the 429-retry-once behavior, batching, and (in `test_run_daily.py`/
`test_propose_updates.py`/`test_deals_collect.py`) each caller's wiring. Every test mocks
`discord_router`'s transport — never assume a bare `patch.object(module, "post_digest")` (or
similar) is enough; a real webhook lives in `.env` and a test that forgets to mock the actual
send call WILL post a live message (this bit the project once during development — see
`test_run_daily.py`'s module docstring).

## Deal Finder (Deal Finder Build Plan, Prompt D1)

A **second discovery source** feeding the same rater: retail sale/clearance feeds instead of
Keepa. `scout/deals/`:

| File | Role |
|---|---|
| `normalize.py` | Regex attribute extractor (`brand`, `core_title`, `pack_count`, `size_value`, `size_unit`) — defuses the #1 documented OA matching failure (retail 1-pack matched to an Amazon 2-pack) before any comparison happens. Has a pluggable `llm_fallback` hook for the long tail regex can't parse; unused until the matcher (Prompt D2) wires one in. |
| `brain_config.py` | Reads `ai-brain.json`'s `dealFinder` block (sources, confidence bands, price-sanity ratio, the manual discount-stack table) — single source, same convention as `config.py`. |
| `sources/slickdeals.py` | Official Slickdeals RSS feeds. No API key needed. Crowd-visible, so margins compress fast on anything front-paged. |
| `sources/bestbuy.py` | Best Buy Products API — the only major US big-box with a free, open developer API (`onSale=true`, UPCs included). Needs `BESTBUY_API_KEY` (see `.env.example`); honestly no-ops without one. |
| `collect.py` | Runs every enabled source, upserts results via `db.upsert_deal()` (idempotent on retailer+sku+price+day — migration 003 is applied to the live Supabase project as of 2026-07-03). |

```bash
python -c "from deals import collect; print(collect.collect_all(dry_run=True))"
```

**Status (2026-07-03):** D1 only — sources + storage; migration 003 applied and idempotency
verified live. **Not yet built:** the AI matcher
(deal → candidate ASIN, Prompt D2, needs `ANTHROPIC_API_KEY` + `KEEPA_KEY`), the
`run_daily.py`/control-center wiring (Prompt D3), and Tier-2 affiliate sources — Impact.com,
Walmart.io (Prompt D4, needs affiliate approvals). See
`../learning-hub/ai-system/deal-sourcing-system.md` for the original design and the
"Deal Finder Build Plan" doc for the full D1–D4 sequence.

**Tests:** `python -m pytest tests/test_deals_*.py` — normalizer (multipack/size traps),
both source connectors (mocked network), `db.upsert_deal`, and the `collect.py` orchestrator.

---

## Scout agent (Scout Agent Build Plan, Prompts S1–S4)

A layer of operational doctrine + operator tooling on top of the rule-based rater — deterministic
code still computes every number and enforces every gate; nothing here can move a gate, change a
verdict, or write to `ai-brain.json`.

**S2 — operational doctrine (implemented, key-free):**
- `scoring.triage_score()` ranks gate-survivors by expected payback SPEED at a STRESSED
  (competed-down) price (`operations.triage` in `ai-brain.json`) — a SORT key only, wired into
  `pipeline.run_once()`'s winners ordering; the score THRESHOLD (pass/fail) is unchanged.
- A softer `price-caution` adjustment (1.15–1.5x the 90-day average, `guards.currentVsAvg90PriceCaution`)
  fires alongside the existing 1.5x `price-spike` hard flag, mutually exclusive with it.
- The BSR gate now prefers the 90-day AVERAGE sales rank when Keepa provides one (`avg_sales_rank_90`),
  falling back to the current value — `explain_oa()`'s `bsr` gate records which was used (`source`).
- `search_log.py` + `scout/db/migrations/004_search_log.sql` (NOT APPLIED): the brand-growth loop —
  every human-approved BUY decision (`db.log_decision(..., brand=...)`) queues that brand for a
  periodic Product Finder re-run; `run_daily.py`'s digest surfaces "N searches due." Execution stays
  Keepa-gated and manual.
- `ops_report.py`: weekly (Mondays, via `run_daily.py`) KPI report — sell-through, a turns estimate,
  and the realized-vs-estimated ROI gap — computed honestly from Supabase outcomes, with
  "not computable yet" / "NOT TRACKABLE" stated plainly where the data doesn't exist (e.g.
  profit-per-review-hour has no logging source anywhere in this repo).

**S1 — LLM analyst pass (implemented, needs `ANTHROPIC_API_KEY`):**
`analyst.py` gives each hard-gate survivor a second, qualitative opinion via Claude — never a
decider. Anti-sycophancy by construction: `build_input()` shows the model gates/adjustments/raw
metrics but DELIBERATELY EXCLUDES the composite score/verdict (finance-LLM research documents
models tend to agree with whatever score they're shown), and a system-prompt rule says
"if it's not in the input, you don't know it — no background knowledge about this brand."
A deterministic post-validator (`_post_validate`) then drops any risk claim citing an
`evidence_fields` value that isn't actually a key in the input (the documented tabular-
hallucination failure mode) — enforced by a real check, not by asking nicely. Wired into
`pipeline.run_once()` as a no-op pass-through when `analyst.configured()` is False (no key set);
the note is merged into the existing `explanation` JSONB (zero schema change) and
`disagrees_with_rules` is tallied into `summary["analyst_disagreements"]`, surfaced in the
Discord digest — track it over time: if it never disagrees, the prompt is decorative and needs
tuning. **NOT verified against a live API call** — no `ANTHROPIC_API_KEY` exists in this repo
yet; the request shape is built from the installed `anthropic` SDK's real signature and tested
against a mocked client.

**S3 — brand memory + weekly reflection (implemented, needs `ANTHROPIC_API_KEY`):**
`reflect.py` runs weekly (Mondays, via `run_daily.py`): finds brands with a new decision,
outcome, or analyst disagreement in the last 7 days, and for each one calls Claude to
regenerate `learning-hub/memory/brands/<slug>.md` — merging in real lessons, pruning stale
entries, capped at ~60 lines (never just appended to forever — stale-memory poisoning is a
documented failure mode). A post-validator rejects any update mentioning an ASIN not present
in the brand's real rows. `pipeline._run_analyst_pass()` feeds the current note into
`analyst.py`'s input for that brand and records `memory_used: bool` on the analyst note.
`memory_report.py` is the honest A/B measurement harness (Prompt S3 sec 4) — it compares the
analyst's disagreement-to-bad-outcome hit rate between the with-memory and without-memory
groups, and says "not enough data yet" until both groups clear 15 real samples; it never
assumes memory helps just because the code exists. **NOT verified against a live API call**
(no `ANTHROPIC_API_KEY` exists in this repo yet).

**S4 — read-only MCP server (implemented, key-free, needs Python 3.10+):**
`mcp_server.py` exposes `get_lead`, `top_leads`, `why_rejected`, `brand_history`, `run_stats`,
`search_log_due` as MCP tools over the scout's own Supabase data — so "why did the scout pass on
this?" is a conversation in Claude Desktop/Code instead of a SQL session. **Read-only by
construction**, enforced by an AST-based test that the module only ever calls an allowlisted set
of read functions on `db`. Requires `pip install mcp` on a **Python 3.10+** interpreter (this
repo's dev environment is 3.9, where that install fails — a real package constraint, verified,
not a bug; the query functions themselves are fully tested against a mocked `db` regardless).

Register it:

```jsonc
// claude_desktop_config.json
{ "mcpServers": { "fba-scout": { "command": "python", "args": ["C:/path/to/scout/mcp_server.py"] } } }

// .mcp.json (project root, Claude Code)
{ "mcpServers": { "fba-scout": { "command": "python", "args": ["scout/mcp_server.py"] } } }
```

It inherits the same `.env` (service-role Supabase access) as the rest of the scout — treat it as
sensitive, never expose it beyond localhost.

**Tests:** `python -m pytest tests/test_scout_agent_s2.py tests/test_mcp_server.py
tests/test_analyst.py tests/test_reflect_and_memory.py` — or, if pytest isn't installed
(`pip install pytest`), most individual files also run standalone via
`python tests/test_X.py`. `run_all_tests.py` (below) requires pytest.

---

## Raw data lake (`datalake.py`, DATA_ENGINE_PLAN.md V0)

Every EXTERNAL response the scout receives is archived RAW at the boundary — Keepa
product/finder/seller responses, the deal sources' RSS/API bodies, low-confidence or changed
clearance HTML, the analyst's exact input+output, and each run summary. This is the regenerable
ground truth: features, scores and verdicts live only in Supabase and can always be rebuilt from
the lake, so nothing derivable is ever stored twice.

- **Where:** `DATA_LAKE_DIR` (default `C:\fba-data-lake`, deliberately **OUTSIDE** the
  OneDrive-synced project — a multi-GB lake inside OneDrive would sync-thrash your cloud and
  disk; `datalake.py` prints a loud warning if you point it back inside the project).
- **Format:** append-only, zstd-compressed Parquet (`DATALAKE_ZSTD_LEVEL`, default 12),
  Hive-partitioned `<source>/date=YYYY-MM-DD/part-*.parquet`, one file per source per run.
- **Dedupe:** a sqlite manifest keyed `(source, entity_id, endpoint)` skips re-storing an
  identical payload (its `last_seen` just bumps); a changed payload appends. Re-pulling the same
  ASIN next week costs nothing on disk if it hasn't moved.
- **Never breaks the pipeline:** archiving is best-effort and self-isolating — a lake failure is
  counted in `datalake.telemetry()['failures']` and swallowed, never propagated into a scout run.
  With `pyarrow` absent, archiving cleanly no-ops.
- **Disabled under test:** `DATALAKE_ENABLED=0` (set by `tests/conftest.py`) so the suite never
  touches the real lake; it's ON by default in production.
- **Ops:** the daily digest carries a `🗄️ Data lake` line (`lake: +N rows, +X MB, total Y GB,
  dedupe Z%`); Mondays run a read-back checksum integrity check that raises a `system_health`
  alert on any mismatch/unreadable file.

### Backup story (honest)

**The lake on local disk is a SINGLE copy.** zstd Parquet + the sqlite manifest are durable
against process crashes, but not against a dead drive. As the corpus grows into real training
data (V1 shadow labels, V2 backtest rows), copy `DATA_LAKE_DIR` to a second location:

- simplest: a scheduled `robocopy C:\fba-data-lake E:\fba-data-lake-backup /MIR` to an external
  drive (weekly is plenty — the lake is append-mostly);
- or a cloud object bucket (`rclone sync` to Backblaze B2 / S3) if you want off-site.

This is a **HUMAN_TODO** — the code cannot provision your backup target. CC3's weekly Supabase
backup will land INTO the lake (`<root>/supabase_backup/date=.../`), so backing up the lake dir
also backs up the database export — one backup target, not two.

## Data & compliance notes

- **No Amazon scraping.** Keepa is a sanctioned, licensed data layer. For your *own*
  store data, the right tool is Amazon's **SP-API** (see extension points below).
- **Keepa field names / Product Finder params are Keepa-specific and change over time.**
  The query in `keepa_client.find_candidates` is a sensible starting set — confirm the
  exact keys for your version with `help(api.product_finder)` or by building the filter
  in Keepa's website Product Finder and clicking **"SHOW API QUERY"** (it prints the
  exact JSON). Keepa expects **prices in cents** and **rating ×10** (4.3★ → 43).
- **Competitor data is proxies, not secrets.** Exact private sales for another seller
  are not available anywhere legitimate. `competitors.py` ranks on **velocity proxies**
  (Sales Rank Drops, Buy Box stability, out-of-stock %) — treat output as directional.
- **Keepa tokens are metered** (seller queries especially). Schedule sensibly and cache;
  don't hammer the API in a tight loop.

---

## Honest limitations & v2 extension points

**This project intentionally implements the core loop and stops there.** The larger
blueprint (Next.js dashboard, Postgres + pgvector, SP-API, Customer Feedback API,
Discord bot with `/approve` `/why`) is a natural v2. Clean places to extend:

- **SP-API** (`AMAZON_SP_API_*` creds): pull your own listings, orders, and Search
  Query Performance to add demand/conversion features and real outcome labels (realized
  ROI, returns, stockouts) instead of manual labels.
- **Customer Feedback API:** add review/return-topic intensity as features (the
  "fixable complaint" signal) — the strongest demand-gap input.
- **Discord bot + Gateway:** turn one-way webhook alerts into `/approve`, `/reject`,
  `/watch`, `/why` so labeling happens in chat and feeds `outcomes` directly.
- **Champion/challenger + drift checks:** version models, evaluate offline before
  promoting, and keep an audit trail (never let the model self-modify code).

See `../04_limitations.md` for the project-wide "what this does NOT do" notes.
