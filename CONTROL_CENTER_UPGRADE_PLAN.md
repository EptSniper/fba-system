# Control-Center Upgrade Plan — from reporting surface to operating cockpit

**Date:** 2026-07-03 · **Author:** Claude (Cowork), applying fba-innovator + fba-designer + fba-architect standards to the Part-2 review findings · **Executor:** Claude Code (Prompts CC1–CC4); Cowork already handled the scheduling piece.
**Prerequisites:** R3 (Part-2 fixes) should land first; CC1 needs migrations applied; CC4's chart piece waits on M2's eval.

> **ML doctrine applies.** Any work here touching data collection, features, training, serving,
> evaluation, guardrails, or the item finder routes through the `fba-ml` crew (`fba-ml-lead` plans;
> see `SKILLS_INDEX.md`'s ML crew section) and must obey `amazon-fba-oa/references/ml-doctrine.md`:
> breadth/no-bias, no leakage (point-in-time features only), hard gates outside ML, shadow-by-default
> with human-only promotion, honest metrics. Never hand-roll ML work without the crew.

---

## 1. The idea that matters most

Every audit said the same thing from a different angle: the dashboard **reports** while the real operation happens elsewhere — review lives in Discord, leads live in Supabase where the UI can't see them, safety lives in your head, and the analyst's opinions go somewhere the operator never looks. A veteran's cockpit is where they *decide*, not where they read about it later.

So the plan is one transformation in four installments: **make the control center the place where every human decision in the loop actually happens** — with live data, one working queue, visible safety rails, and the expert layer's reasoning on every card. Each installment is independently shippable and honest about what's connected.

What this buys, per the innovator's levers: better learning signal (every decision becomes a clean label at the moment of decision), less risk (capital/aging rails visible before you buy, not after), less manual time (one queue, keyboard-first, triage-ordered), and more expert (the analyst's precedent-grounded reasoning finally reaches the human it advises).

## 2. Ranked improvements

**Quick wins (low effort, high value):**

- **Runs health panel** — last run, tokens used/left, leads written, analyst disagreements, heartbeat status. The observability the system already records but nobody can see. (CC1)
- **Brain-proposals page** — pending G5 proposals rendered with evidence + a copy-button "apply proposal N" command for Claude Code. Closes the self-improvement loop's last manual gap. (CC2)
- **Aged-inventory countdown** — day-181 surcharge clock per inventory item; red at day 120. One computed column that prevents real money loss. (CC2)
- **Weekly command review** — DONE (Cowork scheduled task, Mondays 9:09am → Discord #daily-digest + weekly-reviews.md).

**The bigger bets (the transformation):**

- **Review Queue cockpit** — THE missing feature. One triage-ordered queue of everything awaiting a human: scout leads (approve/reject/watch + reason code), deal matches (same-product verification), needs-ungating flags. Every verdict writes a labeled decision. Keyboard-first (j/k navigate, A/R/W decide). (CC1)
- **Live Supabase truth** — the UI finally reads what the scout writes: leads, runs, deals, decisions — merged honestly with the local ledger. (CC1)
- **Morning Brief page** — the Discord digest, rendered richer: triage-ordered candidates with explain-why + analyst notes, seasonal window awareness ("BTS buying closes in N weeks"), due searches, pending proposals. The dashboard becomes the first tab of the day. (CC2)
- **Capital & safety cockpit** — bankroll buckets (operations.bankroll) vs actual committed capital, 20% reserve line, cut-loss list (60-day no-sale), capital-at-risk widget. Turns the encoded doctrine into visible rails. (CC2)
- **Security hardening** — the dashboard grew write powers (capture, soon decisions) with zero auth. Local-secret token on all mutating routes, security headers, rate limits, weekly Supabase backup export. (CC3)
- **Expert surfaces** — analyst note + disagreement badge + cited precedents on every lead card; brain change-history viewer; chart-upload on Find once M2's eval passes. Makes the "thinking layer" inspectable, which is what builds trust in it. (CC4)

**Considered and deliberately NOT chosen:** public deployment of the dashboard (adds attack surface for zero benefit — it's a solo local cockpit; CC3 hardens it anyway as defense-in-depth); a mobile app (the 375px-clean responsive web is enough); real-time websockets (a daily-batch system doesn't need them); what-if threshold simulator (needs months of outcomes first — revisit when labels exist).

## 3. The prompts

### Prompt CC1 — live truth + the Review Queue cockpit

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Read
CONTROL_CENTER_UPGRADE_PLAN.md §1-2 for intent. Use amazon-fba-oa:fba-architect to confirm
the data boundary (server-only Supabase reads via API routes — service key must never
reach client JS; note control-center currently has NO Supabase dependency at all), then
amazon-fba-oa:fba-coder with amazon-fba-oa:fba-designer for layout (operator-terminal
design system, design-system/oa-control-center/MASTER.md). Pre-req: migrations applied.

1. Server-side Supabase read layer: lib/supabase-server.ts using SUPABASE_URL +
   SUPABASE_SERVICE_ROLE_KEY from server env (document in .env.example; honest
   "not configured" state when absent). Same-origin API routes: /api/ops/runs,
   /api/ops/leads, /api/ops/deals, /api/ops/queue — server-only, read-only, no key
   material in any response.
2. Runs health panel on Today: last run time/status, tokens consumed/left, leads
   upserted, analyst disagreement count, searches due, heartbeat state — with honest
   "scout has never run" empty state (true today until KEEPA_KEY exists).
3. Leads page upgrade: merge Supabase leads with the local leads.json ledger (tag each
   row's source), show asin/roi/verdict/analyst-flag, link each to a detail view showing
   the full explanation structure (gates, adjustments, analyst note).
4. THE REVIEW QUEUE (/queue, new page — the centerpiece): one list, triage-ordered
   (operations.triage formula server-side), of everything with status review: scout
   leads, deal_matches gray zone, needs_ungating flags. Card shows: product, prices,
   the explain-why summary, analyst note + disagrees badge, and for deal-matches the
   side-by-side same-product comparison. Actions: Approve / Reject / Watch with a
   REQUIRED reason code (ip-risk / price-war / slow-mover / bad-match / gated /
   thin-margin / other+text) — POSTS to a new /api/ops/decide route that writes the
   decision to Supabase decisions (and deal_matches.human_verdict for matches) AND
   appends to events.jsonl (both stores, honestly labeled). Keyboard-first: j/k
   navigate, A/R/W act, number keys pick reason codes; visible focus; works at 375px.
5. Discord review_queue stream: when the daily run leaves items in review status, the
   digest's review-queue section links to this page (the stub caller from Session 25
   gets its real caller).
6. Guardrails: no auto-approve anywhere; decisions require the reason code; the decide
   route validates enums server-side and is same-origin only.
7. typecheck + build + tests (route validation, triage ordering, merge logic, decide
   round-trip with mocked Supabase); 375px clean; journal entry.
```

### Prompt CC2 — Morning Brief + capital/safety cockpit + proposals page

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
CONTROL_CENTER_UPGRADE_PLAN.md. Use amazon-fba-oa:fba-coder + fba-designer. Builds on CC1's
read layer.

1. /brief (Morning Brief): today's run summary, the triage-ordered top candidates with
   explain-why one-liners + analyst notes, seasonal awareness chips computed from
   operations.seasonal2026 vs today's date ("Q4 FBA arrival deadline in N weeks",
   "Prime Day window open"), searches due (search_log), pending brain proposals count,
   and HUMAN_TODO.md unchecked items if the file exists. Honest empty states per
   section. This page is the designed morning entry point — link it first in nav.
2. Capital & safety cockpit (extend Money page): bankroll buckets from
   operations.bankroll rendered against actual committed capital (sum of open buy
   decisions from Supabase + inventory), the 20% reserve line, a cut-loss list (any
   inventory item with no sales in operations.bankroll.cutLossDays), and the
   aged-inventory countdown: days-at-FBA per item with amber at 120 / red at 150 /
   "surcharge live" at 181 (policy2026.agedSurchargeDay from the brain — no hardcoding).
   All computed from real data; sections state their source and go honest-empty when
   data doesn't exist yet.
3. /proposals: render learning-hub/tracking/brain-proposals.md parsed into cards
   (pending vs applied), each with evidence + sample size and a copy-to-clipboard
   "apply proposal <id>" command for Claude Code. Read-only — the page NEVER applies
   anything itself.
4. KPI panel from the weekly ops report (ops-report.md + weekly-reviews.md): render the
   latest honestly ("no outcomes yet" included).
5. typecheck + build + tests (seasonal chip date math incl. year boundaries, countdown
   thresholds from brain, proposals parser with fixture file); 375px; journal entry.
```

### Prompt CC3 — security & resilience hardening

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
CONTROL_CENTER_UPGRADE_PLAN.md. Use amazon-fba-oa:fba-architect briefly (threat model: a
local-first operator app whose mutating routes now write business decisions — defense in
depth, not enterprise theater), then amazon-fba-oa:fba-coder.

1. Auth on mutating routes: OPERATOR_TOKEN in control-center/.env.local (generate one,
   document it, never commit); middleware requiring the token (header) on /api/capture
   and /api/ops/decide; the UI attaches it from a server-provided session so the
   operator never types it; honest 401 state. GET routes stay open (local reads).
2. Security headers via next.config: CSP (self + inline styles Next needs; no external
   script origins), X-Frame-Options DENY, nosniff, referrer-policy. Verify the app
   still works with CSP enforced (the theme no-flash script may need a nonce).
3. Rate limiting: simple in-memory limiter on mutating routes (e.g. 30/min) with 429 +
   honest message.
4. Weekly backup job: scout/backup_business_data.py — exports leads, decisions,
   outcomes, deals, deal_matches, runs, search_log from Supabase to
   learning-hub/backups/<date>/*.jsonl (gitignored), keeps the last 8, wired into
   run_daily.py's Monday branch alongside ops_report; digest line reports backup
   success/failure honestly.
5. Dependency hygiene: npm audit must be clean; add an audit step + Python
   pip-freeze-vs-requirements drift check into run_all_tests.py; pin any loose
   versions it finds.
6. Verify nothing broke: typecheck + build + full test suite + capture/decide round-trip
   with and without token. Journal entry.
```

### Prompt CC4 — expert surfaces (ship after S1 runs live + M2's eval reports)

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
CONTROL_CENTER_UPGRADE_PLAN.md. Use amazon-fba-oa:fba-coder + fba-designer. Pre-reqs:
ANTHROPIC_API_KEY live (analyst notes actually exist), M3's precedents landing in notes,
and for item 3 M2's eval showing acceptable image+data Tier-1 accuracy.

1. Expert lead cards: everywhere a lead renders (queue, leads, brief), show the analyst
   note with its evidence-field citations expandable, the disagrees-with-rules badge
   (loud amber), cited precedent cases (from M3) as expandable "similar past cases",
   and memory_used indicator. Add a small "analyst accuracy so far" stat where the
   disagreement-outcome data exists (honest n<15 refusal text from memory_report).
2. Brain history viewer (/brain extension): render the brain's ingestionLog + a diff
   view of the last N brain changes (git log -p on ai-brain.json now that the repo
   exists), so every rule change is auditable from the UI.
3. Chart upload on Find (GATED): a "paste/upload Keepa screenshot" affordance that
   POSTs to a new /api/chart-read route calling scout/chart_reader.py — ONLY enabled
   when a config flag chartReader.evalPassed is true in the brain (set by M2's eval,
   never by hand); until then the UI shows the honest "chart reading is in evaluation —
   accuracy N% on pattern X" state from the eval report. Extraction results pre-fill
   the analyzer's optional fields with a "from chart, verify" tag.
4. Keyboard/productivity polish across the cockpit: consistent hotkeys (documented in a
   ? overlay), focus management, reduced-motion respected.
5. typecheck + build + tests (gating flag, chart-read route mocked, badge rendering);
   375px; journal entry.
```

## 4. Order + who does what

CC1 → CC2 → CC3 can run back-to-back once R3 + migrations are done (CC1 is the big one). CC4 waits for live analyst data and M2's eval. Cowork's share is done: the weekly command review is scheduled (Mondays 9:09am → Discord + weekly-reviews.md) and this plan exists. Mehmet's share is unchanged from HUMAN_TODO.md — nothing here adds new purchases; CC1–CC3 need only the migrations + keys already on that list.

## 5. What this does NOT fix

The cockpit makes decisions faster, safer, and better-labeled — it does not create decisions. The system's expertise still grows exactly as fast as real analyses, real buys, and real outcomes flow through it. The best UI in the world is step 8 on HUMAN_TODO.md wearing a nicer shirt.
