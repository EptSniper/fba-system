# Product Research → Buy / No-Buy Template

*The structured way I capture a product I'm researching (in SellerAmp / Keepa) so
the AI can judge it now and learn from it later. Copy the blank block per product.
Each finished row also goes into [`../tracking/product-leads.md`](../tracking/product-leads.md).*

---

## The buy/no-buy checklist (the gate logic — v1, transparent)

A product is a **BUY** only if **all** of these pass. Any "no" → reject or review.

- [ ] **Eligible / not gated** — I can actually sell it (checked in SellerAmp/Seller Central).
- [ ] **ROI ≥ 30%** after *all* fees (referral + FBA + fuel surcharge), and after a
      returns/prep allowance.
- [ ] **Healthy BSR** for its category — it sells regularly (not a dead listing).
- [ ] **Consistent Keepa history** — steady price + rank over 90+ days, not a one-time spike.
- [ ] **Bearable competition** — Buy Box not locked by Amazon/the brand; offer count not brutal.
- [ ] **Low IP/brand risk** — not a brand known to file complaints; not obviously restricted.
- [ ] **Sane cash** — the test buy fits my $500–$2,000 starting budget.

> Borderline on one? → mark **REVIEW** and ask the mentor. Never force a "yes."

### Instant reject — Keepa red flags (from the OA course, 2026-06-19)
Skip immediately if the Keepa chart shows any of these:
- **Offer count climbing** → too many sellers piling in; the price is about to tank.
- **IP cliff** (sellers crash, e.g. 56 → 1) → brand filed an IP complaint; hurts account health. Worse than a price drop.
- **Amazon holds ~80–100% of the Buy Box** → you won't get sales even if it's profitable.
- **No Buy Box / no featured offer** → buyers must dig through "see all buying options"; far slower sales + price battles.

> **Cost-lowering lever:** a thin deal can clear the ROI bar by *stacking* sale price +
> coupon + cashback (Rakuten / TopCashback / Coupert; compare rates via RevROI) +
> discounted gift cards. Use it to win the buy — but don't bake cashback into COGS.

### Two more checks before buying (from the live sessions)
- **Sells ≥50/mo?** The Keepa chart should show a **yellow "sold" line** (e.g. "50 sold"). No yellow line ⇒ <50/mo ⇒ usually pass. An **"!"** by estimated sales = number is shared across all variations.
- **True landed cost** — include shipping. A $10 item with $9.95 shipping = **$20** cost; enter the real number in SellerAmp.

### How many units to buy
- **Beginner:** 5–10 units until you know how it moves.
- **Formula:** `variation monthly sales ÷ (price-competitive sellers + you)`, then cut **30–50%**.
  (Per-variation sales = open Variations → sort by ratings → that variation's review % × total estimated sales.)
- **Worst case** should be break-even or ≤$1–2/unit loss at the lowest historical Buy-Box price.

Full method: [`../playbooks/sourcing-playbook.md`](../playbooks/sourcing-playbook.md).

---

## Worked example (so the fields are clear)

| Field | Value |
|---|---|
| Date | 2026-06-19 |
| Product | *(example)* Brand X 12oz Widget |
| ASIN | B0EXAMPLE0 |
| Amazon listing | (link) |
| Buy source + link | RetailerY.com clearance (link) |
| **Buy cost (COGS)** | $14.00 |
| **Sell price** | $30.00 |
| Category / referral % | Home / 15% |
| BSR (rank) | ~25,000 (category) |
| Est. monthly sales | ~200 (Keepa rank drops) |
| # FBA sellers | 4 |
| Eligible to sell? | ✅ Yes (ungated) |
| Keepa read | Price + rank steady 90d ✅ |
| SellerAmp ROI / profit | ~47% / ~$6.58 |
| Fees estimate | $4.50 referral + ~$4.90 FBA |
| **Checklist result** | ✅ All pass |
| **Verdict** | **BUY (test 10 units)** |
| Outcome (fill later) | _e.g. sold 8/10 in 3 wks @ 31% margin_ → **label: good** |

---

## Blank template — copy one per product

```
### [Product name]  ·  [date]
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
- VERDICT: BUY / NO-BUY / REVIEW   — reason:
- Decision made: bought ___ units  /  passed
- OUTCOME (fill after it sells): units sold, days, realized margin → label good/bad
```

---

## Completed research entries

### Baldur's Gate 3 Deluxe Edition (Xbox Series X)  ·  2026-06-30
- ASIN: B0DD8MRVL5
- Amazon listing: (not captured — analysis was from a pasted SellerAmp/Keepa screenshot, no listing URL saved)
- Buy source + link: ? (not captured)
- Buy cost (COGS): $79.99
- Sell price: $142.25 (current Buy Box)
- Category / referral %: Video Games / referral % not itemized — SellerAmp gave an aggregate fee figure only
- BSR (rank): 8,269
- Est. monthly sales: ~57/mo (60 rank-drops in 30 days; "57 drops/month" shown directly in the panel)
- # FBA sellers / Buy Box price: 9 FBA sellers hold the $142.25 Buy Box; lowest FBM offer $130.45; an "Amazon Resale" offer sits underneath at $124.92
- Eligible / gated?: NOT confirmed — SellerAmp showed "Check Alerts Panel" with 6 unresolved alerts (not green-eligible)
- IP / brand risk: not one of the hard-gated brands (licensed game, not Nike/Adidas/Jordan/Yeezy/Apple/Sony/Disney), but video games are a frequently-gated category and deluxe/collector editions carry variation-trap + return/disc-swap fraud risk
- Keepa read (price + rank stable? spike?): 3-month view — BSR oscillating ~#5k–#18k (healthy, not a spike); Buy Box flat $140–145 with a dip toward ~$125 in early May; offer count ~20 (dipped to 17, no seller-spike); pink Buy-Box line "wobbling downward" at the most recent edge — an early price-erosion signal, not yet a hard red flag
- SellerAmp ROI / profit: 38.8% ROI / $31.04 profit at the $142.25 Buy Box; breakeven $105.73; Max Cost $88.82
- Fee estimate (referral + FBA + fuel): ~$31.22 total, derived (sell $142.25 − cost $79.99 − profit $31.04) — SellerAmp gave this as an aggregate, not itemized by referral/FBA/fuel
- Checklist (7 items) → pass/fail:
  - Eligible/not gated: ⏸️ unknown (6 open SellerAmp alerts, not confirmed)
  - ROI ≥30%: ✅ pass at current Buy Box (38.8%) — ⚠️ fails downside case (~24% if the Buy Box slides to ~$125)
  - Healthy BSR: ✅ pass (8,269, ~57 sales/mo)
  - Consistent Keepa history: ⚠️ mostly steady, but a downward wobble at the recent edge
  - Bearable competition: ✅ pass (9 FBA sellers, Amazon does not hold the Buy Box, no seller spike)
  - Low IP/brand risk: ✅ pass on brand, ⚠️ category/edition risk (video games, deluxe edition — variation/return-fraud risk)
  - Sane cash: ⚠️ borderline — $79.99/unit means only ~6 units on a $500 starter budget, and the price sits well outside the project's $8–$60 OA band (`ai-brain.json` priceMax $60)
- VERDICT: REVIEW — lean NO-BUY. Profitable on paper (38.8% ROI) but priced well outside the $8–$60 OA band, eligibility is unconfirmed (6 unresolved alerts), there's real price-erosion risk (an Amazon Resale offer + lower FBM offers sit under the Buy Box — a slide to ~$125 compresses ROI to ~24% and profit to ~$19), and the $80/unit cost concentrates too much of a beginner's starting capital in one SKU.
- Decision made: not yet decided by Mehmet — this was an analysis-chain test (fba-chart-reader's first real-image run), never revisited to a final bought/passed call
- OUTCOME (fill after it sells): — n/a, no purchase made

---

## How this trains the AI

Every completed card is a data point:

- The **fields** are exactly what the scout scores on (price, BSR, sellers, fees, ROI).
- The **OUTCOME** is the honest label the scout learns from:
  ```bash
  # in scout/ or scout_pro/
  python train.py --label B0EXAMPLE0 --good --notes "sold 8/10 in 3wks @31% margin"
  ```
- Over time the model shifts toward the features that predicted *my* real winners —
  not generic theory. See [`vision-and-requirements.md`](vision-and-requirements.md).
