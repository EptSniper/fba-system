# Amazon cash flow management: the FBA seller playbook (Nova Analytics)

- **URL:** https://novadata.io/resources/blog/amazon-cash-flow-management-fba-sellers
- **Fetched:** 2026-07-02 (article updated 2026-05-06)
- **Type:** [practitioner] — analytics vendor blog; DD+7 mechanics reference Amazon's Finances API docs but confirm in Seller Central
- **Topic:** fba_oa_mastery (finances/cash flow)

## Cleaned content (condensed)

Core claim: most Amazon sellers have a cash flow problem dressed up as a profit problem — Amazon collects
from buyers immediately but holds seller money, while the seller has already paid supplier, freight, and ads.
Growth makes it worse: every extra revenue dollar ties up working capital first.

### How Amazon actually pays (4 moving parts)
1. **DD+7 disbursement clock** — since **March 12, 2026**, every seller account runs on Delivery Date + 7:
   the clock starts at carrier-confirmed delivery, then Amazon holds funds 7 calendar days before queueing
   the transfer. Fast 2-day Prime FBA often pays *faster* than the old 14-day cycle; slow FBM/economy
   shipping stretches sale→bank to 17–21 days.
2. **Reserve hold** — new sellers see 50–100% reserves for the first 90 days; established sellers typically
   3–12% of recent revenue held at any time. Reserve grows automatically with sales velocity, so a great
   week shrinks the next disbursement before it grows it.
3. **Transfer lag** — bank receives funds 3–5 business days after Amazon initiates; cross-border adds 1–3.
4. **Account-level holds** — policy issues/IP complaints can freeze disbursements without warning; rarely
   visible until the transfer date passes.

### The 5 cash leaks
1. Reserve growth on a hot month (a 30% revenue jump can pull an extra 6–10% into reserve — model reserve
   as % of trailing 14-day sales, not a fixed number).
2. Returns posted to the wrong period (buyer refunded immediately; cost posts to the *next* settlement).
3. FBA storage fee spikes (Oct–Jan elevated; LTSF + aged-inventory surcharges hit the 15th monthly).
4. PPC overshoot (ad spend deducts from the disbursement — model as cash outflow, not just a margin line).
5. COGS-to-cash lag (wire supplier day 0 → cash back ~day 70; sellers underestimate by ~30%).

### Cash conversion cycle
CCC = DIO + DSO − DPO. Typical FBA: DSO 14–22 days; whole cycle 60–120 days. Worked example
($500K/mo, 35% COGS): DIO 62 + DSO 18 − DPO 45 = 35-day CCC ≈ ~$200K working capital tied up; cutting DIO
by 15 days frees ~$87K without changing margin.

### Weekly Monday routine (4 numbers, investigate >10% moves)
1. Net disbursement vs forecast. 2. Total reserve balance WoW. 3. Days of inventory on hand by category
(>90 days = eating storage; <21 days = stockout risk). 4. Contribution margin per SKU, rolling 28 days.

### Working capital options
Supplier terms (free, first lever) → Amazon Lending (fast, 10–17% APR, repayment locked to disbursements) →
bank LOC (prime+2–5%, slow setup) → AR/inventory financing (12–24% APR, fast).

### Forecasting
13-week rolling cash forecast; replace forecast with actuals every Monday; clean SKU-level fee inputs get
forecasts within 5–8% of actual disbursements.
