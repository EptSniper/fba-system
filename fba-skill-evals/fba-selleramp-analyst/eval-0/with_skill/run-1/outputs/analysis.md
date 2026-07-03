# SellerAmp (SAS) Setup — get the ROI numbers trustworthy before you source

Short version: weird ROI almost always means a settings problem, not a math problem. SellerAmp is the human verification front end of this operation — there's no live SAS API, so a correct manual setup is what makes every profit number you read afterward trustworthy. Set these once, then your ROI will stop jumping around.

## The settings to put in (one-time, in SAS settings)

| Setting | Value | Why |
|---|---|---|
| **Inbound shipping** | **~$0.60/lb** (range $0.50–0.80) | Your cost to ship units into Amazon FBA. If this is blank or wrong, ROI is off on every item. Re-check the rate after each real FBA shipment. |
| **Min BSR / Max BSR** | **Min 0% / Max 2%** | Targets the top 2% of the category so you only see things that actually sell. |
| **Min profit** | **$3.00 / unit** | Our floor — thinner deals aren't worth the time. |
| **Min ROI** | **30%** (≈25% acceptable only for non-returnable grocery) | The gate SAS colors the deal against. |
| **Prep fee** | **Your real per-unit prep-center fee** (use $0.50/unit if you self-prep / no center) | Amazon no longer preps/labels US FBA, so this is a real cost. |
| **Sales tax** | **Leave the % field OFF — bake tax into the cost price instead** (see below) | This is the #1 cause of weird ROI. |

## The most likely cause of your "weird ROI numbers": tax double-counting

This is the trap. SellerAmp has a **sales-tax % field** AND it uses the **cost price** you type in. If you enter your buy price *and* turn on the tax %, SAS adds tax on top of a number that, depending on how you entered it, may already include tax — so it's counting tax twice and crushing your ROI. Then on the next item you enter it differently and ROI swings the other way. That inconsistency is the "weird numbers."

**Fix — pick ONE method and always do it the same way:**
- **Recommended:** turn the tax % field OFF and **bake tax into the cost price**: `cost price = total receipt / number of units`. That single landed number is exact and never double-counts.
- Do **not** also use the % field once you've baked it in.

## The second most likely cause: shipping not in the landed cost

True landed cost **must include inbound + the cost to get the item to you**. A $10 item with $9.95 shipping is a **$20 cost**, and 100% ROI becomes break-even. Make sure the inbound-shipping setting above is filled, and enter the item's true delivered cost (or bake delivery into the cost price the same way you do tax).

## After you fix the settings — reading the panel

- **Profit / ROI / Margin** — the headline. Compare against the **$3 / 30%** gates. ROI = profit / landed cost. With tax and shipping correct, these stop swinging.
- **Breakeven** — the sell price where profit hits $0. Your downside marker.
- **Max Cost — use it as a reverse calculator.** This is the most you can pay per unit and still hit 30% ROI. **This is the number to take shopping.** If you can land below Max Cost after stacking discounts (coupons, cashback, discounted gift cards), the deal works.
- **Estimated sales / rank** — sanity-check against Keepa. An **"!"** means the figure is shared across variations, so trust it less.
- **Eligibility & IP alert** — SAS shows gated/eligible and an IP flag. **Trust the IP Alert tool over the SAS IP flag** unless the SAS one is RED. Eligibility still has to be confirmed by **listing the ASIN in Seller Central before you buy** — SAS can't grant real account-specific eligibility.

## Quick self-test
Run one item you already know. If ROI looks sane and the same item gives the same ROI twice in a row, your tax/shipping setup is fixed. If it's still swinging, you're still entering tax inconsistently — go back to "bake it into cost price, % field OFF."

---

```
SELLERAMP READ — [setup, no ASIN yet]
- Settings sanity: fix needed -> set inbound shipping ~$0.60/lb; Max BSR 2%; Min profit $3; Min ROI 30%; prep = real fee; TAX baked into cost price, % field OFF (this is your weird-ROI cause)
- Profit / ROI / Margin vs gates ($3 / 30%) -> reliable only after the tax + shipping fixes above
- Breakeven = downside marker; Max Cost = the number to take shopping (land below it after stacking)
- Eligibility: confirm by list-before-you-buy in Seller Central; IP: trust IP Alert over the SAS flag unless SAS is RED
- Read: settings first -> once ROI is stable and repeatable, the panel is trustworthy
Hand-off: confirm demand in fba-keepa-analyst; final gate run in fba-deal-analyst. SAS is verification, not a buy order. No money moves without your approval.
```
