# The AI We're Building — Vision & Requirements

*The north-star spec for the assistant / "control center." Captured from Mehmet's
own words and mapped to what already exists in this folder. Updated 2026-06-19.*

---

## What I (Mehmet) want it to do — in my words

1. **Find items for us** to sell (product/deal discovery).
2. **Tell me if an item is a good buy or not** based on the research I do.
3. **Track our finances** (what we spent, made, profit, ROI).
4. **Manage / make it easy to view & control inventory** with Amazon.
5. **Learn from this chat** — feed it everything useful from our conversations.
6. Eventually become a **control center** (one place to view & control it all),
   maybe a website.

I think **SellerAmp SAS** will be useful for the AI — integrate it.

---

## What already exists in this folder (don't rebuild)

| Capability | Where | State |
|---|---|---|
| Item discovery via Keepa + scoring + Discord alerts | [`../../scout/`](../../scout/) | **Runnable** (needs paid Keepa key) |
| Full-stack discovery: gates → ML classifier → ranker → review queue → retrain | [`../../scout_pro/`](../../scout_pro/) | **Runnable** (SQLite/Postgres) |
| Learning loop (model improves from *my labeled outcomes*) | scout `train.py` | Implemented |
| Buy/no-buy *rule score* + 2026 fee/margin estimate | scout `scoring.py` | Implemented |
| Honest limits & "what it does NOT do" | [`../../04_limitations.md`](../../04_limitations.md) | Read this |
| Learning-progress tracker web page | [`../../tracker/`](../../tracker/) | Static site |

**Translation:** "find items" and a first-pass "is this a good buy" already exist.
The gaps are: **using my SellerAmp research as input**, **finances**, **inventory**,
and **tying it together into one control center.**

---

## Requirement → plan (each goal mapped)

### 1 & 2 · Find items + judge buy/no-buy from my research
- The scout finds candidates from **Keepa** and scores them.
- **SellerAmp SAS is the human-research front end.** When I analyze a product in
  SellerAmp, I capture its readout (ROI, profit, BSR, # sellers, eligibility, COGS,
  sell price) using [`product-research-template.md`](product-research-template.md).
- That captured research becomes **two things**: (a) a record the AI can judge with
  a transparent **buy/no-buy checklist**, and (b) a **labeled outcome** later
  (did it sell? at what margin?) that trains the scout to match *my* real winners.
- **Verdict logic (v1, transparent):** PASS only if eligible/not gated **and**
  ROI ≥ 30% after fees **and** BSR healthy for the category **and** Keepa shows
  consistent sales (not a one-time spike) **and** Buy Box/offer count not brutal.
  Anything ambiguous → "review," never an auto-yes.

### 3 · Track finances
- Start simple and structured (so the AI/website can read it):
  [`../tracking/finances.md`](../tracking/finances.md) = a purchase ledger + running P&L.
- Later: pull **real** numbers from Amazon via **SP-API** (payouts, fees, refunds)
  — already a documented stub in `scout_pro/connectors.py`.

### 4 · Manage / view inventory
- Start: [`../tracking/inventory.md`](../tracking/inventory.md) — units owned, in-transit,
  at FBA, sell-through, restock flags.
- Later: SP-API inventory sync for live stock + low-stock alerts.

### 5 · Learn from this chat
- The capture system ([`../tracking/session-archive.md`](../tracking/session-archive.md),
  [`links-and-assets.md`](../tracking/links-and-assets.md),
  [`../knowledge-index.json`](../knowledge-index.json)) is the AI's long-term memory.
  Everything we discuss is stored in a structured, machine-readable way it can load.

### 6 · Control center
- All `tracking/` files use consistent structure and `knowledge-index.json` is a
  manifest. A future web dashboard (extending [`../../tracker/`](../../tracker/)) can
  read these + scout alerts + finances to become one view-and-control hub.

---

## Where SellerAmp SAS fits (the integration)

SellerAmp doesn't have a public buy-data API the way Keepa does, so the integration
is **workflow-level, not a live API** (for now):

1. **Input capture:** I research in SellerAmp → log the readout via the template →
   it's stored as structured data the AI reads.
2. **Cross-check:** the scout's Keepa-based estimate and SellerAmp's numbers should
   agree; disagreements are a flag to slow down.
3. **Source of truth for labels:** my SellerAmp-driven buy decisions + their real
   outcomes are the **honest labels** that train the scout (`train.py`).
4. **Future:** if/when I want automation, SellerAmp data can be entered into the
   scout DB so verdicts and history live in one place.

---

## Build order (crawl → walk → run)
- **Now (v1, manual+rules):** capture chat + research + finances + inventory in
  these files; use the scout rule-score + checklist for buy/no-buy. *The "AI" is me
  + the transparent rules.*
- **v2 (data flywheel):** run scout on Keepa; log my real outcomes as labels; keep
  finances/inventory in structured files; let the model start to help rank.
- **v3 (control center):** wire **SP-API** for live finances + inventory; build the
  web dashboard that unifies tracker + scout + finances + this archive.

> **Honesty (from [`../../04_limitations.md`](../../04_limitations.md)):** this is a decision-support
> system, not autonomous magic. It never moves money, never auto-buys, and hard
> compliance/margin gates always override the model. I make the final call.
