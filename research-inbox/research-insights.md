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

<!-- The scheduled task appends cited takeaways under the right heading. -->
