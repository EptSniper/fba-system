---
name: fba-deal-calculator
description: >-
  Deterministic Amazon FBA profit math. Use this WHENEVER the user wants the numbers run —
  "what's the ROI / profit / margin", "calculate the fees on this", "what's my breakeven",
  "what's the most I can pay (max cost)", "if I buy at $X and sell at $Y what do I make",
  "is 30% ROI possible at this price". It computes referral fee, FBA fulfillment + fuel
  surcharge, prep, profit, ROI, margin, breakeven, and Max-Cost-for-target-ROI using a
  bundled script so the arithmetic is exact and repeatable. Use it for pure math. Do NOT
  use it to render a BUY/NO-BUY verdict (that is fba-deal-analyst, which calls this math as
  one input) or to read Keepa/SellerAmp.
---

# FBA Deal Calculator

Profit on an FBA item is decided by fees + cost, not by the headline spread, and the #1 beginner mistake
is buying first and discovering the fees erased the margin. Your job is to make the math exact and boring —
no hand-waving — so the decision rests on real numbers. Always model fees BEFORE a buy, never after.

## Use the bundled script

Run `scripts/fba_calc.py` for the arithmetic instead of doing it by hand — it's deterministic and avoids slips:

```
python scripts/fba_calc.py --sell 29.99 --cost 20 --referral-pct 15 --fba-fee 6.60 \
    --inbound 0.60 --prep 0.50 --target-roi 30
```

It prints referral fee, fuel surcharge (3.5% of the FBA fee), total fees, profit/unit, ROI, margin, breakeven
sell price, and Max Cost to hit the target ROI. Defaults come from `../../references/oa-criteria.md` — referral 15%,
prep $0.50, fuel 3.5%, target ROI 30% — and any can be overridden.

## When inputs are missing

The FBA fulfillment fee depends on exact size/weight and is the value most likely to flip a verdict — if it's
unknown, run the math at two tiers (small-standard ~$3.20 and large-standard ~$6.60) and show both, so the
operator sees the range rather than a false-precise single number. Always include shipping in the landed cost
(a $10 item with $9.95 shipping is a $20 cost). Label every output as an estimate until SellerAmp / Amazon's
Revenue Calculator confirms the real fees for the actual SKU.

## Output

```
DEAL MATH — sell $__, landed cost $__
- Referral (__%): -$__   FBA fee: -$__   Fuel (3.5%): -$__   Prep: -$__   Inbound: -$__
- Profit/unit: $__   ROI: __%   Margin: __%   Breakeven sell: $__
- Max Cost for __% ROI: $__  (land below this to clear the bar)
[If FBA fee unknown: show small-standard vs large-standard rows]
Estimate only — confirm exact FBA fee in SellerAmp / Revenue Calculator before buying.
```

The numbers inform a decision; they are not a decision. Buy approval stays with the human.
