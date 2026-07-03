---
name: fba-lead-capture
description: >-
  Captures a researched product lead into the project trackers in a clean, validated row.
  Use this WHENEVER the user wants to save or record a product they're researching —
  "log this lead", "add this to my product leads", "save this product", "record this for
  later", "I analyzed this, write it down", or right after fba-deal-analyst produces a
  verdict the user wants to keep. It writes a structured row into
  learning-hub/tracking/product-leads.md (and mirrors the count in leads.json), matching the
  buy/no-buy template fields, so the data can later train the scout from real outcomes. Use
  it to build the ground-truth lead bank. Do NOT use it to make the buy decision
  (fba-deal-analyst) or to record realized sales outcomes only (it captures leads + an
  outcome field to fill later).
---

# FBA Lead Capture

The project's stated next safe step is building real, validated capture of leads, decisions, and outcomes —
because the scout can't honestly learn without ground-truth labels. Your job is to turn a finished analysis
into a clean, consistent record, with honest empty fields where data is missing, so the lead bank stays
trustworthy rather than full of half-rows.

## Match the existing format

Read `learning-hub/tracking/product-leads.md` and `learning-hub/ai-system/product-research-template.md` before
writing, and follow their field structure exactly. The canonical fields:

```
### [Product name] · [date]
- ASIN:
- Amazon listing:
- Buy source + link:
- Buy cost (COGS): $
- Sell price: $
- Category / referral %:
- BSR (rank):
- Est. monthly sales:
- # FBA sellers / Buy Box price:
- Eligible / gated?:
- IP / brand risk:
- Keepa read (price + rank stable? spike?):
- SellerAmp ROI / profit:
- Fee estimate (referral + FBA + fuel):
- Checklist (7 items) → pass/fail:
- VERDICT: BUY / NO-BUY / REVIEW — reason:
- Decision made: bought ___ units / passed
- OUTCOME (fill after it sells): units sold, days, realized margin → label good/bad
```

## Rules

- **Validate, don't fabricate.** Only fill fields the user actually provided or that came from an analysis. Leave
  unknowns blank or marked "?" — an honest empty field beats an invented number.
- **A lead is not a purchase.** Capturing a BUY verdict records a recommendation; it never means a buy happened.
  The "Decision made" and "OUTCOME" fields are filled by the human, later.
- **Keep the mirror honest.** If you update `leads.json` pipeline counts, increment the correct stage
  (idea/researching/buy/ordered) to match reality — don't inflate the pipeline.
- No secrets; links only.

## Output

Append the row to `product-leads.md`, update the `leads.json` count if appropriate, and show the user the saved
row plus which pipeline stage it landed in. Remind them the OUTCOME field is what eventually trains the scout, so
it's worth coming back to fill after the product sells (or doesn't).
