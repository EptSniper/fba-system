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

<!-- The scheduled task appends cited takeaways under the right heading. -->
