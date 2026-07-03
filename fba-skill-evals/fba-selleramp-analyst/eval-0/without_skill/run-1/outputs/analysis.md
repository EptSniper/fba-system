# SellerAmp (SAS) Settings — Set These Once, Correctly

Weird ROI numbers almost always come from SellerAmp's **cost inputs being wrong or empty**, not from a SAS bug. ROI = profit / your-cost, so if any cost field (buy cost, inbound shipping, prep) is off, the ROI it shows is off. Set the fields below once in **Settings**, and the panel will match your real economics on every listing.

## The settings that actually move your ROI

### 1. Cost price / buy cost
This is the single biggest cause of "weird ROI." If you leave the cost field blank or let it default, SAS will compute ROI against $0 or against the live Amazon price, and you'll see absurd numbers (like 900% or a blank/negative ROI). **Always type in your real net buy cost** — and type the cost *after* discounts/cashback/gift-card stacking, because that is the number your ROI is actually earned against.

### 2. Inbound shipping (cost to ship to Amazon)
Set this to roughly **$0.30–$0.50 per lb** (use your real rate if you know it). If this is left at $0, your profit and ROI will read too high. This is a per-item-weight cost, so make sure SAS is pulling the product weight (check the weight field looks sane).

### 3. Prep & label cost — easy one to miss
Since **January 2026, Amazon no longer preps/labels US FBA for you** — you do it. So bake in a prep cost of about **$0.50–$1.00 per unit** in SAS. If your SAS prep cost is still $0, every deal will look ~$0.50–$1.00/unit more profitable than reality. This is a very common reason SAS ROI disagrees with your own hand math.

### 4. Minimum ROI threshold → set to **30%**
Set the ROI target/threshold that drives the color and the "Max Cost" calc to **30%**. This makes the green/amber/red verdict match your actual buy rule, so you're not eyeballing it.

### 5. Minimum profit → set to **$3.00 per unit**
Below ~$3/unit the fees and your time aren't worth it. Setting this makes SAS flag thin deals for you automatically.

### 6. VAT / tax settings (US seller)
If you're a US seller, make sure VAT is **off / set to 0%** in the SAS profile. A VAT setting left on (common if the account defaulted to a UK/EU profile) will quietly distort profit and ROI. This is another classic "weird numbers" culprit.

### 7. Sales-volume / BSR reference
Confirm your **storage/marketplace is set to the US (amazon.com)** and that SAS is reading BSR + estimated monthly sales. A wrong marketplace skews fees and the sales estimate.

## Quick reference — what to enter

| Field | Set it to |
|---|---|
| Cost price | Your **net** buy cost after cashback/discount/gift-card stacking |
| Inbound shipping | ~$0.30–$0.50 per lb |
| Prep cost | ~$0.50–$1.00 per unit (you prep US FBA yourself since Jan 2026) |
| Minimum ROI | 30% |
| Minimum profit | $3.00 / unit |
| VAT / tax | 0% (US seller) |
| Marketplace | amazon.com (US) |

## Why your ROI keeps looking weird — the checklist

Run down this list when a number looks off:

1. **Cost field blank or auto-filled** → ROI computed against $0 or the live price. Type your real cost.
2. **Prep cost still $0** → every deal reads ~$0.50–$1.00/unit too good.
3. **Inbound shipping at $0** → profit/ROI inflated.
4. **VAT still on** → profit silently reduced/distorted.
5. **You entered shelf price, not net cost** → ROI looks bad because you haven't applied your discount stack yet. Re-enter the post-stack cost. ("You make products profitable by lowering the buy cost.")
6. **Wrong marketplace / weight** → fees and FBA fulfillment cost wrong, so ROI wrong.

## Pro tip: use "Max Cost" as a reverse calculator
Once your ROI target is set to 30%, SAS shows a **Max Cost** — the most you can pay for the unit and still hit 30% ROI. Instead of guessing, source toward that number: if Max Cost is $9.40, any net buy price at or under that clears your rule. This is the fastest way to turn SAS from a checker into a buying tool.

---

*Sourced from this project's OA brain and field SOPs — criteria: minimum ROI 30%, minimum profit $3/unit, prep cost ~$0.50/unit, inbound shipping ~$0.30–$0.50/lb (learning-hub/data/ai-brain.json and learning-hub/playbooks/field-sops.md). SellerAmp tells you if a deal is profitable TODAY; pair it with Keepa for whether it's been profitable over time. Always confirm eligibility/gating before buying, and keep purchase approval with you — nothing here auto-buys.*
