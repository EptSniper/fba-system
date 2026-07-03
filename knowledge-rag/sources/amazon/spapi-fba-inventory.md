---
title: SP-API FBA Inventory API — real-time inventory states
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/fba-inventory-api.md
category: FBA operations
collected: 2026-06-23
---

# FBA Inventory API (SP-API)

Retrieve and track **real-time availability** of your inventory in Amazon's fulfillment network at
the marketplace level (`getInventorySummaries`). Inventory is reported in these states:

- **Fulfillable** — can be picked, packed, and shipped (sellable now).
- **Inbound** — on its way to Amazon's fulfillment network.
- **Reserved** — being picked/packed/shipped, or sidelined for measurement/sampling/internal processes.
- **Unfulfillable** — cannot be sold (damaged, expired, etc.).
- **Researching** — misplaced or warehouse-damaged units being confirmed at an FC.

Available in all marketplaces; requires the **Amazon Fulfillment** or **Product Listing** role.

**Why it matters:** this is the live feed the control center's Inventory module would use to show
units at FBA, in transit, and stranded/unfulfillable — replacing the manual inventory tracker.
