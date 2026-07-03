# Mehmet's Amazon Learning Hub

**Owner:** Mehmet · **Started:** 2026-06-19 · **Status:** Complete beginner, learning fundamentals

This is the home base for everything I learn about selling on Amazon. It captures
every question, lesson, link, and screenshot from my chats so the knowledge
compounds over time — and so it can later feed an AI assistant or a personal
"control center" website.

---

## Why this exists

I'm starting from zero. The goal of this hub is three things, in order:

1. **Learn the fundamentals** of how selling on Amazon actually works.
2. **Track literally everything** — every chat, link, and screenshot — in a
   structured, durable archive (see [tracking/](tracking/)).
3. **Feed the automation.** Everything here is structured so it can power the
   product-scout AI and, eventually, a personal control-center website.

> **One asset I have:** a mentor — my dad's friend — who has been doing
> **online arbitrage since 2017**. He's someone I can ask real questions.
> That heavily shapes the recommended starting path (see fundamentals 02 & 05).

---

## How this folder is organized

```
Amazon FBA/
├── learning-hub/              ← THIS hub (beginner learning + full capture)
│   ├── README.md              ← you are here (start here every time)
│   ├── knowledge-index.json   ← machine-readable map of the hub (for AI / website)
│   ├── fundamentals/          ← the lessons, written for a beginner
│   │   ├── 01-how-amazon-selling-works.md
│   │   ├── 02-business-models-compared.md
│   │   ├── 03-fees-explained-simply.md
│   │   ├── 04-glossary.md
│   │   └── 05-beginner-roadmap.md
│   ├── playbooks/             ← step-by-step how-to (distilled from the videos)
│   │   ├── sourcing-playbook.md     ← how to find products (reverse sourcing, Keepa Finder)
│   │   ├── ungating-playbook.md     ← how to get approved to sell gated brands
│   │   ├── operations-playbook.md   ← account setup, supplies, shipping, returns
│   │   ├── brands-and-sources.md    ← brands, sourcing sites & tools named in the videos
│   │   └── field-sops.md            ← condensed criteria/red-flags/SOP checklist (2026-06-25)
│   ├── ai-system/            ← the spec for the AI we're building
│   │   ├── vision-and-requirements.md
│   │   ├── ai-architecture.md            ← agent roster + two-DB (knowledge/business) spec
│   │   ├── control-center-blueprint.md   ← the control-center design
│   │   ├── ingestion-pipeline.md         ← feed-in -> ai-brain.json -> scout+dashboard update
│   │   ├── deal-sourcing-system.md       ← deal-API sourcing design (not live yet)
│   │   ├── knowledge-rag-pipeline.md     ← RAG pipeline design
│   │   ├── reliability-intelligence-roadmap.md  ← staged reliability/Ask upgrade plan
│   │   ├── ai-upgrade-plan.md            ← priority-ordered lessons-to-build list
│   │   └── product-research-template.md  ← the buy/no-buy checklist
│   ├── tracking/              ← the living "track everything" layer
│   │   ├── session-archive.md      ← chronological capture of every chat
│   │   ├── links-and-assets.md     ← index of every link / screenshot / file
│   │   ├── questions-for-mentor.md ← what to ask my dad's friend
│   │   ├── product-leads.md        ← product ideas + scout output
│   │   ├── finances.md             ← purchase ledger + P&L
│   │   ├── inventory.md            ← units owned / at FBA / restock
│   │   ├── decisions-and-milestones.md
│   │   └── tools-and-resources.md
│   ├── transcripts/           ← video transcripts + distilled insights.md
│   └── assets/                ← saved screenshots & files (see assets/README.md)
│
├── 01_research_brief.md       ← deep, sourced operator brief (advanced; private-label focus)
├── 04_limitations.md          ← honest "what this does NOT do" notes — read it
├── scout/                     ← minimal product-discovery AI (Keepa + scoring + learning loop)
├── scout_pro/                 ← full-stack version of the scout (gates, ML, review queue)
├── tracker/  &  fba-tracker-site/  ← learning-progress tracker web pages
```

**The hub vs. the existing files:** the brief and the scout system are powerful
but pitched at someone already running. This hub is the on-ramp — beginner-level
lessons plus the capture system — and it points into the brief/scout when I'm
ready for depth.

---

## The capture rule (how "track everything" works)

Every session, Claude:

1. **Logs the conversation** to [`tracking/session-archive.md`](tracking/session-archive.md)
   — what I asked, what was decided, action items.
2. **Saves every link, screenshot, and file** I share into
   [`assets/`](assets/) and indexes it in
   [`tracking/links-and-assets.md`](tracking/links-and-assets.md).
3. **Files new lessons** into `fundamentals/` and updates `knowledge-index.json`.
4. **Records decisions** in [`tracking/decisions-and-milestones.md`](tracking/decisions-and-milestones.md).

When I paste a screenshot or link, I don't have to say "save this" — that's the
default. Nothing gets lost.

---

## The future vision (control center)

The `tracking/` files use consistent structure and `knowledge-index.json` is a
machine-readable manifest. That means this hub can later become:

- **An AI assistant** that already knows my full history, my decisions, and my
  product leads (it reads these files as context).
- **A control-center website** — combining the existing `tracker/` page, the
  `scout` product alerts, and this archive into one dashboard.

We build that when the fundamentals are solid. For now: learn, capture, repeat.

---

## Quick start for me (Mehmet)

- New to this? Read fundamentals **01 → 04 (glossary) → 02 → 03 → 05** in that order.
- Ready to find products? Read [`playbooks/sourcing-playbook.md`](playbooks/sourcing-playbook.md) and [`playbooks/ungating-playbook.md`](playbooks/ungating-playbook.md).
- Have a question? Just ask in chat — it gets logged automatically.
- Got a screenshot / link / video transcript? Paste or drop it — it gets saved, indexed, and distilled automatically.
- Talking to my mentor soon? Open [`tracking/questions-for-mentor.md`](tracking/questions-for-mentor.md).
