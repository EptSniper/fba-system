# Claude Code directive — wire SP-API as the free ASIN-resolution + eligibility layer (the token cost-killer)

Paste the block below into Claude Code. This makes free Amazon SP-API do the discovery/eligibility work Keepa currently charges ~30 tokens/deal for, so deal matching drops to ~1–5 tokens/deal. Sequence this BEFORE bulk deal matching. Guardrails: SP-API creds are server-side only (never browser); eligibility feeds the hard compliance gate (stays outside ML); no auto-buy; `fba-code-reviewer` + `fba-qa-tester` before ship; `fba-session-journal` at the end.

## PREREQUISITE — Mehmet must provision SP-API credentials (human step, gating)
The scaffold (`scout/spapi.py`) is fully built + mock-tested but has NEVER made a real call — every `SP_API_*` value is a placeholder. Mehmet: register a **self-authorized private developer app** in Seller Central (Apps & Services → Develop Apps), grab the LWA **client id + secret + refresh token**, and put them in `scout/.env` (+ `API_KEYS.env`): `SP_API_LWA_CLIENT_ID`, `SP_API_LWA_CLIENT_SECRET`, `SP_API_REFRESH_TOKEN`, `SP_API_SELLER_ID`. Solo Professional-plan seller, no restricted roles needed — typically days. Nothing below runs live until these exist (`spapi.configured()` gates every path).

## Build (Claude Code)

1. **Add free title→ASIN search to `spapi.py`.** Today only `catalog_lookup_upc` (UPC→ASIN) exists. Add `catalog_search_keywords(query, brand=None) -> [{asin, brand, title, ...}]` using the SAME Catalog Items API `/catalog/2022-04-01/items` with `keywords` + `includedData=summaries,identifiers` on the existing 2 req/s `catalog` limiter. This is the free replacement for the Keepa 10-token title search. `fba-coder` + `fba-qa-tester` (mock-test like the existing endpoints).

2. **Rewire the matcher's candidate generation to SP-API first, Keepa last.** In `scout/deals/matcher.py`, `_upc_candidates`/`_title_candidates` should resolve ASINs via SP-API when configured: UPC → `catalog_lookup_upc` (exact); else → `catalog_search_keywords`. Keepa is then used ONLY to price the already-resolved ASIN (a `query_history`/`enrich` on a known ASIN), not to discover it. Fall back to the current Keepa search only when SP-API is unconfigured or returns nothing. Net: ~30 tok/deal → ~1–5 tok/deal. `fba-architect` confirms the seam; `fba-ml-guardian` confirms hard gates unaffected.

3. **Use eligibility as a FREE pre-filter in the funnel.** Before spending any Keepa token (and before D3 creates a lead), call `get_listings_restrictions(asin)` — drop `NOT_ELIGIBLE`, flag `APPROVAL_REQUIRED`. This both saves tokens (don't price a product you can't sell) and feeds the real compliance gate. The 7-day Supabase cache already exists — use it; never re-check a fresh ASIN.

4. **Optional bonus — real fees on survivors.** For a matched buy candidate, `get_fees_estimate(asin, price)` returns Amazon's ACTUAL referral + FBA fees (1 req/s — survivors only). Feed it into the profit/ROI math as the honest fee source, falling back to the rule-based estimate and recording which was used. Improves the label accuracy too.

5. **Live-verify before wiring in.** Once creds exist: run a careful smoke test — one real call to each of the three endpoints (restrictions, catalog UPC, catalog keywords), confirm the responses parse against the code's assumptions (the module is UNVERIFIED against the live API), THEN enable it in the pipeline. Keep the `configured()`/`available:false` honest-degradation paths intact.

## Token accounting to report
Per-deal matching cost before vs after SP-API (measure it), and confirm eligibility pre-filtering + the 7-day cache keep Keepa spend on discovery near zero. Keepa's remaining job: price the survivors only.

## Where this sits in the sequence
SP-API (this) → then D3 deal-first lead creation → then match the ~1,069 in-band priority subset cheaply → then real-cost leads → then retie the ML label + re-run walk-forward. This directive is the prerequisite that makes the rest affordable on a 1,440-token/day budget.
