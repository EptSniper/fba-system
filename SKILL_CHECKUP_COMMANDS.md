# Skill checkup commands — run these in Claude Code (plugin installed)

One line per skill (35). Each tells that expert to audit its domain end-to-end against the LIVE system,
find bugs/gaps/risks, tell you exactly what to do next and what to upgrade, and confirm everything works as
it should. Paste them one at a time (each is its own task). Guardrails always hold: no auto-buy, no
auto-promote, no secrets printed, hard gates stay outside ML.

## Sourcing & product analysis
/amazon-fba-oa:fba-deal-analyst - Re-run the buy/no-buy gates on our latest candidates and the review-queue backlog, confirm the thresholds still match ai-brain.json, flag any deal that would wrongly pass or fail, and tell me what to fix or upgrade next.
/amazon-fba-oa:fba-sourcing-scout - Audit today's sourcing coverage, tell me which stores/brands/categories to hit next for breadth, surface any stale or stuck lead sources, and what to upgrade.
/amazon-fba-oa:fba-compliance-checker - Sweep our brand lists and recent leads for eligibility/IP/hazmat/gating risk (incl. 2026 rule changes), flag anything unsafe, and tell me what to verify next.
/amazon-fba-oa:fba-keepa-analyst - Check how we read Keepa across the pipeline (BSR→sales, offer trends, cliffs), find any misread or stale logic, and recommend upgrades.
/amazon-fba-oa:fba-selleramp-analyst - Verify our SellerAmp settings and Max-Cost logic match reality and the 2026 fees, flag any miscalculation, and tell me what to tune.
/amazon-fba-oa:fba-chart-reader - Confirm the Keepa/SellerAmp screenshot decoding is accurate on a real image, flag anything it misreads, and what to improve.
/amazon-fba-oa:fba-market-analyst - Review our category/brand strategy and seasonality, tell me which markets to lean into or drop next, and flag stale assumptions.
/amazon-fba-oa:fba-deal-calculator - Re-verify the fee/ROI/breakeven math against the current 2026 fee schedule + fuel surcharge, find any wrong constant, and tell me what to update.
/amazon-fba-oa:fba-listing-optimizer - Check whether listing work even applies to us (OA on listings we don't control); if so what to improve, otherwise report the honest no-op and where it WOULD help.

## Project rituals
/amazon-fba-oa:fba-session-journal - Audit AI_COLLABORATION_JOURNAL.md for gaps, missing session entries, and honesty-word slips, then write or queue whatever is missing.
/amazon-fba-oa:fba-brain-updater - Validate ai-brain.json is well-formed and in sync with scout/config.py and the control-center, list pending proposals to approve, and what to update next.
/amazon-fba-oa:fba-transcript-ingest - Check the RAG corpus/ingest pipeline for drift (local vs Supabase counts), stuck transcripts, and tell me what to re-ingest or fix.
/amazon-fba-oa:fba-lead-capture - Verify the lead trackers and leads.json are consistent and the Review-Queue→decisions path works, flag the zero-decisions gap, and what to do next.

## Engineering crew
/amazon-fba-oa:fba-architect - Review the overall system structure (scout/scout_pro/RAG/control-center/Supabase) for architectural risk and drift, and tell me what to refactor or build next.
/amazon-fba-oa:fba-coder - Do a pass over recent changes, fix any small bugs you find, and tell me the next implementation work — verify what you actually ran.
/amazon-fba-oa:fba-code-reviewer - Review the latest diffs/commits for the project's failure modes (secrets in browser, ML leakage, hard-gate erosion, stale snapshots) and list blockers vs nits.
/amazon-fba-oa:fba-debugger - Hunt for anything broken, stuck, or silently failing right now (collector, trainer, CI, dashboards, Discord) and root-cause it with the minimal fix.
/amazon-fba-oa:fba-database-expert - Audit the Supabase schema/migrations/RLS and key separation, list any unapplied migrations, and tell me what to fix or optimize.
/amazon-fba-oa:fba-designer - Review the control-center UX for clarity, honest connected/estimated/empty/error states, and accessibility, and tell me what to improve.
/amazon-fba-oa:fba-context-keeper - Catch me up on the true current project state from the journal + live tables, decode any drift/shorthand, and surface the next safe step.
/amazon-fba-oa:fba-feedback-giver - Poke holes in our current plan/roadmap, tell me what's risky or missing, and the single highest-leverage change.
/amazon-fba-oa:fba-innovator - Propose the next upgrades/features ranked by value-vs-effort, tied to where the project actually is, with the cheapest validating experiment for each.
/amazon-fba-oa:fba-qa-tester - Check test coverage on the risk areas (scoring gates, retrieval, the knowledge route, leakage), add/run the missing tests, and tell me what's under-tested.
/amazon-fba-oa:fba-data-analyst - Analyze our real numbers (runs, backtest_rows, shadow_outcomes, decisions, leads) honestly, tell me what they do and do NOT support, and what to collect next.

## ML crew (learning system)
/amazon-fba-oa:fba-ml-lead - Run a full ML health read from the live tables, give me a working/broken/starved verdict + the single highest-leverage next step, and coordinate the crew to fix it.
/amazon-fba-oa:fba-scout-strategist - Check the corpus breadth/concentration now vs the targets, tell me which categories/brands to widen next, and confirm the rotation cursor is actually advancing.
/amazon-fba-oa:fba-ml-data-engineer - Audit the collection→dataset pipeline for starvation/duplication/schema drift, confirm the caps + stratification work, and tell me what to fix.
/amazon-fba-oa:fba-feature-engineer - Review the feature set for dead/constant features, missing-data handling (NaN + stale flags), and drift, and recommend features to add or fix.
/amazon-fba-oa:fba-ranker-architect - Review the ranker design and serving/promotion path, confirm the trained model is actually loaded and used, and what to upgrade (toward LGBMRanker when the data supports it).
/amazon-fba-oa:fba-ml-trainer - Verify training actually runs on new data (not silently skipping), the fingerprint/refuse logic is correct, and every artifact is versioned and reproducible.
/amazon-fba-oa:fba-leakage-auditor - Re-audit the whole feature/label pipeline for target/temporal/train-test leakage, run the poisoned-future test, add regression tests, and sign off or BLOCK.
/amazon-fba-oa:fba-ml-evaluator - Evaluate the current challenger honestly (time-held-out, bootstrap CI, per-brand/category slices), tell me if it's truly promote-worthy yet or still noise, and what to measure next.
/amazon-fba-oa:fba-ml-guardian - Verify the guardrails hold (hard gates outside ML, shadow-by-default, no auto-promote/buy, one-flip rollback + kill switch, drift alarms) and flag any risk before anything ships or promotes.
/amazon-fba-oa:fba-ml-debugger - Find any silent ML failure (stuck backtest_rows, skipping trainer, unused model artifact, telemetry reading None) and root-cause it with a regression guard.
/amazon-fba-oa:fba-ml-ops - Audit the ML ops/infra (training cadence, GitHub Actions runners, persisted cursors, monitoring/Discord alarms, artifact storage) and tell me what's flaky and what to harden.
