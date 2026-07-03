# amazon-fba-oa — the FBA online-arbitrage expert team

A bundled plugin of **24 `fba-` skills and roles** for the Amazon FBA online-arbitrage operation.
They encode this project's real rules so every Claude session follows them automatically: the
single-source gates in `learning-hub/data/ai-brain.json`, the **allowed-vs-profitable** split, honest
status words, no secrets, and **human-approved purchasing** (nothing here auto-buys or moves money).

## The team

**Sourcing & analysis (9)**

| Skill | What it does |
|---|---|
| `fba-deal-analyst` | The buy/no-buy gatekeeper. Runs the gates, splits allowed vs profitable, returns BUY/NO-BUY/REVIEW — never an auto-approval. |
| `fba-sourcing-scout` | Deal-first sourcing plans + lead lists (storefront stalking, Keepa Product Finder). |
| `fba-compliance-checker` | "Am I allowed?" — ungating, IP/brand risk, hazmat, meltable, eligibility. |
| `fba-keepa-analyst` | 20-yr-veteran read of Keepa history: BSR→sales, price/offer trends, Buy Box rotation, red flags. |
| `fba-selleramp-analyst` | SellerAmp SAS setup + panel reading + Max-Cost reverse calc. |
| `fba-chart-reader` | Decodes Keepa/SellerAmp **screenshots/images** into a structured read. |
| `fba-market-analyst` | Trends, demand, seasonality, category economics, budget/portfolio strategy. |
| `fba-deal-calculator` | Deterministic ROI/fee math via a bundled script (`scripts/fba_calc.py`). |
| `fba-listing-optimizer` | Listing & SEO copy (titles, bullets, A+, keywords) when you control the listing. |

**Project rituals (4)**

| Skill | What it does |
|---|---|
| `fba-session-journal` | Writes the mandatory `AI_COLLABORATION_JOURNAL.md` entry in the required format. |
| `fba-brain-updater` | Safely edits `ai-brain.json` (validates JSON, preserves provenance, bumps date). |
| `fba-transcript-ingest` | Turns a transcript/doc into insights + a RAG corpus entry. |
| `fba-lead-capture` | Validated lead rows into `product-leads.md` / `leads.json`. |

**Engineering crew (11)**

`fba-architect` · `fba-coder` · `fba-code-reviewer` · `fba-debugger` · `fba-database-expert` ·
`fba-designer` · `fba-context-keeper` · `fba-feedback-giver` · `fba-innovator` · `fba-qa-tester` · `fba-data-analyst`

## Shared source of truth

All skills read from `references/`:

- `oa-criteria.md` — the gates, guards, cost assumptions, brand hints (mirrors `ai-brain.json`).
- `guardrails.md` — allowed-vs-profitable, human approval, honesty, no secrets, source-of-truth order.
- `sourcing-methods.md` — distilled sourcing playbook.
- `stack-map.md` — codebase orientation + non-negotiables for the engineering crew.

If a reference and `ai-brain.json` ever disagree, **`ai-brain.json` wins** — the skills say so.

## Install

See [`INSTALL.md`](INSTALL.md). In short: add this folder as a local plugin/marketplace under
Claude **Settings → Capabilities**, and the 24 skills appear in your skill list.

## Versioning

This plugin describes how to think; it does not contain business data. When the criteria change, edit
`ai-brain.json` (via `fba-brain-updater`) — the skills read it, so they stay in sync without edits here.
