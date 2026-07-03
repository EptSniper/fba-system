# FBA Eligibility Analysis — Scented Candles + Hand Sanitizer (Q4 clearance)

**Question being answered:** *Am I allowed to send these into FBA?* — eligibility and account risk only. This is **not** a profit opinion. Whether either deal makes money (ROI, fees, Keepa demand, sell-through before the season ends) is a separate question for fba-deal-analyst / fba-deal-calculator.

**Honest limitation up front:** Eligibility is **account-specific** and is ultimately decided in Seller Central / SP-API. I can flag risk and likelihood, but I cannot truly clear any ASIN. The decisive test for every SKU is **list-before-you-buy**: try to create the listing in Seller Central; if it is hard-gated for your account, don't buy. Everything below is a risk read, not a clearance.

Also note: you gave me product *categories*, not specific ASINs or brands. Without ASINs I can't check gating, IP history, the Keepa offer-count cliff, or brand-as-seller for the actual items. The two categories you named, however, both carry well-known structural eligibility problems that apply regardless of brand — so the headline answer is driven by category, and the per-ASIN checks still have to happen before you buy.

---

## 1. Scented candles

```
ELIGIBILITY CHECK — Scented candles (category, no ASIN/brand given)
- Gating: unknown — must verify per ASIN in Seller Central. Candles themselves are
  not a universally gated category, but specific brands may be gated or IP-protected.
- IP / brand risk: unknown per brand — clearance/closeout candles are frequently
  private-label or store brands (lower IP risk) but can also be name brands the owner
  polices. Check each brand against the avoid-list, run IP Alert, and look for a Keepa
  offer-count cliff before buying.
- Hazmat / meltable / expiry / oversize:
    * HAZMAT — YES, likely. Candles contain wax + a wick and are commonly classified
      by Amazon as a flammable/hazmat item. Hazmat ASINs require Amazon's dangerous-
      goods review and an approved hazmat path before they can go into FBA; some are
      FBA-ineligible and must ship FBM. This is the primary blocker, not brand.
    * MELTABLE — YES. Wax is heat-sensitive. Amazon enforces a meltable/heat-sensitive
      FBA window (roughly mid-spring through early fall, ~Apr 15-Oct 15 historically),
      during which meltable inventory is restricted or surcharged. For a Q4 inbound this
      is largely in your favor — Q4 sits outside the typical meltable restriction window
      — but confirm the current dates in Seller Central, because the window and the
      hazmat rule are two separate gates and hazmat does not go away in Q4.
    * Expiry — generally not dated goods.
    * Oversize — usually standard size; confirm per ASIN (multi-wick / jar sets can be heavy).
- Condition / variation notes: sell New only. Watch scent/size variation listings —
  you may be eligible/hazmat-approved on some children and not others; match the exact ASIN.
VERDICT: VERIFY-FIRST  (hazmat classification is the gate that decides this)
Decisive next step: for each candle ASIN, (1) check the hazmat / dangerous-goods
  classification and your hazmat-eligibility status in Seller Central, and (2) try to
  list it before buying. If it shows as hazmat-restricted or FBA-ineligible for your
  account, do not buy for FBA.
Caveat: risk assessment only; real eligibility is account-specific and confirmed in Seller Central.
```

**Plain read:** Candles are the riskier of the two on *eligibility*, but the risk is hazmat/meltable classification, not brand gating. The good news for your Q4 timing is that the meltable restriction window is typically a warm-season rule, so a Q4 inbound usually sidesteps it. The bad news is the hazmat (flammable) classification is year-round — if these ASINs are flagged dangerous-goods and your account isn't approved for that path, they're blocked from FBA regardless of season. Resolve hazmat status per ASIN first.

---

## 2. Hand sanitizer

```
ELIGIBILITY CHECK — Hand sanitizer (category, no ASIN/brand given)
- Gating: VERY LIKELY GATED / restricted. Hand sanitizer is a topical antiseptic —
  an OTC drug-adjacent / health-and-personal-care item. These categories are commonly
  approval-gated, and hand sanitizer specifically drew tightened Amazon restrictions
  (and FTC/FDA scrutiny over methanol contamination and false efficacy claims). Expect
  to need approval, and expect some brands/ASINs to be hard-gated. Verify per ASIN.
- IP / brand risk: unknown per brand — check each against the avoid-list, run IP Alert,
  watch for an offer-count cliff. Brand risk is the secondary concern here; the primary
  concern is the regulated-product gating below.
- Hazmat / meltable / expiry / oversize:
    * HAZMAT — YES, likely. Alcohol-based hand sanitizer is flammable and is routinely
      classified as hazmat/dangerous goods by Amazon. Requires dangerous-goods review
      and an approved hazmat path; may be FBA-restricted.
    * EXPIRY — YES. Hand sanitizer is a dated/regulated OTC product. Amazon enforces
      expiration-date and remaining-shelf-life requirements on dated goods, and you must
      meet labeling/lot/expiry rules. CLEARANCE STOCK IS THE RISK HERE: clearance is
      often clearance because it is near expiry or discontinued. Short-dated sanitizer
      can be refused at the FBA dock or fail Amazon's remaining-shelf-life rule.
    * Meltable — no. Oversize — usually no; confirm per ASIN.
- Condition / variation notes: New only. Regulated OTC product — labeling, drug facts
  panel, and lot/expiry compliance matter. Variation packs (sizes/multipacks): match exact ASIN.
VERDICT: VERIFY-FIRST, leaning BLOCKED for clearance stock specifically
Decisive next step: before buying, (1) confirm the category/brand is approvable for your
  account in Seller Central (try to list it), (2) confirm hazmat path eligibility, and
  (3) verify the actual expiration date on the clearance lot meets Amazon's remaining-
  shelf-life requirement with margin to spare. If it's short-dated or you can't get
  ungated, do not buy.
Caveat: risk assessment only; real eligibility is account-specific and confirmed in Seller Central.
```

**Plain read:** Hand sanitizer stacks three eligibility problems at once — likely category/brand gating (regulated OTC/health item), likely hazmat (flammable alcohol), and expiration/shelf-life rules. The fact that it's **clearance** makes the expiry problem materially worse: clearance health goods are frequently near-dated, and Amazon can refuse short-dated inventory. For a beginner protecting the account, this is the higher-risk of the two products on eligibility grounds.

---

## Summary verdict

| Product | Eligibility verdict | The gate that decides it |
|---|---|---|
| Scented candles | **VERIFY-FIRST** | Hazmat (flammable) classification per ASIN; meltable window mostly OK for Q4 |
| Hand sanitizer | **VERIFY-FIRST, leaning BLOCKED on clearance** | Category/OTC gating + hazmat + short-dated clearance shelf-life |

**So: are you "good to send these into FBA"?** Not yet — not on the strength of "they're on clearance for Q4." Neither is clearly ALLOWED at this point, and neither is auto-cleared. Both are **VERIFY-FIRST**, and hand sanitizer in particular leans toward BLOCKED specifically *because it's clearance* (expiry/shelf-life risk on a regulated, hazmat product).

**Decisive next step for both:** for each real ASIN, list-before-you-buy in Seller Central. That single test resolves gating. On top of it: confirm hazmat/dangerous-goods eligibility on both, confirm the candle meltable window for your Q4 inbound dates, and physically verify the expiration date on every hand-sanitizer clearance lot before committing a dollar.

**Account-safety note:** you're a beginner and the account is the one asset you can't afford to damage. Both of these categories are exactly the kind that get accounts into trouble (hazmat refusals, expired-goods complaints, OTC compliance). A profitable item that suspends the account is a catastrophic loss — so caution beats optimism here.

**Reminder on scope:** this is the *allowed* half only. Whether either is worth buying on the numbers (ROI >= 30%, profit >= $3, BSR <= 200k, real demand, ability to sell through before Q4 ends) is a separate analysis for fba-deal-analyst / fba-deal-calculator. And no purchase is approved here — the buy decision stays with you, the human.
