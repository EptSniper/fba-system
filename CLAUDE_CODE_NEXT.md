# Claude Code — next actions (post Session 64 review)

Paste the block below into Claude Code in the repo. Ordered by priority. Guardrails as always: no auto-buy, no model promotion (`scoring.rankingChampion` stays `rule`), brain/migration changes via the proper skill + Mehmet's approval, `fba-code-reviewer` + `fba-qa-tester` before ship, `fba-session-journal` at the end.

---

Context: Cowork reviewed Session 64 (Phases 1–2 of SOURCING_AND_QUEUE_PLAN.md) and applied one live DB change. Do these in order.

1. **Record the predictions-RLS change in the repo (hygiene).** Cowork already ran `ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;` live (it was the lone public table with RLS off — 652 rows exposed to the anon key; now service-role-only, matching every sibling). Add a tracked migration file under `scout/db/migrations/` capturing this so the repo schema matches prod. `fba-database-expert`.

2. **Dry-run the matcher — SMALL limit first (the actual next safe step).** `matcher.py --dry-run` is NOT token-free: it skips DB writes but still spends ~30 Keepa tokens/deal (term search + enrich 5 candidates). Run `python -m scout.deals.matcher --dry-run --limit 3` first, eyeball the candidate matches for false positives (especially pack/size traps), then step up only if clean. Do NOT run at the default `--limit 50` — that's ~1,500 tokens, the whole daily bank the collector needs. Report the matches + token spend before any real (non-dry) run writes to leads.

3. **Verify the Phase 1.4 gate leak is actually closed on the LIVE path.** Cowork found live leads at $80–$191 with 57–64 offers (B0BQ3WJ12K etc.) — outside the $8–60 price band and past the 25-offer cap. Confirm the hard gates now reject out-of-band / over-offer candidates on the production discovery path (not just in tests), and clean or re-gate the existing bad leads already sitting in `leads`/the Review Queue. `fba-debugger` to confirm, `fba-ml-guardian` to confirm gates stay outside ML.

4. **Queue (not urgent — do BEFORE enabling UPC/LLM, not after): fix the auto-accept revert gap.** Today nothing reaches the auto-accept band (no real UPC, placeholder LLM key), so this is latent. The moment a real `ANTHROPIC_API_KEY` or live UPC data lands, an auto-applied match (a) isn't excluded from the review queue and (b) if a human later rejects it, `apply_verified_matches` does not revert the lead's already-written `buy_cost`/`source_store`. Fix both as part of turning the LLM/UPC path on. `fba-architect` + `fba-coder`.

5. **Still pending from the throughput plan (needs Mehmet, then you):** if Mehmet approves `DISPATCHER_APPROVAL_NOTE.md`, install the reliable collector dispatcher (fixes token capture ~69%→~95%) and verify two full days with no >90-min gaps. Also the Action-B efficiency lever: add a pre-screen so `run_backtest` doesn't spend a history token on ASINs already in `backtest_rows` or too-new (<90d history) to yield a row (currently 26.1% 0-row waste). `fba-ml-data-engineer`.

6. **Optional, low priority:** two advisor WARNs — `match_chunks` is anon-EXECUTE via RPC (revoke the grant if Ask isn't meant to be public), and the `vector` extension sits in `public` (cosmetic). And clean the working-tree line-ending churn (`train-ranker.yml`, `CLAUDE.md`, `SKILLS_INDEX.md`, the fba-ml SKILL.md files show as modified — looks like OneDrive CRLF noise) before the next commit.

NOT yet: Phase 3 (retie ML labels to real costs) stays blocked until the matcher has run live and produced real-cost leads — correct, don't start it. Finish with a `fba-session-journal` entry.
