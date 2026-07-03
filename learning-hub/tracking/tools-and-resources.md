# Tools & Resources

*The stack I'm using and trusted places to learn. Confirmed with the startup
breakdown Mehmet shared on 2026-06-19.*

---

## The core stack (the "tools we need")
| Tool | Cost | Link | What it's for |
|---|---|---|---|
| **Amazon Seller Central** | ~$40/mo (Pro) or $0.99/item (Individual) | sell.amazon.com | The seller account itself — list, ship, get paid. |
| **Keepa** | ~$20/mo | keepa.com | Price + sales-rank (BSR) **history** for any product. Industry standard; the `scout` AI runs on it. |
| **SellerAmp SAS** | ~$20/mo (14-day trial) | selleramp.com | Sourcing + profit **calculator**. Instantly shows ROI, profit, BSR, eligibility, Keepa data while browsing. *"Makes sourcing a thousand times more efficient."* |
| **Amazon Revenue Calculator** | free | (in Seller Central) | Final fee/profit check before buying. |

**Startup budget:** ~**$80/mo** tools + **$500–$2,000** inventory to begin.
*SellerAmp tiers: **Getting Started** (~$20, 1,000 lookups/mo) → **Getting Serious** (~$28, unlimited).*

## Discount & cashback tools (lower your cost = more profit)
Free browser extensions/sites the videos use to make thin deals profitable:

| Tool | Use |
|---|---|
| **Coupert** ("Cooper") | auto-applies coupon codes at checkout |
| **RevROI** | compares cashback rates across sites |
| **TopCashback / Rakuten / BeFrugal** | cashback (lowers COGS; don't bake into the math) |
| **gift card wiki** / **cardbear.com** | aggregate discounted gift cards (cardbear has price-drop alerts) |
| **Boxem** | all-in-one ungating/listing/shipping + bulk auto-ungate checker (2-wk trial) |
| **Target Circle / Subscribe & Save** | retailer discounts (cancel S&S before next ship) |

Best ungating source: **target.com** (receipts say "Invoice"). Full lists in
[`../playbooks/brands-and-sources.md`](../playbooks/brands-and-sources.md).

## Our own systems (already in this folder)
| System | Where | What it does |
|---|---|---|
| **scout** | [`../../scout/`](../../scout/) | Finds candidates via Keepa, scores buy/no-buy, alerts Discord, learns from my labels. |
| **scout_pro** | [`../../scout_pro/`](../../scout_pro/) | Full-stack version: hard gates → ML scoring → review queue → retraining. |
| **tracker site** | [`../../tracker/`](../../tracker/) | Learning-progress web page (could grow into the control center). |
| **Operator brief** | [`../../01_research_brief.md`](../../01_research_brief.md) | Deep, sourced FBA reference (private-label focus). |

## SellerAmp ↔ our AI
SellerAmp is my **research front end**; its readouts get captured in the
[buy/no-buy template](../ai-system/product-research-template.md) and become the
honest data/labels that train the scout. Details in
[ai-system vision](../ai-system/vision-and-requirements.md).

## Learning resources
- **My mentor** (dad's friend, OA since 2017) — primary resource. Questions in
  [`questions-for-mentor.md`](questions-for-mentor.md).
- **Video transcripts** I add to [`../transcripts/`](../transcripts/) — distilled into
  `transcripts/insights.md`.
- Free, current YouTube/creator content (the tracker page can surface tuned searches).

> **Spending caution (from `04_limitations.md`):** don't buy a $1,000–$3,000 course
> before selling anything. I have a mentor and trusted free sources — validate the
> model first, spend on courses later (if ever).
