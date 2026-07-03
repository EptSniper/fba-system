# Scout + Deal-Finder Expert Upgrade Brief

**Date:** 2026-07-01 · **Author:** Claude (Cowork) · **Executor:** Claude Code (Mehmet pastes the prompts below)
**Goal:** make the scout pipeline (`scout/`, `scout_pro/`) and the control-center Find page evaluate deals like a veteran OA seller — deeper analysis logic, then live Keepa data, then a provable learning loop.

How to use this file: work through the phases **in order**. Each prompt is self-contained — paste one prompt into Claude Code, let it finish (including tests + journal entry), review, then move to the next. Do not run two prompts in parallel; several touch `ai-brain.json` and the scorer.

---

## 1. Gap analysis (what the audit found)

Audited 2026-07-01 against the code and the knowledge base (51 transcripts, 3 playbooks, field-sops, ai-brain.json).

**Already expert (encoded, single-sourced, tested):** the 5 OA hard gates (BSR ≤ 200k, sales ≥ 50/mo, offers 3–25, ROI ≥ 30%, profit ≥ $3), price-spike guard (1.5× 90-day avg), offers-rising guard (1.4×), Amazon Buy Box share hard-reject (≥ 20%), IP-cliff detector, no-featured-offer penalty, worst-case-loss check (> $2/unit at 90-day low), brand friendly/avoid lists, hazmat/meltable/expiration keyword hints, 2026 fee schedule with fuel surcharge and $0.50 prep. ~24 rules total.

**Documented in the knowledge base but NOT encoded (~40 rules).** The high-value ones:

| Gap | Where it matters | Blocked by |
|---|---|---|
| Category-specific referral fees (flat 15% today) | scout + Find page | nothing — fee table already ingested in RAG |
| Grocery ROI exception (25% — non-returnable) | scout + Find page | nothing |
| Preferred 5–7 offer "goldilocks" bonus | scout scoring | nothing |
| Explain-why verdicts (which gate/penalty and by how much) | both surfaces | nothing |
| Find page missing ALL history guards (spike, offers-rising, BB share, IP cliff, worst-case, brands, restriction hints) | Find page | nothing — thresholds already in ai-brain.json `guards` |
| Penny-war / oscillation detector (BB price volatility) | scout | needs Keepa `history=True` |
| Seasonality windows (1-year BSR humps; buy 6–8 weeks pre-peak) | scout | needs 1-year Keepa history |
| All-time IP cliff (current one approximates with 90-day data) | scout | needs full history |
| Amazon in-stock band presence | scout | needs Keepa Buy Box/stock history |
| Variation trap warning (per-variation sales) | both | Keepa variation data (partial) |
| ASIN lookup on Find page (auto-fill from live Keepa) | Find page | paid `KEEPA_KEY` |
| Product Finder discovery stack (brand + BSR + Amazon-OOS + offers ≥ 4) | scout discovery | paid `KEEPA_KEY` |
| One-click "capture this verdict as a lead" from Find page | learning loop | nothing — `/api/capture` exists |
| Outcome-labeled calibration + promotion gate actually exercised | scout_pro | real outcomes accumulating |

## 2. Architecture constraints every prompt already embeds

These are the project's non-negotiables (per fba-architect standards). If Claude Code proposes something that violates one, stop it.

1. **Single source of truth:** every new threshold lives in `learning-hub/data/ai-brain.json` with a `source:` provenance line. `scout/config.py` and the control-center both read from it. No second copy of a number.
2. **Hard gates stay outside ML.** New detectors are transparent rules with named penalties, not model features that can erode gates.
3. **Leakage prevention:** only pre-decision features enter training; outcomes are labels only. The scout's verdict is never its own success label.
4. **No secrets in the browser.** `KEEPA_KEY` and Supabase service keys are server-side only (`.env` / `API_KEYS.env`). The Find page talks to a same-origin Next.js API route.
5. **Honest data flow:** estimated data is labeled estimated; empty states stay honest; after editing `ai-brain.json`, re-sync `control-center/hub-data/` or note the drift.
6. **Human approval:** nothing auto-buys. Highest automated status is `review`.
7. **Every session:** tests for scorer changes, `npm run typecheck && npm run build` for control-center changes, and a dated entry in `AI_COLLABORATION_JOURNAL.md`.

---

## PHASE 1 — Encode the expert knowledge (no new keys, works today)

### Prompt 1.1 — Expand the brain with the missing expert thresholds

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use the
amazon-fba-oa:fba-brain-updater skill for this task — it owns ai-brain.json edits.

Task: extend learning-hub/data/ai-brain.json with the following new values. Preserve all
existing keys and source: provenance lines, add a source: line for each new block, bump
"updated" to today, and append an ingestionLog entry describing this change.

1. criteria.exceptions: { "groceryMinRoi": 0.25 } — non-returnable grocery can accept 25%
   ROI instead of 30% (source: field-sops.md / sourcing-playbook.md).
2. scoring.preferredOffers: { "min": 5, "max": 7, "bonus": 5 } — the 5–7 seller goldilocks
   band earns a small bonus (source: transcripts/insights.md #9). This is a bonus, not a gate.
3. fees.referralRates: a category → rate map replacing the flat 15% assumption. Pull the
   real category table from the already-ingested Amazon referral-fee document in
   knowledge-rag/corpus (it was ingested from sell.amazon.com). Include a "default": 0.15
   fallback and keep the $0.30 minimum. Only include categories relevant to OA (toys, home,
   kitchen, grocery, beauty, health, clothing, shoes, office, pet, sports, tools, baby,
   electronics accessories).
4. guards.pennyWar: { "windowDays": 30, "bbStdPctFlag": 0.04, "status": "proposed default —
   tune after live Keepa history is available" } — flag active price wars when the Buy Box
   price standard deviation over 30 days exceeds 4% of its mean. Mark clearly as a proposed
   default; Phase 2 wires the data.
5. seasonality: { "backToSchool": { "months": [6,7,8], "brands": ["Puma","Cuddle Duds","Gap",
   "Carter's"] }, "q4": { "months": [9,10,11,12], "brands": ["Stanley","Yeti","LEGO",
   "Hot Wheels","Pokemon","Jellycat","Tonies"] }, "buyLeadWeeks": [6,8] } (source:
   field-sops.md seasonal calendar).
6. discovery.productFinderStack: { "bsrMax": 200000, "amazonOutOfStock": true, "minOffers": 4,
   "sortHint": "90-day price-drop % (surface value buys)" } (source: insights.md #8 /
   sourcing-playbook.md reverse-sourcing method).

Validate the JSON parses, confirm scout/config.py still loads (run python -m py_compile on
the scout package and the existing scout test suite — all 15 scoring tests must still pass
untouched, since nothing reads the new keys yet). Re-sync control-center/hub-data/ai-brain.json
to match. Append a journal entry using the fba-session-journal skill.
```

### Prompt 1.2 — Scout scorer: category fees, grocery exception, offer band, explain-why verdicts

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use the
amazon-fba-oa:fba-coder skill for implementation and amazon-fba-oa:fba-qa-tester for tests.

Context: Prompt 1.1 added criteria.exceptions.groceryMinRoi, scoring.preferredOffers, and
fees.referralRates to learning-hub/data/ai-brain.json. Now make scout/ read and apply them.

Changes in scout/ (config.py, scoring.py — follow the existing single-source pattern where
config.py loads from ai-brain.json with env fallbacks):

1. Category-aware referral fees: load fees.referralRates; estimate_oa_profit_roi() and the
   fee helpers accept an optional category string and use the category rate, falling back to
   default 0.15. Keep the $0.30 floor.
2. Grocery ROI exception: when the candidate's category is grocery (or a
   category_hint="grocery" is passed), the ROI gate uses groceryMinRoi (0.25) instead of
   minRoi (0.30). This changes the GATE THRESHOLD only for that category — do not weaken any
   other gate. Log which threshold was applied.
3. Preferred-offer-band bonus: +scoring.preferredOffers.bonus points when offer count is
   within [min, max]. Bonus only — the 3–25 hard band is unchanged.
4. Explain-why verdicts: every scored candidate returns a structured explanation:
   { verdict, score, gates: [{name, passed, actual, threshold}], adjustments:
   [{name, points, reason}] }. The existing penalties/bonuses (price spike -15, offers rising
   -12, IP cliff -20, no featured offer -8, worst-case loss -10, generic brand -8, friendly
   brand +5, and the new offer-band bonus) must each appear as a named adjustment with its
   point value and a one-line human reason. Wire this into pipeline.py so the Supabase lead
   log and any Discord alert include the explanation. Do not change any threshold values.

Tests: extend scout/tests/ — category fee selection (incl. unknown category → default),
grocery gate at 25% vs non-grocery at 30%, offer-band bonus applied at 5 and 7 but not 4 or 8,
and an explanation-structure test asserting every adjustment is named with points. All
existing 15 scoring tests + 2 pipeline-memory tests must still pass. Run the full suite.

Do NOT touch scout_pro/ in this prompt. Append a journal entry (fba-session-journal skill).
```

### Prompt 1.3 — Find page parity: history guards, brand/restriction checks, explain-why UI

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder for implementation; consult amazon-fba-oa:fba-designer for the
layout of new fields (operator-terminal design system in design-system/oa-control-center/).

Context: the control-center deal analyzer (control-center/components/deal-analyzer.tsx,
app/find/page.tsx) applies only the 5 basic gates. The scout applies 6 more guards whose
thresholds already live in ai-brain.json. Bring the Find page to parity so a manual analysis
is as expert as a scout run. All new thresholds must be read from getBrain() (lib/data.ts),
never hardcoded.

Add OPTIONAL inputs (clearly grouped as "Keepa history — optional, sharpens the verdict";
empty = check skipped and shown as "not checked", never as passed):
  - 90-day average price → price-spike guard (guards.priceSpikeRatio, 1.5×)
  - 90-day average offer count → offers-rising guard (guards.offersRiseRatio, 1.4×)
  - Amazon Buy Box share % (from Keepa BB stats) → hard reject ≥ guards.amazonBuyBoxShareMax
  - 90-day lowest price → worst-case check: recompute profit at that price; flag if loss
    > $2/unit (mirror scout's _worst_case_loss logic)
  - Brand (text) → check against brands.friendly / brands.avoid; avoid-list = hard reject
    with an IP-risk message, friendly = positive signal chip
  - Product title (text) → restriction keyword hint mirroring scout's hazmat / meltable /
    expiration-dated keyword lists (surface as a warning chip: "verify eligibility in Seller
    Central", never as an eligibility verdict)
  - Category select (from fees.referralRates keys) → drives the referral rate used in the
    math (replacing flat 15%) and applies criteria.exceptions.groceryMinRoi when grocery.

Verdict logic update: hard rejects (Amazon BB checkbox, BB share ≥ max, avoid brand) force
PASS. Otherwise keep BUY / REVIEW / PASS by failed-gate count, counting only checks the user
actually filled in. Render an explain-why panel listing every check with pass/fail/not-checked,
actual vs threshold, and each penalty/bonus by name — same vocabulary as the scout's
explanation structure from Prompt 1.2.

Also add a "Save as lead" button on the verdict card that POSTs the current analysis
(inputs + verdict + explanation summary) to the existing /api/capture route as a lead event,
matching the capture-forms lead shape. Show the honest 503 message on Vercel (the route is
local-only).

The restriction keyword lists must not be duplicated: add them to ai-brain.json under
guards.restrictionKeywords (with a source: line, via the fba-brain-updater conventions) and
have BOTH scout/scoring.py and the UI read them from there. Update scout to load from the
brain with its current hardcoded list as fallback, and keep scout tests green.

Verification: npm run typecheck, npm run build, existing behavior unchanged when optional
fields are empty, no horizontal overflow at 375px, no console errors. Re-sync
control-center/hub-data/ai-brain.json. Append a journal entry (fba-session-journal skill).
```

### Phase 1 acceptance checklist

- ai-brain.json has the 6 new blocks, each with `source:` provenance; hub-data copy re-synced.
- Scout: all old tests green + new tests for fees/grocery/band/explanations.
- Find page: optional-empty behavior identical to today; filled guards change verdicts; explain-why panel matches scout vocabulary; Save-as-lead writes an events.jsonl lead locally.
- No new hardcoded thresholds anywhere. Journal entries appended per prompt.

---

## PHASE 2 — Live Keepa data (needs the paid KEEPA_KEY in scout/.env — never in the browser)

Run Prompt 2.1 only after the Keepa subscription is active and the key is placed in `scout/.env` (registry copy in `API_KEYS.env`).

> **Update 2026-07-01:** verified Keepa API research (see `SYSTEM_BLUEPRINT.md` §2–3) found the stats object already includes 90-day avgs/lows, per-seller Buy Box share, Amazon out-of-stock %, sales-rank drops, variation info, and per-ASIN fee data — at 3 tokens/ASIN, with full history costing no extra tokens. **Paste the "Keepa facts box" from SYSTEM_BLUEPRINT.md together with Prompts 2.1 and 2.2** so Claude Code uses the stats fields instead of recomputing from raw history.

### Prompt 2.1 — History-powered detectors: penny war, seasonality, all-time IP cliff, Amazon in-stock

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect briefly to confirm the fetch design, then amazon-fba-oa:fba-coder.

Context: scout/keepa.py currently requests stats=90, buybox=True, history=False. The brain
(ai-brain.json) now has guards.pennyWar and seasonality blocks waiting for data.

1. Extend the Keepa client to optionally fetch history (history=True, 365 days) for
   candidates that SURVIVE the hard gates — gate first on the cheap stats call, enrich only
   survivors, to control token cost. Make the enrichment batch size configurable.
2. New transparent detectors in scoring.py, each a named adjustment in the explanation
   structure (thresholds from ai-brain.json, no hardcoding):
   a. Penny war: std of Buy Box price over guards.pennyWar.windowDays / mean >
      bbStdPctFlag → penalty (propose -10, add to brain as guards.pennyWar.penalty).
   b. Oscillation/velocity: count of Buy Box price changes + offer-count changes in the last
      30 days; long flat "blocky" stretches with BSR flatlines → "slow mover" warning
      adjustment (insights.md #9's oscillation-vs-blocky rule, made numeric).
   c. Seasonality: detect repeating 1-year BSR humps; if the candidate's peak window (or its
      brand's window in the brain's seasonality block) is > seasonality.buyLeadWeeks away,
      add a "seasonal — wrong buy window" warning adjustment.
   d. All-time IP cliff: run the existing _ip_cliff logic against full history, not just the
      90-day window (a 56→1 seller collapse a year ago is still a hard reject).
   e. Amazon in-stock band: fraction of the last 90 days Amazon was in stock; penalize above
      a brain-defined threshold (propose guards.amazonInStockShareFlag: 0.3, marked
      "proposed default").
3. Variation warning: if the Keepa response marks the ASIN as part of a variation family,
   attach a "variation trap — per-variation sales unknown, verify in SellerAmp" warning.
4. Each new brain value goes in via fba-brain-updater conventions (source: line, updated
   bump, ingestionLog entry); re-sync control-center/hub-data.

Tests: unit-test each detector with synthetic history arrays (war vs stable, seasonal vs
flat, cliff vs healthy, in-stock bands). Full suite green. Run ONE real scout cycle in dry-run
mode and paste the summary (no purchases, no Discord). Journal entry at the end.
```

### Prompt 2.2 — Find page ASIN lookup + Product Finder discovery stack

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to confirm the route design (the pattern must match the existing
/api/knowledge-search server-side approach), then amazon-fba-oa:fba-coder.

1. New same-origin route POST /api/asin-lookup in control-center: given an ASIN, call the
   scout's Keepa client server-side (KEEPA_KEY from server env only — never NEXT_PUBLIC_,
   never in client code) and return: current price, BSR, offer count, 90-day averages
   (price/offers), 90-day low, Amazon BB share, Amazon-current-BB flag, brand, title,
   category guess. Honest 503 with a clear message when the key is absent or on serverless.
2. Find page: an ASIN field + "Fetch from Keepa" button that auto-fills the analyzer inputs
   (including the Phase 1 optional history fields) and marks the card "live Keepa data,
   fetched <timestamp>" vs "manual input". User can still edit any value after fetch.
3. Scout discovery: implement the reverse-sourcing filter stack from
   discovery.productFinderStack in ai-brain.json (brand seed × BSR ≤ 200k × Amazon
   out-of-stock × offers ≥ 4) as the default Keepa Product Finder query the scout runs per
   friendly brand, with the 90-day price-drop sort hint where the API supports it.

Verification: typecheck + build; confirm via grep that KEEPA_KEY appears nowhere in
control-center client bundles; one dry-run discovery cycle per one brand with the summary
pasted. npm audit clean. Journal entry.
```

---

## PHASE 3 — Learning loop (starts paying off as real decisions/outcomes accumulate)

### Prompt 3.1 — Close the loop: verdict → decision → outcome, and prove calibration

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to sanity-check the leakage boundary, then amazon-fba-oa:fba-coder,
then amazon-fba-oa:fba-code-reviewer on the diff before finishing.

Non-negotiable: only pre-decision features may enter training; outcomes are labels; the
scout's own verdict is never a success label; hard gates remain outside any model.

1. Lead linkage: when the Find page "Save as lead" fires (Phase 1.3) or the scout logs a
   lead, ensure the stored record contains the full pre-decision feature snapshot AND the
   explanation structure (gates + adjustments). Decisions and outcomes captured later via
   /api/capture or the Log page must link back by ASIN/lead id so each lead can eventually
   carry {features, human_decision, realized_outcome}.
2. Label builder: a script in scout/ (or scout_pro/ if its labels module already fits) that
   assembles the training table from linked records only — no post-decision fields — and
   reports how many complete labeled rows exist. It must refuse to train below a minimum
   (propose 30 labeled rows with both positive and negative outcomes, stored in the brain as
   learning.minLabeledRows with a source: line).
3. Calibration + promotion report: extend/exercise scout_pro's existing calibration and
   champion/challenger machinery to output an honest markdown report: sample size, class
   balance, calibration curve summary, and an explicit "NOT enough data to promote" statement
   until thresholds are met. Never silently promote.
4. Weekly threshold-tuning report (analysis only, no auto-change): compare realized outcomes
   against each gate/penalty (e.g., "REVIEW leads with offers 20–25 lost money 3/4 times") and
   emit suggested brain adjustments for HUMAN review. The report writes to
   learning-hub/tracking/, it never edits ai-brain.json itself.

Tests: label-builder leakage test (post-decision field injected → must be excluded), minimum-
rows refusal test, linkage round-trip test. Full suites green in scout/ and scout_pro/.
Journal entry.
```

### Phase 3 acceptance checklist

- A lead can be traced end-to-end: features → decision → outcome, with the explanation attached.
- Training refuses to run under `learning.minLabeledRows`; the refusal message is honest.
- Tuning suggestions are recommendations to a human, never auto-applied.

---

## Sequencing summary and what NOT to let Claude Code do

Order: 1.1 → 1.2 → 1.3 (all possible today) → [Keepa key arrives] → 2.1 → 2.2 → 3.1 (3.1's UI/linkage parts can start before Phase 2 if desired — it has no Keepa dependency).

Stop Claude Code if it tries to: hardcode a threshold outside ai-brain.json; put any key in client code or NEXT_PUBLIC_ vars; let a model score bypass or soften a hard gate; train on post-decision data or scout verdicts as labels; auto-apply tuning suggestions; mark anything as an automatic buy; or skip the journal entry.

Open items for Mehmet (not Claude Code): activate the paid Keepa subscription before Phase 2; keep capturing real decisions/outcomes in the Log page — Phase 3's value scales directly with how many honest outcomes exist; rotate the Supabase service_role key that was pasted into chat (flagged in journal Session 14).
