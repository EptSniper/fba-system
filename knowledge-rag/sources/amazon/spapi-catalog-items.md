---
title: SP-API Catalog Items API — product data by ASIN / keyword
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/catalog-items-api.md
category: APIs and data
collected: 2026-06-23
---

# Catalog Items API (SP-API)

Pull detailed catalog data for an item, or search the catalog. The data this returns is exactly
what a finder/rater needs to enrich a candidate:

- **getCatalogItem** (by ASIN + marketplaces) returns: summarized details, **attributes**,
  **browse classifications** (category — drives the referral-fee %), **dimensions** (size tier →
  FBA fee), **product identifiers** (UPC/EAN/GTIN), **images**, **sales rankings** (BSR), and
  **relationships** (variations).
- **searchCatalogItems** — find items by identifier, product code, or **keyword**.
- Sellers and Vendors; **Product Listing** role; v2022-04-01.

**Why it matters:** Keepa gives price/BSR history; Catalog Items gives the authoritative
category + dimensions + identifiers straight from Amazon — so the scout can pick the *correct*
referral-fee % (see selling-fees.md) and size-tier FBA fee instead of guessing, and match a retail
UPC to its Amazon ASIN automatically.
