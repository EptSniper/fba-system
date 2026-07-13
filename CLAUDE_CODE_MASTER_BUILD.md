# Master build order — finish the price-gap engine + make the ML honest (no seller account needed)

Paste the block below into Claude Code. This is the single ordered plan; the referenced files hold the detail. The mental model: the system is TWO engines (Amazon-side quality + the price gap) and a buy needs BOTH. Right now engine 1 exists but its ML label is fake, and engine 2 (the price gap) is only half-built. Finishing engine 2 the deal-first way is a double win — it's the gap finder AND it produces the real buy prices that make the ML honest. Guardrails: hard gates stay outside ML and MUST fire on any new lead; no auto-buy; no model promotion (`scoring.rankingChampion` stays `rule`); brain/migration changes via the proper skill + Mehmet approval; `fba-code-reviewer` + `fba-qa-tester` before ship; `fba-session-journal` at the end. Coordinate via `fba-ml-lead`.

Do these in order. Steps 1–3 need NO seller account and NO purchases.

**1. Make the backtest label honest (FREE, do first — this is why the model thinks everything wins).** Per DATA_STRATEGY_FOR_RELIABLE_ML.md + LEAKAGE_AUDIT_2026-07-13.md: (a) STOP discarding losers — keep price-crash / out-of-stock-at-horizon / seller-swarm windows as NEGATIVE examples; (b) change the label from `profit>0 @ 50% cost` to the real buy gate (**profit ≥ $3 AND ROI ≥ 30%**); (c) fix the $8–60 dealfeed price-band filter so the corpus matches the servable band. Then re-run the walk-forward experiment (EXPERIMENT_WALKFORWARD_2026-07-13.md) — expect the base rate to fall well below 85% and lift@10% to become meaningful. `fba-ml-data-engineer` + `fba-leakage-auditor` + `fba-ml-evaluator`.

**2. Turn on paper-trading (FREE — the truest no-buy labels).** Run the `shadow_outcomes` rechecks at +30/+60 days so the scout's picks get graded against what actually happened on Keepa. No money, no seller account. Confirm `outcomes`/shadow rows start maturing. `fba-ml-*`.

**3. Finish the deal-first price-gap engine (the core build).** Per CLAUDE_CODE_REALPRICES_DIRECTIVE.md:
   a. **Build D3** — a verified deal↔ASIN match with no existing lead becomes a NEW lead ONLY after passing the same hard gates (eligibility/compliance/AVOID-brand, price band, offers, Amazon-share); its `buy_cost` = real deal price (clamped discount stack), `source_store`/`source_url` set, real profit/ROI. `fba-architect` → `fba-coder` → `fba-qa-tester`; `fba-ml-guardian` verifies gates can't be bypassed.
   b. **Run the matcher on the priority subset** — the ~1,069 in-band ($8–60) + ≥20%-off deals, in small token-budgeted batches (`--limit 20–30`, hard token guard so it never starves the collector).
   c. Result: first real-cost leads in the Review Queue AND the first honest "bronze" real-label training rows.

**4. Wire SP-API as the free ASIN/eligibility layer (when Mehmet's SP-API creds land).** Per CLAUDE_CODE_SPAPI_DIRECTIVE.md — free title/UPC→ASIN + eligibility drops matching from ~30 to ~1–5 tokens/deal, so step 3b scales across all in-band deals cheaply.

**5. Retie the ML to the real-cost data + re-evaluate.** Once steps 2–3 have produced real-label rows: train on them (real cost / cost-free Max-Cost target), re-run walk-forward, read lift@10% + per-category + calibration. Shadow-only; promote only on consistent multi-fold lift over the champion; `rankingChampion` stays `rule`.

**6. Later (Amazon-first gap finder + scale).** Reverse ASIN→source lookup (for the scout's own Amazon-side picks, find a cheaper retail source), UPC enrichment of the deal feeds, more retailers. Only after 1–5 are solid.

## The definition of "done well"
Engine 1 (ML) is reliable when it beats "buy everything" by a real margin on the walk-forward held-out set AND a human gold set, is calibrated, has survived paper-trading, and abstains on unfamiliar products. Engine 2 is done when a real retail price and source URL sit on a lead and the profit/ROI are computed from that real spread, never the 50% assumption. A product is a BUY only when both engines agree, the hard gates pass, and a human approves.
