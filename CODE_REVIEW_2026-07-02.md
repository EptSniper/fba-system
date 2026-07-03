# CODE REVIEW — full pre-flight review of the entire codebase

**Date:** 2026-07-02 · **Reviewer:** Claude (Cowork), read-only per fba-code-reviewer standards — findings, not fixes. Fixes go to Claude Code via the prompts at the end.
**Scope:** scout/ (all modules through Session 24), scout_pro/, control-center/, knowledge-rag/, migrations 001–004, env/secrets hygiene, brain consistency, workspace. Two findings were **empirically verified** by executing the import sequence in a sandbox, not just read.

**Headline:** the architecture is sound where it was deliberately designed — hard gates hold, the new learning loop is leakage-clean, the analyst is provably advisory, secrets grep is clean outside env files, the brain is byte-identical everywhere. But **the system would go live broken**: two silent-failure bugs mean the learning loop would record nothing while looking healthy, the migrations as written can never deliver the idempotency they promise, a legacy training loop violates the project's own #1 ML rule, and error paths can leak API keys into Discord. Fix order matters — read §Fix sequence.

---

## BLOCKERS (must fix before any key goes in)

**B1. Supabase is silently disabled in every `run_daily.py` run — import-order bug. [VERIFIED]**
`scout/db.py:38-39` reads `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` at module import time, but `run_daily.py:37` imports `db` before anything triggers `config`'s `load_dotenv()`. Result: `db.enabled()` is False for the entire daily cycle — no leads, no runs row, no snapshots, no search-log — with only `"supabase_enabled": false` buried in the summary. The whole learning loop no-ops while the digest looks healthy. Same class: `run_daily.py:61` reads `LOW_TOKEN_WARNING_THRESHOLD` pre-dotenv. Fix: read env lazily inside `db.enabled()`/`_headers()` (or `load_dotenv()` at the top of `db.py` and `run_daily.py`).

**B2. Pre-migration lead writes don't degrade — they fail entirely.**
`db.log_lead()` (`db.py:127-129`) sends `features_snapshot` and `explanation`, columns that exist only after unapplied migration 001. PostgREST rejects unknown columns, so the upsert fails AND the plain-insert fallback fails → **zero lead rows ever written**, contradicting `pipeline.py:178-182`'s stale comment. Migrations must be applied before go-live — but not before B3.

**B3. The migrations' unique indexes can't be targeted by the code's upserts — idempotency will never materialize even after applying them.**
PostgREST `on_conflict=` can't bind to **partial** or **expression** unique indexes: `db.py:131` (`asin,found_via`) vs 001's `...WHERE asin IS NOT NULL` partial index → 42P10 at runtime → silent fallback to plain insert → the duplicates migration 001 exists to prevent. Same for `db.py:146` (snapshot_date), `db.py:350` (deals natural key vs 003's partial index), and worst: `db.py:368` `on_conflict=brand` vs 004's `lower(brand)` **expression** index — there is no unique constraint on `brand`, so `queue_brand_search()` errors and returns None: **the brand-growth loop never queues anything**. Fix: rewrite migrations to plain `UNIQUE` constraints (`ALTER TABLE ... ADD CONSTRAINT ... UNIQUE (asin, found_via)` etc.) and store normalized lowercase brand. **This must be corrected in the SQL files BEFORE Mehmet applies 001–004.**

**B4. ML integrity: the legacy training loop violates the leakage doctrine and runs by default.**
`scout/model.py:32-33` includes `rule_score` in `FEATURES`; `storage.training_rows()` feeds it; `pipeline.run_once(retrain=True)` (`pipeline.py:210,231-232`) retrains once 20 SQLite labels exist — the scout's own judgment becomes a model feature, and `blended_score` then decides what gets posted. This is precisely the self-confirmation the project bans, and it bypasses the carefully guarded `labels.py` path (which requires 30 brain-sourced labels). Fix: remove `rule_score` from FEATURES or hard-disable `maybe_retrain` until the legacy loop is unified with `labels.py`.

**B5. Secrets can leak into logs, Discord, and the runs table via raw exception text.**
(a) `deals/sources/bestbuy.py:43` puts the API key in the URL query; `raise_for_status()` errors embed the full URL → logged (`bestbuy.py:95`, `deals/collect.py:70`). (b) `pipeline.py:333-334` and `run_daily.py:127/167` push raw `str(e)` into `runs.error_summary`, the digest embed, and the system-health Discord post — Keepa also carries its key as a URL param, so one Keepa exception can post the key to Discord. Fix: a `redact()` helper applied to every error string that leaves the process (mask known env-var values + `key=`/`webhooks/` URL patterns).

**B6. There is no functioning git repo — version control is an illusion.**
`.git/` exists but is empty (no HEAD, no objects; `git status` fails). Nothing has ever been committed: no rollback, no history, no diff-based review for a codebase now at ~284 tests. Silver lining: no secret has ever been committed either. Fix (Mehmet + Claude Code): add `.env.*` to the root `.gitignore` (it currently misses `.env.local` — `tracker/.env.local` holds a live Vercel token), then `git init` + first commit.

**B7. `knowledge-rag/upload_to_supabase.py` still defaults to the WRONG embedding provider with no runtime guard.**
`PROVIDER = os.environ.get("EMBED_PROVIDER", "gemini")` (line 28). The live corpus is 768-dim local bge-base; one forgetful run without `EMBED_PROVIDER=local` starts writing incompatible vectors into the same table and silently degrades retrieval. The only protection is a comment in API_KEYS.env. Fix: invert the default to `local`, and refuse non-local providers unless an explicit `--force-provider` flag is passed, with a message explaining why.

## SHOULD-FIX (before trusting the system, not before running it)

**S1.** `run_daily.py:282` pings the healthchecks **success** heartbeat even on `--dry-run` — a dry run can mask a dead real schedule. Skip heartbeat when dry.
**S2.** Keepa token exhaustion = indefinite hang: `keepa_client.py:273,291-297` use `wait=True` with no cap; a drained bucket blocks past the next scheduled run. Add a run-level deadline + honest abort into the digest.
**S3.** `category` is never populated (`keepa_client._normalize()` has no category field) — so the grocery ROI exception, category referral rates, and triage's category arg are **inert dead features**. Map Keepa's category tree into the normalize step.
**S4.** Gate semantics: `explain_oa` presents ROI/profit/BSR/sales as "gates" but they're score components — a 20%-ROI candidate can still score ~92 and get posted; only Amazon-BB/avoid-brand/IP-cliff/no-price hard-reject (`scoring.py:594-610`). Either make them true gates or rename them in the explanation ("scored checks") — currently it's quiet gate erosion in the UI of the explanation itself.
**S5.** Score-affecting constants still hardcoded outside the brain: adjustment magnitudes (`scoring.py:443-478`: −15/−12/−20/−10/−8/+5), IP-cliff shape (avg≥8→cur≤2), worst-case $2 bar, `SCORE_THRESHOLD`/`TOP_N` (.env-only), assumed 7,500-token budget (`propose_updates.py:47`). Move to ai-brain.json `scoring.adjustments` block via fba-brain-updater.
**S6.** Control-center deal-analyzer hardcodes `FUEL_RATE=0.035`, `PREP=0.5`, `$0.30` floor (`deal-analyzer.tsx:57-58,129,152`) — not brain keys, so tuning `OA_PREP_COST` diverges dashboard math from scout math. Add `fees.fuelSurcharge`/`fees.prepCost` to the brain; both sides read it.
**S7.** `upsert_keepa_snapshot` relies on 001's UTC-generated `snapshot_date` — late-evening local runs bucket into "tomorrow." Send an explicit local-date `snapshot_date` (and align the unique constraint per B3).
**S8.** Digest run-id race: `run_daily.py:232-233` cites `recent_runs(limit=1)` — a concurrent manual run makes the digest report the wrong run. Thread the run id through instead.
**S9.** AST guards are narrower than their docstrings claim: `test_mcp_server.py:27-36` misses `from db import X`/getattr bypasses; `open()` guards miss `pathlib.write_text`/`os.open`. Tighten or reword.
**S10.** `db.py:123` hardcodes `ATVPDKIKX0DER` (use `config.AMAZON_SELLER_ID`); `amazon_present` goes truthy on ANY bb share > 0, inconsistent with the 0.20 gate semantics.
**S11.** `db.py:100-103` prints "run migration 001" for ANY upsert error (network down, bad payload) — distinguish missing-constraint errors from the rest.
**S12.** Doc/test drift: `scout/README.md` + `CLAUDE_CODE_GUIDE.md` tell people to run pytest, which isn't installed/required anywhere and the env can't run; "15 tests" claims vs 27 actual in test_scoring; corpus counts stale in `knowledge-rag/README.md:17,20` and `control-center/README.md:24` (say 45/78/1,224; truth is 51/97/1,316); no single command runs all ~284 tests — add `scout/run_all_tests.py`.
**S13.** `control-center/hub-data/leads.json` lags the live copy — the drift check watches only ai-brain.json; extend it to all mirrored hub-data files.
**S14.** scout_pro: dormant but diverging — it hard-gates hazmat/margin where scout only flags (make the difference deliberate or align), and its notifier reads legacy `DISCORD_WEBHOOK_URL` that the new routing scheme no longer sets (dead if ever run).

## NITS

Workspace: 82MB dead `Unconfirmed 983812.crdownload`, `Codex Installer.exe`, byte-identical duplicate transcript `(1).txt`, four abandoned dashboard prototypes (`oa-control-center.html` embeds a stale 48-doc corpus snapshot — a confusion hazard), `tracker/` vs `fba-tracker-site/` near-duplicates, 0-byte `research-manifest.json.bak`. Code: `pipeline.py:116`/`discord_notify.py:133` call private `discord_router._resolve_url`; `_slug` duplicated (reflect/mcp_server); reflect's ASIN regex misses non-B0 ASINs; dead legacy (`competitors.py`, PL scoring path, `config.have_discord()`); `✓✗→★` symbols in dry-run output on a cp1252 console; tz-naive `last_run_at` TypeError path in `search_log._is_due`; scout/.env's legacy `SCOUT_DISCORD_WEBHOOK_URL` read by nothing; journal-claimed 235 tests vs ~284 actual. Standing: Session 14's exposed service_role key **still unrotated**; Session 24 accidentally printed webhook URLs into a Claude Code tool output (post-only risk — rotate at leisure).

## WHAT'S GOOD (keep doing this)

Hard-gate integrity holds end-to-end (gates before posting; analyst provably can't touch score/verdict/gates; triage genuinely sort-only — all assert-tested). The NEW learning loop's leakage prevention is real: allowlist enforced on write AND re-filtered on read; honest refusal below 30 labels. Anti-sycophancy analyst design (score withheld, evidence-field post-validation) is genuinely well built. Every outbound HTTP call has a timeout; Discord 429s handled; response codes checked; no fake "sent" claims anywhere. Honest empty states throughout. The knowledge-search route is injection-safe (execFile arg-array, timeout, maxBuffer, length cap, dev-only error detail) and the capture route validates properly with honest 503s. Secrets grep across the full tree: clean outside gitignored env files. Brain: byte-identical in all three copies; thresholds trace to brain keys with only documented fallbacks. 281/284 tests pass in a clean environment (3 failures were sandbox artifacts).

## Verification gaps (unprovable until keys/hardware exist)

Everything Keepa-specific (Product Finder params, stats array shapes, token telemetry attrs) is untested against the live API — first run must be `--dry-run` with field-by-field inspection. `spapi.py` is fully mocked. `mcp_server.build_server()` has never run against the real `mcp` package (needs Python 3.10+). S1/S3 have never made a real Anthropic call.

---

## Fix sequence (order matters)

1. **Claude Code — Prompt R1 below** (B1–B5, B7 + S1/S2/S7/S8/S10/S11): the silent-failure and leakage fixes, including rewriting the migration SQL (B3) BEFORE anything is applied.
2. **Mehmet:** apply the CORRECTED migrations 001–004 in the Supabase SQL Editor.
3. **Claude Code — Prompt R2 below** (S3–S6, S9, S12–S14 + top nits): parity, brain-sourcing, docs, test runner.
4. **Mehmet:** add `.env.*` to root .gitignore is included in R1; then `git init` + first commit (R1 includes the .gitignore fix; Claude Code can run the init + commit too if you tell it to).
5. Then keys (Anthropic → Keepa) and go-live per the existing roadmap.

### Prompt R1 — critical fixes (paste first)

```
Read CLAUDE.md and the latest AI_COLLABORATION_JOURNAL.md entries first, then read
CODE_REVIEW_2026-07-02.md in the project root — this prompt implements its BLOCKERS plus
S1/S2/S7/S8/S10/S11. Use amazon-fba-oa:fba-coder; use amazon-fba-oa:fba-database-expert for
the migration rewrite. Findings reference exact file:line locations — trust them but verify
against current code.

1. B1: make scout/db.py read SUPABASE_URL/SUPABASE_SERVICE_KEY lazily (inside enabled()/
   _headers()) or load_dotenv at module top; same for run_daily.py's
   LOW_TOKEN_WARNING_THRESHOLD. Add a regression test that imports db BEFORE config and
   asserts enabled() still sees .env values.
2. B3 (do this BEFORE anyone applies migrations): rewrite migrations 001/003/004 to use
   plain UNIQUE constraints that PostgREST on_conflict can bind: UNIQUE(asin, found_via) on
   leads, UNIQUE(asin, snapshot_date) on keepa_snapshots (make snapshot_date a plain date
   column the code fills explicitly — S7 — not a generated UTC column),
   UNIQUE(retailer, sku, price_current, seen_date) on deals, and search_log storing
   normalized lowercase brand with UNIQUE(brand). Update db.py to send snapshot_date
   (local date) and lowercase brand. Keep IF NOT EXISTS idempotency and RLS.
3. B2: make db.log_lead degrade honestly pre-migration — strip features_snapshot/
   explanation from the fallback insert payload so a plain insert SUCCEEDS pre-migration,
   and log exactly one warning naming migration 001. Fix the stale comment at
   pipeline.py:178-182.
4. B4: eliminate the legacy leakage path — remove rule_score from model.py FEATURES and
   gate maybe_retrain behind the brain's learning.minLabeledRows (30) using labels.py's
   leakage-safe rows, OR hard-disable retrain with a documented flag until the loops are
   unified. Add a leakage regression test (rule_score in a training row → must be
   excluded/refused).
5. B5: add scout/redact.py — masks values of every *KEY*/*TOKEN*/*WEBHOOK* env var plus
   key=/webhooks/ URL patterns in any string — and apply it to: runs.error_summary writes,
   all digest/system-health Discord content, and every logger/print of exception text in
   pipeline.py, run_daily.py, deals/collect.py, deals/sources/*.py, discord_router.py.
   Move the Best Buy apiKey out of logged URLs where the API allows (or redact). Test:
   fake key in env → exception containing it → assert redacted everywhere it flows.
6. B7: knowledge-rag/upload_to_supabase.py — flip the default to EMBED_PROVIDER=local and
   refuse gemini/openai unless --force-provider is passed, printing WHY (768-dim bge corpus
   compatibility). Update its header comment and API_KEYS.env's warning comment.
7. S1: skip the healthchecks success ping on --dry-run. S2: add a configurable run deadline
   around Keepa wait-for-tokens; on expiry, abort gracefully with an honest digest line and
   runs-row status. S8: thread the actual run id from start_run() through to the digest
   instead of recent_runs(limit=1). S10: use config.AMAZON_SELLER_ID in db.py:123 and align
   amazon_present with the 0.20 share semantics. S11: in db._upsert's error handler,
   distinguish 42P10/constraint-missing (advise migration) from other errors (report as-is,
   redacted).
8. Root .gitignore: add `.env.*` (B6 prep).
9. Run the FULL test suite (every scout/tests/*.py standalone + scout_pro + knowledge-rag
   tests); all green + the new regression tests. Journal entry via fba-session-journal,
   including an explicit list of which review findings were fixed vs deferred.
```

### Prompt R2 — consistency + hygiene (paste after R1 and after migrations are applied)

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and
CODE_REVIEW_2026-07-02.md (this implements its SHOULD-FIX S3-S6, S9, S12-S14 and top NITS).
Use amazon-fba-oa:fba-coder; amazon-fba-oa:fba-brain-updater for brain changes.

1. S3: populate category in keepa_client._normalize() from Keepa's category tree; map to
   the brain's fees.referralRates keys (+ "grocery" detection for the ROI exception);
   record category_source. Test with fixture product payloads.
2. S4: rename non-gate checks in explain_oa from "gates" to "scored checks" in the
   explanation structure AND decide with a test what IS a hard gate (keep the current five
   hard rejects; assert the list). Update the Find page's explain panel vocabulary to match.
3. S5 (brain-updater): move adjustment magnitudes, IP-cliff shape, worst-case-loss bar,
   SCORE_THRESHOLD, TOP_N, and the assumed daily token budget into ai-brain.json
   (scoring.adjustments / scoring.thresholds blocks, source lines); scoring.py/
   propose_updates.py read them with current values as fallbacks. Re-sync hub-data.
4. S6 (brain-updater): add fees.fuelSurcharge (0.035) and fees.prepCost (0.50) to the
   brain; scout config.py AND control-center deal-analyzer.tsx read them (kill the
   hardcoded FUEL_RATE/PREP constants; keep the $0.30 floor reading fees.minReferralFee).
   npm run typecheck && npm run build.
5. S9: tighten the AST guards (catch from-imports and pathlib/os write forms in the
   guarded modules) or correct their docstrings to what they actually check.
6. S12: fix README/guide drift — corpus counts (51/97/1,316), remove pytest instructions
   (document the standalone runner), correct stale test counts; ADD scout/run_all_tests.py
   that discovers and runs every test file across scout/, scout_pro/, knowledge-rag/ and
   prints one aggregate line; reference it in README + CLAUDE_CODE_GUIDE.md.
7. S13: extend run_daily's drift check to every mirrored hub-data file, not just
   ai-brain.json. S14: point scout_pro's notifier at the router env names and add one test;
   document (or align) its stricter hazmat/margin gating as a deliberate difference.
8. Nits (cheap ones only): route pipeline/discord_notify through a public router function
   instead of _resolve_url; dedupe _slug into a shared util; replace ✓✗→★ in console
   output with ASCII; fix search_log tz-naive subtraction; delete competitors.py if truly
   dead (verify no imports); remove the unused SCOUT_DISCORD_WEBHOOK_URL line from
   scout/.env.example (leave .env itself to Mehmet).
9. Full suite green (via the new run_all_tests.py). Journal entry with fixed-vs-deferred
   list.
```

---

# PART 2 — Control-center full review (added 2026-07-03, Cowork Session 27)

The dedicated control-center pass that was rate-limited out of Part 1. Verdict per page at the end.

## BLOCKERS

**CB1. Money and Inventory pages render NOTHING when real data exists.** The populated branch is literally `null`: `app/money/page.tsx:45` (`{m.sales.length ? null : <EmptyState/>}`) and `app/inventory/page.tsx:33,43`. Masked today because the files are empty — but the Log page's inventory capture sets `connected: true` and pushes items, so the FIRST real unit recorded shows a "connected" badge, non-zero KPIs, and a blank panel. Dishonest state, one-line JSX fix each.

**CB2. Two writers, two units for the same `roi` field.** Deal analyzer saves ROI as a fraction (0.35, `deal-analyzer.tsx:291`); the Log page lead form sends percent ("35", `capture-forms.tsx:132`); `/api/capture` stores whichever arrives (`route.ts:177`). Both land in `leads.json`. The existing real lead uses fractions. Future consumers (label builder, pct renders) will silently mix 0.35 with 35. Standardize on fraction at the API boundary (divide by 100 when value > 1.5, or validate).

## SHOULD-FIX

**CS1.** Save-as-lead's context is invisible: `applyLead` (`capture/route.ts:71-79`) persists only product/asin/roi/status to leads.json — the verdict/profit/notes survive only in events.jsonl, and the Leads page renders only product+status (`leads/page.tsx:40-44`). Show roi/notes/asin on the Pipeline page.
**CS2.** `LEAD_STATUS` lacks `review` (`route.ts:17`) while leads.json's pipeline has a review stage — a "review" lead is silently coerced to "idea".
**CS3.** UI lags the brain: zero references anywhere in app/ to `currentVsAvg90PriceCaution` (scout now applies a 1.15× caution the analyzer doesn't), `operations.*`, `policy2026`, `preferredOffers`, `seasonality`, `dealFinder`. Intelligence page readiness rows are hardcoded `false` literals (will go stale silently); Today's guards panel lists only the original 3 guards.
**CS4.** Leads page reads only local leads.json (`lib/data.ts:42-44`); no Supabase read exists anywhere in control-center — scout-written leads will NEVER appear in the UI. Needs a same-origin route reading the Supabase leads table (publishable/read path or server-side service read) once migrations are applied.
**CS5.** Deals page reads only deals.json and its empty-state hint is stale ("needs FMTC/LinkMyDeals key") — the brain's dealFinder block says Slickdeals needs no key and Best Buy needs BESTBUY_API_KEY. Page tells the operator the wrong unblock path. (Full fix = D3's Deals module rebuild.)
**CS6.** Brain data bug that bites in the analyzer: `fees.referralRates.grocery = 0.08` is Amazon's ≤$15 band; above $15 it's 15%. A $40 grocery item overstates profit ~$2.80/unit while ALSO getting the relaxed 25% ROI gate — compounding optimism on the one relaxed category. Fix the brain value to a banded structure or 0.15-with-note; scout reads the same key (check scout's usage when fixing).
**CS7.** No price-band check anywhere for manual deals: Find page advertises "$8–$60" but the analyzer never checks it (scout only encodes the band in the Finder query). The one saved real lead ($142) is outside the band.
**CS8.** Live-file reads aren't `force-dynamic` except /log — a local `next build && next start` freezes "live" hub data at build time with no indication. Add `export const dynamic = "force-dynamic"` to the pages that read live files (or document dev-only).

## NITS

Second copies of worst-case `>2` and margin-health `>=0.2` thresholds in the analyzer (`deal-analyzer.tsx:161,404`) — Settings page's "never a second hardcoded copy" claim is currently false; KnowledgeAsk fallback answers hardcode the 5 core thresholds (third copy); core numeric inputs coerce "" → 0 mid-edit (`deal-analyzer.tsx:243`); BB-share placeholder says "%" instead of "not checked"; dead `getKnowledge()`/wrong `Knowledge` type; "Pipeline" nav label vs "Leads" title; next@15.5.18 + react@18.3.1 is off Next 15's supported matrix (works today; note before next upgrade).

## WHAT'S GOOD

Verdict logic is correct and honest (hard rejects force PASS with reason banner; soft signals only demote BUY→REVIEW; empty optionals are "skipped, never passed" — matching scout semantics deliberately, with the asymmetries documented in comments). Save-as-lead payload matches the capture contract exactly (no dropped fields). Restriction/brand checks mirror scout's word-boundary regexes. No secrets near the browser; all fs reads server-side; honest empty states pervasive; all 14 nav routes exist; tsconfig strict; hub-data bundling is a sound Vercel fallback; knowledge-search and capture routes confirmed solid.

## FUNCTIONING AS INTENDED? (one line per page)

Today YES (guards panel lags) · Log YES (best page) · Find MOSTLY (missing band check + 1.15 caution; grocery rate bug bites here) · Deals YES-as-honest-empty (stale hint) · Leads PARTIAL (drops context; will never see Supabase) · Money NO-once-data-exists (CB1) · Inventory NO-once-data-exists (CB1) · Amazon YES · Ask YES · Knowledge YES · Intelligence YES-as-prose (hardcoded readiness) · Brain YES (no S2 blocks) · Tools YES · Settings YES (false guardrail claim).

### Prompt R3 — control-center fixes (paste after R1/R2)

```
Read CLAUDE.md, the latest AI_COLLABORATION_JOURNAL.md entries, and PART 2 of
CODE_REVIEW_2026-07-02.md — this implements its CB and CS findings. Use
amazon-fba-oa:fba-coder; amazon-fba-oa:fba-brain-updater for the grocery-rate fix;
amazon-fba-oa:fba-designer for any new panel layout.

1. CB1: fix the null populated branches on Money (money/page.tsx:45) and Inventory
   (inventory/page.tsx:33,43) — render real tables/rows from the same data the KPIs use.
2. CB2: standardize lead ROI as a FRACTION at the /api/capture boundary (values > 1.5
   treated as percent and divided by 100, with a validation note), fix the Log form
   placeholder/label to say %, and normalize the one existing leads.json row if needed.
3. CS1+CS2: add "review" to LEAD_STATUS; persist roi/notes/sourceSite through applyLead;
   show asin, roi (pct format), and notes on the Leads page rows.
4. CS3: surface the new brain blocks — add the 1.15x currentVsAvg90PriceCaution to the
   deal analyzer as a soft caution (same demote-to-REVIEW semantics as the other soft
   signals, thresholds from getBrain().guards); render operations.seasonal2026 +
   policy2026 + preferredOffers on Today/Brain pages; replace Intelligence's hardcoded
   readiness literals with values derived from the brain/hub-data.
5. CS6 (brain-updater): fix fees.referralRates.grocery to the banded truth (0.08 <= $15,
   0.15 above) — implement band support in BOTH the analyzer and scout's
   config.referral_rate_for; provenance line; re-sync hub-data.
6. CS7: add the $8-$60 price-band check (criteria.priceMin/priceMax from the brain) to
   the analyzer as a scored check (not a hard reject), matching how Find advertises it.
7. CS8: add export const dynamic = "force-dynamic" to every page reading live hub files.
8. CS4/CS5 minimal now, full later: fix the Deals page empty-state hint text to the real
   unblock path (Slickdeals = no key; Best Buy = BESTBUY_API_KEY); leave the Supabase
   leads/deals reads for the D3 session and say so in a code comment.
9. Nits if cheap: kill the second/third threshold copies by importing from getBrain();
   fix "" -> 0 coercion (allow empty state during edit); BB-share placeholder; remove dead
   getKnowledge.
10. npm run typecheck && npm run build; verify 375px no overflow on Find/Leads/Money/
    Inventory; journal entry (fba-session-journal) with fixed-vs-deferred list.
```

### Mehmet's non-code checklist

1. After R1 lands: apply the corrected migrations 001–004 in the Supabase SQL Editor.
2. `git init` + first commit (or tell Claude Code to do it in R1's session after the
   .gitignore fix).
3. Delete the 82MB `.crdownload`, `Codex Installer.exe`, the `(1)` duplicate transcript;
   decide the fate of the four old dashboard prototypes and `tracker/` vs
   `fba-tracker-site/` (archive one).
4. Still pending from before: rotate the Supabase service_role key; optionally rotate the
   Discord webhooks (they appeared in one more tool output — Session 24's own admission);
   ANTHROPIC_API_KEY; Keepa decision; SP-API registration.
```
