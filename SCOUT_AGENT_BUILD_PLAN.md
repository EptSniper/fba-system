# Scout Agent Build Plan — from batch scorer to expert operator

**Date:** 2026-07-02 · **Author:** Claude (Cowork), from live web research (citations flagged in the research notes; pricing verified against official sources July 2026) · **Executor:** Claude Code (prompts S1–S4); Mehmet for keys/decisions.
**Builds on:** the scout as it exists after journal Sessions 18–19 (Phase 1 expert rules, explain-why verdicts, G1 state layer, G2 runner, G3 SP-API backend, G5 proposals — 97/97 tests).
**Companions:** `SCOUT_EXPERT_UPGRADE_BRIEF.md` (rules), `SYSTEM_BLUEPRINT.md` (loop), `DEAL_FINDER_BUILD_PLAN.md` (discovery).

---

## 1. What "agent" should mean here (research verdict)

The 2026 consensus — including Anthropic's own workflow-vs-agent doctrine — is blunt: a nightly scoring pass is a **workflow**, not an agent, and adding an autonomous agent loop would add cost, latency, and compounding error for nothing. The winning production pattern for exactly this shape of system is **hybrid LLM-over-rules**: deterministic code computes every number and enforces every gate; the LLM sits on top as a *qualitative analyst* whose judgment is structured, evidence-bound, and never decisive on its own.

So the scout "agent" = four additions, not a rewrite:

```
Keepa → hard gates (untouchable) → rule scoring (deterministic)
   → [S1] LLM ANALYST PASS over gate-survivors — second opinion, risk notes
   → [S2] OPERATIONAL DOCTRINE — triage ranking, seasonal clock, brand-growth loop,
          storefront tracker, bankroll guardrails (encoded expert practice)
   → [S3] MEMORY — per-brand/category lesson files, written by weekly reflection
   → [S4] OPERATOR INTERFACE — read-only MCP server so Mehmet can interrogate the
          scout's brain from Claude Desktop/Code conversationally
```

What the LLM must NEVER do (each backed by the research and existing project rules): move a hard gate, compute any number that reaches a decision (LLM arithmetic is documented-unreliable — all math stays in Python), auto-approve or buy, write to ai-brain.json, or assert brand/product facts not present in its input.

## 2. S1 — the LLM analyst pass (the "second opinion" layer)

Design, each element evidence-backed:

- **Placement:** after rule scoring, before the digest, on gate-survivors only (~5–50/night). Failed candidates don't burn tokens.
- **Input = pre-computed JSON only:** gate results, named adjustments with point values, ROI/velocity/trend metrics, brand memory notes (S3). **Deliberately withhold the final composite score and verdict** — finance-LLM research documents sycophancy (models agree with whatever score they're shown), which would make the second opinion decorative.
- **Output = strict schema** (structured outputs are GA on the Claude platform): `{qualitative_risk, disagrees_with_rules: bool, top_risks: [{claim, evidence_fields}], narrative ≤120 words, unknowns[]}`. Every claim must cite the input fields that drove it; a **deterministic post-validator rejects any note citing a field not in the input or misquoting its value** (tabular hallucination is the documented #1 failure mode). "UNKNOWN, not background knowledge" is an explicit instruction — the model may not use what it "knows" about a brand.
- **Model + cost:** Sonnet-class for the analyst note (this is the judgment step; Sonnet 5 intro pricing $2/$10 per MTok through Aug 31 2026), via **Batch API (50% off) with a cached system prompt (90% off cache hits)**. At 100 candidates/night ≈ **$10–30/month**. Cost does not constrain this design; quality-per-candidate is the only selector.
- **Prove it's not decorative:** log `disagrees_with_rules` per lead. If the analyst never disagrees → sycophancy, tune the prompt. When it disagrees, the review queue shows why, and realized outcomes eventually settle who was right — measurable, honest.

## 3. S2 — the operational doctrine (what expert sellers do that the scout doesn't yet)

The second research track distilled published expert practice into encodable rules. The highest-value ones missing from our brain:

1. **Gate on 90-day averages, not current values** — current BSR/price are trap-prone (stockout spikes); veterans gate on avg90 and reject when current price >1.1–1.2× avg90 Buy Box. We partially do this (spike guard at 1.5×); tighten per research.
2. **Triage ranking = payback-speed-under-stress.** With many candidates, review order should be `expected profit × realistic monthly velocity ÷ buy cost` (ROI × turns), evaluated at a STRESSED price (assume sellers pile in), checked in the order Eligibility → Speed → Downside, kill on first fail. Published baseline: manual review converts ~4–6% of candidates to buys.
3. **Brand-growth loop with a search log:** every winning lead's brand → brand-mining queue → Product Finder run → sellers on those listings → storefront candidates → their catalogs → new brands. Search log with last-run dates; re-run saved searches every 2–4 weeks; re-audit replen brands every 30–60 days.
4. **Storefront tracker:** 10–40 storefronts, qualified by: mixed-category, ≤1,000 SKUs, OA/RA listing pattern, healthy feedback, no Amazon on their listings. Re-scan frequently; new-ASIN diffs are the freshest lead source and decay in hours-to-days once widely seen. (Keepa /seller endpoint automates this — 2.2's storefront work feeds it.)
5. **Seasonal clock, 2026 edition:** toys buys Feb–Mar clearance + October; back-to-school buying late Jun–mid Aug; Q4 stock must ARRIVE at FBA by ~Oct 20–30, stop speculative Q4 buys after week 46; **Prime Day moved to June 23–26, 2026** (sourcing window, not selling event, for OA); bias Q4 toward low-return categories; January = clearance + returns-wave defense.
6. **Bankroll guardrails:** weekly budget buckets (proven winners largest share / capped test buys / seasonal reserve), ~20% cash reserve, pre-committed cut-loss (no sales in 60 days at realistic price → liquidate; nothing approaches 181 days in FBA — the aged surcharge now starts there), reorder point = weekly velocity × lead time + buffer.
7. **Weekly ops KPIs:** 90-day sell-through (target ≥3), inventory turns (6–12×/yr floor), realized-vs-estimated ROI gap per source (expect 10–20% realized net margins in 2026 vs 30%+ estimates — track the slippage), lead→buy conversion, profit per review-hour per source.
8. **Mid-2026 policy facts the brain doesn't know yet:** FBA payouts held until **7 days after delivery** (Mar 2026 — lengthens the cash cycle materially), aged-inventory surcharge from **day 181** (was 271), commingling ended Mar 2026, +$0.08/unit avg fee increase Jan 2026, Prime Day in June.

## 4. S3 — memory, S4 — operator interface

**Memory (S3):** per-brand and per-category markdown lesson files (verdicts given, realized outcomes, IP observations, seasonal quirks), written by a **weekly reflection job** — a Claude call that reads the week's new outcomes/decisions and updates the notes, with consolidation and pruning (stale-memory poisoning is a documented failure mode). Notes load into the S1 analyst prompt for matching brands. Honest caveat from research: measurable gains for this exact domain are unproven — so S3 ships with its own A/B measurement (analyst accuracy with vs without memory, judged against realized outcomes).

**Operator interface (S4):** a small **read-only MCP server** over our Supabase (`get_lead(asin)`, `top_leads(date)`, `why_rejected(asin)`, `brand_history(brand)`, `run_stats()`), registered in Claude Desktop/Code. Then "why did the scout pass on this?" is a conversation, not a SQL session. Read-only = can't corrupt the pipeline. (Research checked third-party Keepa MCPs: hobby-grade, and we already speak Keepa natively — skip them.)

## 5. Claude Code prompts

### Prompt S1 — the analyst pass

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect to confirm placement (post-scoring, pre-digest, survivors only),
then amazon-fba-oa:fba-coder. Requires ANTHROPIC_API_KEY in scout/.env (skip gracefully with
an honest log line when absent — same pattern as KEEPA_KEY/SP-API).

1. scout/analyst.py: for each gate-survivor, build an input JSON of PRE-COMPUTED facts only:
   gate results, named adjustments with points, profit/ROI/velocity metrics, trend deltas,
   restriction hints, and (when S3 exists) brand memory notes. Deliberately EXCLUDE the
   final composite score and verdict (anti-sycophancy). Call Claude Sonnet with structured
   outputs, schema: {qualitative_risk: low|medium|high, disagrees_with_rules: bool,
   top_risks: [{claim: str, evidence_fields: [str]}], narrative: str (<=120 words),
   unknowns: [str]}. System prompt: the OA analyst persona, the rubric, and the hard
   instruction "if the input does not contain it, output UNKNOWN — never use background
   knowledge about this brand or product." Use the Batch API when >10 candidates and cache
   the static system prompt.
2. Deterministic post-validator: reject/flag any response whose evidence_fields are not
   present in the input JSON or whose quoted values don't match; rejected notes are stored
   with status invalid and excluded from the digest (count them in telemetry).
3. Persist to the lead row (extend the explanation JSONB or add analyst_note JSONB) and
   track disagrees_with_rules in run telemetry; digest shows the analyst line under each
   pick, marks disagreements loudly, and reports "analyst disagreed on N of M".
4. The analyst NEVER changes a verdict, score, or gate — assert this in a test (AST-based
   guard like tuning_report's: analyst.py has no write path to scoring/gates/ai-brain).
5. Tests: schema round-trip with mocked API, post-validator catches fabricated fields,
   graceful no-key skip, batch-vs-single path selection. Full suite green. Journal entry.
```

### Prompt S2 — operational doctrine into the brain + pipeline

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-brain-updater for ALL ai-brain.json changes, amazon-fba-oa:fba-coder for
code. Sources for every value below are 2025–2026 practitioner research (BowTiedSlinger /
FBA Mogul / FBA Lead List / Clear The Shelf / Amazon official fee announcements) — cite
"SCOUT_AGENT_BUILD_PLAN.md research, 2026-07-02" in the source: lines.

1. Brain additions (validate, provenance, bump updated, re-sync hub-data):
   a. operations.triage: { formula: "expected_profit * monthly_velocity / buy_cost,
      stressed", stressedPriceFactor: 0.90, reviewOrder: ["eligibility","speed","downside"],
      manualReviewBuyRate: "0.04-0.06 baseline" }
   b. operations.seasonal2026: primeDay June 23-26 (sourcing window), btsBuyWindow
      "late Jun - mid Aug", q4ArrivalDeadline "Oct 20-30", q4StopWeek 46, toysBuyWindows
      ["Feb-Mar clearance","Oct"], janReturnsWave true, biasQ4LowReturnCategories true.
   c. operations.bankroll: { cashReservePct: 0.20, cutLossDays: 60, agedSurchargeDay: 181,
      reorderFormula: "weekly_velocity * lead_time + buffer", buckets: ["winners","tests",
      "seasonalReserve"] }
   d. operations.kpis: sellThrough90Target 3, turnsFloor 6, trackRealizedVsEstimatedGap
      true, profitPerReviewHour true.
   e. policy2026 facts: payoutHoldDaysAfterDelivery 7 (Mar 2026), commingling ended,
      feeIncreasePerUnit 0.08 (Jan 2026). Cross-check against existing keys — do not
      duplicate what Phase 1 already added (fuel surcharge, prep cost).
   f. guards: add currentVsAvg90PriceCaution 1.15 (softer than the existing 1.5 spike
      hard-flag: a caution adjustment, not a gate change — do NOT touch priceSpikeRatio).
2. Pipeline: implement triage ranking — order the digest/review queue by the stressed
   payback formula (all math deterministic); add the 1.15 caution adjustment as a named
   explanation entry; gate demand checks on avg90 BSR when available (fallback current,
   record which was used).
3. Brand-growth loop scaffolding: a search_log table migration
   (scout/db/migrations/00N_..., NOT-APPLIED pattern) — saved Product Finder searches with
   last_run + rerunAfterDays (default 21) — and a brand-mining queue: brands of winning
   leads (human-approved) get queued; the runner surfaces "searches due for re-run" in the
   digest. Actual Product Finder execution stays Keepa-gated.
4. Weekly ops report: scout/ops_report.py appending to learning-hub/tracking/
   ops-report.md — the operations.kpis computed from Supabase (honest "no data yet" until
   outcomes exist), including realized-vs-estimated ROI gap per source and profit per
   review-hour. Wire into run_daily.py weekly (e.g., Mondays), same try/except isolation
   as propose_updates.
5. Tests: triage ordering (stressed vs headline ROI produce different orders), caution
   adjustment naming, search-log due-date logic, ops report empty-state. Full suite green.
   Journal entry.
```

### Prompt S3 — brand/category memory + weekly reflection

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-architect (5 min: file-based vs Supabase-table memory — prefer files in
learning-hub/memory/ for git-visibility and human editability), then amazon-fba-oa:fba-coder.
Requires ANTHROPIC_API_KEY; degrade gracefully without it.

1. learning-hub/memory/brands/<brand-slug>.md and categories/<cat>.md: structured notes
   (## Verdict history, ## Realized outcomes, ## Risk observations, ## Seasonal notes),
   machine-appended + human-editable.
2. scout/reflect.py, weekly from run_daily.py: reads the week's new decisions/outcomes +
   analyst disagreements, and for each affected brand/category calls Claude (Sonnet,
   structured output) to UPDATE the note file: merge lessons, deduplicate, prune stale
   entries (consolidation prevents memory poisoning), max ~60 lines per file. The
   reflection prompt forbids inventing facts not present in the provided rows; a
   post-validator checks every ASIN/number cited exists in the input.
3. S1 integration: analyst input includes the matching brand + category notes (truncated).
   Track memory_used: bool per analyst call.
4. Measurement harness: once >=30 leads have realized outcomes, report analyst
   disagreement-accuracy WITH vs WITHOUT memory (memory_used flag makes this queryable).
   Until then the report says so honestly.
5. AST guard: reflect.py has no write path to ai-brain.json or scoring. Tests: note
   merge/prune with fixtures, post-validator, graceful no-key. Full suite green. Journal
   entry.
```

### Prompt S4 — read-only MCP server over the scout's brain

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Use
amazon-fba-oa:fba-coder. Python official `mcp` package (FastMCP style), new module
scout/mcp_server.py, stdio transport.

Read-only tools (few, high-level, compact structured results): get_lead(asin),
top_leads(date=today, n=10) ordered by the S2 triage formula, why_rejected(asin) (gates +
adjustments + analyst note), brand_history(brand) (leads, outcomes, memory note),
run_stats(days=7) (runs telemetry incl. token spend and analyst disagreement rate),
search_log_due(). All queries via the existing scout/db.py read paths; the server never
writes anything — enforce with an AST guard test like tuning_report's. Include a
claude_desktop_config.json snippet + Claude Code .mcp.json registration in scout/README.md.
Uses the same .env; note plainly in the README that the server runs locally and inherits
the service key's access, so it must never be exposed beyond localhost. Tests with a mocked
db layer. Journal entry.
```

## 6. Order, cost, and honest expectations

Sequence: **S1 → S2** (both work today — S1 needs only the Anthropic key; S2 is key-free except the Keepa-gated Product Finder execution) → **S4** (any time, pure convenience) → **S3** (ships now, pays off once outcomes exist). Natural interleaving with the other plans: S1/S2 before or alongside deal-finder D2 (they share the Anthropic key), Phase 2 (Keepa) unlocks S2's storefront/search-log execution and floods S1 with real candidates.

Running cost: ~$10–30/month LLM spend at full volume (Sonnet, batched, cached). New keys needed: only `ANTHROPIC_API_KEY` — shared with deal-finder D2.

What this will and won't do: the analyst catches qualitative risk the rules can't see, the doctrine makes the queue ordered by what deserves your minutes, memory compounds your own outcomes into institutional knowledge, and the MCP server makes the whole thing conversational. It will NOT out-judge the gates (by design), won't be provably smarter until realized outcomes accumulate (the disagreement log measures it honestly), and the research flag stands: no published study covers LLM-over-rules for OA specifically — we're applying finance-screening evidence and measuring ourselves.
