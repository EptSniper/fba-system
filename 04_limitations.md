# What this does NOT do (and where you still need judgment)

Read this before trusting any output. These artifacts are an honest scaffold for
learning and triage — not a money machine, not financial advice, and not a substitute
for your own checks.

## Across everything
- **No income promises.** A realistic private-label launch costs ~$2,500–$5,000 and
  takes ~3–6 months to a first profitable month. Most sellers earn modest revenue.
  There are **no guaranteed returns**, and nothing here changes that.
- **Eligibility is real.** You must be **18+** to hold an Amazon seller account.
- **Fees and policies move.** Numbers were verified for **Q2 2026** (incl. the 3.5%
  fuel surcharge live since Apr 17, 2026, and the 75-char title rule landing Jul 27,
  2026). Re-verify in Seller Central before you commit money — especially the
  low-inventory-level fee threshold, where sources disagree (28 vs 35 days).
- **No Amazon scraping.** Everything uses sanctioned sources (Keepa, and — for your own
  store — Amazon's SP-API). If you bolt on scraping, that's on you and against ToS.

## The research brief
- It **synthesizes sources**; it is not original market data. Agency case studies (e.g.,
  the pet-supplement turnaround) are **self-reported** and labeled as such. The launch
  study is from a defined sample/time window. Treat practitioner blogs as signal, not proof.
- It does **not** pick a product for you or tell you a niche is "safe."

## The tracker website (`tracker/index.html`)
- It tracks **learning and process**, not your real Amazon account. Checkboxes and the
  readiness gauge measure *your study progress*, nothing about live sales.
- **Progress is local only** (browser `localStorage`). Clearing site data or switching
  devices/browsers resets it. There is no account or cloud sync.
- **YouTube:** without an API key, "Find videos" opens a tuned YouTube search (always
  current, zero cost). With a key, it shows the top embeddable results inline and uses
  ~100 quota units per search (10,000/day free). It does **not** rank, cache, or judge
  video *quality* — relevance is YouTube's, not ours.
- It is a **single static file** by design — no backend, no AI coach, no Keepa/Deal-
  Analyzer modules. Those are the v2 in the uploaded blueprint.

## The product scout (`scout/`)
- **Requires a paid Keepa key** to do anything real. No key → no data.
- **Scores are heuristics.** The rule score and the fee/margin estimate are based on
  limited fields (weight, not true dimensions; assumed COGS/PPC). **Always confirm a
  real SKU in Amazon's Revenue Calculator** before buying.
- **Keepa field names / Product Finder params drift.** Confirm them via
  `help(api.product_finder)` or Keepa's "SHOW API QUERY" — the included query is a
  starting point, not guaranteed-correct for your Keepa version.
- **"Sales Rank Drops" are estimates** — accurate at low volume, noisy above ~50/mo.
- **Competitor signals are proxies**, never exact private sales.
- **The model only learns from honest labels.** With < ~20 labeled outcomes it runs on
  the rule score alone. Garbage or biased labels → a worse model. It will not discover
  winners on its own, and it does **not** place orders, set prices, or move money.
- **Not implemented (intentional):** SP-API integration, Customer Feedback API features,
  a Discord bot with approval buttons, champion/challenger model evaluation, and the
  full Next.js/Postgres dashboard from the blueprint. These are documented v2 hooks.

## Where your judgment is irreplaceable
Sourcing and supplier vetting (always inspect the first order), category gating and
restrictions, hazmat/lithium rules, trademark/IP and Brand Registry, real landed-cost
math, cash-flow timing, and the final buy/no-buy call. The tools narrow the field;
**you** make the decision.
