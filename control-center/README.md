# OA Control Center — operator dashboard

A command-center dashboard for the Amazon online-arbitrage business. It shows real hub
data, provides a local deal calculator and live cited knowledge search, and opens
the correct Seller Central operating surfaces. It does not invent account data or
claim that disconnected services are live.

## Run it

```bash
cd "Amazon FBA/control-center"
npm install
npm run dev        # → http://localhost:3000
```

Requires Node 18+.

## Main workspaces

- **Today:** next action, business KPIs, ingestion state, picks, and profit status.
- **Find:** interactive OA calculator with scored criteria, the real hard-reject conditions
  (Amazon Buy Box, brand/IP risk), and explicit limitations.
- **Amazon Ops:** Account Health, inventory, payments, inbound, listing, and fee tools,
  plus the planned SP-API connection sequence.
- **Ask:** live, read-only Supabase semantic search over the knowledge corpus (chunk count
  grows with every research-pipeline run — see the live badge on the page, not a number pinned
  here), with a concise zero-cost cited answer, source-tier reranking, runtime health, retry,
  expandable evidence, deterministic fallback, and a 15-minute repeat-query cache.
- **Scout Intelligence:** readiness, evidence flywheel, model-promotion rules, drift
  controls, and the explicit no-total-accuracy guardrail.

## What it reads (single source of truth)

It reads the **real hub data** from the sibling `../learning-hub/` folder, server-side:

| Module | Source file |
|---|---|
| Command deck / Money | `learning-hub/data/finances.json` |
| Inventory | `learning-hub/data/inventory.json` |
| Leads | `learning-hub/data/leads.json` |
| Find (scout picks) | `learning-hub/data/picks.json` |
| **Brain** (criteria, brands, ingestion log) | `learning-hub/data/ai-brain.json` |
| Knowledge counts | `learning-hub/knowledge-index.json` |

**`ai-brain.json` is the single source of truth** — the **scout** (`scout/brands.py`)
and this dashboard both read it. Feed Claude new info → it updates `ai-brain.json` →
the finder/rater and the dashboard both update. (See
`../learning-hub/ai-system/ingestion-pipeline.md`.)

## Why everything shows zeros / "not connected"

Because that's the truth right now — no account, no sales, no Keepa key yet. The
dashboard shows **honest empty states** instead of inventing numbers. As real data
appears (manual entries now, SP-API + the scout later), the same views fill in.

## Design

Dark-OLED, data-dense, high-contrast — the `ui-ux-pro-max` skill's prescription for a
financial dashboard. Tokens live in `app/globals.css`. Animations are intentionally
minimal in Phase 1 (a live pulse, subtle panel entrance); richer motion comes from
**21st.dev** components when there's real data worth animating.

## Architecture

- **Next.js 15 (App Router) + TypeScript + Tailwind**, shadcn-style components (hand-written in `components/`).
- Server Components read the hub files via `lib/data.ts` — nothing is bundled, no secrets in the browser.
- The Ask API runs `../knowledge-rag/ask.py` server-side with `execFile` (never a shell),
  validates input, and returns reranked retrieval evidence plus maintained OA guidance.
  It does not use a paid language model. The service-role key is neither needed nor
  exposed to browser JavaScript.
- Deals, Leads, Money, Inventory, Sources, Brain, and Scout Intelligence now expose
  explicit working actions instead of presenting display-only panels as operational.
- Charts: Recharts. Icons: lucide-react.

## What's next

- Build validated local forms for manual leads, decisions, inventory, and realized
  outcomes; these labels are the prerequisite for genuine model improvement.
- Add the Supabase service-role key to the scout's private `.env` so real runs log all
  evaluated leads. Never put this key in browser code.
- Connect SP-API Listings Restrictions first, followed by inventory, finances, inbound,
  catalog, and notifications.
- Add human approve/reject/watch controls and realized-outcome entry so the model can
  be trained and evaluated against actual results.

## CodeRabbit

The current app passes TypeScript checking and a production build. `npm audit` reports
zero known vulnerabilities as of 2026-06-27.
