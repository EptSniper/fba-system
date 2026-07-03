# Listings Restrictions API (Amazon Selling Partner API)

- URL: https://developer-docs.amazon.com/sp-api/docs/listings-restrictions-api
- Date fetched: 2026-07-01
- Classification: [policy] — official Amazon SP-API developer documentation.

## Takeaways

- **What it does.** `getListingsRestrictions` (Listings Restrictions API v2021-08-01) programmatically checks whether restrictions exist that would block creating a listing for a catalog item — identified by ASIN, by brand name, or by brand + product type. This is the SP-API equivalent of manually checking "Listing Limitations Apply" in Seller Central, and could programmatically back `fba-compliance-checker`'s ALLOWED/BLOCKED/VERIFY logic if the project ever integrates SP-API.
- **Multi-marketplace + condition-type filtering in one call.** Supports checking several marketplaces at once and optionally filtering restrictions by condition type (New, Used, etc.) in a single request — relevant if the scout ever needs to batch-check eligibility across leads instead of one-by-one.
- **GTIN exemption auto-evaluation.** When you pass a brand together with a product type, the API also evaluates GTIN-exemption restrictions, which can enable auto-approval of GTIN exemptions for eligible combinations — a detail worth knowing if the project ever needs to list without a UPC/GTIN.
- **Approval next-steps returned inline.** If an item is restricted, the response includes "next step" links toward requesting approval to create the listing — useful for surfacing a direct "how do I get ungated for this" action rather than just a boolean blocked flag.
- **Pairs with the Listings Items API.** Recommended pattern: call Listings Restrictions first; if clear, call the Listings Items API to create an offer-only listing. Two-step check-then-act flow.
- **Access requirements.** Sellers only (not vendors); requires the "Product Listing" SP-API role; available in NA/EU/FE regions; static (non-dynamic) rate-limited endpoint. Latest release note as of this fetch: May 27, 2026.
- **Relevance to this project:** this is the concrete API path if `fba-compliance-checker`'s eligibility checks are ever automated beyond manual Seller Central lookups — captured here as a build-reference, not something to wire up without an explicit decision (would need SP-API app registration/credentials, kept out of the browser per the no-secrets-in-browser rule).
