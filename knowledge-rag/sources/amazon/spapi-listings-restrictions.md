---
title: SP-API Listings Restrictions API — "can I list this ASIN?"
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/listings-restrictions-api.md
category: Listing rules
collected: 2026-06-23
---

# Listings Restrictions API (SP-API)

Programmatically check whether **restrictions prevent creating a listing** for an item in the
Amazon catalog — the automation answer to the arbitrage question *"am I allowed to sell this?"*.

- `getListingsRestrictions` takes an **ASIN** (or brand name, or brand + product type) and returns
  any restrictions, optionally **filtered by condition type** (new/used). Checks **multiple
  marketplaces in one call**.
- If an item **is restricted**, the response includes **next-step links to request approval**
  (ungating). When you provide brand + product type, it also evaluates **GTIN exemption** and can
  auto-approve eligible combinations.
- Pair it with the **Listings Items API**: first check restrictions here; if none, create the
  offer-only listing. Requires the **Product Listing** role; sellers only; version v2021-08-01.

**Why it matters for the scout:** this is the API that turns the manual "check gating in Seller
Central" step into an automated pre-buy gate — surface only ASINs your account can actually list.
