---
title: SP-API Finances API — real fees, transactions, settlements
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/finances-api.md
category: APIs and data
collected: 2026-06-23
---

# Finances API (SP-API)

Get the **actual financial events** for your orders — without waiting for a statement period to
close. Version v2024-06-19; requires the **Finance and Accounting** role; sellers only.

- `listTransactions` — review transactions on the account (per order or date range).
- Determine which released transactions make up a given **payment/payout**.
- v0 also offers current **balance**, payment amount/status, and financial-event groups.

**Why it matters for the system:** this is the source of **real, realized numbers** — actual Amazon
fees, refunds, and payouts per ASIN. Feeding these back closes the scout's learning loop: instead of
*estimated* ROI, the scout can label each pick with its **realized** ROI/returns and learn from true
outcomes. It's also what powers the control center's Money module with live profit instead of
manual entry.
