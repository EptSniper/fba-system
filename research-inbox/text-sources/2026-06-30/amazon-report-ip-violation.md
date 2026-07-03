# How to Report an IP Violation to Amazon (Brand Registry / Report a Violation)

- **Source URL:** https://sell.amazon.com/blog/report-a-violation-to-amazon
- **Referenced policy:** Amazon IP Policy for Sellers — https://sellercentral.amazon.com/help/hub/reference/external/G201361070
- **Published:** 2025-03-26 (Amazon Selling Partner Blog)
- **Fetched:** 2026-06-30
- **Classification:** [policy] — official Amazon description of IP enforcement tooling
- **Topic:** amazon_help_docs

## Distilled takeaways

1. **[policy]** Amazon enforces three IP categories only: **copyright** (original works), **trademark**
   (brand words/symbols/designs, incl. counterfeits), and **patent** (inventions). An OA reseller's account
   risk on a listing almost always traces to one of these three — useful framing for the compliance gate.
   (sell.amazon.com/blog/report-a-violation-to-amazon)
2. **[policy]** Rights owners report via two paths: the public **Public Notice Form**
   (amazon.com/report/infringement, open to any rights owner/agent) and the Brand-Registry-only **Report a
   Violation** tool (requires Rights Owner / Registered Agent role; needs a *fully registered* trademark —
   pending trademarks can't use it). This is the machinery behind the IP complaints that suspend reseller
   listings.
3. **[policy]** Amazon states **99% of suspected infringements in 2024 were blocked proactively** before
   brands acted (2024 Brand Protection Report). Implication for OA: gated/brand-protected listings are
   increasingly auto-enforced, so brand-risk screening before buying is not optional.
4. **[policy]** Patent disputes can route through **Amazon Patent Evaluation Express (APEX)** — a neutral
   third-party evaluation that is faster/cheaper than court. Relevant when a listing carries a utility-patent
   risk flag.
5. **Action for this project:** the `fba-compliance-checker` brand-risk logic should treat any
   Brand-Registry-enrolled brand as elevated IP-complaint risk; reinforces the guardrail of separating
   "Am I allowed?" from "Can it profit?".
