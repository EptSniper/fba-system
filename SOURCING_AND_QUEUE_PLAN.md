# The arbitrage-gap + review-queue plan — make the scout actually find *buyable* deals

**Author:** Cowork (fba-architect + fba-market-analyst + fba-designer + fba-debugger + the ML crew), 2026-07-13.
**Why:** the scout finds Amazon listings and *invents* a buy cost (flat 50% of the sell price). It never tells you **where to buy cheaper**, so no lead has a real ROI — which is also why the ML is training on fiction. This plan fixes the arbitrage gap, the wrong/mislabeled prices, the broken Review Queue, and reties the model to real costs. Every ai-brain / migration / gate change goes through the proper skill + Mehmet's approval. No auto-buy, no model promotion.

---

## 1. What's actually wrong (evidence, not opinion)

**A. There is no buy price. The whole ROI is manufactured.**
- Buy cost = `price × OA_COGS_FRACTION` (0.50), hard-coded — `scout/config.py:102`, `scout/scoring.py:245`. Keepa has no cost data, so the code assumes one and says so in its own comments.
- The `leads` table *has* `buy_cost`, `source_store`, `source_url` columns — but they are **null on every lead** (verified live: B0BQ3WJ12K, B006CSRBTC, B0D4FFJN7N all null). Nothing ever populates them.
- Every profit/ROI/priority number the operator sees traces back to the 50% assumption (`estimate_oa_profit_roi`, `triage_score`, and the backtest/shadow labels all call `assumed_landed_cost`).

**B. A real retail-source pipeline exists but is orphaned.**
- `scout/deals/` ingests real retailer feeds (Slickdeals, Woot, Best Buy, DealNews, clearance) with real `price_current`, `price_original`, `discount_pct`, `retailer`, `url` — `scout/deals/normalize.py`, `scout/deals/sources/*`.
- But it's used **only to derive brand "hints."** Its own footer admits it: `run_watch.py:214` → *"matching not yet built — these feed the scout as hints, not buys."*
- The bridge — `scout/deals/matcher.py` (deal→ASIN by UPC/EAN/title, "Prompt D2" in `DEAL_FINDER_BUILD_PLAN.md`) — **was never written.** Its tables (`deals`, `deal_matches`, migration `003_deals_and_matches.sql`) are marked **"NOT YET APPLIED."** No `upsert_deal_match` exists. So `deal_matches` is always empty — and the Review Queue's "deal-match verification" cards render against a table nothing populates.

**C. The prices on the card are wrong/mislabeled, and gates are leaking.**
- The lone `$…/u` on each card is **profit, unlabeled** (`review-queue.tsx:216`). "$57.65/u" is profit; the real sell price ($190.97) is fetched but never shown. That's why your online check never matched.
- Leads at **$80 and $191 with 57–64 offers** are in the queue despite the $8–60 price band and 25-offer cap — the same out-of-band leak found in the backtest. The live hard gates need an audit (fba-debugger).
- No price freshness: the only timestamp is `created_at`, and the card doesn't even show it — a days-old "current" price looks live.

**D. The Review Queue buttons *are* wired but feel dead, and the card is starved of info.**
- Approve/Reject/Watch open a **second reason-code step** (a bar pinned to the screen bottom); a single click records nothing, so it looks broken. A deployed instance missing `BASIC_AUTH_*` returns 503 on everything. No auto-refresh after a decision.
- The card shows only profit/ROI/BSR + a terse summary. It **omits** sell price, buy cost, monthly sales, offer count, Amazon-present, the ASIN link, image, freshness, and the LLM narrative/unknowns — all of which already exist in the data. Not enough to decide, exactly as you said.

**E. The ML consequence (ties to LEAKAGE_AUDIT_2026-07-13.md).** Because the cost is a fixed 50% assumption and the sampled prices are out-of-band, the backtest labels are ~91% "profitable" — an artifact, not skill. **Real buy prices are the fix for the model, not just the UI.** Keep `scoring.rankingChampion = rule` until labels are real.

---

## 2. The reframe

Amazon/Keepa data answers *"will it sell, and for how much?"* It can **never** answer *"where do I buy it cheaper?"* — that needs a retail source. Online arbitrage is **deal-first**: start from a real retailer price, match it to an Amazon ASIN, then check if the spread clears the gates. The scout today runs the other direction (Amazon-first) and fabricates the missing half. The plan adds the missing half and makes "no real source" an honest state, not a fake ROI.

---

## 3. The plan (phased, highest-value first)

### Phase 1 — Truth in the Review Queue (fast, no new data; fba-designer + fba-coder + fba-debugger)
Make the queue honest about what a lead is *today* before we add sourcing.
1. **Label every metric** and show the fields that already exist: **Sell price**, Profit, ROI (mark it "est. @50% cost" until real), BSR, **monthly sales**, **offer count**, **Amazon-present**, ASIN link, and a **price-as-of** timestamp. Stop showing an unlabeled profit number.
2. **Flag estimated vs real:** every ROI/profit derived from the assumed cost gets an explicit "ESTIMATED — no source yet" badge. This alone ends the "these numbers are wrong" problem.
3. **Fix the buttons:** make Approve/Reject one obvious action (reason picker inline, not pinned off-screen), add a loading state, auto-refresh the list after a decision, and set `BASIC_AUTH_*` so a deploy can't 503. (fba-debugger to confirm the deploy/write path; fba-code-reviewer before ship.)
4. **Gate audit:** find why $80–191 / 57-offer leads pass the $8–60 / 25-offer gates on the live path and fix it (same price-band family as the backtest bug).

### Phase 2 — The real buy price: build the deal→ASIN matcher (the core fix; fba-architect → fba-database-expert → fba-coder → fba-qa-tester)
This is what makes it an arbitrage tool.
1. **Apply migration 003** (`deals`, `deal_matches`) via fba-database-expert (with RLS correct).
2. **Build `scout/deals/matcher.py`** (the never-built D2): match a retail deal to an Amazon ASIN by UPC/EAN first (high confidence), then title+brand+pack-size with a confidence score; write `deal_matches` rows; low-confidence matches go to the existing "deal-match verification" queue for a human.
3. **On a verified match, populate the lead's real fields:** `buy_cost` = retailer `price_current` (+ shipping/prep), `source_store`, `source_url`. Then compute **real** profit / ROI / Max-Cost from the real spread — not the 50% assumption.
4. **Honesty rule:** a lead with no verified source is shown as *"Amazon-side only — no buy source found yet,"* never with a fabricated ROI. The assumed-cost estimate may still rank/triage, but it's labeled as such.

### Phase 3 — Retie the ML to real costs (ML crew; after Phase 2 produces real-cost rows)
1. Switch the backtest/shadow label from `profit>0 @ 50% cost` to the **real buy gate** (profit ≥ $3 AND ROI ≥ 30%) computed on real costs where available; keep assumed-cost rows as their own clearly-tagged weak tier.
2. Fix the dealfeed **$8–60 price-band filter** so collection matches the servable distribution (from LEAKAGE_AUDIT_2026-07-13.md).
3. Re-evaluate: positive rate, marginal-win %, AUC + bootstrap CI, time-held-out, per-brand/category slices — fba-ml-evaluator. Only then are importances trustworthy. `rankingChampion` stays `rule` until it earns promotion on real labels.

### Phase 4 — Broaden sourcing (later; fba-sourcing-scout + fba-market-analyst)
Reverse source lookup for Amazon-first ASINs (UPC → retailer/Google-Shopping search), more retailer feeds, cashback/coupon awareness. Only after the matcher + honest queue are solid.

---

## 4. Accuracy & overfitting guardrails (non-negotiable, carried throughout)
- **No fabricated confidence:** estimated ROI is labeled estimated; a lead with no source is not presented as buyable.
- **Real labels beat proxies:** once real costs exist, they outrank the 50%-assumption labels; don't blend tiers silently.
- **Leakage boundary unchanged:** only pre-decision features train the model; source price enters the *label*, never as a leaked feature.
- **Hard gates stay outside ML and must actually fire** (Phase 1.4 audit).
- **No auto-promotion, no auto-buy:** `rankingChampion` stays `rule`; every buy is human-approved with a real source in hand.

## 5. Sequencing for Claude Code
Phase 1 first (honest queue — days), then Phase 2 (matcher — the real unlock), then Phase 3 (ML retie), then Phase 4. Full directive in `CLAUDE_CODE_SOURCING_DIRECTIVE.md`. Architecture decisions (matcher design, schema) go through fba-architect/fba-database-expert before code; fba-code-reviewer + fba-qa-tester before ship; fba-session-journal at the end.
