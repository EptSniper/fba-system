# HUMAN_TODO — the irreducible human list

**Created:** 2026-07-03, Claude Code Session 30 (executing Mehmet's scope-limited authorization
from that session's chat message). Ordered by value — do these roughly top to bottom. Every
item here needs a human because it requires an account signup, a payment, an identity/appeal
decision, or a real product-analysis judgment call — nothing here can be automated further.

Exact env var names below always mean: paste the real value into **both**
`API_KEYS.env` (the central registry) and the specific component `.env` file named — never
into any tracked file, the journal, or chat.

---

## 1. ANTHROPIC_API_KEY (~10 min, unlocks the most capability per dollar)

1. Go to `console.anthropic.com` → sign in → **API Keys** → **Create Key**.
2. Add a small starting credit (~$5 is months of runway at this project's usage).
3. Copy the key (starts with `sk-ant-...`).
4. Paste it as `ANTHROPIC_API_KEY=` in **`API_KEYS.env`**, **`scout/.env`**, AND
   **`control-center/.env.local`** (added 2026-07-03 for the /proposals page's "Approve"
   drafting flow, below).

**Unlocks:** `scout/analyst.py`'s LLM second-opinion pass, `scout/reflect.py`'s weekly
reflection, the deal-matcher's pairwise LLM verification (Prompt D2, not yet built but needs
this key to exist first), `MASTERY_PLAN.md`'s M2/M3 chart-reading and judgment-engineering
work, and the control-center's `/proposals` page — approving a brain-proposals.md finding
drafts the exact ai-brain.json edit via Claude immediately; without this key it honestly
records "approved — no draft" instead of drafting anything.

---

## 2. Keepa API plan (~5 min signup, recurring cost — verify the price in-account first)

1. Go to `keepa.com` → **API** → subscribe (verify the current monthly price shown in your
   account before committing — pricing can change).
2. Copy your API key from the Keepa account API page.
3. Paste it as `KEEPA_KEY=` in **both** `API_KEYS.env` and `scout/.env`.

**Unlocks:** live Keepa discovery (`scout/keepa_client.py` — currently code-complete but
untested against a real key), Phase 2 of the System Blueprint, and `MASTERY_PLAN.md`'s M2
self-generated Keepa chart gallery for the chart-reading eval.

---

## 2b. eBay Browse API keys (~10 min, free developer account) — optional, unlocks active-listing comps

Session 55's free signal-type features include `scout/signals/ebay.py`: eBay active-listing
comps (active listing count + median asking price vs. Amazon price) for a candidate's UPC. Fully
optional — until these exist, `ebay.py` degrades to an honest skip (never an error, never
fabricates a comp).

**Naming note (review fix, 2026-07-06):** this was originally called "sold-comps," but the free
Browse API `item_summary/search` endpoint this module calls has no sold/completed-item filter —
it only returns currently ACTIVE listings. True sold-comps require eBay's separate Marketplace
Insights API, which needs its own invitation-gated application approval beyond the free
developer account below — a real future upgrade, not something this key unlocks.

1. Go to `developer.ebay.com` → sign up for a free developer account (no cost, no card needed
   for the sandbox/production Browse API tier used here).
2. Create an application ("keyset") under **Application Keys** → note the **App ID (Client ID)**
   and **Cert ID (Client Secret)** for the PRODUCTION environment (not sandbox — sandbox has no
   real listing data).
3. Paste them as `EBAY_APP_ID=` and `EBAY_CERT_ID=` in **both** `API_KEYS.env` and `scout/.env`.
4. **Verify the current rate limits at signup** (eBay's free-tier Browse API call quota has
   changed over time — check developer.ebay.com's current published limits for your account
   tier before assuming a number from any documentation written before today).
5. If real sold-comps (not just active listings) matter enough to pursue, apply separately for
   Marketplace Insights API access (eBay reviews these applications — no fixed timeline).

**Unlocks:** `ebay_active_listing_count` / `median_active_price_vs_amazon_ratio` features
(`scout/signals/ebay.py`, wired into the same pre-decision feature snapshot as Keepa/Trends/
calendar signals) — currently code-complete but untested against a real key.

---

## 3. Rotate the exposed Supabase service_role key (5 min — overdue)

The current `SUPABASE_SERVICE_KEY` / `SUPABASE_SERVICE_ROLE_KEY` value has been visible in
chat/tool output across earlier sessions. It grants full read/write to the whole database
(bypasses RLS), so it should be rotated even though it has never left this project's own files.

1. Supabase dashboard → project `oa-sourcing-brain` → **Settings → API**.
2. Click **Roll** / **Regenerate** next to the `service_role` key.
3. Immediately update **both** spellings in **both** files (they must match, several scripts
   read one or the other name):
   - `API_KEYS.env`: `SUPABASE_SERVICE_ROLE_KEY=` and `SUPABASE_SERVICE_KEY=`
   - `scout/.env`: `SUPABASE_SERVICE_KEY=`
   - `knowledge-rag/.env`: whichever name it currently uses (check the file — keep in sync)
4. Do this in one sitting — the old key stays valid until you roll it, and everything breaks
   for a few seconds while you update all copies, so have all three files open first.
5. Also update `control-center/.env.local` (`SUPABASE_SERVICE_ROLE_KEY=`) — the control-center
   reads the same key since CC1.

---

## 3b. ~~Apply migration 005~~ — DONE (2026-07-03, applied on your explicit go-ahead)

`decisions.reason_code` and `deal_matches.human_reason` now exist in the live
`oa-sourcing-brain` project (verified via a live query). Nothing left to do here.

<details><summary>Original instructions (kept for reference)</summary>

The 2026-07-03 code review added structured decision reasons (`decisions.reason_code`,
`deal_matches.human_reason`). The SQL is written and additive-only, but applying schema
changes to the live project needs your go-ahead (the auto-mode classifier correctly blocked
an unattended apply). Until it's applied, the Review Queue still works — the code falls back
to writing the reason inside the free-text column and logs a reminder.

1. Supabase dashboard → project `oa-sourcing-brain` → **SQL Editor**.
2. Paste and run the contents of `scout/db/migrations/005_decision_reasons.sql`.
   (Or just tell Claude Code "apply migration 005" in a session — with your explicit
   instruction it can run it through the Supabase connector.)

</details>

---

## 3c. ~~Set control-center operator auth~~ — DONE (2026-07-03, applied on your explicit go-ahead)

`BASIC_AUTH_USER=mehmet` / `BASIC_AUTH_PASS=<24-char random, in API_KEYS.env and
control-center/.env.local>` are set — locally in both env files, and in Vercel's production
environment for `control-center` (verified via `vercel env ls`). The `/api/ops/*` routes and
every page now require these credentials whenever Supabase is also configured. If you ever
want different credentials, generate a new password and update all three places (both .env
files + `vercel env rm/add BASIC_AUTH_PASS production`).

---

## 3d. ~~Apply migration 006~~ — DONE (2026-07-04, applied on your explicit go-ahead)

The `predictions` table now exists in the live `oa-sourcing-brain` project (verified via a
live query — genuinely empty, as expected until the scout runs). Nothing left to do here;
predictions will start accumulating the next time a scoring cycle runs, and can't be SCORED
against live Keepa data until item #2 (`KEEPA_KEY`) exists.

_(Migration 007 — deal_hints/source_http_cache/deals columns for the Top-100 deal watch — was
also applied 2026-07-04 on your "build everything" go-ahead; no action left there either.)_

---

## 3e. GitHub deal-watch cloud runner (~10 min, free — unlocks the nightly 100-source watch)

The Top-100 deal watch (`scout/deals/run_watch.py`) is built, tested, and already runs LOCALLY
(it can be Task-Scheduled like the scout). To move it to the FREE cloud runner so it fires at
9 PM ET every night with your PC off (the design in `TOP100_DEAL_WATCH_PLAN.md` §2), it needs a
GitHub repo with a few Actions secrets:

1. **Create a PRIVATE GitHub repo** (github.com → New repository → Private). If this local git
   repo has no remote yet:
   ```
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin master
   ```
   **Before pushing, confirm no secret files are tracked** — run `git ls-files | grep -Ei "\.env|API_KEYS"`;
   it must print NOTHING (`.gitignore` already excludes them; Claude Code verified this at
   `git init`, but re-check before a first public-ish push).
2. **Add Actions secrets** (repo → Settings → Secrets and variables → Actions → New repository
   secret), each name exactly:
   - `SUPABASE_URL` — `https://cakbzcvtqhdtxfjuxstd.supabase.co`
   - `SUPABASE_SERVICE_KEY` — the service_role key (same value already in `scout/.env`)
   - `DISCORD_WEBHOOK_RETAIL_DEALS` — the #retail-deals webhook (from `scout/.env`)
   - `DISCORD_WEBHOOK_SYSTEM_HEALTH` — the #system-health webhook (for failure alerts)
   - optional: `WOOT_API_KEY`, `BESTBUY_API_KEY`, `HEALTHCHECK_URL_DEALWATCH`
3. **Verify it end-to-end:** repo → Actions tab → "deal-watch" → **Run workflow** (the manual
   `workflow_dispatch` button). It should produce a real digest in #retail-deals and new rows
   in the Supabase `deals`/`deal_hints` tables within a couple minutes. (Or, if you've
   authenticated `gh` locally, tell Claude Code to trigger it — it can run
   `gh workflow run deal-watch`.)

The workflow (`.github/workflows/deal-watch.yml`) is already written and committed — it only
does anything once the repo + secrets exist. Until then the local run is the fallback (Claude
Code registered a "FBA Deal Watch" Task Scheduler entry as that fallback).

---

## 4. Submit the SP-API developer registration

Draft text below — read it, adjust anything that doesn't sound like you, then paste it into
Amazon's Developer Central private-developer application form (Seller Central → Apps & Services
→ Develop Apps → Register as a private developer).

### (a) Use case description

> This is a private, self-authorized integration for a single Amazon seller account (my own),
> used to support online-arbitrage sourcing and inventory decisions. The application reads my
> account's own catalog, pricing, inventory, order, and financial data to: (1) check whether a
> product I'm considering buying and reselling is currently restricted or requires approval
> before I commit money to it (Listings Restrictions API); (2) pull current Buy Box and
> competitive pricing on ASINs I'm evaluating so my profit/ROI estimates use real, current
> numbers instead of stale manual lookups (Product Pricing API); (3) confirm FBA eligibility
> and shipping/dimension requirements before sending inventory in (Fulfillment Inbound /
> Catalog Items); (4) track what I've actually sent to FBA and its current inventory state, so
> my own records stay accurate without manual reconciliation (FBA Inventory API); and (5) pull
> realized settlement/fee data after a sale closes, so I can compare my pre-purchase profit
> estimate against what Amazon actually paid out and improve my future estimates (Finances API).
> There is no multi-seller, SaaS, or third-party-account component — this integration only ever
> reads and acts on my own seller account, and no purchase or listing action happens without my
> explicit manual approval. The end goal is a personal decision-support tool, not a product I
> intend to distribute or sell to other sellers.

### (b) Security controls answers

> All credentials (LWA client ID/secret, refresh token) are stored in a local, gitignored
> environment file on my own machine — never committed to source control, never sent to a
> browser or client-side script, and never logged in plaintext (a redaction layer strips any
> environment variable whose name contains KEY/TOKEN/WEBHOOK from every error message and log
> line before it's written anywhere). All SP-API calls are made server-side over HTTPS directly
> to Amazon's endpoints; nothing proxies through a third party. The refresh token is used only
> to mint short-lived access tokens per the standard LWA flow and is never persisted outside
> that one local environment file. This is a single-user tool with no multi-tenant data
> storage — all pulled data (pricing, inventory, restrictions) is cached locally for my own
> account only, with no data shared, sold, or exposed to any other party. Access is limited to
> the specific roles the use case requires: Product Listing, Pricing, Amazon Fulfillment,
> Inventory and Order Tracking, and Finance and Accounting — no broader scope is requested.

**Roles to select on the form:** Product Listing, Pricing, Amazon Fulfillment, Inventory and
Order Tracking, Finance and Accounting.

---

## 5. Buy a domain for the deals blog (~$10/yr), then submit Impact + CJ

The blog is built and live at **https://deals-blog-five.vercel.app** (5 original guides: reading
a price chart, the 2026 fee changes, cashback/gift-card stacking math, a seasonal buying
calendar, and spotting fake deals — no scraped content, no fake bylines).

1. Buy a domain (~$10-15/yr — Namecheap, Cloudflare, or Porkbun are all fine) for the blog, e.g.
   something like `honestdealguides.com` (check availability/pick your own).
2. In Vercel: project `deals-blog` → **Settings → Domains** → add the domain, follow its DNS
   instructions.
3. A domain gives you a `you@yourdomain.com`-style email (via your registrar's forwarding or a
   free Cloudflare email route) — **this unblocks the Best Buy API signup below**, which
   requires a non-generic email domain.
4. Once the domain is live, submit the two affiliate applications:

### (b) Impact.com partner application (Target / Walmart / Home Depot / Best Buy)

> Honest Deal Guides (https://deals-blog-five.vercel.app, moving to [your new domain]) publishes
> original, independently written shopping guides — currently five articles covering how to
> read a retailer's price-history chart before buying, what changed in Amazon's 2026 fee
> schedule, how cashback and gift-card stacking actually works mathematically, a seasonal
> buying calendar, and how to identify an inflated "was" price. All content is written
> in-house, cites no scraped material, and carries no fabricated author credentials. We are
> applying to feature relevant, in-context links to Target, Walmart, Home Depot, and Best Buy
> as we expand from general shopping-strategy content into specific, current deal roundups
> across those retailers. The site is new (launched 2026-07-03) and growing — we are applying
> early and are happy to start with a smaller/starter tier and demonstrate traffic and content
> quality over time.

### (c) CJ (Commission Junction) publisher application — Walgreens

> Same site and description as above (Honest Deal Guides). We are applying specifically for
> the Walgreens affiliate program to support future content on pharmacy/health-and-household
> deal timing and cashback stacking relevant to that retailer, an extension of our existing
> cashback-stacking guide. The site is new; we can provide the URL above for review and are
> open to a probationary/starter approval tier.

### (d) Best Buy API key request notes

Best Buy's developer API signup requires a business email on a real domain (not a free
webmail address) — this is why the domain purchase above comes first. Once you have
`you@yourdomain.com`:

1. Go to `developer.bestbuy.com` → **Get an API Key**.
2. Fill in the form with your new domain email.
3. Paste the resulting key as `BESTBUY_API_KEY=` in **both** `API_KEYS.env` and `scout/.env`.

**Unlocks:** `scout/deals/sources/bestbuy.py`'s live Best Buy deal collection (currently
code-complete with tests, but has never run against a real key).

---

## 6. healthchecks.io dead-man's-switch (~2 min, free)

`scout/run_daily.py`'s `ping_heartbeat()` already reads `HEALTHCHECK_URL` and no-ops honestly
if it's unset — the empty placeholder is already in both `scout/.env` and `API_KEYS.env`.

1. Go to `healthchecks.io` → free account → **Add Check**.
2. Set its schedule/period to match whatever time your Task Scheduler entry runs
   `run_daily.py` at (e.g. once daily — pick the period that matches your actual cadence).
3. Copy the ping URL shown (looks like `https://hc-ping.com/<uuid>`).
4. Paste it as `HEALTHCHECK_URL=` in **both** `scout/.env` and `API_KEYS.env`.

**Unlocks:** a real alert if the scheduled scout run ever silently stops firing — right now a
dead Task Scheduler entry would fail silently forever.

---

## 7. Rotate the Discord webhooks (optional, at leisure)

These have been visible in chat/tool output across sessions. Risk is low (a webhook URL only
allows *posting* messages into your channels — nobody can read anything with it), but if you
want to close the exposure: Discord → each channel → **Edit Channel → Integrations → Webhooks**
→ regenerate → update the corresponding `DISCORD_WEBHOOK_*` var in both `scout/.env` and
`API_KEYS.env`.

---

## 8. The part no one can automate: run 10-20 real analyses through the Find page

Every model-improvement claim in this project is honestly labeled "architectural, not proven"
until real outcomes exist. The learning loop (`scout_pro`'s calibration, the eventual retrain
path, `fba-lead-capture`'s ground truth) is fueled by **your actual buy/pass decisions on real
products**, not synthetic data. Run 10-20 real candidates through the control-center's Find
page or a manual SellerAmp/Keepa check, save the ones you'd actually consider as leads (the
Leads page / capture form), and — once you buy or pass — record the real outcome. This is the
single highest-leverage thing left that no session, human or AI, can shortcut.

---

## Reference: what Session 30 (Claude Code) executed under this session's explicit authorization

See `AI_COLLABORATION_JOURNAL.md`'s dated entry for the full account. Summary: applied
migrations 001-004 to the live Supabase project (fixing a new bug — `deals.seen_date` couldn't
be a generated column — found only once actually applying to prod), ran a live idempotency
smoke test and cleaned up the synthetic rows, `git init` + verified `.gitignore` coverage +
made the initial commit (no secrets staged, verified explicitly), deleted the named junk files
(hash-verified the duplicate transcript first), archived old prototypes into `archive/`, wired
the `HEALTHCHECK_URL` placeholder into both env files, and built + deployed the `deals-blog/`
app (live at the URL above). Everything requiring a human account, payment, or judgment call is
listed above instead.
