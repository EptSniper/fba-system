# Mastery Plan — making the scout, deal finder, and analyst genuine experts

**Date:** 2026-07-03 · **Author:** Claude (Cowork), from the full-system audit + web research (sources in `RESEARCH_WATCHLIST.md` and the research notes) · **Executor:** Claude Code (Prompts M1–M4); Mehmet for keys/decisions.
**Companions:** `CODE_REVIEW_2026-07-02.md` (Parts 1–2 + R1/R2/R3 fix prompts), `DEAL_FINDER_BUILD_PLAN.md` (D2–D4), `SCOUT_AGENT_BUILD_PLAN.md` (S1–S4, built), `RESEARCH_WATCHLIST.md` (the material).

> **ML doctrine applies.** Any work here touching data collection, features, training, serving,
> evaluation, guardrails, or the item finder routes through the `fba-ml` crew (`fba-ml-lead` plans;
> see `SKILLS_INDEX.md`'s ML crew section) and must obey `amazon-fba-oa/references/ml-doctrine.md`:
> breadth/no-bias, no leakage (point-in-time features only), hard gates outside ML, shadow-by-default
> with human-only promotion, honest metrics. Never hand-roll ML work without the crew.

---

## 1. Honest verdict first: are the tools experts today?

**No — they are a very well-built intermediate with an expert's bookshelf and no flight hours.** Precisely:

- **Scout:** the rule layer is genuinely strong (gates, guards, explain-why, triage, avg90 discipline, 2026 policy encoded — ~284 tests). But it has never scored a real candidate (no Keepa key), the analyst brain (S1) has never made one real call (no Anthropic key), and the R1-blocker bugs meant the learning loop would have recorded nothing. Expertise that has never touched live data is a syllabus, not experience.
- **Deal finder:** D1 only — it can collect deals (Slickdeals RSS, Best Buy) and normalize them, but there is **zero matching code** (D2) and **zero pipeline wiring** (D3): collected deals go nowhere today (and without migration 003, aren't even persisted). It does NOT yet work with the scout — that's not a bug, it's the unbuilt half of the plan.
- **Control-center:** functions as intended on most pages with 2 real bugs and honest-lag findings — see CODE_REVIEW Part 2 + Prompt R3.
- **Chart reading:** nothing in the system can read a Keepa/SellerAmp image today. The fba-chart-reader skill guides ME (Claude in chat), but the pipeline is numbers-only.

What "20 years of experience" actually decomposes into — and how each maps to work in this plan:

| Veteran capability | Mechanism | Status |
|---|---|---|
| Pattern recognition on charts | Vision LLM + labeled example bank + eval (M2) | missing → build |
| Judgment beyond rules | Analyst pass + case-based reasoning (M3) | built, unproven → upgrade + arm |
| Deep domain knowledge, current | Corpus + watchlist ingestion (M1) | good → expand with advanced/failure content |
| Scar tissue from failures | Failure-postmortem content (M1) + own outcomes loop (built) | thin → ingest + accumulate |
| Knowing when rules mislead | disagrees_with_rules telemetry + exemplars of rule-breaking veterans (M1 §A3) | built, needs data |
| Muscle memory / ops discipline | operations.* doctrine (S2, built) + runner | built |

## 2. "Thinking skills, not this-rule-that-rule" — the design, stated plainly

The research is unambiguous on how to do this without wrecking what works:

1. **Rules stay as the floor, not the ceiling.** Real 20-year veterans use hard checklists for eligibility and risk — that's not amateurism, it's what keeps them alive. Hard gates (Amazon BB, IP cliff, avoid brands, account eligibility) remain non-negotiable. "Thinking" happens ABOVE the floor.
2. **The thinking layer is the analyst (S1) — and it becomes case-based.** Research finding: retrieving a few hundred labeled expert cases into context matches or beats fine-tuning (Many-Shot ICL, NeurIPS 2024), and case-based reasoning is exactly how veterans think ("this chart looks like that Jellycat situation from March"). So we build an **exemplar bank** — expert-annotated chart cases from the guides + our own accumulating decisions/outcomes — and the analyst retrieves the 3–5 most similar cases before judging each candidate. Its opinion is grounded in precedent, not rules.
3. **Chart eyes: image + data together, never image alone.** Vision LLMs are documented to misread exactly Keepa's hard parts (dual inverted axes, color legends) — but providing the underlying data next to the image moves chart-QA accuracy from ~31% to ~87% (Charts-of-Thought). We always have the data (Keepa CSV/stats). So chart reading = image + derived stats + extraction-first prompting, tested against a two-tier eval (perception, then judgment) before anyone trusts it.
4. **Honesty stays measurable.** The analyst's `disagrees_with_rules` log and the memory A/B harness (built in S1/S3) are how we'll KNOW it's thinking rather than rubber-stamping. Chart-reading gets the same treatment: held-out test set, per-pattern accuracy with confidence intervals, published in the ops report.

## 3. The prompts

### Prompt M1 — feed the machine: watchlist ingestion (transcripts + articles)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first. Read
RESEARCH_WATCHLIST.md in the project root — it is the complete input list. Use the
amazon-fba-oa:fba-transcript-ingest skill's conventions for corpus entries and
amazon-fba-oa:fba-brain-updater for any ai-brain.json count/insight updates.

1. Transcripts: pull transcripts for all Section A videos via the existing
   knowledge-rag/fetch_transcripts.py path (YOUTUBE_TRANSCRIPT_API_KEY in
   knowledge-rag/.env; this must run from Claude Code, not Cowork — Cowork's sandbox
   can't reach the transcript API). FIRST dedupe by videoId against the existing corpus
   (at least wwNw5vNAyeM and TZyBG1_-jLM are suspected duplicates — skip them if present).
   Stage through research-inbox/ per the established daily-pipeline conventions, then
   ingest.py -> corpus, then upload_to_supabase.py (defaults are now safe post-R1:
   EMBED_PROVIDER=local). Verify live doc/chunk counts after upload.
2. Articles: fetch every Section B URL as text (respect robots; skip any that block and
   list them for manual pull — BowTiedSlinger is known-blocked). For the chart guides
   (B1-B7), ALSO save the annotated chart IMAGES with their surrounding interpretation
   text into knowledge-rag/sources/chart-examples/<source>/<pattern>.md+png — these are
   the seed corpus for Prompt M2, so preserve the image-to-commentary pairing and tag
   each with its pattern (seasonal / price-war / amazon-oos / flooded / dying /
   pl-single-seller / data-gap-artifact / ip-cliff).
3. Distill: after ingestion, run focused retrieval passes ("what do veterans do that our
   rules don't capture", "2026 policy changes affecting OA", "failure postmortems") and
   append the durable new lessons to learning-hub's insights per fba-transcript-ingest;
   anything that suggests a brain change goes to learning-hub/tracking/brain-proposals.md
   as proposals (NEVER direct edits).
4. Ongoing: add the 5 monitoring channels + 2 tool feeds (watchlist Section A end) to the
   daily research pipeline's source list so new uploads flow in automatically.
5. Update ai-brain.json knowledge counts + ingestionLog via fba-brain-updater; re-sync
   hub-data; Discord digest note to #brain-proposals if proposals were generated.
   Journal entry.
```

### Prompt M2 — chart eyes: the Keepa/SellerAmp reading corpus + honest eval

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and MASTERY_PLAN.md §2
point 3. Use amazon-fba-oa:fba-architect briefly (module placement), then
amazon-fba-oa:fba-coder; the amazon-fba-oa:fba-chart-reader and fba-keepa-analyst skills
define the interpretation vocabulary — read both SKILL.md files and reuse their decoding
structure. Requires ANTHROPIC_API_KEY; the self-generated gallery additionally needs
KEEPA_KEY (build it key-gated).

1. scout/chart_reader.py: given a chart image (and, when available, the matching Keepa
   stats/CSV-derived numbers), call Claude vision with EXTRACTION-FIRST prompting:
   step 1 extract {series present, current BB price, rank range, amazon in-stock spans,
   offer-count trend, drops count} as JSON; step 2 classify pattern(s) from the fixed
   taxonomy (seasonal / price-war / amazon-oos-opportunity / flooded / dying /
   pl-single-seller / ip-cliff / data-gap-artifact / stable-healthy); step 3 verdict-
   relevant narrative. ALWAYS include the derived numeric stats in the prompt when they
   exist — never send the image alone in production (documented ~31%->87% effect). Post-
   validate: every numeric claim in step 1 must be consistent with provided stats where
   both exist; inconsistent responses are marked low-confidence.
2. Exemplar bank: load the M1 chart-examples (image + expert interpretation pairs) and
   include the 3 most pattern-relevant exemplars in each call (case-based prompting).
3. Two-tier eval harness (scout/tests/eval_chart_reader.py + fixtures):
   - Tier 1 PERCEPTION: scored automatically against ground truth. Build the primary set
     self-generated: once KEEPA_KEY exists, select 100-200 ASINs spanning the taxonomy,
     render Keepa's graph image per ASIN, and derive labels programmatically from the
     same window's API data (drops, OOS%, offer trend, BB volatility). Until the key
     exists, run Tier 1 on the ~30-40 public annotated charts from M1 with hand-checked
     labels.
   - Tier 2 JUDGMENT: pattern classification + buy-relevance vs the expert annotations.
   - Report per-pattern accuracy with binomial confidence intervals; refuse to report a
     class with n<30 as anything but "insufficient sample"; keep a held-out split that
     never appears as exemplars; run image-only as a stress condition vs image+data as
     the production condition and report both.
4. Integration: pipeline candidates that have chart images (Phase 2 enrichment / manual
   Find-page uploads later) get a chart_read attached to the analyst input; the analyst
   may cite it but chart_reader NEVER changes gates/scores (same AST-guard pattern as
   analyst.py). The Find page gets a "paste Keepa screenshot" affordance ONLY after the
   eval shows Tier 1 image+data accuracy is acceptable — until then it stays internal.
5. Tests (mocked vision calls) + the eval harness runnable via run_all_tests.py.
   Journal entry including the FIRST honest eval numbers.
```

### Prompt M3 — thinking upgrade: case-based analyst + exemplar bank

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and MASTERY_PLAN.md §2.
Use amazon-fba-oa:fba-architect to confirm storage shape, then amazon-fba-oa:fba-coder.
Requires ANTHROPIC_API_KEY.

1. Exemplar bank: learning-hub/memory/cases/*.md — one file per labeled case:
   {source: guide|own-decision|own-outcome, structured facts (the same pre-computed
   metric JSON the analyst sees), chart pattern tags, the expert/human verdict, the
   realized outcome when known, and a <=80-word lesson}. Seed it from: (a) M1's annotated
   chart examples, (b) every existing decision in Supabase/events.jsonl, (c) the
   watchlist's veteran-judgment content where a concrete case is narrated (e.g. "panel
   where four veterans disagreed"). Index cases with the local bge embedding model
   (reuse knowledge-rag's helper) over their structured-facts text.
2. analyst.py upgrade: before each candidate call, retrieve the 3-5 most similar cases
   (cosine over structured facts + shared pattern tags) and include them as precedents in
   the prompt with the instruction "reason from these precedents; note where this
   candidate differs from the nearest one." Add cited_precedents to the output schema and
   post-validate they were actually provided. memory_used telemetry stays; add
   precedent_ids to the stored note.
3. Reflection integration: reflect.py's weekly pass also writes NEW case files from the
   week's resolved outcomes (decision + outcome + lesson), so the bank grows from OUR
   data over time — the flight hours accumulating.
4. Measurement: extend memory_report.py to compare analyst disagreement-accuracy across
   three conditions (no-memory / brand-memory / brand-memory+precedents) with the same
   >=15-per-group refusal. The claim "it thinks better with cases" gets proven or
   dropped.
5. AST guards (no gate/score/brain writes), mocked tests, full suite green. Journal
   entry.
```

### Prompt M4 — make the pair actually work together (deal finder ⇄ scout) + end-to-end proof

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, DEAL_FINDER_BUILD_PLAN.md
(Prompts D2 and D3 — implement BOTH, they are already fully specified), and the
integration-audit findings in MASTERY_PLAN.md §1. Pre-reqs: migrations applied (incl.
003), ANTHROPIC_API_KEY present; KEEPA_KEY optional (UPC path degrades to SP-API/skip
with honest logging).

1. Implement D2 (the matcher) and D3 (runner wiring + Deals UI) exactly per their
   prompts in DEAL_FINDER_BUILD_PLAN.md.
2. THEN add the end-to-end integration proof the user asked for —
   scout/tests/test_e2e_dealflow.py: a fixture-driven golden-path test that runs the
   WHOLE chain offline: fixture Slickdeals RSS payload -> normalize -> (mocked Keepa/
   SP-API) match at >=0.90 -> enters pipeline.run_once() as source="deal-finder" with
   discount-stacked landed cost -> hard gates apply -> scoring + triage -> (mocked)
   analyst pass runs on it like any candidate -> Supabase upsert called with
   features_snapshot + explanation + analyst note -> digest content contains it under
   "Retail deals" -> gray-zone fixture (0.7 confidence) lands in deal_matches as
   status=review and appears in the review_queue Discord stream payload instead. Assert
   every hand-off. This test is the definition of "the deal finder works with the scout"
   — it must pass before any live run.
3. Also verify the analyst treats deal-finder candidates identically (no source-based
   bypass) with an explicit test.
4. Full suite via run_all_tests.py; typecheck+build for the UI half. Journal entry.
```

## 4. Order and dependencies

R1 → migrations → R2 → R3 (fix what exists) → **M1** (no keys beyond the existing transcript key; feeds everything) → keys: ANTHROPIC_API_KEY (unlocks S1/S3 live + M2 seed eval + M3 + D2) → **M4** (deal finder complete + integration proof) → **M3** → KEEPA_KEY (unlocks Phase 2, the self-generated chart gallery, live scouting) → **M2 full eval** → go-live per SYSTEM_BLUEPRINT with 10–20 manual analyses running throughout.

## 5. Honest expectations

Ingesting 35 more videos makes the KNOWLEDGE veteran-grade; it does not make the tools veterans — the exemplar bank, the disagreement telemetry, and above all REAL outcomes do that, and outcomes only come from running the loop on real buys. Chart vision will be measurably good at some patterns and measurably bad at others (the eval exists to know which — expect data-gap artifacts and dual-axis confusions to be the weak spots, per the published failure modes). The "20-year expert" is the system three months from now with a few hundred of your own decisions and dozens of realized outcomes in its case bank — everything in this plan is the machinery that makes those months count.
