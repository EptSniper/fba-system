# Getting the data for a buy-grade ML — without buying anything

**Author:** Cowork (fba-ml-lead + fba-ml-data-engineer + fba-scout-strategist), 2026-07-13.
**Goal:** enough data that the model is trustworthy enough to source from — with no seller account and no purchases yet.

## The one principle
Reliability = **honest + varied + validated** labels, not raw volume. Our current 10,936 rows are near-useless because the label is fake (50% cost, losers deleted). **500 real win/loss examples beat 10,000 fake ones.** So maximize *real labeled examples across the products you'd actually buy* — not row count.

## What "useful data" means — the label ladder
From weakest to strongest. Reliability comes from climbing it, not from piling up the bottom rung.
- **(avoid) fake backtest** — profit>0 at a made-up 50% cost, losers censored. This is what we have. Thinks everything wins.
- **weak/rule labels** — historical products auto-labeled by expert doctrine (our knowledge corpus rules). Cheap, high-volume, real-ish signal.
- **bronze — honest backtest** — real retail buy price (from the 9,798 deals) + real Keepa outcome 60 days later, losers KEPT. Real win/loss, large volume, no purchase.
- **silver — paper-traded** — the system predicts today, then watches via Keepa for 60 days; reality grades it. The truest no-buy label.
- **gold — realized** — you actually bought and sold. NOT required to get reliable; it's the final polish, later.

## No-buy data sources, in priority order

1. **Fix the label on the data we already have (free, do first).** Stop deleting losers — keep price-crash / out-of-stock / seller-swarm windows as NEGATIVE examples. Switch the target from "profit>0 @ 50%" to the real buy gate (**profit ≥ $3 AND ROI ≥ 30%**) and fix the $8–60 price band. This alone turns the 10,936 rows from a yes-machine into honest-ish win/loss data, with zero tokens and zero purchases.

2. **Turn on paper-trading (silver — the truest no-buy labels).** Let the scout pick candidates now and re-check them on Keepa at +30/+60 days (the `shadow_outcomes` scaffold already exists — 178 rows, needs to mature and the rechecks to run). Every pick becomes a graded outcome: "it said hold+sell, did it?" Out-of-sample, forward in time, no money. This is what actually earns trust.

3. **Turn the 9,798 real deals into bronze labels (the volume engine).** Real retailer price + real Keepa history = real profit/loss at a real cost, thousands of examples. Needs the matcher/SP-API (in progress) to link deal→ASIN cheaply — but the raw data already exists. This is where big *honest* volume comes from.

4. **Hand-label a few hundred (gold-grade validation anchor).** You + the deal-analyst helper + the knowledge-base rules mark ~200–300 products "buy/pass" with reasons. Small but high-trust — it's the yardstick you validate every model against. No buying.

5. **Weak-label from the knowledge corpus (cheap extra volume).** We have 99 docs / 1,340 chunks of OA expert rules. Encode them as automatic labelers (avoid Amazon-on-listing, avoid rising offers, require velocity, avoid price spikes) and apply to historical products. Not perfect, but real signal at scale, free.

6. **Keep collection BROAD (variety = reliability).** A model reliable on toys but blind on tools is useless to you. Widen categories, brands, and price bands (the de-bias work) so the data covers your real sourcing surface. Cheap (dealfeed ~5 tokens/150 products). The walk-forward already showed signal lives in the varied categories.

## When is it reliable enough to source from?
Trust it only when ALL of these hold — not before:
- It beats "buy everything" by a **real margin** on a **held-out, forward-in-time** test (walk-forward lift@10%), AND on the human gold set.
- Its scores are **calibrated** (a "70% good" pick is right ~70% of the time).
- It's been **shadow-proven** — its picks tracked against real market outcomes for a couple months.
- It **abstains** on products unlike anything it's seen (says "I don't know" instead of guessing).
- Even then it **ranks, never buys** — the hard gates and your approval always stand.

## What to do now (no seller account)
1. Fix the label (keep losers, real gate, price band) — free, immediate.
2. Turn on paper-trading and let it accumulate — free, starts the truest labels.
3. Keep collection broad — cheap variety.
4. Hand-label ~200–300 as the gold yardstick.
5. Weak-label from the knowledge rules for volume.
6. When SP-API/matcher land: convert the 9,798 deals to bronze real-cost labels.
7. Re-run the walk-forward after each step; watch lift over "buy everything," not raw accuracy.

**Bottom line:** the market already ran the experiment thousands of times and Keepa recorded it. Read that history honestly (steps 1, 3, 6), grade your own forward predictions against reality (step 2), and anchor it with a little expert judgment (steps 4–5) — and you reach a genuinely trustworthy shortlist without spending a dollar. Your real sales, once you're selling, only sharpen the last mile.
