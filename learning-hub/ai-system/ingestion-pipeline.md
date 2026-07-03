# Ingestion Pipeline — "feed it, everything updates"

*How new information Mehmet sends flows into the whole system. The rule: there is
**one source of truth** (`learning-hub/data/ai-brain.json`) that both the item
finder/rater (`scout/`) and the control center read — so a single update reaches
both. Created 2026-06-20.*

---

## The loop

```
  YOU FEED ME            I DISTILL                  ONE SOURCE              EVERYTHING UPDATES
  ───────────            ─────────                  ──────────              ──────────────────
  • Amazon help doc  ─►  read it fully         ─►   ai-brain.json     ─┬─►  scout/  (finder/rater)
  • YouTube transcript   pull the useful,            (criteria,        │     reads criteria + brand
  • a screenshot         non-obvious points          brand lists,      │     lists from the brain
  • an item / ASIN       update playbooks +          knowledge,        │
  • a new rule           insights.md +               ingestion log)    └─►  control-center/ (dashboard)
                         knowledge-index.json                                reads the same brain +
                                                                             hub data; Brain page shows it
```

Every feed also gets **logged** (`ai-brain.json → ingestionLog`, `tracking/session-archive.md`,
`tracking/links-and-assets.md`) — so the system visibly grows, and the dashboard's
**Brain → "Ingestion log"** panel shows exactly what's been fed and what each thing changed.

---

## What happens, by input type

| You send… | I do… | Updates |
|---|---|---|
| **YouTube transcript** | read in full → distil into `transcripts/insights.md` + the relevant playbook; bump `knowledge.transcripts`; add to `ingestionLog` | dashboard Brain + Knowledge counts; scout if it implies a criteria/brand change |
| **Amazon help doc** | extract the rule → `operations-playbook.md` / fundamentals; log it | dashboard Knowledge; scout if it's a gating/fee/eligibility rule |
| **A new brand or item** | vet it → add to `ai-brain.json` `brands.friendly` / `avoid` (or a lead) | **scout's search + scoring immediately use it**; dashboard Brain shows it |
| **A new criterion / threshold** | update `ai-brain.json` `criteria` (and `scout/config.py` if needed) | scout's rater + dashboard Find page both reflect it |
| **A screenshot** | transcribe → `assets/` + `links-and-assets.md`; pull any numbers/tools | dashboard + relevant docs |

---

## Why this isn't slop
- **One write, not five.** Brands/criteria live in `ai-brain.json` only. The scout
  (`brands.py` `_load_from_brain()`) and the dashboard (`lib/data.ts`) both read it. No
  drift, no contradictory numbers.
- **Visible provenance.** The `ingestionLog` records *what changed because of each feed*,
  shown in the dashboard — so you can always see why the AI believes what it believes.
- **Honest until real.** Finances/inventory/picks stay at their true (often empty) values
  until the account + Keepa key exist; the dashboard shows honest empty states, never
  invented numbers.

---

## How to keep it flowing
1. Mehmet sends something.
2. Claude distils it into the hub **and** updates `ai-brain.json` (+ `ingestionLog`).
3. The scout picks up new brands/criteria on its next run; the dashboard reflects it on
   next load (it reads the files live).
4. It's logged in `session-archive.md`. Nothing is lost.

> This is the standing process — see [[feedback-capture-everything]] in memory. The more
> that's fed in, the sharper the finder/rater and the richer the control center get.
