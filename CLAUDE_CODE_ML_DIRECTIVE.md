# Claude Code — ML directive (paste this into Claude Code once; it's also loaded automatically)

This doctrine is now permanent in the repo: it lives in `amazon-fba-oa/references/ml-doctrine.md`, is imported
into `CLAUDE.md` (via `SKILLS_INDEX.md` + `CLAUDE_CODE_GUIDE.md` §0.5), and is what every session must apply.
Paste the block below into Claude Code once to make it (a) adopt the standing behavior and (b) propagate the
doctrine into every command-center plan so all future builds inherit it.

---

```
Read, in order: CLAUDE.md, CLAUDE_CODE_GUIDE.md (esp. §0.5 THE ML MANDATE), SKILLS_INDEX.md (the ML crew
section), and amazon-fba-oa/references/ml-doctrine.md. Then adopt this as a permanent standing rule for every
session from now on.

STANDING BEHAVIOR (forever):
- The learning system (item finder + ranker) is the core of this project. ANY task touching ML or the command
  center's learning path — data collection, features, training, serving/utilization, evaluation, guardrails,
  debugging, the item finder — MUST route through the fba-ml crew: fba-ml-lead plans → fba-scout-strategist /
  fba-ml-data-engineer / fba-feature-engineer / fba-ranker-architect / fba-ml-trainer implement →
  fba-leakage-auditor + fba-ml-evaluator + fba-ml-guardian SIGN OFF before any promotion or ship →
  fba-ml-debugger when something's wrong. Never hand-roll ML work without them.
- Enforce the ML laws every time: (1) breadth/no-bias — collect as much and as varied data as possible,
  brand-agnostic and category-diverse; the corpus is skewed today (Crocs+Jellycat ~30%, 4 categories) so every
  change must WIDEN coverage and report concentration; hints order, never gate membership. (2) no leakage —
  pre-decision features only, point-in-time (≤ simulation_date), missing=NaN + stale flags, outcomes are labels.
  (3) hard gates stay outside ML; the model only ranks, never buys. (4) shadow-by-default, no auto-promotion
  (a human flips scoring.rankingChampion), no auto-buy. (5) honest metrics — time-held-out, small-sample caution,
  offline != realized outcomes, per-brand/category slices.

PROPAGATE IT NOW (so future builds/upgrades inherit it automatically):
- Add a short header block to each of these that references amazon-fba-oa/references/ml-doctrine.md and states
  the crew-routing + ML-laws requirement: THIS_WEEK.md, DATA_ENGINE_PLAN.md, SYSTEM_BLUEPRINT.md, MASTERY_PLAN.md,
  CONTROL_CENTER_UPGRADE_PLAN.md, HUMAN_TODO.md (and any other active plan/brief). Keep it concise; do not
  duplicate the whole doctrine — point to it.
- From now on, every build/upgrade prompt or new module you create for the command center must reference the
  doctrine at the top and bake in the crew-routing. If you add a NEW learning component, add/update a matching
  fba-ml-* skill for it in amazon-fba-oa/skills/ and register it in the plugin.json + SKILLS_INDEX.md.

THEN do a first pass with the crew (real work, not just docs):
- Use fba-ml-lead to produce a current ML health read from the LIVE Supabase tables (backtest_rows,
  shadow_outcomes, decisions, outcomes, runs): corpus size, brand/category concentration, label-tier mix, last
  train result, champion-vs-challenger status, and whether the ranker's minimum-rows threshold is met yet.
- Use fba-scout-strategist + fba-ml-data-engineer to propose the concrete plan to DE-BIAS the corpus (widen
  brand/category coverage, per-brand/category caps, stratified sampling) — this is the top ML priority.
- Have fba-leakage-auditor re-verify the current feature set is point-in-time before the next retrain.

Guardrails unchanged: no auto-buy, no auto-promotion, no secrets in output, hard gates outside ML. Journal a
Session entry documenting what you propagated and the ML health read. Do NOT print any key.
```

---

**Why this is permanent:** `CLAUDE_CODE_GUIDE.md` §0.5 is imported into `CLAUDE.md`, so every Claude Code session
already loads the mandate. This file is the one-time seeding prompt that pushes the doctrine into the older plan
docs and starts the crew working. After it runs once, the standing behavior carries itself.
