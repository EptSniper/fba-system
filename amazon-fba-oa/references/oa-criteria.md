# OA Criteria — shared single source for the skill suite

These are the pre-filter gates and red-flag guards the operation runs on. They mirror
`learning-hub/data/ai-brain.json`, which is the **real** single source of truth that the
scout (`scout/config.py`) and the control-center both load. If this file and `ai-brain.json`
ever disagree, **`ai-brain.json` wins** — read it and prefer its values. Treat the numbers
below as the current baseline, not as gospel frozen in a skill.

## Pass gates (a candidate must clear all of these to be a BUY)

- BSR ≤ 200,000 in its category (sells regularly; not a dead listing).
- Estimated monthly sales ≥ 50 (look for the Keepa yellow "sold" line).
- Offer count between 3 and 25 (real competition, not single-seller/wholesale, not a brawl).
- ROI ≥ 30% after **all** fees and a returns/prep allowance (≥25% acceptable only for non-returnable grocery).
- Profit ≥ $3.00 per unit (thinner deals usually aren't worth the time).
- Sell price between $8 and $60 (the band where OA math and demand both work for a beginner).
- Amazon does **not** hold the current Buy Box (hard reject).

## Red-flag guards (penalize or hard-reject even if the gates pass)

- **Price spike:** current price > 1.5× its 90-day average → likely to revert; brutal with FBA's ~2-week delay.
- **Rising offers:** new-offer count > 1.4× its 90-day average → seller pile-in, price about to tank.
- **Amazon Buy Box share:** Amazon wins the Buy Box ≥ 20% of the time historically → hard reject (rotation), even if a 3P holds it right now.
- **IP cliff:** offer count crashes and never recovers (e.g. 56 → 1) → brand filed IP complaints. Worse than a price drop.
- **No Buy Box / no featured offer:** buyers must dig through "see all buying options" → far slower sales.
- **Brand is a seller on its own listing:** the brand owner kicks resellers off.

## Default cost assumptions

- Prep cost: $0.50/unit default (override with the real prep-center fee if used).
- Inbound shipping: ~$0.60/lb (range $0.50–0.80; re-check after each real FBA shipment).
- Referral fee: ~15% of sale price for most categories (range 8–15%, $0.30 minimum).
- FBA fulfillment fee: by size/weight (small standard ~$3.20, large standard ~$6.60, large bulky ~$10+).
- Fuel surcharge: 3.5% of the FBA fulfillment fee.
- True landed cost **must include shipping**: a $10 item with $9.95 shipping is a $20 cost.

## Brand hints (discovery/risk signals only — NOT eligibility proof)

- **Friendly (often resellable / commonly auto-ungated):** Jellycat, Crocs, Yeti, Stanley, Crayola, Elmer's, Monster Jam, LEGO, Hot Wheels, Pokemon, Owala, Gap, Nautica, Carter's, Under Armour, New Balance, Hoka, Mrs. Meyer's, Native, Milwaukee, DJI, Fancy Feast, Puma, Tonies.
- **Avoid (IP-aggressive / commonly gated):** Nike, Adidas, Jordan, Yeezy, Apple, Sony, Disney.

A friendly brand is a hint to look closer, not permission to sell. An avoid-brand is a hint to be
careful, not an automatic no. Account-specific eligibility is decided in Seller Central, never here.

## These are pre-filters, not a buy authorization

Clearing every gate means "worth verifying," not "buy it." Every real SKU still gets confirmed in
SellerAmp and Amazon's Revenue Calculator, checked for account-specific eligibility, and approved by
a human before any money moves. See `guardrails.md`.
