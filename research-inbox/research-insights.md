# Research insights (staged)

Distilled, actionable takeaways from material the daily pipeline ingests — grouped by topic. These are
staged here for review before merging into the maintained playbooks / `learning-hub/`. Mark each takeaway
as **[policy]** (verifiable Amazon documentation) or **[practitioner]** (creator opinion, treat as input),
per the project's source-of-truth order. Cite the source URL.

## Amazon FBA / online arbitrage

### 2026-06-30
- **[policy]** 2026 US FBA fees rise an **average of $0.08/unit**, effective **Jan 15 2026**; **referral fees
  and fee types unchanged**. "Average" is tiered by size/price band — recheck each ASIN, don't assume the
  average. Recompute with Amazon's Revenue Calculator / Fee & Economics Preview / Profit Analytics (updated to
  2026 rates). A separate **April 17 2026 fuel & logistics surcharge** is reported by secondary sources —
  confirm in the official detail page before trusting ROI. (sellingpartners.aboutamazon.com/update-to-u-s-referral-and-fulfillment-by-amazon-fees-for-2026)
- **[policy]** Amazon enforces only three IP categories — copyright, trademark (incl. counterfeit), patent —
  via the public Public Notice Form and the Brand-Registry-only Report a Violation tool (needs a *fully
  registered* trademark). Amazon says **99% of suspected infringements in 2024 were blocked proactively**, so
  brand-protected listings are increasingly auto-enforced. Screen brand/IP risk before buying.
  (sell.amazon.com/blog/report-a-violation-to-amazon)

### 2026-07-01
- **[practitioner]** Restricted-category screening is a *pre-sourcing* step, not post-purchase. High-gate
  categories in 2026: Beauty/Personal Care, Dietary Supplements, Health, Grocery, Electronics
  (batteries/wireless), Jewelry, Medical Devices, children's Textiles. Approval docs are category-specific
  and strict (supplements: ISO/IEC 17025 CoA <6 mo; electronics: FCC ID / UL; food: FDA reg + 50+ day shelf
  life; devices: FDA 510(k)) — a plain distributor invoice is often not enough. Ungating runs ~1 wk–1 mo and
  ~$500–$2,000+; the downside of listing un-approved is account-level (suspension/ban), not just a lost sale.
  Verify each gate live via "Add a product" → "Listing Limitations Apply" → "Apply to Sell".
  (sellerlabs.com/blog/amazon-restricted-products-2026) [practitioner — vendor blog, confirm in Seller Central]
- **[policy]** Amazon's **Listings Restrictions API** (`getListingsRestrictions`, SP-API v2021-08-01) can
  programmatically check whether a listing is blocked, by ASIN or brand+product-type, across multiple
  marketplaces in one call, and returns "next step" links toward approval when restricted — the SP-API
  equivalent of manually checking "Listing Limitations Apply" in Seller Central. Sellers-only, requires the
  Product Listing SP-API role. Pairs with the Listings Items API (check restrictions, then create the
  listing). **Not wired up** — flagged here as the concrete API path if `fba-compliance-checker`'s
  eligibility checks are ever automated; would need SP-API app registration/credentials kept server-side, no
  auto-listing without explicit approval. (developer-docs.amazon.com/sp-api/docs/listings-restrictions-api)
- **[practitioner]** *Buy the price cycle; don't hold dead stock.* Many evergreen listings oscillate between
  price bands several times a year — buy at the low (offers falling), sell through the ~2–8-week upswing, then
  wait to re-buy next cycle. Prefer **retail-priced evergreen** (reverse-sourced) listings over clearance,
  which saturates the moment it hits FBA. (youtube.com/watch?v=pP-zQ4-u370)
- **[practitioner]** Two fresh 2026 beginner guides restate the buy box already in `ai-brain.json` — **<200k
  BSR, ≥30 sales/mo, ≥$3 profit, ≥30% ROI** (25% OK for durable non-returnables), storefront stalking as the #1
  method, and "**you make items profitable (discount stacking), you don't find them profitable**." Sharper bits:
  all-FBM + heavy + cheap (<$50) listings are usually dropshippers → skip; cited tool stack ~$99/mo (SellerAmp
  ~$20 + Keepa ~$29 + Boxem ~$50, 2-week trials). (youtube.com/watch?v=OUGc0aiT7l4, youtube.com/watch?v=V0lMedQJzmQ)

### 2026-07-04
- **[practitioner]** Sales rank (the green line) should be read against its PARENT category, not a
  subcategory — subcategory rank can mislead, especially on listings with no Monthly Sold data point to
  cross-check against. Pair BSR with the "Monthly Sold" estimate (trailing-30-day, not exact units) as the
  real demand signal. A healthy new-offer-count line moves up and down over time (sellers cycle in/out);
  a flat, unchanging seller count — even a high one — means the listing isn't actually moving.
  (youtube.com/watch?v=XdUGuD4ouKI)
- **[practitioner]** A rapid, large seller-count jump (e.g. 1→43 sellers within ~2 weeks) is a strong
  precursor to a price crash — treat a sudden offer-count spike as a pass signal absent a real edge (FBM
  speed, unusually low cost, or genuinely huge volume). Never price off the current spot alone — expand to
  1+ years of history; a current multi-year-peak price with a much lower trailing-12-month range should be
  expected to revert by the time inventory lands. Also check for seasonal/event-driven demand (summer,
  Easter, movie tie-ins) by zooming out — buying at a seasonal peak risks both a price drop and dead stock
  once the season ends. (youtube.com/watch?v=XdUGuD4ouKI)
- **[practitioner]** Amazon-on-listing is only disqualifying if Amazon holds the Buy Box almost
  exclusively (check Buy Box Statistics' 30/90/180/365-day splits, not just current status); a single
  seller dominating the Buy Box while priced HIGHER than competitors → avoid (won't get sales), but
  dominating while priced LOWER can still be worth testing. Sharp seller-count collapses on a brand-owned
  listing ("Keepa cliffs," e.g. 32→4 sellers) are the strongest signal of active IP enforcement — stronger
  evidence than a supplementary ipalert.com lookup. Avoid misbranded/generic listings (actual manufacturer
  ≠ listed brand, no "distributed by" relationship) — Amazon treats the mismatch as a counterfeit signal
  that can trigger a Section 3 suspension requiring proof of authenticity. Also avoid single-seller,
  professionally-optimized private-label listings sourced via wholesalers — tight seller control tends to
  cause account issues before inventory even lands. (youtube.com/watch?v=XdUGuD4ouKI)
- **[practitioner]** On variation listings, evaluate each child ASIN individually (its own Monthly Sold,
  reviews, price history via the Variations tab) — a parent listing can hide a profitable variation even
  if the first child you open isn't one. For sparse-data ("advanced") listings with no Monthly Sold
  estimate, triangulate via rating-count trend, the Offers tab's sold-in-last-30/90-days total, and 6-month
  stock-level changes; a long time-on-market (e.g. 239 days) with zero reviews and zero recent sales is a
  pass regardless of apparent margin. Keepa is a screening tool for throughput (screen more, find more
  winners) — once a real test-buy's sales data exists, it outweighs any Keepa estimate; test uncertain
  leads with a small quantity (e.g. 10 units), not a large order. (youtube.com/watch?v=XdUGuD4ouKI)
- **[practitioner]** **Flips4Miles full OA course, sourcing method:** of the four Amazon selling models
  (arbitrage/wholesale/PL/dropshipping), OA is the lowest-capital entry point (recommended start ~$1,000-3,000
  + ~$40/mo Seller Central + ~$16-20/mo SellerAmp + ~$20/mo Keepa) since listings already have proven sales
  history. **Storefront stalking** (browsing a high-review seller's full catalog) is the best beginner method
  — everything there already has proven demand; only move to **manual sourcing** on a specific retailer once
  storefront stalking has proven that retailer/brand reliably converts. **"Leaf sourcing"**: search a
  brand/niche directly in Amazon's own search bar (paired with SellerAmp's QuickView) and let Amazon's ranking
  surface what's actually selling. Seasonal sourcing: find a listing that spiked in a past Q4/BTS peak, use
  Keepa Buy Box Statistics (365-day, filtered to "sold at highest price"), then storefront-stalk those sellers
  for other seasonal inventory. Rough retail-to-Amazon heuristic: Amazon price should be ~2x+ the retail buy
  cost before discount stacking. (youtube.com/watch?v=PydYmi56Sso)
- **[policy]** Retail dropshipping (buying from a third-party retailer that ships straight to the Amazon
  customer) violates Amazon's seller policies — the customer can receive a package branded from a different
  retailer than they ordered from. (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Keepa/SellerAmp reading rules (this course's version):** BSR belongs to the whole
  PARENT listing, not a specific variation — always check the Variations tab for the variation with real
  offer-count movement, since a good overall BSR can mask a dead one. Only new-offer-count and price/BSR
  really matter for arbitrage: want offer count flat-or-declining and price flat-or-rising; a flat "blocky"
  chart = slow-selling, avoid. A sharp offer-count collapse on the year/all-time view = a past IP complaint
  signature, avoid going forward; rising offers + falling price = "price tanking," too easy to resource, also
  avoid. Don't trust the "sold last 30 days" estimate at face value (sellers can hide stock via a max-order-
  qty cap) — rely on offer-count trend + Buy Box Statistics history instead; that estimate also splits only
  across sellers priced within ~5-9% of the Buy Box, not evenly across every seller. Amazon-on-listing is
  workable if third parties still capture ~20%+ of Buy Box share (less if the item moves very fast); ~100%
  Amazon share + flat offers = avoid. FBM-friendliness check: 20%+ of 30-day Buy Box share going to non-FBA
  sellers signals FBM can win the Buy Box there. A listing Keepa can't identify (generic/unbranded) is a red
  flag — can't verify authenticity or sales history. Use Keepa's price/offer-count tracking alert on
  near-miss listings instead of abandoning them. (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Manufacturing margin, not finding it:** items are rarely profitable at list price —
  margin comes from STACKING a sales-tax exemption (reseller cert), site coupons, cashback extensions
  (Capital One Shopping, Rakuten, BeFrugal, TopCashback), discounted gift cards, and store loyalty cash.
  Always run BOTH FBA and FBM calculators (FBM shipping entered manually from a weight table, not assumed) —
  items priced >$20 but <1 lb tend to be more profitable FBM (avoids per-unit FBA fees while shipping stays
  cheap). If an FBM seller holds the Buy Box, price a new FBA offer ~5-10% above it to capture the "Prime
  bump." Rough shipping: ~$0.70/lb FBA inbound; FBM outbound ~a few dollars under a few oz up to ~$9-13+ past
  1 lb. Cited full-month P&L anchor: ~$322K revenue, ~$156K COGS, ~$4.5K referral + ~$22K FBA fees + ~$3K FBM
  shipping, netting ~$50-55K profit (~35% ROI on capital deployed) — offered as a real-world anchor for the
  25-35% ROI targets discussed elsewhere. (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Buy criteria (this course's version):** stay under ~200,000 BSR generally (large
  categories like clothing/home-kitchen can move at a much higher rank — offer-count movement matters more
  than raw rank); baseline $3+/unit profit and 30%+ ROI, push to ~35-40%+ for shoes/clothing (higher return
  rates), while non-returnable categories (grocery/supplements/vitamins) can work as low as ~22-27% ROI since
  there's no return risk. (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Ungating/compliance:** buy 10+ units of an already-listed ASIN from a major retailer,
  save the confirmation email as a PDF, submit as invoice documentation — unlocks the whole brand/category,
  not just that ASIN (split across multiple orders if a retailer caps quantity). Rejections on first (or many)
  submissions are normal — resubmit with more supporting docs (delivery email, product photo, card statement,
  tracking) and vary the filename; one cited case needed 27 attempts. Avoid IP complaints mainly by checking a
  brand's OTHER ASINs for a past offer-count collapse before committing to that brand at all. "Inauthentic"
  complaints are treated as a low-frequency cost of business (~1/2,000 orders per this course) — keep an
  order-tracking spreadsheet (retailer order #, supplier, ASIN, cost, date) to resubmit the original invoice
  fast. A resale/sales-tax certificate is needed for most wholesale accounts and often useful for tax-free
  arbitrage buying too (verify per retailer/state). (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Seasonal calendar (this course's version):** slower Jan-Mar; building Apr-Jun (Easter/
  Mother's/Memorial/Father's Day); BTS ~Jul 15-Sep 15 (peaking early-mid Aug); Q4 (Oct-Dec) is strongest, with
  **Nov 15 as the cutoff to stop new FBA shipments and shift to FBM**, Black Friday deals starting the Sunday
  before, and **Dec 5-20 as the best window to restock proven ASINs**. FBM favored for beginners and during
  demand spikes (same-day list/ship vs FBA's 1-3+ week inbound lag; raise expedited FBM shipping charges
  during BTS/Q4 since carrier cost stays flat); FBA wins on long-run scale and the Prime-bump price. Typical
  pattern: mostly FBA Jan-Oct, heavy FBM Nov-Dec (lighter version Jul-Aug). New FBA shipments commonly priced
  ~25% above the current Buy Box while inventory checks in, then dropped to match once fully live.
  (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Scaling notes:** test-order depth 2-10 units for a newer seller, scaling to 50-100+
  only once a SKU is proven; prep centers (often no-sales-tax states like DE/NH) ~$1-1.75+/unit, commonly
  requiring ~300-500 units/month before onboarding; VAs (Philippines/India/Pakistan) ~$3-6/hr or ~$200-500/mo
  flat, recommended around $20-30K/mo in sales, not a substitute for sourcing skill; repricing software
  (cited: BQool ~$25/mo) suggested once a store has ~10+ active ASINs. Niche notes: beauty (easy, low
  returns, low ASP, easy to saturate); toys (high ASP, very Q4-seasonal); grocery/supplements (non-returnable,
  cash-efficient at lower ROI, thin/pricey-to-ship supply); electronics (scalable, high ASP, higher returns);
  shoes/clothing (huge brands, many variations, year-round demand, higher returns — for RA, avoid
  missing/damaged shoe boxes even with no explicit Amazon rule against it, customers still expect the full
  package); sporting goods (rotates with in-season sports). (youtube.com/watch?v=PydYmi56Sso)
- **[practitioner]** **Keepa Parameter Method** — reverse-engineer a known-good OA lead's Keepa graph
  into Product Finder filters: instead of trusting the noisy "current" BSR/price, take the 30/60/90/180-day
  AVERAGES from a winning listing's Keepa Data tab and set narrow ranges around each in the Product
  Finder, plus a buy-box price-average range, to surface other ASINs with a similar sales/price shape.
  Layer in category, "Amazon out of stock," a minimum offer count (3+, to skip private-label-shaped
  single-seller listings), and "no variations" (recommended for newer sellers) to cut noise before
  eyeballing results. (youtube.com/watch?v=Cflrv_y9lSA)
- **[practitioner]** When scanning candidate Keepa graphs from a parameter search: offer count
  DECREASING while price holds/rises = sellers thinning out, a buyable signal; offer count rising while
  price falls = competitive pressure, a pass signal. Also verify a "Walmart"-labeled listing is actually
  sold-and-shipped by that retailer (not a third party riding the listing) before trusting its price, and
  check whether Amazon itself is the seller before sourcing from your own Prime account.
  (youtube.com/watch?v=Cflrv_y9lSA)
- **[practitioner]** Very low sales-rank targets (~10,000 BSR) in this method tend to surface
  wholesale-shaped items with thinner margins rather than genuine OA opportunities — a moderate BSR band
  works better for parameter-matching. Cited example target: ~40% ROI / ~$4 profit per unit; the
  presenter's own worked example noted peak-Q4 storage/fee rates cost about $1/unit versus non-Q4 timing.
  (youtube.com/watch?v=Cflrv_y9lSA)

### 2026-07-02
- **[practitioner]** **Meltable window check — it's the restricted season right now.** Amazon-classified
  meltables (all chocolate, gummies/gel supplements, wax melts, some cosmetics; anything degrading at 155°F)
  are FBA-inboundable only **Oct 16 – Apr 14**; from **Apr 15 – Oct 15** they arrive unfulfillable and can be
  disposed of at the seller's cost, with listing suppression on complaints. So through mid-October any
  meltable lead is **FBM-only** regardless of margin; remove unsold meltables from FBA before ~early April
  (removals take 10–14 business days). Amazon publishes a downloadable Meltable ASIN List; reclassification
  appeals need a manufacturer letter proving 155°F tolerance — and complaints can re-suppress anyway.
  (sellerassistant.app/blog/amazon-meltable-fba-inventory-all-you-need-to-know) [practitioner restating
  Amazon policy — official help page G200140860 is JS-rendered, not fetchable this run; verify dates in
  Seller Central]

### 2026-07-03
- **[practitioner]** Full 2026 fee-change map in one place (Seller Snap, updated Apr 2026), extending the staged
  fee notes with the pieces our math doesn't model yet: **low-inventory-level fee is now seller-FNSKU-level**
  (triggered only when BOTH 30-day AND 90-day days-of-supply < 28; $0.32–$2.09/unit; new sellers exempt 365
  days, <20 units/7 days exempt — most small-OA SKUs dodge it, but check before deep replen buys);
  **returns-processing fee** hits only above category return-rate thresholds (Grocery 2.9% … Computers 11.4%;
  apparel/shoes per-unit, no threshold; <25 units shipped/mo exempt) → return-prone categories carry a hidden
  per-unit cost the profit calc won't show; **non-SIPP bulky items now pay a ~$2.07/unit packaging fee** and
  new **Overmax surcharges $17–$25/unit** — skip oversize unless priced in; **inbound defect fee consolidated
  ~$0.60/unit avg**; removal 0–0.5 lb cheaper ($0.84). Each claim links the official Seller Central rate card —
  verify per-ASIN there. (sellersnap.io/amazon-fee-changes-and-updates) [practitioner restating policy]

### 2026-07-04 (daily run)
- **[practitioner]** 2026 OA reality check (Ecom Circles, tool-vendor blog — verify policy claims officially):
  realistic net margins are **10–20% after all fees**, not the 50%+ often claimed; never pursue deals under
  **40% gross margin** because total COGS must absorb inbound shipping, 3PL prep ($0.50–$2/unit), 2–5%
  inspection loss, and storage. Asserted 2026 rule changes worth verifying: **commingling ends Mar 31 2026**
  (manufacturer barcodes required), Amazon's own **FBA prep services ended Jan 1 2026**, and **retail receipts
  no longer work for ungating** (wholesale invoices / LOA only) — the last one matches the staged IBXT2txZtJE
  ungating transcript. Test 20–50 units, verify sell-through + BSR <30K, scale only at 10+ units/week. Market
  context: 2025 new-seller registrations down 44%, surviving sellers' traffic per seller up 31% since 2021.
  (ecomcircles.com/blog/online-arbitrage-amazon)
- **[practitioner]** 750+ gated/restricted-brand tracker updated **Jul 1 2026** (The Selling Guys, community
  list — risk radar, not policy): tiered by severity (legal action → C&D → IP warning → gated → low-risk).
  Fully gated incl. **Nike, Lego (US only), Fitbit, Under Armour, Logitech, Asics**; legal-action/C&D tier
  incl. **Apple, Bose, Ninja, NutriBullet, Razer, Makita, Netgear, KONG, Johnson & Johnson**. Durable rules:
  gating varies by country but action in one country predicts action elsewhere; don't hold deep stock of
  risky brands (the inventory trap ends in policy warnings/suspension); check eligibility per-ASIN on YOUR
  account before buying. → Candidate input for the ai-brain avoid/caution brand lists — review via
  fba-brain-updater, don't auto-import.
  (thesellingguys.com/current-list-of-amazon-gated-and-restricted-brands)

### 2026-07-05 (daily run)

- **[practitioner]** **Decide quantity LAST.** EntreResource's 2026 playbook fixes a strict buy order — scan →
  eligibility → listing red-flags → fees/price-history/seller-count → quantity — because beginners reverse
  it under discount-tag urgency and trap capital. Mirrors the gate order already in ai-brain.json; quantity
  is a separate final decision, not part of "is it a deal". (entreresource.com/arbitrage-on-amazon)
- **[practitioner]** **Always subtract a return allowance** — the most commonly skipped line in unit economics;
  it "makes weak buys look profitable." Worked example: $12 buy / $34.99 sale nets ≈ $11.50 after referral
  $5.25 + FBA $5.92 + storage $0.32 — before returns. Candidate check: does fba-deal-calculator expose a
  return-allowance input? (entreresource.com/arbitrage-on-amazon)
- **[practitioner]** "Sellable margin, not spreadsheet margin." Three predictable loss patterns: buy first /
  check gating later; receipts that won't survive a complaint; chasing headline ROI without price-stability +
  seller-count checks. (entreresource.com/arbitrage-on-amazon)
- **[practitioner]** Aura's 2026 OA guide converges on the same floors already in the brain — $3+ profit /
  30% ROI / BSR <100k (pros: $4 / 35%), realized profits typically 10–15%/item — and adds inventory-turn
  rules: the **3-month rule** (only buy ~90 days of sales; OA often can't restock anyway), removal cadence
  30/60/90 days, never >20% of capital in one ASIN, 20% cash reserve for restriction surprises, IPI > 450.
  Margin stacking (card → portal → discounted gift cards → coupons → loyalty) turned a 40% ROI example into
  68% on the same product. (goaura.com/blog/online-arbitrage-guide)

### 2026-07-06 (daily run)

- **[practitioner]** **Prep is 100% on the seller in 2026.** Amazon eliminated its own FBA prep/labeling
  services in the US (Jan 1, 2026) and fulfillment centers no longer fix labeling/packaging errors at
  check-in — mistakes now mean receiving delays, rejected inventory, unplanned fees, or stranded units.
  For OA that means prep cost/quality is part of the buy decision, not an afterthought.
  (snapl.com/news/amazon-fba-prep-requirements-in-2026...)
- **[practitioner]** Top prep failure modes to design out: multiple competing barcodes on one unit (#1
  cause of mis-scans — cover retailer barcodes), missing suffocation warnings on polybags, bundles not
  physically contained as ONE unit with ONE barcode, carton labels on seams/under stretch wrap. Process
  fix: scan-test samples, visual QC on first runs, standardized packaging spec per SKU. (snapl.com)
- **[practitioner→VERIFY]** Search snippets (PrepVia/StarterX, not fetched) claim a Mar 31, 2026 mandate:
  non-Brand-Registry resellers must FNSKU-label every unit (manufacturer barcodes no longer accepted), with
  inbound defect fees $0.32–$5.72/unit. NOT confirmed in a fetched source; Seller Central G200141500 is a
  JS shell from this sandbox. If true this adds a per-unit labeling cost to every OA deal — verify in a
  real browser before touching ai-brain.json.
- **[practitioner]** **IP complaints suppress first, ask questions never.** Amazon doesn't investigate —
  ASIN is suppressed the moment a rights owner files. Flags live in Account Health → Policy Compliance →
  Intellectual Property Complaints; check daily, and treat any listing that quietly goes "inactive" or
  loses all traffic as a possible silent IP flag (cross-check Performance Notifications). Complainants
  aren't always the brand: agencies, ex-distributors, rogue competitors, trademark aggregators.
  (sellerapp.com/blog/amazon-ip-complaint)
- **[practitioner]** IP response playbook: valid → remove ASIN immediately, email complainant for
  retraction, POA (what/fixed/prevent), keep docs ≥180 days. Invalid → evidence to complainant, then
  escalate the chain to notice-dispute@amazon.com; DMCA counter-notice is copyright-only and starts a
  10–14-day sue-or-relist clock. Zero-tolerance brands confirmed again: Nike, Apple, Disney, LEGO,
  OtterBox, Funko, Beats, Hasbro — authentic inventory + invoices does not protect you. Overlaps our
  avoid-brands list; the article's "keep your own IP-complaint tracker" is exactly what leads.json/
  ai-brain brand lists already do — keep feeding outcomes back. (sellerapp.com/blog/amazon-ip-complaint)

### 2026-07-09 (daily run)
- **[practitioner]** *Amazon Arbitrage: The Complete Guide for 2026* (ScoutClaw, vendor blog) — a clean
  standard OA/RA primer that **corroborates the project's existing gates** rather than adding new mechanics:
  target **≥30% ROI after all fees** ("most experienced sellers" — matches ai-brain `minRoi:0.3`); **start
  with 3–5 units** of any new ASIN before scaling; **BSR under ~100k** in most categories and a *climbing*
  BSR = fading demand; ASIN-match variation traps (color/size/model/pack = different ASIN/price) are the
  most common costly error; build a **5–10% returns buffer** (apparel/shoes run 15–25% returns — "if a deal
  only works at 0% returns it doesn't work"); research brand/IP risk before sourcing. Two useful contrasts:
  (1) the guide's own ScoutClaw tool advertises a **15%+ margin deal bar** while the editorial advice says
  30% ROI — a reminder that vendor deal-flow thresholds are looser than a disciplined buyer's. (2) Honest
  2026 reality: margins compressed (~40% → ~25% on comparable deals), fees up, more gating; still viable as
  a disciplined business. Nothing here should change ai-brain; it's confirmation, not new signal.
  (scoutclaw.com/blog/amazon-arbitrage-guide.html)

## Sourcing & finding products (incl. Keepa, SellerAmp, storefront stalking)

### 2026-06-30
- Pulled + ingested **2026-07-01** — takeaways under the 2026-07-01 bullets below. 3 of these 4 transcribed;
  the "advanced Keepa tactics" video (TBFh9vFBq7k) had **no transcript available** from the API and stays queued.

### 2026-07-01
- **[practitioner]** Keepa Product Finder (~120 filters). **Filter logic is AND across sections** — every added
  section shrinks results multiplicatively, so don't over-constrain. Always use **Sales Rank**, and prefer the
  **90-day avg BSR over current** (current swings intraday). Beware the "Out of stock" checkbox: on **Buy Box
  Price** it means *no Buy Box winner*; on the **Amazon** filter it means *Amazon's own offer is absent* — not
  "product unavailable." The OA play is filtering for **Amazon OOS** (BB left open to 3P), but confirm it's
  persistent by pairing with **90-day OOS %** + **Amazon OOS Count** (a live "Amazon OOS now" can be a blip).
  Set a **min price** (~$8–£10+) to clear FBA fees and a **max** to budget; use price **drop %** for
  clearance (falling) or demand (rising). (fbamogul.com/keepa-product-finder-getting-started-guide)
- **[practitioner]** *Offer-count TREND beats offer-count LEVEL (Keepa).* Sellers cycling on/off a listing
  (volatility) = real reseller arbitrage, not a locked wholesale/PL listing; source during offer-count
  **downtrends**, when the Buy-Box price peaks and margins widen. A sharp **cliff** drop in offers (e.g. 28→17
  at once, not gradual) flags IP-complaint/delisting risk → avoid. Sharpens the scout's IP-cliff guard.
  (youtube.com/watch?v=MAFpI4Wdd4w)
- **[practitioner]** *~<20s/listing reverse-sourcing filter.* Rapid disqualifiers before opening a listing:
  Buy Box missing/suppressed ≥6 mo, Amazon on the listing, offers high vs monthly sales, price volatility
  >~20% recently, all-large-seller competition. Then confirm Buy-Box rotation **<50% per seller**, ~200+
  sales/mo, healthy FBA/FBM mix, and ~6-month price stability before a 5–10-unit test; coupon-stack only when
  within ~5% of the ROI target. Store-brand names (Great Value, Member's Mark, Good & Gather) are quick
  verified entry points. (youtube.com/watch?v=TZyBG1_-jLM)
- **[practitioner]** The "new storefront-stalking reveal" is the standard method repackaged: SellerAmp brand
  filters (≥~200 products, ≤~6 sellers/listing, ≤~1% Amazon) → find profitable sellers → Storefront Stalker to
  scan their catalog; plus a reverse path (strong ASIN → grab seller ID → filter their storefront by BSR <~180k
  + weight). The one genuinely useful habit: check the **Keepa break-even price first** and skip if retail cost
  is above it. (youtube.com/watch?v=HXYMH_l6Ufk)
- **[practitioner]** *Mirror the smarter seller.* On the SellerAmp/Keepa Offers tab, prefer sellers who entered
  during low-offer (peak-price) windows and copy their ASIN catalog; while stalking, run ASINs through Boxem's
  **bulk auto-ungate checker** and source mostly auto-ungated leads first. Corroborates storefront stalking as
  the #1 beginner method. (youtube.com/watch?v=OUGc0aiT7l4, youtube.com/watch?v=MAFpI4Wdd4w)
- **[practitioner]** SellerAmp SAS Masterguide 2026 (vendor tutorial, seller "Flips4Miles" + SellerAmp
  founder): configure **Offer Summary + Buy Box Analysis panels** manually before trusting any number; an
  **"!" next to Estimated Sales means the figure is shared across all variations**, not per-variation —
  easy to overstate demand if missed; alerts (e.g. "suspected private label") are a **prompt to check deeper**
  (is the brand really dominating the buy box, or do 3P sellers still share it?), not an auto-pass; **BSR is
  category-relative** — use the Ranks & Prices panel to judge whether a rank is actually strong for that
  category size before comparing across products; **Max Cost can be worth exceeding on cheap items** that
  double your money even if they miss a flat profit-dollar target; use the Profit Calculator's cost field to
  model coupon/tax/multi-buy/bulk-discount stacking rather than judging a deal at raw retail price; multi-year
  chart views surface seasonal demand spikes worth buying ahead of. (selleramp.com/tips-and-tutorials/selleramp-sas-masterguide-for-2026)

### 2026-07-02
- **[practitioner]** Keepa Product Finder power moves beyond the filter basics already staged: **bulk-brand
  filter** (paste an Excel list of brands separated by `###` to source all favorite brands in one query);
  **price-stability screen** (Buy Box "90 days drop %" in a tight −20…20 band ≈ steady pricing, easier
  long-term profitability read); **negative keywords** (`-term`) to prune niches; deliberately **dropping
  the sales-rank filter** to surface "rankless" items with steady price history + growing reviews that
  rank-filtering competitors ignore; the **"Corridor" method** (tight price band, e.g. $15–25, + strict
  demand filters, re-run weekly); and **URL-decoding saved PF bookmarks** to learn how advanced queries are
  built. (talloakadvisors.com/11-keepa-product-finder-hacks-for-profitable-amazon-sourcing)
- **[practitioner]** 2026 sourcing shifts, consistent with the staged "you make items profitable" rule:
  (1) **work the search page** — unprofitable single-packs often have profitable multi-pack/bundle variants
  with their own Buy Box and less competition; SellerAmp **Quick View Simplified** (free) puts rank/FBA
  count/ASIN on the search results page; (2) **bulk ungate checking while stalking** — dump the stalked
  seller's ASINs into a bulk checker and chase only cleared items (beginners commonly clear 50–100 brands
  on a first auto-ungate scan); (3) margin is *created*: coupons + discounted gift cards + rewards stacking,
  reseller certificate (~5–10% instant), tax-free prep center, and checking FBM for <1 lb items. Vendor blog
  (Boxem) — tool pitches discounted, mechanics generalize.
  (boxem.com/article/amazon-sellers-are-falling-behind-the-new-rules-of-sourcing-products-in-2026)

### 2026-07-03
- **[practitioner]** *Sourcing is the new bottleneck; run it as a database, not a hunt.* 2026 manual sourcing
  yields ~2-3 testable products/session where it used to yield 10 (more competition + GS1/GTIN/brand-gating
  enforcement — e.g. the Oct-2025 Trader Joe's GTIN validation wave blocked inventory through no seller fault).
  Their "three-punch" workflow matches and extends our staged 1-2-punch notes: (1) Keepa storefront-stalk up to
  **50 storefront IDs at once** to extract every active ASIN, (2) ArbiSource reverse-scan the list across 240+
  retail stores for price/stock/estimated margin, (3) custom-scan any store not in the database. Key habit:
  **save every ASIN including the non-buys** — leads become viable in 2-6 months when retail price, stock,
  competition, or gating changes; rescan your own lead bank instead of starting from zero ("shopping from the
  back of the list"). Directly validates the project's `leads` table + outcome-tracking design; vendor math
  (25X leads at 1/6 cost) is a sales pitch — the mechanism, not the numbers, is the takeaway.
  (fbaleadlist.com/why-amazon-fba-sourcing-will-be-harder-in-2026-and-how-modern-arbitrage-resellers-are-preparing-now)

### 2026-07-04 (daily run)
- **[practitioner]** *Reverse sourcing, the supplier-side use* (B2B Supplier Hub, Jun 23 2026): its
  highest-value use is finding **2nd/3rd authorized sources for products you already sell**, not new
  products — one supplier's stockout shouldn't cost the Buy Box on your best SKU. 2026 twist: Amazon's
  **chain-of-custody enforcement** means "who sells this AND can prove authorization" — a supplier with
  stock sourced via a middleman may fail verification even with legitimate goods. Workflow: proven product
  (UPC/brand/MPN) → map the brand's distributor network (mid-size brands often share lists) → confirm
  authorization + invoice compliance BEFORE wiring money → compare cost/MOQ/lead-time/terms (cheapest unit
  price loses to faster ship + no minimum surprisingly often) → keep a **2–3-supplier bench per top SKU**.
  Field notes: Sports & Outdoor ~3–5 authorized distributors per SKU vs electronics ~20–25 per brand;
  compliant invoices can still bounce until Amazon verifies the distributor directly; some distributors are
  brand-authorized but not authorized to supply Amazon resellers. Mostly wholesale-tier tactics — file for
  when the operation graduates from pure OA. (b2bsupplierhub.com/blog/reverse-sourcing-for-amazon-sellers)
- **[practitioner]** Storefront-quality screen for stalking (Stealth Seller, 2024 — basics, but concrete):
  the best storefronts to stalk are **mixed-category, under ~1,000 products, listing in irregular smaller
  batches** (= a small reseller who researches each item), with **no Amazon on their listings**; skip huge
  single-brand storefronts (wholesale, not reproducible OA). Confirms and sharpens the staged
  storefront-selection heuristics — usable as a storefront-scoring filter in scout_pro.
  (stealthseller.co/blog/everything-on-storefront-stalking-as-a-arbitrage-seller)

### 2026-07-05 (daily run)

- **[practitioner]** SellerAmp's official Charts-panel doc (updated Jun 2026): the SAS Charts panel is
  **licensed Keepa data inside every lookup** — historic BSR, Amazon/Buy Box/lowest-FBA/lowest-FBM prices,
  offer + review counts, over 30/90/180d or full history. Read it as a pair: **rank history sanity-checks
  the monthly-sales estimate; price history tells you whether today's price is normal or a spike**. Frequent
  BSR drops = regular sales; stable price = less race-to-the-bottom risk. A profitable-looking deal must
  also be a *reliable* one. (selleramp.com/selleramp-charts-panel-tutorial)
- **[practitioner]** Keepa read discipline from EntreResource: BSR is **a filter, not a decision**; what fails
  is treating the current Buy Box as a reliable future selling price. Want: stable price history, regular
  sales signs, livable seller count, no pattern of Amazon jumping onto the listing.
  (entreresource.com/arbitrage-on-amazon)
- Queued two counterweight videos on storefront stalking (D3FhvdMVLl8 argues it's NOT profitable;
  ljlERpMrcBk is a live click-path session) so the corpus doesn't hold only pro-stalking sources —
  takeaways land once transcripts are pulled.

### 2026-07-07 (daily run)

- **[practitioner]** *5 Keepa "Power Moves" + a 60-SOP tactic taxonomy* (OA Challenge, Nate McCallister).
  The five headline Keepa Product Finder plays: (1) **stalk multiple storefronts at once** (batch several
  seller IDs into one KPF search instead of one-at-a-time); (2) **find profitable FBM inventory** (heavier/
  oversized items most FBA sellers skip); (3) **filter for stable-priced ASINs** (low price variance = less
  race-to-the-bottom); (4) **find brand-new products (<1 month old)** to get in before offers saturate;
  (5) **reverse-source by brand** to expand from one proven brand to its whole catalog. The more durable
  signal is the *named taxonomy of advanced KPF tactics* worth knowing for later scout discovery-hint work:
  "lead synthesizer" (turn one good lead into many), A2A (Amazon-to-Amazon) flips for pricing-mistake/holiday
  sourcing, KPF **negative keywords**, "buy the pinch" (OOS-driven) sourcing, filtering ASINs **with no
  current sales rank** via BSR history + review-count growth, and estimating monthly sales from review count.
  The step-by-step lives behind Scribehow embeds / a paid playbook — this is a map of what's possible, not
  the procedures. (oachallenge.com/5-keepa-power-moves)

### 2026-07-08 (daily run)
- **[practitioner]** *Online Arbitrage Sourcing Using Keepa (ADVANCED TACTICS)* (TBFh9vFBq7k, Chris Grant /
  OA Challenge — transcript re-fetched with real captions this run; actual content is a full Keepa
  settings + chart-reading + Pro-tracking tutorial). Most of the demand-read material duplicates
  wwNw5vNAyeM already staged (monthly-sold gold line is a customer-count RANGE not literal units and only
  ~3.5M of 1B+ ASINs get it, losing the line ≠ sales stopped; rank-drops ≠ units; buy-box is regionally
  directional via Amazon's flywheel). New, durable pieces: (1) **Concrete settings config** — custom range
  180 days, close-up view OFF, filter out extreme values, tracking mode = **Pro**, 30% price-reduction
  preset, alert re-arm timer at the **1-day minimum** (so you can see how often a product actually drops),
  enable "let Keepa gather Amazon prices" (crowd-sourced accuracy), enable **hover-overlay mini-graphs**
  (sales rank + buy box + Amazon + new, 180d) to read a chart without opening the listing, and enable
  stock-quantity on the offers page (Pro). (2) **Use all THREE Keepa sub-graphs, not two** — turn on the
  **sub-category rank**; top-level and sub-category rank should move congruently, and a large divergence is
  a flag to dig deeper. (3) **Line semantics that change reads:** the purple "new" line **excludes**
  shipping (no truck icon) while the buy-box line **includes** shipping; the little orange triangles are
  new-3P-FBA offer data points, **not sales**. (4) **Pro tracking as a sourcing tool, not just alerts:**
  track **new-offer-count thresholds** (e.g. "only profitable at ≤6 sellers" → alert at 6-or-fewer; a
  meltable only sellable at ≥3 sellers), **sales-rank thresholds** for seasonal sell-timing, and buy-box
  up/down; always toggle **include-shipping** when tracking new 3P sellers so the tracked number is the
  true landed price; use **memo + tags** (source URL + "sell at $X") to build a searchable tracked-item DB.
- **[practitioner]** *SellerAmp SAS: Moves to Max Out Your Margins — 10 under-used features*
  (selleramp.com, Hollie Payne, pub Oct 2025 / updated Jun 2026) — SAS power-features operators skip:
  (1) **Profit-Calculator what-ifs** ("shipping +10%", "packaging ×2") + **FBM-vs-FBA side by side** (winner
  flips seasonally). (2) **Settings are the foundation** — wrong sales-tax/prep/inbound/return-rate/labor/
  packaging makes every ROI wrong; update quarterly. (3) **Offers Panel** — seller rating/review-count/
  fulfilment type, live stock (max/min order-qty signal), price incl+excl shipping, your ROI if matched,
  lowest-10 prices, FBA-vs-FBM split, Prime-only filter → spot weak/low-stock/overpriced competition.
  (4) **Google Sheets export** for team/VA lead pipelines. (5) **History tab** — re-check "almost
  profitable" leads; shifts can flip old rejects into buys. (6) **Notes & Tags** — personal sourcing DB
  (Seasonal/High-Margin/Brand-Restricted/Heavy; "avoid – returns issue"), filter/export by tag.
  (7) **Charts Panel** (Keepa-powered) — hover exact points, zoom/pan 30d↔1yr. (8) **AI Image Search** —
  photo → correct ASIN with no link; catches mismatched/duplicate listings. (9) **QVS** — ASIN,
  is-Amazon-selling, FBA/FBM counts, variations, BSR, first-review on the Amazon search page.
  (10) **Variation navigation** — check each variant's own rank/margin; low-competition variants leak
  profit. Bonus: keep a **10–15% margin buffer** for seasonal volatility. Related: SAS **Advanced Search**
  (launched Jun 2026) = saved/shareable custom filter searches — relevant to scout-style saved queries.

## Finances & account management

### 2026-06-30
- **[practitioner]** Don't book the bi-weekly Amazon settlement deposit as "sales." Decompose every settlement
  (gross sales, referral, FBA fulfillment, storage, ads, refunds, reimbursements) on an **accrual** basis;
  the net deposit hides expenses and understates revenue. Keep Amazon fees **below gross margin as variable
  expenses, not in COGS**. Use a **clearing + deposits-in-transit** account reconciled each period or balances
  drift. Returns are a **net-zero COGS adjustment**. → True per-unit profit (for `outcomes`/realized-ROI) must
  net out all fee components and refunds, not Seller Central's headline number.
  (eightx.co/blog/amazon-fba-accounting-bookkeeping) [practitioner — CFO firm, not Amazon policy]

### 2026-07-01
- **[practitioner]** Confirms the surcharge flagged 2026-06-30: a **~3.5% fuel/inflation surcharge started
  April 17 2026** on top of all FBA fulfillment fees (US+CA), **separate from** the ~$0.08/unit Jan-15 increase.
  Example: $5.00 fee → ~$5.18. Also in 2026: **aged-inventory surcharges start ~90 days earlier (~181 days)** —
  review stock nearing ~150 days and liquidate/remove; **inbound defect fees jumped** to ~$0.32–$5.72/unit
  (prep accuracy now has real cost); **Amazon ended its own FBA prep services (Jan 1 2026)**; a new **Overmax
  handling surcharge** hits extra-large items; West-Coast storage rising. → Fee math must include the surcharge;
  re-price oversize/heavy candidates; don't reuse 2025 storage assumptions. Verify per-ASIN in the official
  fee pages / Revenue Calculator. (amzprep.com/amazon-fba-fees) [practitioner — 3PL, confirm official]
- **[practitioner]** *Run capital like a portfolio, not a daily hunt.* Keep a persistent **lead bank** (product,
  ASIN, cost, sell price, profit, source URL) and each week allocate cash to the best saved leads across all
  products rather than chasing that day's clearance; re-buy sold-through winners first, then spend to a weekly
  target. Scale sourcing with a VA (~$400–600/mo) around ~$20k revenue/mo. (youtube.com/watch?v=pP-zQ4-u370)

### 2026-07-02
- **[practitioner]** **DD+7 is the cash-flow clock now.** Since **March 12, 2026** every account disburses
  on Delivery Date + 7 (clock starts at carrier-confirmed delivery, +7 calendar days hold, +3–5 business
  days bank transfer): fast Prime FBA can pay *faster* than the old 14-day cycle, slow FBM stretches
  sale→bank to ~17–21 days. Reserve is typically **3–12% of recent revenue** (50–100% first 90 days for new
  accounts) and **grows with sales velocity** — model it as % of trailing 14-day sales, so a hot week thins
  the next disbursement. Practical weekly routine (Monday, 4 numbers, investigate >10% moves): disbursement
  vs forecast, reserve WoW, days-of-inventory by category (>90 = storage bleed, <21 = stockout), rolling
  28-day contribution margin per SKU. FBA CCC runs 60–120 days; supplier terms are the first working-capital
  lever, Amazon Lending (10–17% APR) locks repayment to disbursements. → Relevant to the operation's
  cash-planning and any future `outcomes` cash-cycle fields.
  (novadata.io/resources/blog/amazon-cash-flow-management-fba-sellers) [practitioner — analytics vendor;
  DD+7 dates cite Amazon's Finances API docs, verify in Seller Central]

### 2026-07-03
- **[practitioner]** Amazon-seller chart of accounts + the mistakes that break profit math (Beancount, Apr 2026):
  give **every fee type its own expense account** (referral, FBA fulfillment, storage, ads, subscription,
  returns processing, other) and keep them **out of COGS** — COGS is product cost + duties + freight-in +
  prep only. Record **lost/damaged reimbursements as taxable income** (missed ones create 1099-K mismatches),
  refunds as contra-revenue, and reconcile every settlement (monthly minimum). FBA placement can create
  **sales-tax nexus** in states you've never visited even though marketplace-facilitator laws cover the
  Amazon-side collection — matters only if selling off-Amazon too. US quarterly estimated-tax dates 2026:
  Apr 15 / Jun 16 / Sep 15 / Jan 15 '27, safe-harbor 100% of last year (110% if AGI >$150k). Reinforces the
  staged Eightx rule: the settlement deposit is not "sales." → The `outcomes` realized-profit fields should
  mirror this fee-type split so realized ROI nets out every component.
  (beancount.io/blog/2026/04/16/bookkeeping-for-amazon-sellers-complete-guide)

### 2026-07-04 (daily run)
- **[practitioner]** The Xero-specific implementation of the staged "never book the net deposit" rule
  (Eightx, Mar 2026, updated Jun 29): worked example — a $47K deposit is really **$68K gross − $21K of
  fees/refunds**; book gross, one expense account per fee type, fees NEVER in COGS (also wrecks exit due
  diligence). Tooling tiers: **A2X ($69/mo) above ~$50K/mo Amazon revenue** (settlement → coded journal
  entries, penny-perfect rec), **Link My Books ($9–49/mo) below**; realistic all-in cost $611–2,111/mo.
  Cadence: reconcile within **5 business days of each bi-weekly settlement** (15–30 min with A2X); 5-day
  month-end close is achievable. Reserves = **Amazon Receivables asset**, not an expense. Weighted-average
  COGS at full landed cost. Cautionary case: a £10M brand's "60% gross margin" was really 52% once fees were
  unbundled, and Amazon CM2 (28%) badly trailed DTC (41%) → ad budget reallocated, +£14K/mo contribution.
  Wrong books = wrong strategy. → When the operation needs real books, this is the setup recipe; the
  `outcomes` realized-profit split should mirror the same per-fee-type granularity.
  (eightx.co/blog/xero-bookkeeping-amazon-fba) [practitioner — CFO firm]

### 2026-07-06 (daily run)

- **[practitioner]** QuickBooks' 2026 guide (updated Jun 2026): **1099-K threshold is back to the
  historical $20,000 AND 200 transactions** for the 2026 tax year — but all income is reportable
  regardless. Forms live in Seller Central → Reports → Tax Document Library. Sole prop/single-member LLC
  files Schedule C; Keepa/SellerAmp subscriptions, shipping, and home office are deductible business
  expenses. (quickbooks.intuit.com/r/running-a-business/amazon-seller-tax)
- **[practitioner]** Sales tax is mostly-but-not-fully Amazon's job: marketplace-facilitator laws mean
  Amazon collects/remits in nearly every state, BUT (1) FBA inventory placement can create physical nexus
  in the ~44 states with Amazon warehouses and economic nexus triggers around $100k sales → registration
  duties; (2) some states still want zero-dollar/informational returns; (3) wrong product tax codes cause
  over-collection. Reseller-relevant: **resale certificates avoid paying sales tax on OA inventory buys**
  — direct COGS reduction. Distinguish the Marketplace Tax Collection Report (Amazon paid) from the Sales
  Tax Calculation Report (you owe). (quickbooks.intuit.com)

### 2026-07-08 (daily run)
- **[practitioner + policy]** *Amazon FBA Reimbursement Guide 2026* (Nova Analytics, updated May 2026) — a
  profit lever the corpus hadn't covered. **[policy] Big shift (effective Nov 15 2025): Amazon reimburses
  lost/damaged/destroyed FBA inventory at MANUFACTURING/sourcing cost, not retail** — recoveries down
  50–75% (a $40 SKU with $9 landed cost now reimburses ~$9). Two mandatory defenses: **enter accurate
  Cost-of-Goods on every active SKU** (Inventory → Manage All Inventory; missing/zero cost → near-zero
  payout) and **submit supplier-invoice cost docs within 60 days** of a claim (else Amazon's lower estimate
  applies). Nine claimable categories: lost-in-warehouse (~35–40% of claims), damaged-in-warehouse,
  lost-inbound, customer-return-not-received (5–10% never arrive), removal lost/damaged, fee overcharges
  (wrong dims/weight tier), switcheroo returns, MCF errors, duplicate refunds. Filing: needs
  SKU/FNSKU/qty/transaction-ID/date; documented inbound claims hit **90%+ approval vs <40%**; ~**18-month
  window** for most types but **removal orders only 90 days**; first-line support denies ~40% of valid
  claims → escalate. Rule of thumb: 1–3% of FBA inventory has a reimbursable issue/yr, ~$1.5–3k/yr
  recoverable. For our OA model this reinforces **honest-COGS** discipline and is a candidate control-center
  signal (reimbursement tracking) later.
- **[practitioner]** *What Amazon FBA Changes in 2026 Mean for Sellers* (Logos Distribution 3PL, Dec 2025 /
  updated Jul 2026 — **verify each in Seller Central before acting**): (1) **another FBA fee increase
  ~+$0.08/unit** average for 2026. (2) **Amazon ended US FBA prep & labeling services (Jan 1 2026)** —
  FNSKU labeling, poly-bagging, bubble-wrap, bundling now the seller's/3PL's job before inventory reaches
  the FC (every OA unit must be prepped upstream). (3) **storage limits tightened mid-2025 ~6 → ~5 months**
  of forecasted sales — more restocking, higher Q4/Prime-Day stockout risk. (4) **reimbursement valued at
  sourcing cost** (corroborates Nova). (5) diversification argument (Dec-2025 regional listing-hide
  incident) — FBM/other channels as a hedge. Search-snippet claims (NOT fetched, for Claude Code to verify):
  **commingling/stickerless ends Mar 31 2026**, and **retail receipts no longer valid for ungating —
  wholesale invoices/LOA required**.

### 2026-07-09 (daily run)
- **[practitioner]** *Amazon Seller Accounting & Bookkeeping (2026 Guide)* (Plugbooks, vendor blog) —
  standard-but-sound bookkeeping fundamentals for OA. Durable points: (1) **"Sales" ≠ "Deposits"** — Amazon
  nets dozens of fees before payout, so reconciling the **settlement report every ~2 weeks** (match gross
  sales, subtract fees, adjust refunds, verify the deposit) is the single most important accounting step.
  (2) **Separate business bank/card**; never commingle. (3) **FIFO COGS + landed-cost tracking** — you can't
  compute true profit without per-unit landed cost (reinforces the honest-COGS rule the reimbursement-at-
  cost change already made urgent — see Nova 2026-07-08). (4) **Categorize fees separately** (referral / FBA
  / storage / PPC) or profitability-by-product is wrong. (5) Cash basis is fine under ~$1M revenue; accrual
  is more accurate period-by-period and required over ~$1M. (6) Marketplace-facilitator sales tax is
  collected by Amazon in many states but **income tax is still the seller's**. Product pitch at the end is
  marketing — ignore. (plugbooks.io/amazon-seller-accounting)
- **[practitioner — UNVERIFIED search snippets, flagged for Seller Central/IRS verification]** Two
  cash-flow/tax items surfaced in search but were **NOT on any fetched page**: **DD+7** — Amazon reportedly
  begins holding funds **7 days after delivery starting Mar 12 2026** (worsens the OA cash-conversion cycle
  and distorts cash-basis month boundaries); and the **1099-K reporting threshold reportedly reverts to
  $20,000 AND 200 transactions for tax-year 2026**. Do not treat as fact until confirmed.

### 2026-07-10 (daily run)
- **[policy]** *Amazon Reimbursement Policy — changes & updates* (SPS Commerce, updated Jun 15 2026;
  vendor sells recovery software, but the policy facts are Amazon's). The reimbursement regime tightened
  materially 2024–2026 and directly affects the **loss/returns buffer** in OA unit economics:
  (1) **Cost-based model (eff. Mar 31 2025)** — lost/damaged FBA inventory is reimbursed on your
  **manufacturing/sourcing cost, not the selling price**. This makes accurate per-unit **COGS/landed-cost
  the reimbursement basis**, not just an accounting nicety (reinforces the honest-COGS rule; ties to
  Nova 2026-07-08 + Plugbooks 2026-07-09). Submit/verify your own cost via the **IDR portal**
  (Seller Central G66ZLS453YSE2Y4R) or Amazon lowballs the estimate. Shipping/labeling/packaging are
  generally excluded from reimbursement. (2) **Claim windows shortened to ~60 days** for most manual
  claims (FC-ops 60d; FBA customer returns US 60–120d; removals 15–75d) → returns/loss must be audited on
  a tight cadence or the money is forfeited. (3) **Some claims are now automatic** (lost, damaged, customer
  returns) but **removals + mishandled returns + misc still require a manual claim**. (4) **MCF caps**
  (Aug 2024, unchanged 2026): UK £250, EU €275, CA $400, AU $450, MX $5000 — high-ASP items may exceed the
  cap (insurance worth considering). (5) **Returnless resolutions**: refunded items are NOT returned to
  inventory — seller eats refund + product cost; weight this in thin-margin, high-return categories.
  (spscommerce.com/community/articles/amazon-reimbursement-policy)
- **[practitioner / policy-cited]** *FBA New Selection Program (2026) launches July 30* (Nova Analytics,
  reporting a Jun 18 2026 Seller Central announcement; Ecomcrew-corroborated). Bigger inbound-placement
  fee credit, **90 days free storage on first 100 units** of a qualifying parent ASIN, and **reduced
  referral on the first $25k/new branded ASIN for 365 days**; existing enrollees migrate automatically.
  **Caveat for us: this is a private-label / brand-owner subsidy (needs Brand Registry + new branded
  ASINs) — NOT a pure-OA tactic** on existing listings. Recorded for fee/market awareness only; if the
  catalog strategy ever adds a PL/bundle SKU, time the launch after Jul 30 and keep the first inbound ≤100
  units to bank the storage waiver. No ai-brain change.
  (novadata.io/resources/news/amazon-fba-new-selection-program-expansion-july-30-2026)

### 2026-07-12 (daily run)
- **[policy-grounded practitioner]** *Amazon FBA Fees, Mid-2026: The Real Cost Math* (Digital Applied,
  Jul 6 2026; every figure recomputed from Amazon's live rate pages). Separates the three fee events that
  seller blogs keep merging into a fake "July overhaul": (1) **The only genuine Jul 1 2026 change** — Amazon
  **ended prep + item-labelling in the Canada store** (sequel to the US ending it Jan 1 2026). Shipments
  *created* before Jul 1 still get prep; created after without proper prep still ship but **lose
  reimbursement eligibility** if damaged/untraceable. (2) **MYTHBUST** — the viral "$0.87/cu ft + 180-day
  storage overhaul on Jul 1" is false: standard storage is **$0.78/cu ft (Jan–Sep), $2.40 (Oct–Dec)**, and
  the **181-day aged tier is the pre-existing baseline** (predates 2026). Budgeting $0.87 overstates storage
  ~12%. (3) **The real H2 driver is January's overhaul (eff. Jan 15–16)** — avg ~$0.08/unit; small
  standard +$0.25; new **consolidated $0.60/unit inbound-defect fee**; aged-inventory 366+ min doubled to
  $0.30 + new **456+ day tier**; low-inventory fee now at **FNSKU level**. (4) **April's 3.5% fuel surcharge
  (eff. Apr 17)** is a % of the already-raised fee → **apply it LAST** in landed-cost math. **Q4 triple-stack:**
  base + utilization ($1.88) + aged surcharge can push one over-stocked cu ft from $0.78 to **$11.18/mo**;
  the **271–300-day aged cliff is $5.45/cu ft (11× the entry tier)**, snapshotted on the 15th, FIFO across the
  network. Defense: order to sell-through so units never hit the 271+ tier.
  (digitalapplied.com/blog/amazon-fba-fees-2026-mid-year-seller-cost-math)
- **[policy]** *Featured Offer Overhaul: Rank-Only Buy Box Rules* (Digital Applied, Jul 10 2026, on Amazon's
  Jul 6 Seller Forums announcement). **Directly on the "can it profit" axis for OA** (winning the Buy Box on a
  listing you don't control). Amazon is **removing seller performance as a standalone pass/fail eligibility
  gate** for the Featured Offer; the gate signals — **chargeback rate, Order Defect Rate (<1% ceiling), Voice
  of the Customer complaints** — become **weighted inputs inside one ranking score** alongside price, free
  shipping, delivery promise. **"Structure changed, criteria didn't"**: a weak account now *competes and
  loses* rather than being excluded (account health scores **continuously**, not once). **Rollout is phased:
  EU/UK reported Jul 20 2026; global by end of 2026; US on an unannounced date** — no action required, offers
  auto-included. **Weights are undisclosed → treat any % you see as invented.** Knock-on nobody covers: per
  Amazon Ads docs, **without the Featured Offer, Sponsored Products/Brands/Display serve ZERO impressions**
  "regardless of campaign status" (a campaign can read *Delivering* at 0 impressions); eligibility is
  **SKU-specific**. Unchanged: reviews/stars not a selection factor; Prime/FBA-vs-FBM excluded as tie-breaker;
  Featured Offer still per-variation and can rotate. **No ai-brain threshold change**, but reinforces that
  low ODR/chargebacks now move Buy Box rank continuously — a signal worth surfacing if the control-center ever
  models account health. (digitalapplied.com/blog/amazon-featured-offer-unified-ranking-buy-box-2026)
- **[practitioner]** *FBA Cash Flow Management: Inventory Is Where the Cash Gets Quiet* (The FBA Guys,
  n≈8,503-valuation DB). The cash-discipline case behind the ai-brain capital rules. Core: **inventory asks
  for cash before the sale** (deposit + freight/duty/prep leave before Amazon pays after the sale), and
  **growth widens the gap** — bigger POs arrive before the extra profit accumulates ("you can grow yourself
  into a cash crunch"). Benchmarks: avg business holds **~17% of annual sales in inventory (~70% of SDE)**;
  **inventory-to-sales rises sharply as turn speed falls** (few weeks 10.6% → months 24.7% → year+ 75.8%) and
  **as sales decline** (the denominator drops even if units don't). Operator's reorder test: **"if this order
  goes wrong, what else has to wait?"** — markdown / hold price / borrow / cut ads are all cash-flow decisions,
  not separate ones. **Credit lines bridge timing but hide weak margin/stale demand** if abused ("the borrowed
  dollar needs a return date"). Minimum system: a **13-week cash forecast** + weekly track of cash, Amazon
  receivables/payout dates, inventory on-hand/inbound/on-order, supplier balances, ad spend, taxes/debt/draws,
  reorder points + lead times. For a tiny OA bankroll: **inventory-to-sales + turn speed are the cash-survival
  signals**; every reorder passes "what does this prevent?" before "can I afford it?". (thefbaguys.com/blog/amazon-fba-cash-flow-management)
- **[practitioner]** *Amazon Fee Increases 2026: How to Protect Profit* (Seller Labs; product pitch ignored).
  Durable reframe: the **+$0.08/unit** avg increase "<0.5% of price" comes **out of profit, not sale price** —
  on a 10% net margin that's roughly a **5% hit to take-home profit**, compounding across SKUs. Measure
  exposure via **Fee Preview CSV** (Reports → Payments), flag SKUs that go red after adding the fee. Five
  tactics: trim SKUs under a **~20% profit buffer**; **shrink packaging ~0.2" to drop a size tier** (biggest
  offset, but N/A for OA on existing listings); 2–3% price lift on bestsellers; reorder-volume negotiation;
  automated margin alerts. Also: **file FBA reimbursement claims monthly** (ties to the cost-based
  reimbursement finding, 07-10). **OA use:** fold the fee add-on into Max-Cost math and drop ASINs whose buffer
  falls under ~20% post-January-fee + April-fuel-surcharge. (sellerlabs.com/blog/amazon-fba-fee-increase-2026)

### 2026-07-13 (daily run)
- **[practitioner]** *Amazon FBA Tax Planning 2026: Multi-State Nexus* (Eightx, CFO-authored). FBA inventory
  creates **physical sales-tax nexus in every state Amazon stores a unit** — no minimum threshold, you don't
  pick the warehouse, and nexus can be assessed retroactively; **register before inventory arrives**. What
  marketplace-facilitator collection (now in all **45** sales-tax states; 5 have none — AK, DE, MT, NH, OR)
  does **NOT** cover: **non-marketplace sales** (Shopify/site/wholesale — you collect yourself in nexus
  states), **local/city taxes** (AZ/CA/CO can need separate filings), **income tax** (apportioned by sales
  factor — CA most aggressive, $800/yr LLC fee for any FBA presence), **property tax on inventory** (assessed
  often on **Jan 1** — inventory timing is a legit lever), and **zero-dollar returns** still required.
  Entity: **LLC→S-Corp election at ~$50K–$100K net profit** saves ~$9K/yr in SE tax (pay reasonable salary
  40–60% of profit, rest as distribution); **file Form 2553 by Mar 15** for retroactive election. Deduction
  fix with highest value = **break out Amazon settlement reports** (referral/FBA/storage/ads separately, not
  one "sales" line) — a $200K seller typically has $50–70K deductible beyond COGS. Run the **Inventory Event
  Detail report** to see which states hold your stock. **OA relevance:** even a tiny operation gets nexus the
  moment FBA stores a unit out-of-state; landed-cost bookkeeping + the Jan-1 property-tax timing point matter
  before scaling. (eightx.co/blog/amazon-fba-tax-planning)
- **[practitioner]** *Amazon FBA Sales Tax Nexus Explained* (The FBA Guys, n=8,416-valuation DB). Core mental
  model: **separate "Amazon collected on the order" from "have we checked registration / filing / income-tax /
  franchise-tax / documentation obligations in that state"** — adjacent but different files. Marketplace
  facilitator = **one mechanism, not a tax department**: it says who collected on a facilitated sale, not
  whether your registration file is complete or a non-Amazon sale escaped the bucket. Recommended first pass
  is **factual, not fear-driven**: three exports — (1) Amazon marketplace tax collected, (2) revenue by
  ship-to state (Amazon + non-Amazon), (3) non-Amazon revenue by state — then flag where non-marketplace
  sales may cross economic thresholds, review FBA-inventory physical presence, check existing registrations
  (**registering "everywhere to be safe" creates a filing calendar, incl. zero returns, that outlives the
  anxiety**), and consult a CPA/SALT specialist before registering. Data point: submissions with tax returns
  averaged a **2.67x** valuation multiple vs **2.10x** without — a documentation/financial-maturity signal,
  not a pure sales-tax finding. **OA relevance:** keep a traceable, boring tax file (what Amazon collected,
  what you filed, what's open) rather than a confident "Amazon handles it." (thefbaguys.com/blog/amazon-fba-sales-tax-nexus-explained)
- **[practitioner]** *Amazon FBA Bookkeeping 2026: A2X vs Link My Books* (The Hustle Tax). The **"Deposit
  Trap"**: Seller Central "Sales" ≠ bank deposit — Amazon nets dozens of fees (ads/refunds/storage/reserves)
  before payout, so **cash-basis books hide true margin** (e.g. ad spend deducted from payout makes a losing
  SKU look healthy). Fix = **accrual accounting** (record the sale when it happens), which is infeasible
  manually at volume → use a connector tool that posts clean journal entries to QuickBooks/Xero. Tool read:
  **A2X** = accountant gold-standard, summary journal entries, per-channel pricing (pricey multi-channel),
  no order-level detail; **Link My Books** = cheaper (all channels included), guided DIY setup, auto-COGS,
  best for small/mid multi-channel; **Webgility** = order-level + inventory sync across channels, enterprise,
  overkill for pure FBA. All three let you upload **per-SKU cost price so COGS posts automatically** — without
  it you never know true monthly profit. Also flags the **"DD+7" policy (funds held 7 days after delivery,
  from ~Mar 12 2026)** as a cash-flow shock that cash-basis books distort across month boundaries — corroborated
  across sources but treat the exact date as a to-verify practitioner claim, not confirmed Amazon policy.
  **OA relevance:** per-unit landed cost as COGS + accrual = the only way the scout's ROI ties to reality.
  (thehustletax.com/amazon-fba-bookkeeping-software-comparison)

## Building the system (AI, RAG, dashboard, control-center)

### 2026-06-30
- **[practitioner]** Chunking: start with fixed-size + overlap as a baseline, then compare **recursive**
  (hierarchy-of-separators, e.g. LangChain `RecursiveCharacterTextSplitter`) and **semantic** (split on
  logical boundaries) splitting. Smaller chunks often retrieve better and cost less. Attach **metadata**
  (title/section/keywords) to each chunk and filter on it during search. → Review `knowledge-rag` splitting +
  metadata before any re-embed. (community.databricks.com — chunking strategies for RAG)
- **[practitioner]** RAG is a multi-step chain (retrieve → rerank → repack → generate); advanced variants raise
  quality but add latency/complexity — benchmark each added step against latency before adopting. Multimodal
  "retrieval as generation" helps QA over images (future: Keepa/SAS screenshots). (arxiv.org/abs/2407.01219)
- **[practitioner]** RAG's own failure modes — retrieval quality, grounding fidelity, efficiency, robustness to
  noisy/adversarial input — map onto this project's leakage/honesty risks. Design around the trade-offs
  (precision vs flexibility, efficiency vs faithfulness, modularity vs coordination) and prioritize
  **retrieval-aware evaluation + grounding/citation checks** in `Ask`, not just answer accuracy.
  (arxiv.org/abs/2506.00054)

### 2026-07-01
- **[practitioner]** *Online-Optimized RAG* (arXiv 2509.20415) targets **embedding misalignment** — the retriever
  fetching the wrong tool/doc because of imperfect embeddings or noisy descriptions, causing task failure. It
  adapts retrieval embeddings **at deployment time from live interactions using minimal feedback (task
  success/failure)**, with **lightweight online gradient updates (negligible latency)** and **no change to the
  LLM**. Plug-and-play for single/multi-hop tool use, **dynamic tool inventories**, and top-K + re-ranking.
  Maps onto learning the scout/RAG from realized **outcomes** instead of offline retraining. Caveat: theory
  says gains depend on **decent embedding initialization** (online adaptation fixes drift, not a bad base), and
  results are on tool-use/doc benchmarks, not FBA data — A/B it behind retrieval-aware eval + grounding checks,
  don't drop it in. (arxiv.org/abs/2509.20415)

### 2026-07-02
- **[practitioner]** The most comprehensive RAG-evaluation survey to date (arXiv 2504.14891, 18 pp) is the
  reference catalog for building an eval harness over `Ask`: it splits **retrieval-component metrics** from
  **generation/grounding metrics** (exactly the retrieval-aware-eval + citation-check split the guardrails
  already demand), and catalogs RAG-specific datasets and automated frameworks (ARES-style) worth borrowing
  when assembling a small gold-question set over the FBA corpus. Read the PDF before implementing.
  (arxiv.org/abs/2504.14891)
- **[practitioner]** **R2C** (arXiv 2510.11483): estimate confidence for multi-step retrieval-augmented
  reasoning by **perturbing reasoning steps and checking answer stability** — perturbations shift the
  retriever's input, which shifts the generator's input, capturing uncertainty from BOTH components;
  >5% avg AUROC gain over prior UQ baselines across five RAR systems. Cheap idea to steal for calibration:
  `Ask` could flag low-confidence answers by re-querying with perturbed retrieval instead of sounding
  equally sure on weakly-grounded answers. Design input only, not implemented. (arxiv.org/abs/2510.11483)
- **[practitioner]** Dashboard patterns 2026 (Linear/Stripe/Grafana-derived), mostly confirming the
  control-center's operator-terminal choices with concrete specs: 4–6 KPI cards max above the fold (one
  number 28–32px + one comparison + ONE visual; >5–7 primary metrics degrades decisions — cut what nobody
  acts on); sidebar 256px/64px-rail, 36px items; 12-col CSS Grid, 24px gutters, container queries per card;
  **three states per component** — skeleton (content-shaped, not spinners), honest empty (illustration + one
  sentence + CTA), component-scoped error banner with retry (never a page-blocking modal — one flaky endpoint
  must not kill the dashboard); tables: sticky solid header, 36–40px dense rows, right-align numbers,
  pagination for reference data; override chart-library default palettes (they fail WCAG contrast).
  (artofstyleframe.com/blog/dashboard-design-patterns-web-apps)
- **[practitioner]** *How to Get Ungated on Amazon in 2026* (youtube.com/watch?v=IBXT2txZtJE) — three approval
  tiers: auto-ungated (sell now), gated-not-restricted (apply + invoice), restricted (nobody gets approved).
  **Boxem's bulk-ungate "suggested ASINs" scanner** auto-applies for 50-100 brands for free in ~10 minutes
  (scans ~5 brands/sec) — the single highest-leverage zero-cost action for a brand-new account, and grows as
  the account sells more. For invoice-gated brands: buy from the **brand's own website first**, a major
  retailer (Target/Walmart/Walgreens) second — never a random wholesaler; submit the full order→ship→delivery
  confirmation as one PDF; the invoice's billing/shipping address **must match the Amazon seller account
  address**; buy only ~10 units regardless of the quantity Amazon's form claims to want — multiple submission
  attempts are normal ("a volume game"), not a sign of doing it wrong. On rejection: wait 24h before
  resubmitting, add supporting evidence (product photos, card statement); after repeated declines, physically
  printing + photographing the same real documents (never altering them) can route the review to a human
  instead of an automated check. Paid "ungating services" ($200-$5,000+) do nothing but this same trick —
  skip them.
- **[practitioner]** *The ULTIMATE SellerAmp SAS Tutorial* (youtube.com/watch?v=rHCB-vSCWcI) — full feature
  walkthrough; durable takeaways: (1) **estimated monthly sales is a floor, not a count** — it's built from
  Keepa BSR "drops," but real sales also happen while BSR rises (just slower than category peers), so treat
  it as directionally accurate only, never size a buy off it alone. (2) **Buy-Box price-change counts split
  increases from decreases** (e.g. 29 up / 35 down over 30 days) — a high count of BOTH means sellers jockeying
  competitively, not necessarily a genuine price decline; read the direction, not just the count.
  (3) The **"all sellers ever on this listing, sorted by last-seen"** view (inside Buy-Box Analysis) is a
  storefront-stalking discovery tool most people skip — sellers who dropped off THIS ASIN weeks/months ago are
  still storefront-stalkable for other current inventory; skip the largest sellers (5,000+ reviews, one
  category concentration — usually wholesale) and prefer smaller/mixed-category ones. (4) Hovering an offer
  shows the seller's total ASIN count + category spread — a fast OA-vs-wholesale heuristic (mixed categories,
  smaller count = probably OA/RA; one dominant category + huge count = probably wholesale). (5) Practitioner's
  own settings as a reference point: inbound FBA shipping 65-85¢/lb, 2 months storage buffer, prep ~$1.40/unit
  blended, FBM cost ~$8.50-10 floor for small/light items. SellerAmp supports **multiple profiles** (e.g. a
  stricter lead-generation profile — his is $4 min profit / 30% min ROI — vs a looser personal-sourcing
  profile) — a workflow pattern worth matching in our own criteria. (6) Advanced Search (SAS's built-in
  Keepa-Product-Finder equivalent) "safety net" recipe: band the Buy-Box-with-shipping price TIGHTLY and
  make current/30-day-avg/90-day-avg **all agree** (e.g. $35-45 / $33-47 / $31-49) plus a bounded 30-day
  drop% (-45% to +7%) and min offer count — multi-window price agreement, not just one 90-day snapshot, is
  the stronger stability signal; a useful extension of the existing "gate on 90-day avg, not current" rule.

### 2026-07-03
- **[practitioner]** Systematic ablation of the RAG knobs `knowledge-rag` actually exposes (arXiv 2501.07391):
  query expansion, retrieval strategy variants, a Contrastive In-Context Learning KB, plus controlled studies
  of LM size, prompt design, **document chunk size, knowledge-base size, retrieval stride**, multilingual KBs,
  and a sentence-level **"Focus Mode"** retriever. Findings are benchmark-specific — abstract staged only, read
  the PDF before touching chunking or retrieval params; use alongside the staged eval survey (2504.14891) so
  any knob change is measured, not vibes. Code public. (arxiv.org/abs/2501.07391)

### 2026-07-04 (daily run)
- **[practitioner]** *Production counter-evidence on retrieval fusion* (arXiv 2603.02153, Dell industry
  deployment, Mar 2026): multi-query retrieval + reciprocal rank fusion **raised raw recall but the gains
  were neutralized after reranking + truncation** — fusion variants did NOT beat single-query baselines on
  KB-level Top-k accuracy (**Hit@10 fell 0.51 → 0.48** in several configs) while adding latency (query
  rewriting + larger candidate sets). → For `knowledge-rag`: if a reranker is in the chain, single-query +
  rerank may dominate multi-query + RRF on both quality and latency; don't add fusion by default, A/B it
  behind the retrieval-aware eval harness (staged 2504.14891). Caveat: PDF returned no machine-readable text
  this run — staged from abstract/snippets, read the paper before design decisions. (arxiv.org/abs/2603.02153)
- **[practitioner]** *An auditable grounding harness worth copying* (arXiv 2605.01664, biomedical
  citation-aware RAG on Bedrock KB + Titan embeddings + OpenSearch, hybrid retrieval → Cohere rerank): a
  **separate LLM judge** (not the generator) makes **claim-level binary support decisions** — no outside
  knowledge allowed; vague/indirect/partial evidence counts as UNSUPPORTED — with structured output (claim →
  supported? → which source → why) persisted as CSVs at every pipeline stage. Reported 100% grounding on
  **only 25 queries** — ignore the number, steal the design: it's exactly the honest-citation check the
  guardrails demand for `Ask`, and the conservative rubric prevents overstating groundedness.
  (arxiv.org/abs/2605.01664)

### 2026-07-05 (daily run)

- **[practitioner]** RAGVA (arXiv 2502.14930, Transurban + Monash experience report): eight engineering
  challenges from a real production RAG assistant, mapping ~1:1 onto this project's risk register —
  (1) data/scope engineering, (2) security guardrails, (3) LLM-churn maintenance, (4) relevancy-vs-
  conciseness tuning, (5) automated testing (test oracle for RAG is an open problem), (6) systematic
  eval metrics (faithfulness, contextual precision/recall), (7) closing the human-feedback loop at scale,
  (8) Responsible AI. Core stance: RAG apps are nondeterministic, so **continuous validation replaces the
  traditional spec-based test plan** — supports the fba-qa-tester emphasis on retrieval regression tests.
  (arxiv.org/abs/2502.14930)
- **[practitioner]** FLAIR (arXiv 2508.13390, Microsoft, deployed in Copilot DECO): a concrete, lightweight
  recipe for the project's "self-learning RAG" goal. Offline: harvest indicators from user feedback +
  **questions synthesized from the docs themselves** (cheap bootstrap before real usage exists). Online:
  **two-track ranking** blends raw similarity with feedback indicators — augments rather than replaces
  vector search, so raw similarity stays inspectable (fits the honesty/hard-gate rules). Reported gains on
  seen AND unseen queries at production scale. → Candidate upgrade path for match_chunks once Ask has
  thumbs-up/down data; the synthetic-questions trick is usable today. (arxiv.org/abs/2508.13390)

<!-- The scheduled task appends cited takeaways under the right heading. -->

### 2026-07-06 (daily run)

- **[practitioner]** **ProductResearch (Alibaba, arXiv 2602.23716):** deep-research agents tuned on web
  search don't transfer to e-commerce — complex product research needs open-web evidence FUSED with
  structured catalog queries and claims grounded in verified product attributes. Their fix: a User Agent
  (persona + query + per-query rubric from real behavior), a Research Agent (Plan→Toolcall→Report ReAct
  over web + catalog tools), and a **Supervisor Agent — a 3-state machine verifying every plan/tool-call/
  report step** and sending targeted corrective feedback; approved trajectories are distilled into
  single-role SFT data. Qwen3-30B-A3B jumps RACE 31.78→45.40, product coverage 3.58→12.45 (>3×).
- **[practitioner]** Two liftable patterns for us without any fine-tuning: (1) step-level supervisor
  verification (check the plan, check each tool call, check the report — not one end-of-pipeline check)
  for scout lead reports and Ask answers; (2) rubric-per-query evaluation (weights over comprehensiveness/
  depth/instruction-following/readability) — pairs with the RAG-evaluation survey (2504.14891) already
  staged. Also independent confirmation of the scout_pro thesis: web + Keepa/SP-API structured data beats
  web alone. (arxiv.org/abs/2602.23716)

### 2026-07-07 (Claude Code — 5 queued YouTube transcripts pulled + ingested)

- **[practitioner]** *Keepa Product Finder live filter walkthrough* (rdltezXxIrk): the filter waterfall
  (SellerAmp's own sales-rank table for a top-1-2%-BSR-per-category cutoff → offer count 3-15, since
  <3 offers is almost always private label and >15 is oversaturated → buy-box not Amazon → rating ≥4 →
  package weight cap) turns millions of Product Finder candidates into a workable few hundred. Two Keepa
  chart signals worth adding to how we read IP risk: a **sudden flatline drop in seller/offer count**
  (e.g. 20→4 sellers in one day) is a real IP-complaint signal, while a **gradual staircase decline** is
  normal sell-through — don't treat every offer-count drop the same. Also: price during an
  Amazon-out-of-stock spike is not sustainable — size buy cost off the LOWEST price in the last 3 months,
  not the current (possibly inflated) one. Storefront-stalk sellers with ~50-1,000 reviews (5,000+ is
  usually wholesale, a different budget/business model). Cash back explicitly NOT counted as reliable
  margin — providers sometimes don't register it, so don't factor it into a buy-cost decision.
- **[practitioner]** *AMZ Prep FBA Profit Calculator* (jeqFx9ZiOhg) — vendor tool demo, verify claims
  against Amazon's own fee pages before trusting. Claims Amazon introduced **2026 price tiers (<$10 /
  $10-50 / >$50) each with a different FBA fulfillment rate**, and bills on **dimensional weight when
  higher than actual weight** — both worth a manual check against current Amazon fee docs since
  ai-brain.json/scoring.py's fee assumptions should reflect whichever is actually true. Worked example:
  Health category referral fee 15%; aged-inventory fee $0 when turnover is ~2 months. The tool's own
  "healthy" bar is 20%+ **margin** — a different metric from our 30% **ROI** gate, not directly comparable.
- **[practitioner]** *Storefront Stalking is NOT a Profitable Sourcing Method* (D3FhvdMVLl8) — short
  rebuttal video, one genuinely useful tip: Keepa Product Finder beats SellerAmp for storefront stalking
  because you can **sort a seller's storefront directly by units-sold-in-the-past-month**, prioritizing
  the fastest movers instead of manually paging through SellerAmp's slower per-page interface. Also
  promotes a paid third-party SaaS ("Arbitrage Stalker") for automated storefront-change alerts — market
  awareness only, not something to adopt.
- **[practitioner]** *Live Online Arbitrage Sourcing: Storefront Stalking Tutorial* (ljlERpMrcBk) —
  a live demo proving storefront-stalking quality is **entirely seed-dependent**: starting from a weak,
  generic seed brand (Great Value) wasted the whole session on dead-end storefronts (low-volume,
  drop-shipping-looking, or wholesale sellers). Starting from an established, high-turnover brand (Adidas
  Originals), filtered in Keepa on "Amazon out of stock ≥95% of the time" + "listed ≥1 year" (a proxy for
  a stable, proven listing), found a genuinely profitable variation within minutes. → Relevant to
  `scout/discovery_hints.py`'s brand-seed selection: seed quality (established, proven-demand brands)
  matters more than the sourcing technique itself.
- **[practitioner]** *Beginners Guide To Amazon FBA Online Arbitrage in 2026* (hxk1JS4EsU4) — a full OA
  fundamentals course. Core Keepa signal, repeated heavily: **offer count falling → price rises** (source
  here); **offer count rising → price falls** (avoid, or expect the price you're anticipating to not
  hold). Buy-Box suppression within the last 6-8 months = reduce order size as a hedge, not an automatic
  pass; the risk resets the longer it's been since the last suppression event. One seller holding a
  disproportionate buy-box % at a shared price point across several same-priced FBA competitors suggests
  an inventory-advantage imbalance — mainly a wholesale-competition risk, less relevant to typical
  arbitrage listings which tend to rotate more evenly. **Ungating claim (unverified against Amazon's own
  docs — treat as a practitioner claim, not policy):** invoices reportedly matter far less now than
  account health score + total sales count, with **~200 sales** cited as a threshold where many
  previously-restricted brands start auto-approving — a new-seller bootstrapping tactic, not something to
  encode into `ai-brain.json` without independent confirmation. Financial hygiene notes: never fold cash
  back into buy-cost math (it's a rebate, and unreliable to register — matches rdltezXxIrk above); stack
  gift-card discount sites (CardCookie, Raise) with retail coupons for real savings. Portfolio rule: buy
  **wide** (many SKUs, few units each), not deep, and reorder roughly 3-4 weeks of stock based on the
  observed sell-through rate once tested. States a personal **30% minimum ROI** threshold — matches
  `ai-brain.json`'s existing `minRoi: 0.3` exactly, a useful independent corroboration.

### 2026-07-07 (daily run)

- **[practitioner]** *Hybrid Search for RAG: Vector + BM25 + Reranking* (BuildMVPFast, Mar 2026) — the most
  directly applicable build source in a while for `knowledge-rag`. Pure vector search fails on exact-match
  queries (error codes, SKUs, acronyms like "GAN", quoted names) — one team saw ~35% of queries hit this;
  the fix is **hybrid**: run vector + BM25 in parallel and merge with **Reciprocal Rank Fusion**
  (`RRF(d)=Σ 1/(k+rank)`, k≈60), which sidesteps the score-scale mismatch that breaks weighted blending.
  Then **rerank**: pull a broad candidate set (top ~20-50), run a cross-encoder reranker, keep top 5-10 for
  the LLM. Weaviate/BEIR benchmarks cited: hybrid+rerank lifts Success@1 0.43→0.52, Recall@5 0.70→0.81,
  nDCG@10 0.61→0.70. **Postgres-native path that fits our Supabase stack: pgvector (dense) + the ParadeDB
  `pg_search` BM25 extension, merged with RRF** — no second datastore. Four production gotchas: (a) if doing
  weighted (not RRF) blending, normalize BM25 (0→∞) vs cosine (-1→1) first; (b) uniform ~500-token chunks
  neuter BM25 length normalization — enrich chunks with section/parent titles; (c) static weights ignore
  query intent — lean keyword for identifiers/code, vector for natural-language questions; (d) rerank 20-50,
  not 5 (miss best hits) or 200 (latency/cost). Added latency ~200-400ms; cost negligible vs the LLM call.
  Not implemented — staged as the concrete upgrade path if `knowledge-rag` retrieval quality needs a lift.
  (buildmvpfast.com/blog/hybrid-search-rag-vector-keyword-reranking-2026)

### 2026-07-07 (Claude Code — 3 more queued YouTube transcripts pulled + ingested)

- **[practitioner]** *Keepa Charts: The Ultimate Amazon FBA Tutorial for 2026* (wwNw5vNAyeM) — the most
  technically precise Keepa walkthrough ingested to date; several corrections to common misreadings worth
  encoding into how we talk about Keepa data. (1) The "monthly sold" gold line is a **customer-count range**
  reported directly by Amazon (50+, 100+, 200+...), not literal units — if avg units/customer is 1.5, "50+"
  could mean anywhere from 50-100+ actual units; it's also a trailing 30-day figure updated daily, and only
  ~3.5M of 1B+ tracked ASINs even get it. When the line disappears, it does NOT mean the item stopped
  selling — it may have just dipped under the next-lowest reporting bucket. (2) Sales-rank "drops/month" is
  directionally useful but has **no fixed correlation to units sold** — one drop can represent one sale or
  several. (3) The Buy Box price is **regionally directional, not exact** — Amazon's flywheel distribution
  model means the price Keepa captured may differ from what a buyer in a different region actually sees;
  useful for trend-reading, not as an exact quote. (4) A **suppressed buy box slows sales, it does not stop
  them** — nuances the common "avoid recently-suppressed listings" heuristic into a matter of degree, not an
  absolute pass signal. (5) Seasonal-product timing rule: **be first in or last out** — entering mid-ramp
  means competing at peak competition for shrinking margin; either front-run the season before competition
  floods in, or hol
### 2026-07-09 (daily run — build-the-system)
- **[fetch-pending / snippet only]** Two on-thread arXiv papers were surfaced but the sandbox fetch-
  provenance rule blocks arXiv `/abs/` + PDF (same failure mode as SAGE 2605.12061 / ROZA 2604.07595 —
  flagged for Claude Code re-fetch): (1) **"Don't Retrieve, Navigate: Distilling Enterprise Knowledge into
  Navigable Agent Skills for QA and RAG" (arXiv 2604.14572)** — argues for distilling a corpus into
  navigable *agent skills* rather than pure vector retrieval; directly relevant to our skills-as-knowledge
  design (the fba-* plugin already encodes rules as skills). (2) **"Adaptive Memory Admission Control for
  LLM Agents" (arXiv 2603.04549)** — when to *admit* a fact into long-term memory; on-thread with the
  AtomMem (2606.19847) / self-learning-RAG line and directly applicable to how ai-brain.json / the corpus
  decide what durable facts to keep vs. drop. Distill both after a real-browser fetch before staging.
- **[fetch-failed]** *Build a RAG System with pgvector on Managed PostgreSQL (2026)* (DanubeData,
  danubedata.ro/blog/pgvector-rag-managed-postgres-2026) — WebFetch returned compressed/binary garbage
  (server sent an unreadable encoding), so no usable text. Directly on-stack for our Supabase/pgvector RAG;
  search snippet frames it as a pgvector production build guide (mature pgvector, <1M vectors, hybrid
  search native). Worth a Claude Code / browser re-fetch. Corroborated by already-staged BuildMVPFast
  (2026-07-07) hybrid-search mechanics — no new action needed until re-fetched.
 data error or a sign
  the rights-holder isn't policing the listing — read both ways, don't assume either).
- **[practitioner]** *Amazon Online Arbitrage Product Sourcing MASTERCLASS For 2026* (1kgp13McYLc) — a
  full beginner course; most content already covered by earlier ingested videos, but two new concrete
  items: (1) **Boxom's "bulk ungate checker"** — paste many ASINs/brands at once and it checks auto-ungate
  eligibility for up to 5 brands/second, replacing the old one-by-one manual Seller Central check; a
  genuinely useful tool to be aware of if we ever build ungating-aware scout logic. (2) When there's a price
  gap between the FBM buy box and the lowest FBA offer, price an FBA listing **5-10% above** the FBM buy
  box — Amazon's own delivery-speed preference means FBA still wins share at a premium over FBM-only
  competition. Restates "you don't find items good, you make items good" via stacked discounts (coupon +
  tax-exempt + cashback + subscribe-and-save + discounted gift cards, this time naming **CardBear** as
  another discount-gift-card marketplace alongside CardCookie/Raise from earlier videos) and a vivid
  COVID-era seasonal-pool-price example ($147 normal -> $325 in 2020 -> $475 in 2021) used to make the
  point that arbitrage is mostly about reliably profitable *boring* products, not chasing spikes.

### 2026-07-10 (Claude Code — transcript ingestion, 3 queued videos)
- **[practitioner]** *Online Arbitrage Just Got Easier — NEW Sourcing Method* (Tcd4jAkOi6Q) — first look
  at **SellerAmp's new Advanced Search**: query across ALL products (not one storefront) by 90-day avg
  sales rank (≤~175k), ≥3 avg sellers/90d, Amazon-in-Buy-Box ≤50%, then narrow by a brand seeded from
  reverse sourcing and sort by 90-day Buy Box **ascending price** (rising price = better profit odds).
  Time brand-digs to retailer promos: check the brand's retail site for sale banners / coupon-extension
  hits FIRST — no promo, skip and revisit. Margin manufacturing: discounted gift cards (CardCenter/
  CardCookie, 12-15%) stacked on retail coupons (15-20%) flipped two near-misses into $8-10/unit at
  30-35% ROI. The **"lowest-ever sales rank" flag** finds all-time-high-demand items (restock-gap and
  price-spike plays). Risk read matches our price-spike guard: a price that "randomly shot up" is a risky
  max-cost base vs a long stable history; rank 14k→2k entering season = accelerating item.
- **[practitioner]** *How to Find Profitable Amazon Products FAST in 2026 — Reverse Sourcing* (FRK7JY7_EJY,
  Chris Grant) — four methods, starting from a blank screen: (1) seed from **retailer-exclusive brands**
  (Equate/Spring Valley=Walmart, Up&Up/Goodfellow=Target, Kirkland=Costco, Sephora Collection) — any 3P
  seller there is necessarily an arbitrageur of that retailer, so their storefronts are pre-qualified for
  stalking; prefer sellers with **≤200-250 reviews and ≥4 stars** (ungating profile closer to a newer
  seller's). (2) The **"shotgun method"**: Keepa product → Data→Offers→include historical offers → export
  up to ~50 seller IDs → Product Finder "seller is one of" + rank <300k (current/30d/90d) + price ≥$25
  (current/30d/90d) + a 30-day price-drop **corridor of -45% to +7%** → a ~200-product sourcing session.
  [NOTE for our stack: this needs Keepa Product Finder, which is REQUEST_REJECTED on our Pro plan — a
  manual/UI method for us; but the rank/price/drop *corridor* idea independently validates our dealfeed
  secondary-axis band rotation.] (3) Margin stack: cashback 3-8% + gift cards 12-15% (CardCookie/CardDepot)
  + coupon extensions (Coupert/Rakuten/Honey); verify pack counts via reviews and images (a "2-pack" image
  that's one pair; 30-count-4-pack vs 60-pack traps) — the same pack-mismatch risk our compliance gate
  flags. (4) Risk heuristics worth encoding: **"buying the pinch"** (rising seller count → price about to
  slide) and the **asymmetric-bet test** (breakeven vs the 6-month price low — Bombas socks failed it).
  Storefront Stalker Pro re-checks chosen storefronts every 4h for new items (creator-affiliated claim).
- **[practitioner]** *How To Use Keepa for Amazon FBA — New Feature Tutorial* (ctwXY3Vwy8o) — three new
  Keepa features: (1) **historical sales-rank filter** ("crystal ball"): current rank 75k-200k AND
  December-last-year rank 1-20k = pre-season Q4 winners before the charts move; brand-scoped variant
  predicts which wholesale SKUs to load before the PO. (2) **No-current-rank + strong historical rank** =
  invisible listings (OOS/merged/bad category node) — restock plays with zero competition. (3)
  **Historical offers + cross-seller matching**: one seller ID with the historical toggle exposes their
  entire lifetime catalog (2,195 vs 158 live ASINs) for export/automation; N seller IDs + "X of them
  match" + Search Insights' top-brands (all-time vs now) reveals which brands competitors converge on and
  how their mix is shifting. Also usable on your OWN seller ID (+ Buy Box 90-day delta -100..-20) as a
  replenishment finder for past products now rising in price. [ML note: the historical-rank-divergence
  signal (Dec-rank vs now-rank) is a legitimate seasonal-demand feature idea for the backtest side —
  flagged for fba-feature-engineer as an idea, no threshold change proposed.]

### 2026-07-12 (Claude Code -- transcript ingestion, 1 queued video)
- **[practitioner]** *The FASTEST Way Find Online Arbitrage Products for Amazon FBA (2026)* (-Rv5hejVnVs,
  Chris Grant) -- one genuinely new tactic not yet in the corpus: **mine your own SellerAmp lookup
  history, not just live storefronts.** SellerAmp's History section keeps every product ever run through
  the profit calculator, even ones rejected as unprofitable at the time (Grant's own example: ~10,000
  products since May 1). Re-walk it periodically -- the market is dynamic on both sides (source-site sale
  prices, coupon/gift-card availability, and Amazon's own price/competition all shift), so a past reject
  can turn profitable later with zero new discovery cost, and each hit doubles as a fresh storefront-
  stalking seed (open the seller who's still on that listing). Live worked example distinguishes this
  from a live catalog re-check: one item priced at $19.99 on May 1 had moved to $23 on Amazon with the
  source price flat -- still dead; the ones that DID clear the bar needed the full cashback+gift-card+
  coupon stack already documented from FRK7JY7_EJY (2026-07-10) to close the gap, so no new stacking
  mechanic here. One caution worth keeping: an item that started as an ORPHAN ASIN (thin/no sales) and
  got MERGED into a parent listing showed continued weak velocity post-merge in Keepa's new-offer-count
  trend -- a reminder that a parent-ASIN merge doesn't retroactively grant the parent's demand to a
  previously-orphaned variation; check the merged child's own post-merge trend, not just the parent's
  aggregate history. Storefront stalking itself (the video's closing point) and the discount-stack
  mechanics are already well covered (see FRK7JY7_EJY above, the 07-08/07-09 entries); not re-summarized
  here to avoid Chris-Grant/storefront-stalking corpus skew -- this entry adds only the History-section
  tactic and the orphan-merge caution, the two things this video contributed that weren't already
  captured. (youtube.com/watch?v=-Rv5hejVnVs)
- **[practitioner]** *Revealing Winning Amazon Online Arbitrage Product Examples (FULL BREAKDOWN)*
  (a4A9YGu71Eg) -- six worked examples restate stacking mechanics already deep in the corpus
  (CardBear/discounted gift cards, tax-exempt reseller certs, cashback/coupon extensions --
  Capital One Shopping/Rakuten/TopCashback, subscribe-and-save auto-ship discounts, the "Prime bump"
  5-10% delivery-speed premium, holiday-sale + signup-coupon combos -- see the 07-08/07-09/07-10
  entries); one new tactic: set up a **catchall email domain via Namecheap** so every inbox alias at
  that domain auto-delivers, letting you re-trigger a retailer's one-time-per-email signup/welcome
  coupon code repeatedly under fresh-looking addresses instead of it working only once per real inbox.
  (youtube.com/watch?v=a4A9YGu71Eg)
- Two more 2026-07-12-queued videos reviewed and **not staged** (thin/duplicate, matching the
  established skipped-thin convention): *The New FASTEST Online Arbitrage Product Sourcing Method |
  SellerAmp QVS* (6sUYXwY7RNw) -- a live "leaf sourcing" demo already staged verbatim from
  PydYmi56Sso, plus already-documented storefront stalking / auto-ungate brands / CardBear / Keepa
  Variations-tab checks; only scrap was 3 new Kohl's-affiliated auto-ungate brand names (Cuddle Duds,
  Stafford, 32 Degrees), too thin on its own. *The BEST Online Arbitrage Sourcing Method For Beginners
  (2026)* (MWyq0J18-sM) -- beginner SellerAmp/storefront-stalking rehash on Jellycat storefronts
  (already-documented winning-product bar, Prime-bump pricing, reverse-sourcing-by-Google, CardBear
  stacking, SAS Sheets export); worked examples add no new mechanic and would worsen the corpus's
  existing Jellycat/storefront-stalking concentration. See `research-manifest.json` for the
  `skipped-thin` records.

### 2026-07-13 (daily run — build-the-system, fetch-pending)
- **[fetch-pending — NOT yet distilled]** Three new arXiv papers on the self-learning-RAG / agent-memory
  thread were surfaced this run but **arXiv `/abs/` + PDF remain blocked by the sandbox fetch-provenance
  rule** (same failure mode as 2604.07595, 2605.12061, 2606.19847 etc.), so only titles/snippets are known —
  **no insights are staged from them** (per the honesty rule, abstracts are not distilled without reading).
  Re-fetch + distill in Claude Code before staging: (1) **Ask Only When Needed: Proactive Retrieval from
  Memory and Skills for Experience-Driven Lifelong Agents** (arXiv 2604.20572) — proactive/on-demand retrieval
  from *both* memory and skills; directly on-thread with our skills-as-knowledge design and the "don't retrieve
  when the answer is already gated/known" idea. (2) **MemR³: Memory Retrieval via Reflective Reasoning for LLM
  Agents** (arXiv 2512.20237) — reflective-reasoning memory retrieval; relevant to how Ask/scout pulls from
  the corpus + ai-brain. (3) **Did You Check the Right Pocket? Cost-Sensitive Store Routing for
  Memory-Augmented Agents** (arXiv 2603.15658) — routing a query to the right memory store cheaply; on-thread
  with the memory-admission line (AtomMem 2606.19847, Adaptive Admission 2603.04549). See
  `research-manifest.json` for the `fetch-pending` records.
