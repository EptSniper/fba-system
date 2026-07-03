---
title: SP-API Fulfillment Inbound API — Send to Amazon shipments
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/fulfillment-inbound-api.md
category: FBA operations
collected: 2026-06-23
---

# Fulfillment Inbound API (SP-API)

Create and manage **inbound shipments** into Amazon's fulfillment network — the API behind the
**Send to Amazon (STA)** workflow. Plans created via API can be edited in STA and vice-versa
(once placement + transportation options are confirmed). Version v2024-03-20; Amazon Fulfillment role.

> ❗ **Important (US):** Starting **January 1, 2026**, Amazon's prep and item-label services are no
> longer available for FBA in the US. **The seller must prep and label all products** before
> sending them in. (Direct impact on OA: budget your own poly-bagging, labeling, and prep time/cost.)

## Shipping options
- **Small Parcel Delivery (SPD)** — individual boxes, with an **Amazon-partnered carrier (PCP)** or
  your own **non-partnered carrier (nPCP)**.
- **Pallets (LTL/FTL)** — partnered or non-partnered; "Pack Later" lets you create pallet deliveries
  before carton info is known.
- **Amazon-recommended packing** — group SKUs into pack groups Amazon suggests to earn a
  **fulfillment discount** (SPD, parcels < 15 kg).

## Flow
Create inbound plan → generate/confirm **placement** options → generate/confirm **transportation**
options → set packing info → get box/pallet labels + bill of lading → ship. `getLabels` and
`getBillOfLading` are required to actually create shipments.

**Why it matters:** automates shipment creation and surfaces the partnered-carrier + recommended-
packing discounts that protect thin OA margins.
