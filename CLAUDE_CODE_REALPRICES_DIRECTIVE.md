# Claude Code directive — switch from the 50% assumption to REAL buy prices

Paste the block below into Claude Code. This is the "kill the 50% COGS fiction" build. It is a BUILD, not a config flip — grounded in the live data profile below. Guardrails: hard gates stay outside ML and MUST run on any deal-first lead; every buy stays human-approved; no model promotion (`rankingChampion` stays `rule`); respect the ~1,440/day Keepa bank (never let matching starve the collector); brain/migration changes via the proper skill + Mehmet's approval; `fba-code-reviewer` + `fba-qa-tester` before ship; `fba-session-journal` at the end.

## The live reality (measured 2026-07-13)
- `deals` = 9,798 real retailer prices+URLs, all `status='new'` (never matched).
- **0 have a UPC. 0 have a structured brand.** Title-only → the high-confidence UPC match path is unusable; every match is title-path → human review (no live LLM key).
- 4,702 are in the $8–60 band; ~1,069 are in-band AND ≥20% off (the priority subset).
- Matching ≈ 30 Keepa tokens/deal. Priority subset ≈ 32k tokens (~22 days in batches). Do NOT attempt the full 9,798.
- The matcher's `apply_verified_matches` only enriches the 62 EXISTING leads — it can't create a lead from a deal. So matched deals currently go nowhere.

## Build, in order

1. **Build D3 — deal-first, gate-checked lead creation (the core of the switch).** `fba-architect` designs; `fba-coder` implements. A verified deal↔ASIN match with NO existing lead must be able to become a NEW lead, but ONLY after passing the SAME hard gates the normal pipeline runs (eligibility/compliance/AVOID-brand, price band, offer-count, Amazon-share). The new lead's `buy_cost` = the real deal `price_current` minus the (clamped) discount stack, with `source_store`/`source_url` set, and profit/ROI computed from the REAL spread — never the 50% assumption. This is what actually flips the system to real prices. `fba-ml-guardian` confirms hard gates are enforced and can't be bypassed by a match.

2. **Match only the priority subset, in token-budgeted batches.** Filter `deals` to in-band ($8–60 after discount) AND meaningful discount first (~1,069 rows). Run `matcher.run()` in small batches (`--limit 20–30`) with a hard token guard so matching never drains the collector's daily bank — schedule it in the leftover budget after collection, or a capped nightly slice. Report matches/token and human-review yield per batch.

3. **Get UPCs — the single biggest match-quality lever.** With 0 UPCs, matching is weak and fully manual. Populate UPCs by: (a) wiring the Best Buy connector with a key (Best Buy feed carries UPCs), and/or (b) clearance-page JSON-LD / `gtin` parsing in the existing sources. A real UPC lets the matcher hit the ~0.95 auto-verified band and cut human load. `fba-coder`.

4. **Enable LLM verification safely.** Add a real `ANTHROPIC_API_KEY` (Haiku) so title-path matches can reach the LLM-confirmed band — but FIRST fix the disclosed auto-accept revert gap (a later human reject must revert the lead's applied buy_cost, and auto-applied matches must be excludable from the review queue). Do not turn on the key before that fix.

5. **Retie the ML once real-cost leads exist.** Only after 1–2 produce real-cost rows: change the training label from `profit>0 @ 50% cost` to the real buy gate (profit ≥ $3 AND ROI ≥ 30%) on real costs — or the cost-free **Max-Cost-for-30%-ROI** target (derivable from sell price + fees + weight, no cost assumption), with the real retail price compared at decision time. Then re-run the walk-forward harness (EXPERIMENT_WALKFORWARD_2026-07-13.md) and read lift@10% + per-category, not raw AUC. `fba-ml-*` crew; `rankingChampion` stays `rule` until it earns it.

6. **Config/UI honesty (finish Phase 1).** Any ROI still derived from the 50% assumption must be labeled "ESTIMATED — no source yet." A lead with a real matched source shows the real number + the retailer link; a lead without one never shows a fabricated ROI.

## Reality check to set expectations
With title-only deals, no UPC, and no LLM key, real prices arrive as a **trickle of human-verified matches**, not a bulk switch — until UPCs (step 3) and the LLM band (step 4) are on. The fastest visible win is D3 + running the priority subset so the first genuinely real-cost leads appear in the Review Queue. Do not promise a full switch before UPC/LLM land.
