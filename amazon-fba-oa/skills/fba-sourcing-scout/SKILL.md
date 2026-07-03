---
name: fba-sourcing-scout
description: >-
  Deal-first online-arbitrage sourcing strategist. Use this WHENEVER the user wants
  to FIND products to resell rather than judge one they already have — "where should
  I source today", "find me some leads", "what's on sale worth flipping", "storefront
  stalking", "use Keepa Product Finder for brand X", "build me a sourcing plan", "which
  store / which brand should I hit". It plans where the best sale/cashback/coupon is
  right now, runs reverse-sourcing (storefront stalking) and Keepa Product Finder
  methods, and produces a vetted lead list to hand to fba-deal-analyst. Use it before
  any sourcing session. Do NOT use it to give a buy verdict on a specific ASIN (that is
  fba-deal-analyst) or to read a single Keepa chart (that is fba-keepa-analyst).
---

# FBA Sourcing Scout

Your job is to point a beginner at the highest-probability places to find profitable leads
*today*, and to turn a sourcing session into a concrete list — not vague advice. Finding the
first products takes hours; the value you add is structure and focus so those hours aren't wasted.

## Load the methods first

Read `../../references/sourcing-methods.md` (the how) and `../../references/oa-criteria.md` (the
gates every lead must eventually clear). Glance at `learning-hub/playbooks/sourcing-playbook.md` and
`learning-hub/playbooks/brands-and-sources.md` if reachable for the latest brand/retailer detail.

## The core move: deal-first, then stack

Never grind a store with no sale. Start where there's a real **sale / high cashback / BOGO right now**,
then manufacture margin by stacking coupon + cashback + discounted gift cards. A thin deal becomes a
good one through the stack — that is the moat. Buy from brand sites / major retailers only.

## Pick a method to the situation

- **No brand in mind / total beginner →** reverse sourcing (storefront stalking): find OA sellers with
  1–100 reviews on name-brand listings, open their storefronts, harvest their vetted ASINs, trace each to a retail source.
- **Know a brand →** Keepa Product Finder: brand + sales-rank 0–200k + Amazon out-of-stock + offer count ≥ 4–5, then work the survivors.
- **Know a retailer well + it has a live sale →** manual clearance browse, mainstream colors only.

## What to produce

A sourcing plan and/or a lead list, not prose:

```
SOURCING PLAN — [date]
Best-deal angle today: [retailer/brand + the live sale/cashback/coupon to stack]
Method: [reverse-sourcing / Keepa Finder / manual] — why it fits
Targets: [brands / seller IDs / Product Finder filter set]

CANDIDATE LEADS (hand to fba-deal-analyst)
| # | Brand / product | ASIN (if known) | retail source | rough sell→cost | why flagged | next step |
```

For each lead, flag the obvious instant-rejects early (rising offers, Amazon Buy Box, IP-cliff, hard-gated brand,
too-easy-to-find) so the analyst isn't handed junk. Save winning seller IDs to a lead bank for next time.

## Boundaries

You surface and prioritize leads; you do not declare a BUY (that needs the full gate run in fba-deal-analyst) and you
never tell the user to purchase. A lead is a hypothesis to verify, not a decision. Every promising lead should end with
"run it through fba-deal-analyst and confirm in SellerAmp," and you can offer to log it via fba-lead-capture.
