# Deal-Sourcing System — the always-on deal tracker

*Adapted from the uploaded "Building an Automated Arbitrage Sourcing System" PDF and
the sourcing course, fitted to our scout + control center. Goal: continuously find
"buy cheap → sell on Amazon for profit" opportunities — **source where the best sale
is TODAY** (Target BOGO today, Walgreens BOGO tomorrow), not where it was yesterday.
Created 2026-06-20.*

---

## The core idea (from the course)

> "It's all about **where is the best place to source TODAY** — where there's a sale,
> high cashback, or a coupon — then stack discounts (manufacturing margin) for a moat."

So the deal-scout's job is to watch many retailers' **sales / clearance / coupons /
BOGOs** and surface the ones that are profitable to flip on Amazon **right now**.

## How it extends the existing scout (not a rebuild)

The product scout already finds via **Keepa** and rates buy/no-buy. The deal-scout adds
a **second discovery source** — retail deal feeds — then runs the **same rater**:

```
  DISCOVERY (new)                MATCH + PRICE                 RATE (reuse)            ACT
  ──────────────                 ─────────────                 ───────────            ───
  • Deal APIs (FMTC,             match deal item → Amazon      same ai-brain.json     • Discord alert
    LinkMyDeals)        ──────►  ASIN; fetch buy-box price,    criteria: BSR<=200k,   • control center
  • Retailer feeds (affiliate)   sales rank, offers, Amazon-   ROI>=30%, $3 profit,     "Deals" module
  • BrickSeek / Slickdeals       on-BuyBox (Keepa / SP-API)    seller band, hard-       (data/deals.json)
  • the "today's best sale"                                    reject Amazon BuyBox
    list                         apply discount stack ───────► + IP-risk screen
```

**Profit math (from the PDF):** `ROI = (Amazon sell price − landed retail cost − Amazon
fees) / landed retail cost`. Landed cost includes the deal price **minus** stacked
discounts (cashback / discount gift cards / coupons). Confirm in SellerAmp before buying.

## Deal sources & tools (the registry)

- **Deal aggregator APIs (the clean way):** **FMTC**, **LinkMyDeals**, **Takedeals** —
  normalized coupon/sale feeds across thousands of retailers; filter by store/type
  ("Target coupons", "Walgreens BOGO").
- **Retail trackers:** **BrickSeek** (Walmart/Target stock + clearance), **Slickdeals**
  (community-voted deals), **ProfitPath Dealwatch** (price-drop monitoring + alerts).
- **Sourcing scanners:** **Tactical Arbitrage** (scans 1,400+ sites, computes FBA ROI,
  bakes in coupon codes), **BuyBotPro** (1-click deal analysis). Study these as the
  feature checklist.
- **Discount stack (manufacturing margin):** cashback — **Rakuten, TopCashback,
  BeFrugal, RetailMeNot** (compare via **RevROI**); discount gift cards — **cardbear.com,
  raise.com, TopCashback gift cards**; coupons — **Coupert, Capital One Shopping**.
- **Risk screen:** **IP Alert** — flags brands that file IP complaints (avoid the Keepa
  "cliff"); plus our seller-spike + brand-on-listing + Amazon-BuyBox checks.

## Compliance (do it the right way)

The deal PDF's companion (RAG plan) is blunt about Amazon's ToS, and retailers have terms
too. So: **prefer official deal APIs and affiliate feeds over scraping**; respect each
retailer's robots/ToS; identify any automated agent honestly; don't hammer sites. The
profitability layer uses **Keepa (licensed) / SP-API (your own account)** — never Amazon
scraping. This keeps the system defensible.

## Build phases (each useful on its own)

- **Phase 1 — manual + the rater (works today).** A curated "today's best sales" list +
  the existing buy/no-buy rater (SellerAmp/scout). Even just *knowing where the deal is
  today* + stacking discounts is most of the edge. → seeds `data/deals.json`.
- **Phase 2 — deal API.** Integrate **one** deal API (FMTC or LinkMyDeals), normalize to
  `deals.json`, match to ASINs, run the rater, post winners to Discord + the Deals module.
- **Phase 3 — scheduled + alerts.** Cron/cloud job runs hourly/daily; "Target BOGO on
  [item] $X → Amazon buy box $Y → ROI Z% → source it" alerts; control center Deals page live.
- **Phase 4 — watch the moat.** Re-check Amazon price/Buy-Box on sourced items (SP-API)
  and re-rate when the market shifts.

## How it plugs into everything

- **ai-brain.json → `dealSourcing`** holds the principle + sources + tools (single source).
- **Control center → Deals module** reads `data/deals.json` (honest empty until connected).
- **The scout** can ingest deal candidates the same way it ingests Keepa candidates.

> Honest status: this is **designed + surfaced**, not live. Going live needs a deal-API key
> (and/or SP-API). The highest-leverage first step is Phase 1 — a daily "where's the best
> sale today" habit + the rater — which needs no new keys.
