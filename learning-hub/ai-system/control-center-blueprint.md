# Control Center Blueprint — "Jarvis, but real"

*How to build a command-center dashboard for the Amazon OA business that looks
like Jarvis but is genuinely functional — not AI slop. Design grounded in the
installed **ui-ux-pro-max** skill (which prescribes **Dark Mode OLED + Data-Dense,
high contrast, real-time, accuracy paramount** for a financial dashboard) and the
**21st.dev** component library for motion. Written 2026-06-20.*

---

## 0. The one idea

> A control center is a **control surface over real systems** — not a picture of one.

That single distinction is the whole game. "AI slop" is a beautiful dashboard with
invented numbers and buttons that do nothing. A real one passes two tests on every
pixel: **(1)** every number traces to a real source you can name, and **(2)** every
control changes real state and shows you the result. If a thing on screen fails both,
delete it.

---

## 1. The anti-slop laws (the actual answer to "how is it not slop")

1. **Real data or honest emptiness.** Never render a fake number to look impressive.
   If data isn't there yet, show a real **empty / loading (skeleton) / error** state.
   Empty states are first-class design, not an afterthought.
2. **One source of truth.** One database. Every screen reads the *same* numbers, so
   the P&L on the overview equals the P&L on the money page. Contradictory numbers =
   instant loss of trust = slop.
3. **Every control does something real.** No dead buttons, no decorative toggles.
   Each action writes to the store and reflects the new state immediately.
4. **Show the seams (honesty builds trust).** Timestamp everything ("updated 2m ago"),
   label the **source**, and mark **estimate vs. actual** (the scout's "confirm in
   SellerAmp" ethos, on screen). A dashboard that admits uncertainty is trusted; one
   that hides it is slop.
5. **Latency budget.** Interactions < 100ms, skeletons for anything > ~1s, optimistic
   updates. Fast *is* the feeling of "real." (ui-ux-pro-max: Performance is CRITICAL.)
6. **One primary action per view.** Clear hierarchy; progressive disclosure. A wall of
   equally-weighted widgets is confusing — the opposite of a command center.
7. **Stateful URLs.** Every view, filter, and selection is a URL — deep-linkable, the
   back button works, you can share a link to "the scout pick for ASIN X." (ux rule:
   URLs reflect state.)
8. **Accessibility is non-negotiable** — 4.5:1 contrast, visible focus rings, full
   keyboard nav, `prefers-reduced-motion`. Doubly important because it's dark + animated.
9. **Motion conveys meaning, sparingly.** 1–2 animated elements per view, 150–300ms
   (ui-ux-pro-max + 21st.dev). A number counting up when it changes = meaning. Glow on
   everything = slop.
10. **Tested + reviewed.** Unit tests on the math, Playwright e2e on every control,
    **CodeRabbit on every PR**. Slop ships unreviewed; this won't.

If you do nothing else, obey #1, #2, #3. They are 80% of the difference.

---

## 2. What it must actually do (modules, mapped to the hub you already have)

Everything below maps to files/systems we've already built — so the dashboard is a
*view + control layer* over real things, not a new fantasy.

| Module | What it shows / does | Backed by |
|---|---|---|
| **Command Deck** (home) | Top KPIs: net profit MTD, cash-in-inventory, blended ROI, units at FBA, pending payout, scout alerts, **account health** | finances + inventory + scout |
| **Find** (scout feed) | Live inbox of candidate products with the **buy/no-buy verdict + reasons**; **Approve / Reject / Watch** → writes a label that trains the scout | `scout/` (Keepa + scoring + Discord) |
| **Leads pipeline** | Kanban: idea → researching → BUY → ordered → sold (drag to advance) | `tracking/product-leads.md` |
| **Money** | P&L (period-over-period), purchase ledger, payouts, reconcile | `tracking/finances.md` → SP-API later |
| **Inventory** | Units owned / in-transit / at FBA, sell-through, **restock alerts** | `tracking/inventory.md` → SP-API later |
| **Knowledge** | Searchable playbooks + transcript insights (the "brain" the AI reads) | `playbooks/`, `transcripts/insights.md`, `knowledge-index.json` |
| **Activity** | Append-only log of *everything* — every pick, buy, sale, decision, chat | `tracking/session-archive.md` + events |
| **Command palette (⌘K)** | Jump to anything, run any action by typing | all of the above |

This is the literal answer to "control and view everything **and** track everything at
the same time": **view** = the modules, **control** = the actions inside them, **track**
= the Activity log + every action being an event written to the store.

---

## 3. Information architecture & layout

- **Left rail** — ≤7 nav items (Command Deck, Find, Leads, Money, Inventory, Knowledge,
  Activity). A short, predictable nav beats a crowded one.
- **Top KPI strip** — 5–6 numbers, always visible, the "vitals."
- **Main canvas** — the active module; one primary action, supporting detail via
  progressive disclosure (drawers/sheets, not new mazes).
- **Right rail (optional)** — live activity ticker + scout alerts (the "Jarvis is
  watching" feel, but every line is a real event).
- **⌘K command palette** — the power-user spine; everything reachable by typing.

Layout style: a **bento grid** of panels on the Command Deck (data-dense but
breathable), full-width tables/charts inside modules.

---

## 4. The "Jarvis" look — done tastefully (this is where slop usually wins)

The skill's recommendation for our product type (Financial Dashboard) is exactly the
right restraint: **Dark Mode (OLED) + Data-Dense + Minimalism**, "high contrast,
real-time, accuracy paramount." Translate that to tokens:

- **Color (semantic tokens, never raw hex in components):**
  - `--bg` deep near-black (OLED, e.g. `#0A0E14`), `--panel` one step up (`#121821`).
  - `--accent` a single "arc-reactor" cyan/teal (`#22D3EE`-ish) — used *only* for the
    primary action and live indicators, so it means something.
  - `--profit` green, `--loss` red, `--warn` amber — semantic, used consistently.
  - `--trust` blue for links/info. High contrast throughout (4.5:1+).
- **Typography:** a clean grotesk for UI (Geist / Inter), **monospace for all numbers/
  data** (JetBrains Mono / Geist Mono) with `font-variant-numeric: tabular-nums` — the
  single biggest cue that reads as "command center" and keeps columns aligned. Base 16px,
  line-height 1.5.
- **Motion (from 21st.dev, sparingly):** number **count-ups** when a KPI changes, a
  one-line **activity ticker**, a soft **pulse on the "scout active" dot**, panel
  reveal on load. All 150–300ms, all gated by `prefers-reduced-motion`.
- **Glass/glow:** one thin glass layer on the top strip *maybe*; no glow on everything.
  Restraint is what separates "premium command center" from "gamer RGB slop."
- **Icons:** SVG only (Lucide), never emoji-as-icons.
- **The slop tells to avoid:** fake "AI thinking…" theater, gratuitous scanlines,
  numbers that animate constantly for no reason, 8 equally-loud widgets, contradictory
  figures, charts with no axis/legend, a "live" feed that's actually static.

> Components: **shadcn/ui** primitives + **21st.dev** animated components (your standing
> directive) + **Recharts/visx** for charts. ui-ux-pro-max governs the *rules*; 21st.dev
> supplies the *motion*; shadcn supplies accessible *primitives*.

---

## 5. Architecture & data flow (why it stays consistent)

```
   PRODUCERS  ───────────────►  SINGLE SOURCE OF TRUTH  ◄────────  CONSUMER
   • scout (Python: Keepa            ┌──────────────┐           • Dashboard
     + scoring + labels) ──────────► │   Database   │ ◄──────►    (Next.js/React)
   • SP-API sync (finances,          │ (Postgres /  │   API +     reads via typed API,
     inventory, orders, payouts) ──► │  Supabase)   │   Realtime  live via Realtime/SSE
   • manual entries (leads, buys) ─► └──────────────┘
   • knowledge base (md → indexed)        ▲
                                          │ every action writes an EVENT (audit log)
```

- **Single store** = the law of "one source of truth" made physical. Scout, finances,
  inventory, leads, and the activity log all live in one DB.
- **Server-only secrets.** SP-API and Keepa keys live on the server/sync job — **never**
  in the browser. The dashboard talks to *your* API, not Amazon directly.
- **Events table.** Every meaningful action (pick surfaced, approved, bought, sold,
  reconciled) is appended as an event → that's the Activity feed and the "track
  everything" guarantee, for free.
- **Real-time** = Supabase Realtime or SSE pushing new scout picks / payouts to the UI.
  That's the genuine "live Jarvis" feel — real events, not a fake animation loop.

---

## 6. Tech stack (specific, with an honest MVP)

**Recommended full stack:** Next.js 14 (App Router) + TypeScript + Tailwind +
shadcn/ui + 21st.dev components + Recharts + **Supabase** (Postgres + Auth + Realtime)
+ the existing **Python scout** writing to Supabase + a small **SP-API sync** worker.
Deploy private on **Vercel**. Auth locked to just you.

**Honest MVP (start here — days, not weeks):** one Next.js app, **read-only**, reading
real data you already have — `knowledge-index.json`, a JSON export from the scout's
SQLite DB, and `finances.md`/`inventory.md` parsed to JSON. It does nothing but *show*
real numbers beautifully. That's not slop — it's the truest version, just without
write-back yet. (You could even start by upgrading the existing `tracker/` page.)

---

## 7. Build plan (each phase ships and is useful on its own)

- **Phase 0 — Data model (½ day).** Define the schema = the single source of truth:
  `candidates`, `picks`, `labels`, `leads`, `inventory`, `transactions`, `events`.
- **Phase 1 — "View everything," read-only, real data.** Command Deck + Money +
  Inventory + Find feed + Leads, all rendering real numbers with honest empty states.
  *This alone is ~80% of the value and structurally cannot be slop if the data is real.*
- **Phase 2 — Controls (write-back).** Approve/Reject scout picks (→ labels that train
  the scout), add/advance leads, mark ordered/sold, set restock flags. Each writes an
  event.
- **Phase 3 — Live + polish.** Realtime push, the Jarvis aesthetic, 21st.dev motion,
  ⌘K palette, activity ticker.
- **Phase 4 — SP-API.** Replace manual finances/inventory with live Amazon data
  (payouts, fees, stock, reimbursements).
- **Every phase:** unit tests on the money math, Playwright e2e on each control, and a
  **CodeRabbit-reviewed PR** before merge.

---

## 8. Keeping it non-slop as it grows
- **Performance budget** in CI (Lighthouse ≥ 90; CLS < 0.1).
- **A test per control** — if a button has no e2e test, it's not done.
- **CodeRabbit on every PR** (your standing directive) — catches the sloppy stuff.
- **Design review vs. the ui-ux-pro-max checklist** before each module ships.
- **The "real data" gate:** no widget merges without a real data source behind it.

---

## 9. How someone else would build it (briefing a developer)
Hand them: this blueprint + the `learning-hub/` + the `scout/` code. Tell them the
stack (Next.js/TS/Tailwind/shadcn/Supabase) and the **five non-negotiables**: real data
only, one source of truth, every control writes back + emits an event, accessibility to
WCAG AA, and tests + CodeRabbit on every PR. A competent full-stack dev can ship Phase 1
in a few days and the full thing in a few weeks. Cost control: start read-only, add
write-back only where it earns its keep.

---

## 10. Honest constraints (so we don't build fantasy)
- **SP-API** needs a developer registration + approval; **Keepa** needs a paid key for
  the live scout. Until those exist, the dashboard shows **manual entries**, clearly
  labeled — not invented numbers.
- Some data (real payouts, ungating eligibility, reimbursements) **won't exist until the
  seller account is live.** Don't build Phase 4 before the account does. Showing "—" with
  "not connected yet" is honest; showing a fake $4,212 is slop.
- Build order honors reality: **view first, control second, live third, Amazon-integrated
  last.**

> Next step when you're ready: I can scaffold **Phase 1** (read-only Command Deck on your
> real hub data) as a Next.js + shadcn + 21st.dev app, behind a CodeRabbit-reviewed PR.
