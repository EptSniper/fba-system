# THIS WEEK — the no-keys build queue

**Updated:** 2026-07-04 (after journal Sessions 32–38 landed) · One Claude Code session per line, in order. Everything works WITHOUT the Keepa/Anthropic keys. When the keys arrive, delete this file — HUMAN_TODO.md takes over.

## Already done (Claude Code Sessions 32–40 — faster than this file could be written)

- [x] R2 — consistency fixes (S32)
- [x] R3 — control-center bug fixes (S33)
- [x] CC1 — live Supabase read layer + Review Queue cockpit (S34, reviewed in S35)
- [x] CC2 — Morning Brief + capital/safety cockpit + proposals page (S36, upgraded S37 with human-confirmed apply flow)
- [x] Knowledge exam — 56-case bank + exam.py + anti-sycophancy scaffold + prediction-ledger scaffold; baseline 56/56 with documented divergences kept honest (S38)
- [x] **W1** — warm knowledge server (`knowledge-rag/server.py`): Ask went from ~1.1s cold to
      ~350-650ms warm (this machine's model was already disk-cached — the gap is larger on a
      fresh machine/model download); `ask.py`'s CLI and the control-center's knowledge-search
      route both try it first and fall back honestly (`latency_source: server|subprocess|cache`
      recorded in every response). Loopback-only, 26 new tests. (S40)
- [x] **W2** — dress rehearsal: Slickdeals collection now runs live every cycle (200 real deals
      collected in first live pull); `run_daily.py --dry-run-live` honestly skips Keepa
      discovery (`status="skipped"`, never `"failed"`) while running everything else for real;
      "FBA Scout Daily" registered in Task Scheduler for real (07:30 daily, `StartWhenAvailable`
      set via XML registration, not left as a manual GUI step); git pre-commit hook (secrets
      scan + fast tests) live-verified to actually block a fake secret and pass clean content.
      Live-verified 2 full `--dry-run-live` cycles end to end (real runs rows, real digest
      posts, no tracebacks) — the second one after fixing a Windows-console mojibake bug the
      first one surfaced. (S40)

## Remaining queue — GO-LIVE ON THE PRO TRICKLE (updated 2026-07-05)

Done since last update: T1+T2+T3 built and live-verified (Sessions 43–44); KEEPA_KEY provisioned
(Session 45) — but it's the **Keepa Pro trickle: 1 token/min, 60 bank** (confirmed in-account), not an API
plan. Decision: stay on Pro for now. Budget split (from the Session-46-era analysis): ~600/day scan,
~80/day shadow rechecks, ~700/day backtest — full first training corpus achievable on Pro in ~5 weeks.

- [ ] **★ TOP ML PRIORITY (added 2026-07-09) — DE-BIAS THE TRAINING CORPUS.** Paste **`ML_DEBIAS_PLAN.md`**
      (it has a ready Claude Code prompt). The live corpus is skewed — **toys 82.5%, Crocs+Jellycat ~30%** —
      so the ranker isn't worth training until coverage widens. Route through the ML crew:
      `fba-ml-lead` → `fba-scout-strategist` + `fba-ml-data-engineer` → `fba-ml-evaluator` +
      `fba-leakage-auditor`. First read `amazon-fba-oa/references/ml-doctrine.md` and propagate the ML mandate
      into the plan docs per **`CLAUDE_CODE_ML_DIRECTIVE.md`** (§0.5 of CLAUDE_CODE_GUIDE is now permanent).
      Every ML / command-center task, now and future, uses the fba-ml crew.

- [ ] **1. GL1** — go live on the trickle (prompt below — paste this FIRST). STILL PENDING (Mehmet's switch):
      V0/V1/V2 are built + tested but no data flows until this run goes live on real Keepa. Also apply
      migrations **009 (shadow_outcomes) + 010 (backtest_rows)** when going live.
- [x] **2. V0** — raw data lake (recorder + idle harvester; harvester disabled-on-Pro) — BUILT + TESTED
      (Claude Code Session 48). Archiving ON by default in code, live-off with data until GL1. → `DATA_ENGINE_PLAN.md`
- [x] **3. V1** — retrieval eval + shadow-outcome tracker — BUILT + TESTED (Session 49). Retrieval eval RAN:
      bge 0.683 recall@5 vs BM25 0.561 (report in learning-hub/evals/). Shadow tracker + labels gold/silver
      tiers done; migration 009 written, NOT applied. → `DATA_ENGINE_PLAN.md`
- [x] **4. V2** — backtest engine (on-policy sampling, leakage boundary, budget guard, resume) — BUILT +
      TESTED (Session 50). Leakage tests are the deliverable; migration 010 written, NOT applied. → `DATA_ENGINE_PLAN.md`
- [ ] **5. M4** — D2 matcher + D3 wiring + golden-path e2e test (Anthropic calls mocked until the key exists) → `DEAL_FINDER_BUILD_PLAN.md` + `MASTERY_PLAN.md`
- [ ] **6. M1** — ingest the 35-video watchlist + chart-example articles → `MASTERY_PLAN.md`
- [ ] **7. CC3** — security hardening + weekly backups (backups redirect into the lake per V0) → `CONTROL_CENTER_UPGRADE_PLAN.md`
- [ ] **8. M3** — exemplar bank, mock-tested → `MASTERY_PLAN.md`
- [ ] **9. V3** — LightGBM ranker: train once V1/V2 rows exist (~week 5-6) → `DATA_ENGINE_PLAN.md`
- [ ] (gated) CC4 + M2-live wait on the Anthropic key + eval.

**Mehmet's items:** leave the PC on overnight (the drip needs it); get ANTHROPIC_API_KEY (~$5 — unlocks the
analyst, matcher verification, reflection: the whole judgment layer); daily Review-Queue verdicts (every one
is a training label); upgrade Keepa to the 20/min API tier when the digest's "scan truncated — token budget"
line gets annoying.

## Prompt GL1 — go live on the Pro trickle

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first (Session 45:
KEEPA_KEY is real). Use amazon-fba-oa:fba-coder. CONTEXT THAT OVERRIDES OLDER ASSUMPTIONS:
Keepa access is the PRO TRICKLE — 1 token/minute, 60-token bank, confirmed in-account —
not an API plan. Mehmet is staying on Pro deliberately. Configure for it:

1. Token budgeting via fba-brain-updater: learning.tokenBudget block { dailyScanTokens:
   600, shadowRecheckTokens: 80, backtestTokens: 700, source: "Pro-trickle split,
   Session 46 analysis" }. keepa_client already reads real refill/tokensLeft telemetry —
   make the pipeline plan batch sizes from OBSERVED refill rate, never assumed tier.
2. First live verification (cheap, ~100 tokens): one run_daily.py --dry-run with real
   Keepa — verify every CONFIRM-flagged assumption in code comments against real
   responses (record actual token costs for stats/buybox/Product Finder in the code
   comments + telemetry), spot-check avg90 BSR gating and triage ordering on real data.
3. Then go live small: hint-led scan capped at dailyScanTokens (~200 ASINs at 3
   tokens), dripping with wait=True — reconfigure the Task Scheduler task to start the
   run at 22:00 so it drips overnight while the PC is on, replacing --dry-run-live with
   the real run (verify StartWhenAvailable survived). The digest must state: actual
   refill rate observed, tokens spent vs budget, and "scan truncated — token budget"
   honestly whenever the cap bites.
4. Harvester/breadth features stay OFF (Pro can't feed them) — mark them
   blocked-on-upgrade in config with an honest log line, not silently absent.
5. Report the first real scan's numbers: ASINs scanned, gate survivors, hints followed,
   tokens consumed, per-call costs observed. Full test suite green. Journal entry. Do
   NOT print the key.
```

---

## Prompt W1 — warm knowledge server (kills the 8-second Ask, powers everything after)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to confirm the shape (a small local FastAPI service is the
project's long-planned "persistent warm embedding worker" — see the Codex Session 04
limitation note), then amazon-fba-oa:fba-coder.

Problem: every Ask query and every future embedding consumer (deal matcher title path,
M3 exemplar index) pays the full BAAI/bge-base-en-v1.5 model load per call because
knowledge-rag/ask.py runs as a cold subprocess (~seconds each time).

1. knowledge-rag/server.py: local FastAPI app (uvicorn, 127.0.0.1 only, port from env
   KNOWLEDGE_SERVER_PORT default 8787) that loads the bge model ONCE and exposes:
   POST /embed {texts[]} -> vectors; POST /ask {question, limit} -> the exact same
   cited-matches JSON ask.py produces today (reuse ask.py's logic as a module import,
   don't fork it); GET /health -> model loaded, corpus counts, uptime.
2. ask.py stays working standalone (CLI unchanged) but gains server detection: if the
   local server responds on /health, delegate to it (fast path); else current cold run.
   Zero behavior change for callers.
3. control-center/app/api/knowledge-search/route.ts: try the local server first
   (http://127.0.0.1:8787, 3s timeout), fall back to the existing subprocess path.
   Latency source recorded in the response (server|subprocess) — honest data flow.
4. A Windows-friendly way to keep it running: scripts + README section (schtasks ONSTART
   or start-server.bat), plus graceful "server not running" behavior everywhere.
5. Security: bind 127.0.0.1 ONLY; assert loopback bind in a test.
6. Tests: /embed and /ask against fixtures, fallback path when server absent, loopback
   assertion. Full suite green. Journal entry with before/after Ask latency measured.
```

## Prompt W2 — dress rehearsal: the system starts running daily NOW, honestly

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder. Goal: everything that CAN run daily without Keepa/Anthropic
starts running daily now, so key-day is a switch-flip, not a launch.

1. Slickdeals collection goes LIVE daily: deals collection needs no key and migration
   003 is applied — verify/complete its wiring into run_daily.py so real deals
   accumulate in the Supabase deals table all week. The digest's retail-deals line
   reports "N deals collected, matching not yet built" honestly. Best Buy source stays
   key-gated with its honest skip.
2. Register the daily run on Windows Task Scheduler FOR REAL (schtasks command from
   scout/README.md, 07:30 daily, "run when missed" enabled) in a new --dry-run-live
   mode: "no Keepa (skip discovery honestly), but DO run deals collection, DO write the
   runs row, DO send the digest, DO ping the heartbeat if configured." This exercises
   Supabase writes, the Discord router, proposals, drift checks, and runs telemetry
   end-to-end every morning — a real digest in #daily-digest starting tomorrow.
3. Git pre-commit hook (.git/hooks/pre-commit + a tracked scripts/pre-commit.py):
   (a) run the fast test files (scoring + db idempotency + router — under 30s),
   (b) a secrets scan on staged files (redact.py's patterns: JWT prefixes, webhook
   URLs, env-secret values), (c) block the commit with a clear message on failure.
   Document --no-verify bypass for emergencies.
4. Requirements/env hygiene: everything the daily run imports must be in
   requirements.txt and importable on this machine's Python (mcp_server's 3.10+
   dependency must stay isolated from run_daily's import chain).
5. Live-verify one full --dry-run-live cycle now: real Slickdeals pull, runs row
   written, ONE digest embed to Discord (authorized — it's the system's normal daily
   digest), no tracebacks. Full test suite green. Journal entry with the run summary.
```
