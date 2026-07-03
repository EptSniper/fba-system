# 2026 Update to U.S. Referral and Fulfillment by Amazon Fees

- **Source URL:** https://sellingpartners.aboutamazon.com/update-to-u-s-referral-and-fulfillment-by-amazon-fees-for-2026
- **Official detail page:** https://sellercentral.amazon.com/help/hub/reference/external/G201411300
- **Published:** 2025-10-15 (Amazon Selling Partner Services)
- **Fetched:** 2026-06-30
- **Classification:** [policy] — official Amazon statement of fee changes
- **Topic:** amazon_help_docs

## Source text (key excerpt)

Amazon's letter to sellers: "In 2026, FBA fees will increase by an average of $0.08 per unit sold, or
less than 0.5% of an average item's selling price. This is on top of no increase in US Referral and FBA
fees in 2025... There will be no new FBA fee types in 2026... Unless otherwise noted, all changes will be
effective January 15, 2026. You have at least 90 days before any fee increases take effect."

## Distilled takeaways

1. **[policy]** US FBA fulfillment fees rise an **average of $0.08/unit** in 2026, effective **Jan 15, 2026**;
   **referral fees and fee types are unchanged** (no new fee types). Average ≠ uniform — increases are tiered
   by size/price band, so re-check fee on each ASIN rather than assuming the average.
   (sellingpartners.aboutamazon.com)
2. **[policy]** Amazon directs sellers to recompute unit economics with the **Revenue Calculator**, the
   **Fee and Economics Preview report**, and the new **Profit Analytics dashboard** (all updated to 2026 rates).
   These are the authoritative inputs for the scout's fee math — prefer them over hard-coded fee tables.
3. **[policy]** Amazon frames "lower-fee options" (packaging updates, lower-cost inbound shipment options,
   healthy inventory levels) as levers — relevant to landed-cost assumptions, not just the headline fee.
4. **Action for this project:** verify `fba-deal-calculator` / `scout/config.py` fee constants reflect the
   Jan 15 2026 schedule; treat the separate **April 17, 2026 fuel & logistics surcharge** (reported by
   secondary sources, confirm in the official detail page) as an additional line before trusting ROI output.
