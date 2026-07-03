# Max Cost for a $32 Buy Box at 30% ROI

**Short answer:** Your maximum buy cost is roughly **$15-$18 per unit**, depending on the item's shipping weight. For a typical small-and-light item it's about **$16-$17**.

This is the SellerAmp "Max Cost" concept worked backwards: holding the sell price at the $32 buy box and your ROI target fixed, solve for the highest cost you can pay and still clear the target.

## Your ROI target

From the project brain (`learning-hub/data/ai-brain.json`, `criteria.minRoi`), the minimum ROI gate is **30%**. The numbers below are calculated to hit exactly that floor. ROI here = net profit / buy cost (the project's definition in `scout/scoring.py`).

## The math (project's own fee model)

Using the exact fee assumptions the scout uses (`scout/config.py` + `scoring.py`):

- Sell price: **$32.00**
- Referral fee: 15% -> **$4.80**
- FBA fulfillment: by weight tier, plus 3.5% fuel surcharge
- Prep cost: **$0.50/unit** (since Jan 2026 the seller preps/labels US FBA)
- ROI target: **30%**

Formula inverted for Max Cost:

```
MaxCost = (price - referral - fulfillment - prep) / (1 + ROI_target)
```

## Max Cost by item weight

| Item weight        | FBA fulfill (incl. fuel) | **Max Cost** | Net profit | ROI |
|--------------------|--------------------------|--------------|------------|-----|
| <= 12 oz (0.75 lb) | $3.33                    | **$17.97**   | $5.39      | 30% |
| 12-16 oz (1.0 lb)  | $4.81                    | **$16.84**   | $5.05      | 30% |
| 1.5 lb             | $5.69                    | **$16.16**   | $4.85      | 30% |
| 2.0 lb             | $6.31                    | **$15.68**   | $4.70      | 30% |
| 2.5 lb (common)    | $6.86                    | **$15.26**   | $4.58      | 30% |
| 3.0 lb             | $6.99                    | **$15.16**   | $4.55      | 30% |

**The single number you probably want:** if it's a light item (under ~1 lb), don't pay more than about **$16.84**. If you don't know the weight yet, **$15.26** (the common 2.5 lb tier) is a safe conservative ceiling.

## Important caveats

1. **Weight drives the answer.** Fulfillment fee is the biggest swing factor. Get the real shipping weight/size tier before committing - heavier or oversize items push Max Cost down fast.
2. **Referral rate varies by category.** I used the standard 15%. Some categories differ (e.g. some are 8%, some 17%), which shifts Max Cost. Confirm the category's actual referral %.
3. **The $3/unit profit floor.** The project also requires >= $3 net profit per unit (`minProfitPerUnit`). At these Max Costs you clear $4.50+, so the 30% ROI gate is the binding constraint here, not the profit floor.
4. **This is a pre-buy estimate.** These fees are approximations from the project's model. **Confirm the exact Max Cost in SellerAmp / Amazon's Revenue Calculator for the specific ASIN before buying** - real dimensions, category fees, and any storage/return costs can move it.
5. **Eligibility is separate.** Hitting ROI doesn't mean you're allowed to sell it. Check gating, IP/brand risk, hazmat/meltable, and that Amazon doesn't hold/rotate the buy box before you source.

## If you want more cushion

The 30% figure is the floor. If you'd rather target a safer 40-50% ROI (more buffer for returns and price drops), your Max Cost drops accordingly - e.g. at 40% ROI on the 1 lb tier, Max Cost falls from $16.84 to about **$15.65**. Tell me your target ROI and the item's weight/category and I'll give you the exact single number.
