---
title: Lithium batteries & dangerous-goods documentation requirements (FBA)
source_type: amazon_policy
source_url: https://sellercentral.amazon.com/help/hub/reference/external/G200383420
category: Policy
collected: 2026-06-23
note: Manually exported from Seller Central (login-gated). Verify against the live page before acting.
---

# Lithium batteries & hazmat documentation (FBA)

Anything that **is** a battery or **contains/ships with** one (electronics, toys, tools, power banks,
watches, keychain lights) triggers extra FBA requirements. Incomplete/inaccurate/conflicting info →
**product blocked for sale through FBA**. This is a major "am I allowed + extra friction" factor for
sourcing electronics.

## US approval thresholds (lithium energy content)
Higher-energy lithium is **rejected** even in the US. Approved/Rejected for the **US**:

**Lithium-ion (incl. Li-polymer) — CELLS:** ≤20 Wh ✅ · >20–60 Wh ✅ · **>60 Wh ❌**
**Lithium-ion — BATTERIES:** ≤100 Wh ✅ · >100–300 Wh ✅ · **>300 Wh ❌**
**Lithium-metal — CELLS:** ≤1 g ✅ · >1–5 g ✅ · **>5 g ❌**
**Lithium-metal — BATTERIES:** ≤2 g ✅ · >2–25 g ✅ · **>25 g ❌**

(Many other countries reject the middle tier — the US is the most permissive. Wh = nominal V × Ah;
it's printed on the battery/packaging.) Power banks and external chargers count as **batteries**.

## What you must provide at listing (or converting to FBA)
- **Battery info**: required? included? button/coin cell? composition; quantity; weight; Wh; packaging
  (packed-with / contained-in-equipment / standalone); state-of-charge **<30%** (else **no air shipping**).
- **UN 38.3 test summary** — required for all lithium batteries/products at ASIN setup (UN 38.3 safety tests).
- **Safety Data Sheet (SDS)** or **exemption sheet** (uploaded via *Manage dangerous goods classification*).
  - SDS must be: created/updated within **5 years**, GHS/CLP hazard info, **match the listing**
    (product + brand name), and include all **16 sections**. Bundles/kits need an SDS per chemical product.
  - **Exemption sheet** only valid for (a) battery & battery-powered products, or (b) products without
    harmful chemicals — submitted as an **Excel** file.

## Timing & risk
- Classification review = **2 business days**; rejected/incomplete adds 2 more days per resubmission.
- If a product already at an FC is flagged as possible hazmat, you have **14 business days** to provide
  docs — **or the inventory is disposed at your expense**.
- Hazmat (any class) **≥ 50 lb per package** is prohibited from FBA.

**Sourcing takeaway:** electronics/battery deals can be great, but factor in the documentation work
(UN 38.3 + SDS/exemption), the risk of being **blocked** if you can't get manufacturer docs, and the
hard **US energy ceilings** (>60 Wh cell / >300 Wh battery = not allowed). The scout flags battery/
hazmat-keyword items so you check this **before** buying.
