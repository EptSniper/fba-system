# Control-center reliability and intelligence roadmap

## Objective

Make the control center dependable first, then improve recommendation quality with measured evidence. “Smarter” means fewer unsupported claims, better source selection, better outcome labels, and higher evaluation scores—not more confident wording.

## Stage 0 — interaction reliability (implemented 2026-06-27)

- Audit every route and distinguish working actions from read-only information.
- Give previously display-only modules explicit actions to the analyzer, knowledge brain, sourcing tools, or the correct Seller Central workspace.
- Remove hover treatment from non-clickable KPI cards.
- Add Ask runtime health, visible recovery states, UTF-8-safe Windows output, and API regression checks.

## Stage 1 — zero-cost answer quality (implemented 2026-06-27)

- Retrieve 12 candidates from the existing 1,224-chunk Supabase corpus.
- Expand common OA concepts before retrieval.
- Rerank by semantic similarity, query coverage, and source tier.
- Prefer maintained playbooks and AI specifications over raw transcript speech.
- Deduplicate passages and reject incomplete fragments.
- Answer common high-risk intents from maintained project rules, then expose the retrieved evidence for inspection.
- Cache repeated questions for 15 minutes to avoid unnecessary embedding work.
- Run `python evaluate.py` as a quality gate with expected facts and citations.

## Stage 2 — local data capture (next, no paid API required)

Build human-approved forms for manual leads, decisions, purchases, inventory, and realized outcomes. Validate every write, keep an append-only event log, and provide export/backup. This is more valuable than another model because no real outcome labels currently exist.

## Stage 3 — knowledge quality and freshness

- Give every source an authority tier: current Amazon official documentation, account evidence, maintained project SOP, distilled practitioner insight, raw transcript.
- Add effective dates, marketplace, account scope, and review dates.
- Detect conflicting thresholds and show the conflict instead of silently choosing one.
- Add official-document refresh checks and quarantine stale policy claims.
- Expand the evaluation suite whenever a bad answer is found.

## Stage 4 — learning from outcomes

- Record human approve/reject/watch decisions separately from scout predictions.
- Record realized profit, ROI, sell-through, returns, price compression, and would-rebuy.
- Train only on pre-decision features; outcomes are labels.
- Use time-based train/test splits, calibration, and champion/challenger promotion.
- Keep account eligibility, compliance, IP risk, and minimum margin as hard gates outside ML.

## Stage 5 — live account evidence

When credentials are deliberately available, connect Listings Restrictions first, then Inventory and Finances. Keep purchases, listing changes, and money movement human-approved. Keepa remains the licensed marketplace-history source; no logged-in Amazon scraping.

## Definition of done for each release

1. Every visible action has a tested result or is clearly labeled unavailable.
2. Typecheck, production build, Python unit tests, live answer evals, API health, and browser interaction checks pass.
3. Answer citations support the displayed claim.
4. No secret reaches browser code or documentation.
5. The collaboration journal records limitations and the next safe step.
