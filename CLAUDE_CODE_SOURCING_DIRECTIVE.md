# Claude Code directive — sourcing gap + review-queue rebuild

Paste the block below into Claude Code in the Amazon FBA repo. Read `SOURCING_AND_QUEUE_PLAN.md` and `LEAKAGE_AUDIT_2026-07-13.md` first — they're the spec and the evidence. Route through the crew per the CLAUDE.md mandate. Do the phases in order; each ships behind fba-code-reviewer + fba-qa-tester. Guardrails: no auto-buy, no model promotion (`scoring.rankingChampion` stays `rule`), every ai-brain/migration change via the proper skill + Mehmet's approval, journal at the end.

---

Read `SOURCING_AND_QUEUE_PLAN.md` and `LEAKAGE_AUDIT_2026-07-13.md`. The core problem: the scout invents the buy cost (flat 50% of Amazon price), never sources a real retail buy price, so no lead has a real ROI and the ML trains on a fiction. A real retail deal pipeline (`scout/deals/`) exists but dead-ends into brand hints because the deal→ASIN matcher ("Prompt D2", `scout/deals/matcher.py`) was never built and migration `003_deals_and_matches.sql` was never applied. Fix it in phases. Coordinate with `fba-ml-lead`; use `fba-architect` for structure, `fba-database-expert` for schema/RLS, `fba-designer` for UX, `fba-coder` to implement, `fba-debugger` to root-cause, `fba-code-reviewer` + `fba-qa-tester` before every ship.

**Phase 1 — make the Review Queue honest (do first, no new data).**
1. `fba-debugger`: confirm the Approve/Reject/Watch write path end-to-end (`components/review-queue.tsx` → `/api/ops/decide` → `decisions` table). The two-step reason-code bar (pinned `bottom-0`) makes a single click look inert; set `BASIC_AUTH_*` so a deploy can't 503. Report the real failure mode before changing UI.
2. `fba-designer` + `fba-coder`: rebuild the lead card to show, LABELED: Sell price, Profit, ROI (badge "ESTIMATED @50% cost — no source yet"), BSR, monthly sales, offer count, Amazon-present, an ASIN link, and a price-as-of timestamp. Stop rendering an unlabeled profit number as if it were a price. Make Approve/Reject one obvious action with an inline reason picker, a loading state, and an auto-refresh after each decision (wire the unused `/api/ops/queue` route).
3. `fba-debugger`: find why leads at $80–$191 with 57–64 offers pass the $8–60 price band and 25-offer cap on the LIVE path (verified live: B0BQ3WJ12K sell $190.97 / 57 offers is queued). Same price-band family as the backtest bug. Fix so hard gates actually fire; `fba-ml-guardian` confirms gates stay outside ML.

**Phase 2 — build the real buy price (the core unlock).**
1. `fba-architect`: design the deal→ASIN matcher against the existing `scout/deals/` pipeline and migration 003. `fba-database-expert`: apply `003_deals_and_matches.sql` (deals, deal_matches) with correct RLS.
2. `fba-coder`: build `scout/deals/matcher.py` — match a retail deal to an Amazon ASIN by UPC/EAN first, then title+brand+pack-size with a confidence score; write `deal_matches` rows (`upsert_deal_match` in `db.py`); route low-confidence matches to the existing deal-match verification queue. `fba-qa-tester`: tests for the match cascade and the pack-size trap.
3. On a verified match, populate the lead's real `buy_cost` (= retailer `price_current` + shipping + prep), `source_store`, `source_url`, and compute REAL profit/ROI/Max-Cost from the real spread. A lead with no verified source shows "Amazon-side only — no buy source yet," never a fabricated ROI.

**Phase 3 — retie the ML to real costs (after Phase 2 produces real-cost rows).**
1. `fba-coder` + `fba-ml-data-engineer`: change the backtest/shadow label from `profit>0 @ 50% cost` to the real buy gate (profit ≥ $3 AND ROI ≥ 30%) on real costs where available; keep assumed-cost rows as a separate clearly-tagged weak tier — never blended silently.
2. Fix the dealfeed `currentRange` ($8–60) secondary-axis filter so collection matches the servable distribution (LEAKAGE_AUDIT_2026-07-13.md). `fba-leakage-auditor` re-checks no leakage (source price enters the LABEL only, never as a feature).
3. `fba-ml-evaluator`: re-slice positive rate, marginal-win %, AUC + bootstrap CI, time-held-out, per-brand/category. `rankingChampion` stays `rule` until it earns promotion on real labels.

**Phase 4 — broaden sourcing (later):** reverse source lookup for Amazon-first ASINs (UPC → retailer/Google-Shopping), more retailer feeds, cashback/coupon awareness. Only after Phases 1–2 are solid.

Do not auto-promote the ranker or auto-buy anything. Where a change needs a brain edit or a migration, propose it via the proper skill and wait for Mehmet. Finish with a `fba-session-journal` entry: implemented vs tested vs configured vs deployed vs planned, plus the exact next safe step.
