# Going forward — real prices + a good model on a tiny Keepa budget

**Author:** Cowork (fba-architect + fba-ml-lead + fba-scout-strategist), 2026-07-13.
**The frame:** Keepa Pro is a hard ~1,440 tokens/day. That ceiling limits SCALE, not model QUALITY. A good model is blocked by the fake 50% label and zero realized outcomes — both fixable with almost no tokens. So: spend tokens only where nothing free can substitute, and spend brainpower on the label + ground truth.

## Doctrine: make Keepa the LAST step, on survivors only
Every product should pass a free funnel before it ever costs a token:

```
retail deal feeds (FREE)  ->  free pre-filters (FREE)  ->  ASIN + eligibility (FREE via SP-API)
        ->  KEEPA only on what's left (economics on an already-identified, pre-qualified ASIN)
```

A Keepa token spent on a deal a free filter would have rejected is pure waste. Today the matcher pays ~30 tokens/deal to *discover* the ASIN by title search — that's the expensive part, and it's the part free sources can replace.

## Token-saving levers, ranked by impact
1. **Wire SP-API catalog (biggest structural win).** Amazon's own catalog search maps title/UPC → ASIN and returns eligibility for FREE (rate-limited, not token-metered). The scaffold exists (`scout/spapi.py`) but is disconnected. Connect it → the ~10-token Keepa title search disappears, and junk/gated items die free. Keepa then only prices an ASIN you've already identified and qualified (~1 token via history).
2. **UPC-enrich the deal feeds.** 0 of 9,798 deals have a UPC today. Pull UPCs from the Best Buy feed / clearance-page JSON-LD `gtin`. A UPC turns a ~10-token guess-search into a ~1–2 token *exact* Keepa lookup AND auto-verifies the match (cuts human review).
3. **Free pre-filters before any Keepa call.** In-band price ($8–60 after discount), real discount, sellable category, dedupe against already-known ASINs. Only survivors cost tokens. (The in-band cut alone drops 9,798 → ~1,069.)
4. **Cache / never re-pull.** Reuse `keepa_snapshots` + the data lake; one history pull per ASIN feeds many sim-date rows (already true in backtest). Skip any ASIN already in `backtest_rows`/snapshots within its freshness window.
5. **Cheaper call shapes.** History (1 tok) over enrich (4 tok) for corpus building; enrich (with buybox) only on real buy candidates; 2–3 candidates per match, not 5; batch 100 ASINs/request.
6. **Split the daily 1,440 on purpose.** e.g. ~60% corpus breadth (cheap dealfeed 5tok/150 + 1-tok history), ~40% matching the priority deal subset — tunable via the brain, so matching never starves collection (extend `corpusAcceleration`).

Net effect: per-deal cost drops from ~30 tokens (title-only, Keepa-discovery) to ~1–5 tokens (SP-API/UPC-resolved). The ~1,069 priority subset goes from ~32k tokens to ~2–5k — days, not weeks.

## Model-quality levers (mostly token-FREE — this is what actually makes it good)
1. **Fix the label (#1, no tokens).** Replace `profit>0 @ 50% cost` with either the real matched buy cost, or the cost-free **Max-Cost-for-30%-ROI** target (from sell price + fees + weight; the real retail price is compared at decision time). This is the single biggest quality lever — the walk-forward proved the current model just re-derives the fake cost.
2. **Log realized outcomes (#2, ~free, highest value/row).** `outcomes` is empty. A handful of real "bought → sold for $X in N days" rows are worth more than 10,000 simulated ones — they're the only true (gold) labels. Capture them on every real buy (manually now; via SP-API Finances later).
3. **Collect where the label VARIES, not more certain-winners.** The walk-forward showed signal lives in mixed-outcome categories (garden/arts_crafts/industrial/grocery/beauty, AUC 0.75–0.98) and vanishes where ~everything wins (tools/baby/clothing). Breadth toward mixed-margin products beats volume of easy wins.
4. **Feature quality over feature count.** Add competition/volatility signals (offer-count trend, price volatility, Amazon in/out frequency, velocity-vs-competition) — the real flip drivers, currently missing. Keep ~15–25 curated features; prune the dead ones (eBay count, brand-trend, day-of-week).
5. **Honest, permanent evaluation.** Walk-forward folds + lift@10% + per-category slice as the standing gate (productionize in `train_ranker.py`). Shadow-only; promote on consistent multi-fold lift over the champion, never on AUC; `rankingChampion` stays `rule` until then.

## Sequence
- **Now (free/cheap):** define the new label; connect SP-API catalog (free ASIN + eligibility); add the free pre-filter funnel; start logging outcomes on any real buys.
- **Next (cheap Keepa):** build D3 (deal-first gate-checked leads); match the ~1,069 priority subset via SP-API/UPC-resolved ASINs (~1–5 tok each) → first real-cost leads in the queue.
- **Then:** retie the ML to real labels; re-run the walk-forward; iterate features; grow gold outcomes.
- **Only then consider paying more:** if, after SP-API offloads discovery, you still need >1,440 Keepa tokens/day sustained, a higher Keepa tier or a 2nd key is the lever — not before. You do not need to spend more on Keepa to get a good model; you need real labels + real outcomes.

## One-line summary
Free sources find and qualify products; Keepa only prices the survivors; the model is made good by a real label and real outcomes — none of which cost tokens.
