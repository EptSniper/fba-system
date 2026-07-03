# Operations Playbook (account → supplies → ship → returns)

*The operational workflow around sourcing — account setup, supplies, prepping,
sending FBA/FBM shipments, and what to do when things don't sell. Distilled from
the 12-hour FBA course (account setup) and the "$0–$10K/Month" OA guide
(supplies/prep/shipping). Not legal or tax advice — verify your own situation.*

---

## 1. Set up the seller account (do this once, carefully)
Account mistakes get people **banned**, so go slow and get details right.

- **Plan:** **Individual** is free ($0.99/item, hidden — scroll to the bottom of the signup page) vs **Professional** ($39.99/mo). Go **Professional if selling >40 units/mo** (and for the Buy Box). You can start Individual and upgrade. Amazon charges month 1 but **won't charge again until you actually sell** (seller support refunds charges during a gap).
- **Use a business email**, not Gmail/Yahoo (a personal email can be a "not serious" red flag).
- **Use a CREDIT card, never a debit card** → signing up with a debit card gets accounts **suspended**.
- **One account only.** A second account (or a household member's old account) is a ban risk; if you genuinely need a second, tell Amazon first.
- **Entity:** "None / individual seller" uses your SSN; or an **LLC** (legal protection — home state, e.g. CA $800/yr; Wyoming/Delaware for non-residents) with an **EIN** (free, fast, from the IRS — a "SSN for your business"). A **DBA** gets you a business bank account/card but no legal protection. *(Not required for OA; an LLC is optional.)*
- **Bank:** a business bank account whose name matches the business (US Bank free in the US; Payoneer / WorldFirst for non-US). Non-US residents **can** sell in the US.
- **ID:** passport (preferred) or driver's license front/back. Expect a **live video verification call** (show your passport; face match).
- **Don't change bank/address details in the first month or two** — it looks like a scam and can trigger suspension. Be **polite, professional, typo-free** in every Amazon message (treat it like a job application).

## 2. Supplies (lean to start)
- **Thermal label printer** (Rollo is durable; cheaper Munbyn/Nelko work). Prints **2×1 labels** (= FNSKU, FBA only) and **4×6 labels** (= shipping labels, FBM + FBA box labels).
- **FNSKU labels** (2×1, ~$10/1,000) · **4×6 shipping labels** (~$22/500).
- **Boxes:** FBA boxes from **Walmart** (~$1–1.25 small/med/large); FBM boxes in bulk from **Uline**; **free Priority Mail boxes** from USPS/UPS.
- **Poly bags** (for multipacks; must show the suffocation warning), **poly mailers**, **bubble wrap** (fragile), **packing tape + tape gun**, box cutter, Sharpie, **scale + measuring tape**.
- **"Do not separate" stickers** — put on multipacks so the warehouse worker doesn't split your bundle.

## 3. Prep & send an FBA shipment

> **2026 rule (Amazon SP-API Fulfillment Inbound doc):** As of **Jan 1, 2026, Amazon no longer
> preps or labels FBA items in the US** — *you* must prep and label everything before it ships in.
> Budget the per-unit prep cost (poly bag + FNSKU label + your labor) into **every** buy — the scout
> now subtracts it (`OA_PREP_COST`, default $0.50/unit) so its ROI isn't optimistic. A prep center
> can do it for you (~$0.50–1.00/unit) if you'd rather not.

1. Source the deal (see [sourcing-playbook.md](sourcing-playbook.md)).
2. **Prep:** bundles → into a poly bag (sealed, warning shown) + a "do not separate" sticker; fragile → bubble wrap. Apply the **FNSKU (2×1)** label to each unit.
3. **Create the shipment** in Seller Central (or **Boxem**, which streamlines listing + shipping): enter quantities; Amazon assigns the fulfillment center(s).
4. Print the **box labels (4×6)**, box it up, and ship via the **partnered carrier** (discounted UPS) to keep inbound cost low (~$0.50–0.70/lb).
5. **Q4 timing:** get FBA shipments in by **~Nov 15** so they're checked-in for the holiday rush. Check-in is usually days, but **1–3 weeks in Q4**.

## 4. Pack an FBM order
Order shows in Seller Central → print the **4×6 shipping label** (UPS/USPS/FedEx — pick the cheapest) → box or poly-mail the item (bubble wrap if fragile) → attach label → drop off. FBM = you're responsible for safe delivery.

## 5. When a product doesn't sell
Lots of exits, so downside is small: **lower the price** (win the Buy Box at a thinner margin), run a sale, **remove/return inventory** from FBA (then sell on **Facebook Marketplace** or back to the retailer within its return window), switch to **FBM**, or use **Amazon's liquidation program**. Buy at Keepa lows so worst case is break-even.

## 6. Returns, reimbursements & taxes
- **FBA returns** are handled by Amazon. Periodically check for **reimbursements** Amazon owes you (lost/damaged inventory) — a real money source to track. *(The courses cover the reimbursement process; flag for a future deep-dive.)*
- **Sales tax:** Amazon **collects and remits** it in most states — you usually do nothing.
- **Tax-exempt / reseller certificate** (same thing, named differently per state): retailers like **Home Depot, Lowe's, Walmart** accept it for **B2B, no-sales-tax** purchases — saves money on your buys. Keep **all invoices/receipts** for proof.

> Account health is everything in OA: avoid IP-complaint brands (see [ungating-playbook.md](ungating-playbook.md) + the Keepa "cliff" check), keep stock available, and stay professional with Amazon. A healthy account unlocks more auto-ungates over time.
