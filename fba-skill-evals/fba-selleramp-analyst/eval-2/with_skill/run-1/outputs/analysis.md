# SellerAmp Read — Max Cost reverse calculation

**Your question:** Buy Box is $32 — what's the most I can pay and still hit my ROI?

In SellerAmp this is exactly what the **Max Cost** field is for: it runs the profit math *backwards* from your target ROI and tells you the highest landed cost you can pay per unit and still clear the bar. Land below Max Cost (after stacking discounts) and the deal works; pay above it and you fall under target.

## The catch: I need one more number

Max Cost moves with the **FBA fulfillment fee**, which depends on the item's size/weight tier — and you haven't given me the product. So I've run it for the two most common tiers. Find your item's real FBA fee in the SellerAmp panel (or Amazon's Revenue Calculator) and use the matching row.

All figures use your project defaults: referral 15%, fuel surcharge 3.5% of the FBA fee, prep $0.50/unit, inbound shipping $0.60/unit, **target ROI 30%**.

## Max Cost at $32 sell price (30% ROI target)

| Size tier | FBA fee | **Max Cost (most you can pay, landed)** |
|---|---|---|
| Small standard | $3.20 | **$17.53** |
| Large standard | $6.60 | **$14.82** |

So the answer is roughly **$15–$17.50 per unit, all-in**, depending on size tier. To be safe before you know the exact fee, treat the **large-standard $14.82** as the conservative ceiling and only stretch toward $17.53 once SAS confirms a small-standard fee.

For reference, if this is **non-returnable grocery** (the only case where ~25% ROI is acceptable), Max Cost rises to **$18.23** (small standard) / **$15.42** (large standard).

## Read this number correctly — "landed cost"

Max Cost is **true landed cost**, not the shelf price. It already has to cover everything that gets the unit to Amazon. The shipping-to-you and any sales tax come out of that ceiling:

- **Bake sales tax into the cost** (total paid ÷ units) — do *not* also use the SAS % tax field, or you double-count.
- A $10 item with $9.95 shipping is a $20 cost — that would blow past this ceiling.
- Cashback is a **cushion**, not part of COGS — don't lower your cost with it. The stack you *can* use to get under Max Cost: coupon/signup codes, discounted gift cards, Subscribe & Save, free-shipping thresholds.

## Settings sanity (so the math doesn't lie)

Confirm these in SAS before trusting any Max Cost it shows you:

- Inbound shipping ~$0.60/lb · Min profit $3 · **Min ROI 30%** · Prep = your real prep-center fee.
- Min BSR 0% / Max BSR 2%.
- Sales tax baked into cost price, **not** also in the % field.

## SELLERAMP READ — [ASIN not provided]

- **Settings sanity:** confirm 30% ROI target, $0.60 inbound, prep fee, tax-in-cost (not double-counted).
- **Sell price $32.00** — inside the $8–$60 OA band. Good.
- **Max Cost @ 30% ROI:** **$17.53** (small-standard FBA) / **$14.82** (large-standard FBA) — land below this, after stacking, to make it work.
- **Take-shopping number:** ~**$15–$17.50 landed**. Use $14.82 as the safe ceiling until SAS confirms the FBA size tier.
- **Read:** I can give you the *price you can pay*, but not a buy verdict — that needs the rest of the panel (BSR, offer count, monthly sales, eligibility, IP, Buy-Box history).

## What this does NOT tell you

This is the price ceiling only. It is **not** a buy decision. Before any money moves you still need:

- **Demand & stability** from Keepa (BSR <= 200k, >= ~50 sales/mo, offer count 3–25, no price spike, no IP cliff) -> hand to fba-keepa-analyst.
- **Eligibility + IP** — list the ASIN in Seller Central *before* you buy; trust the IP Alert. SAS eligibility is a hint, not permission.
- **Amazon not on the Buy Box** (hard reject if it is, or rotates in >= 20% of the time).
- **Final gate run** in fba-deal-analyst, then human approval.

> Estimate only — confirm the exact FBA fee in SellerAmp / Amazon's Revenue Calculator before buying. SAS is verification, not a buy order.
