# Session Archive

*Chronological capture of every chat between Mehmet and Claude about Amazon.
Newest at top. This is the AI's long-term memory of how we got here — every
session, decision, link, and screenshot is recorded or pointed to from here.*

---

## 2026-06-27 — Codex: reliability audit + zero-cost smarter Ask

**Focus:** Fix the control-center reliability problems Mehmet reported without adding a paid AI API.

- Audited all 12 routes. Confirmed that seven core modules were display-only and Ask returned raw passages rather than a useful answer.
- Added working page actions, removed misleading hover affordances, added runtime health/recovery, and fixed Windows UTF-8 citation failures.
- Ask now retrieves 12 candidates, expands OA concepts, prefers maintained playbooks, deduplicates/reranks, returns concise cited guidance, exposes raw evidence on demand, and caches repeat questions for 15 minutes.
- Added free quality gates: 5 Python unit tests and 5 live fact/citation evaluations; all passed. TypeScript, production build, Python compile, HTTP health/API, and audit also passed; 0 dependency vulnerabilities.
- Post-change in-app browser interaction QA remains pending because tab discovery timed out even though the page/API remained healthy over HTTP.
- Full diagnosis, files, limitations, and next step: [`../../AI_COLLABORATION_JOURNAL.md`](../../AI_COLLABORATION_JOURNAL.md), Codex Session 05.

## 2026-06-27 — Codex: live cited Supabase Ask connected

**Focus:** Continue the control-center build by replacing the local-only Ask experience with real, read-only semantic retrieval from the Supabase knowledge brain.

- Added strict JSON output to `knowledge-rag/ask.py` and a server-only Next.js API route with input validation, a 75-second timeout, bounded output, and no shell execution.
- Rebuilt Ask to search all **1,224 knowledge chunks**, show six full cited passages and honestly labeled semantic-match percentages, preserve the cited local fallback, and provide explicit loading/retry/error states.
- The browser never receives a Supabase service-role key or business-table access. Results are evidence passages, not purchase authorization or fabricated confidence.
- Verified the Python query, real HTTP API, TypeScript, desktop interaction, 375px responsive layout, and a clean browser console. Production build/audit results are recorded in the full journal entry.
- Current limitation: each local request starts Python and loads the embedding model; production hosting should use a persistent warm embedding worker.
- Full rationale, file list, verification, and exact next step: [`../../AI_COLLABORATION_JOURNAL.md`](../../AI_COLLABORATION_JOURNAL.md), Codex Session 04.

## 2026-06-27 — Codex: control center rebuilt + Supabase memory path completed

**Focus:** Build the maintainable OA control center, inspect the live Supabase knowledge brain, add Amazon operating tools, and make the scout’s improvement loop real rather than implied.

- Rebuilt the canonical `control-center/` as a polished Next.js 15 operator dashboard: Today, interactive Find calculator, Amazon Ops launchpad/SP-API roadmap, cited Ask quick-reference, and Scout Intelligence/readiness/guardrail views.
- Live Supabase semantic retrieval was verified at **78 documents / 1,224 chunks** using `BAAI/bge-base-en-v1.5` (768 dimensions). Business tables remain empty until the private service-role key is configured.
- Found that `scout/db.py` existed but the pipeline never called it. `scout/pipeline.py` now logs every real evaluated lead to optional Supabase memory as `review` or `pass`, preserves hard rejects/negative examples, and skips external writes in dry runs.
- Security/quality: Next.js upgraded to 15.5.18, PostCSS pinned, `npm audit` 0 vulnerabilities, TypeScript/build passed, scoring 15/15, new memory tests 2/2, Python compile passed, responsive browser checks passed with no console errors.
- Still not live in this Session 03 snapshot: Keepa, Discord, Supabase business writes, control-center semantic Ask, and SP-API. Session 04 subsequently connected semantic Ask without private credentials. First SP-API priority remains account-specific Listings Restrictions, then Inventory and Finances.
- Full rationale, file list, tests, and limitations: [`../../AI_COLLABORATION_JOURNAL.md`](../../AI_COLLABORATION_JOURNAL.md), Codex Session 03.

## 2026-06-20 — Session 08: Deal-sourcing system + RAG + sourcing transcript + IP Alert

**Focus:** Mehmet sent 2 PDFs (a deal-sourcing system + a RAG ingestion plan), a sourcing-focused transcript, 3 course slides, and asked to focus on deal-finding + add the IP Alert tool + find more tools.

- **Deal-sourcing system (PDF1):** designed [`ai-system/deal-sourcing-system.md`](../ai-system/deal-sourcing-system.md) — deal APIs (FMTC/LinkMyDeals) + BrickSeek/Slickdeals/Tactical Arbitrage → match ASIN + price (Keepa/SP-API) → **reuse the scout's rater** → alert. Added a **Deals** module to the control center (`data/deals.json`, honest empty) and deal tools to `ai-brain.json`. Principle: **source where the deal is TODAY**, stack discounts for a moat.
- **RAG (PDF2):** designed [`ai-system/knowledge-rag-pipeline.md`](../ai-system/knowledge-rag-pipeline.md) (compliance-forward — no Amazon scraping; cite + link back) and scaffolded `knowledge-rag/` to index OUR hub docs (FAISS + bge-small) now; Amazon-help docs gated for later.
- **Sourcing transcript (#17):** added **IP Alert** tool, avoid-order-cancels, list-before-you-buy, new red flags (price spike, seller spike, brand-on-listing, Keepa cliff), deal-first starting point → sourcing playbook + ai-brain.
- **Tools added:** IP Alert, Tactical Arbitrage, BrickSeek, Slickdeals, ProfitPath, BuyBotPro, FMTC/LinkMyDeals, raise.com, Capital One Shopping.
- Logged the 3 slides as an asset; ai-brain ingestion log + this archive updated. Both PDFs are **designed + scaffolded** — going live needs deal-API keys / a RAG run.

## 2026-06-20 — Session 07: Built the control center (Phase 1) + the ingestion loop

**Focus:** Mehmet asked to scaffold Phase 1 of the control center, and to make it so the more he feeds me, the more the control center *and* the finder/rater update.

- Scaffolded a **read-only Next.js 14 + TypeScript + Tailwind** dashboard at `control-center/` (23 files): Command deck, Find, Leads, Money, Inventory, **Brain** pages; dark-OLED data-dense design per ui-ux-pro-max; shadcn-style components; Recharts; lucide icons.
- It reads the **real hub data** server-side and shows **honest empty states** (everything is $0 / "not connected" because that's the truth until the account + Keepa key exist) — the anti-slop proof.
- **Single source of truth = `learning-hub/data/ai-brain.json`** (criteria + brand lists + knowledge + ingestion log). The **scout** (`brands.py._load_from_brain()`) and the **dashboard** (`lib/data.ts`) both read it → feed info, both update. Verified the scout loads 29 friendly / 7 avoid brands from the brain.
- The **Brain page** + **"What you've fed me"** panel make the feedback loop visible (the ingestion log).
- Docs: `ai-system/control-center-blueprint.md` (the how) + `ai-system/ingestion-pipeline.md` (the loop). Seed data: `learning-hub/data/*.json`.
- **Not run through a build** in this environment (45s sandbox limit) — run `npm install && npm run dev`; should go in via a CodeRabbit-reviewed PR.

## 2026-06-20 — Session 06: Knowledge now drives the scout's *finder*

**Focus:** Mehmet's point — "wouldn't knowledge help the scout finder?" Yes. So the brand knowledge is now an input to the search + scoring, not just docs.

- New `scout/brands.py` (seeded from `playbooks/brands-and-sources.md`): **OA_FRIENDLY_BRANDS** + **AVOID_BRANDS** (hard-gated/IP-risky).
- **Search:** the Keepa Product Finder is now **seeded toward known-good brands** (the videos' brand-filter method) — toggle with `SCOUT_USE_BRAND_SEEDS` / `BRAND_SEED_LIMIT`.
- **Scoring:** hard-gated brands (Nike/Adidas/Jordan…) are **hard-rejected**; known-good brands get a **+5 nudge** + ★ tag; brand-generic listings get a risk flag.
- Verified: compiles; Nike → rejected, Jellycat → 100 + ★, no false positives (e.g. "Pineapple Co" not flagged).
- **Next level (offered):** an LLM "judge" that reads the playbooks as context to score candidates — the fullest use of the knowledge base.

## 2026-06-20 — Session 05: Deep-dive on 3 more transcripts (incl. 2 mega-courses)

**Focus:** Mehmet added 3 more transcripts (~296k words total) and asked for the same deep process.

- **Read the 20k-word Sourcing Masterclass (Miles) in full;** worked the operational chapters of the 114k-word "$0→$10K/Month" guide and the 162k-word 12-hour course. (Honest note: the two mega-courses are too large to read every word into memory — I focused on the genuinely new material; the rest overlaps with the 13 already distilled.)
- **New tools:** **Boxem** (bulk auto-ungate checker + listing/shipping) and **cardbear.com** (discounted gift cards).
- **New tactics:** "manufacturing margin" (stack coupons + gift cards + member discounts), the FBA pricing-gap, Keepa graph settings + IP-"cliff" detection, tax-exempt/reseller certs.
- **New artifact:** `playbooks/operations-playbook.md` — account setup (Pro vs Individual, credit-card-not-debit, LLC/EIN, verification call), supplies, FNSKU/4×6 labels, prep, FBA/FBM shipping, what to do when a product doesn't sell (liquidation/removal).
- Added per-video entries 14–16 to `insights.md`; updated sourcing & ungating playbooks, brands-and-sources, glossary, tools, README.
- **Flagged:** the 12-hour course is a **private-label** course — only its account-setup is relevant; PL tactics deliberately excluded. Earnings claims remain coaching-funnel marketing.

## 2026-06-20 — Session 04: Wired the OA criteria into the scout (Discord AI)

**Focus:** Mehmet asked whether the distilled knowledge was actually fed into the scout AI that finds items and posts to Discord. It wasn't (only the docs) — so I wired it in.

- The `scout/` scorer was tuned for **private label**; added a default **OA mode** (`SCOUT_MODE=OA`) that scores on our criteria: BSR ≤200k, ≥50 sales/mo, a seller-count band (3–25), **ROI ≥30%**, **≥$3 profit/unit**, and a **hard reject when Amazon holds the Buy Box**.
- Touched `config.py` (OA criteria + knobs), `scoring.py` (`estimate_oa_profit_roi`, `score_product_oa`, `risk_flags_oa`, `oa_hard_reject`), `keepa_client.py` (OA Product Finder query), `pipeline.py` (OA path + hard gate), `discord_notify.py` (alert now shows BSR / offers / ROI / $-profit).
- Verified: all files compile; OA scoring tested (healthy product = 100, Amazon-Buy-Box = hard-rejected, thin product = 52 with all red flags).
- **Boundary:** to actually search + post live, the scout needs a paid **KEEPA_KEY** + **DISCORD_WEBHOOK_URL** in `.env` (not provided here).
- **Not yet done:** the bigger `scout_pro/` system + SP-API for live finance/inventory — offered as next steps.

## 2026-06-20 — Session 03: Deep-dive on 12 more transcripts

**Focus:** Mehmet added 12 more OA transcripts and asked me to go through *every* one in full detail and extract everything useful.

- Read all 12 (plus re-confirmed #1) **end to end** — SellerAmp tutorials, the Ungate Master Guide, the Q4 guide, the $100-start, the Keepa-Finder session, 3 live sourcing marathons, and 3 student case studies (Peter, King, Josh).
- Wrote a **detailed per-video breakdown** for all 13 in `transcripts/insights.md`.
- Created **3 new playbooks**: `playbooks/sourcing-playbook.md`, `playbooks/ungating-playbook.md`, `playbooks/brands-and-sources.md`.
- Propagated new knowledge into the README map, the buy/no-buy template (unit-buy formula, yellow-line, landed-cost, worst-case), the glossary, the roadmap, and tools.
- **Biggest new techniques captured:** Keepa Product Finder filters (brand + BSR<200k + Amazon-OOS + offers≥4–5); reverse-sourcing rabbit holes; the units-to-buy formula; Keepa "oscillation vs blocky" + "yellow sold-line" reads; coupon/cashback/gift-card stacking; FBM-first + grocery for low capital; break-even-first to build trust; "base hits, go deep on winners"; outsource (VA + prep center) to become a manager.
- **Scout AI:** noted candidate gates/criteria to encode (in `insights.md` → "What we change").
- Flagged all earnings claims as coaching-funnel marketing.

## 2026-06-19 — Session 02: First transcript processed (OA beginners course)

**Focus:** Mehmet dropped a YouTube transcript into the `Amazon Video Transcripts` folder and asked what it covers.

- Read & summarized **"Complete Amazon Online Arbitrage for Beginners Guide 2026 (FREE COURSE)"** by **@wiiThomas** (youtube.com/watch/HJes4bs2d64).
- Copied it into `transcripts/`, distilled it into `transcripts/insights.md`.
- Propagated new knowledge → **glossary** (BOLO, manual/reverse sourcing, cashback tools) and the **buy/no-buy checklist** (4 Keepa red-flag auto-rejects + cashback stacking).
- It strongly validates the **OA-first** plan + the tool stack. Flagged the earnings claims as marketing and a "$150/unit prep" transcript typo (≈ $1.50/unit).
- **Action item:** confirm the author's ROI/BSR cutoffs & cashback tools with the mentor.

## 2026-06-19 — Session 01: Setting up the learning hub

**Present:** Mehmet + Claude · **Focus:** fundamentals + building the capture system

### What Mehmet asked for (his intent, captured)
1. Make this chat his **Amazon learning hub** — track *everything* discussed/sent,
   feed it to the AI being built, find items, automate, and ask him questions.
2. **Track literally everything** — every screenshot, link, and message — saved and
   made **usable for AI**, and eventually a **website / control center**.
3. **Tools we need:** Keepa (industry standard) and **SellerAmp SAS** (product-research
   tool + calculator; "makes sourcing a thousand times more efficient"). Shared a
   screenshot of the startup stack (see assets).
4. **The AI should:** find items, **decide if an item is a good buy** from his research,
   **track finances**, **manage/view inventory** with Amazon, and **learn from this chat**.
   He thinks **SellerAmp SAS** will be useful to the AI — integrate it.
5. **Video transcripts** will be added to the folder as a knowledge source for him and the AI.

### Clarifications he gave
- Experience: **complete beginner**.
- Model: **undecided**, but his **dad's friend has done online arbitrage since 2017**
  and is available to ask.
- First focus: **learn the fundamentals**.
- Tracking style: **full knowledge base**.

### What Claude did this session
- Researched & verified **2026** Amazon fees/plans and SellerAmp details (sources logged).
- Built the **`learning-hub/`**: README, `knowledge-index.json`, 5 fundamentals docs,
  the `ai-system/` spec + buy/no-buy research template, the `tracking/` layer
  (this archive, links/assets, mentor questions, product leads, finances, inventory,
  tools, decisions), `transcripts/` intake, and `assets/`.
- Recommended **starting with Online Arbitrage** (mentor + low capital + OA-shaped tools),
  graduating to private label later (where `01_research_brief.md` + `scout` shine).

### Decisions
- **Start model = Online Arbitrage** (confirm with mentor). → `decisions-and-milestones.md`
- **Tracking = full knowledge base + capture-everything system.**

### Action items
- [ ] Mehmet: book time with the mentor; bring `questions-for-mentor.md`.
- [ ] Mehmet: read fundamentals 01–04.
- [ ] Mehmet: drop video transcripts into `transcripts/` when ready.
- [ ] Claude (ongoing): keep logging every session, link, and screenshot here.

### Links & assets this session
- Screenshot: startup tools & costs → `assets/2026-06-19_startup-tools-stack.md`
- Links: `sell.amazon.com`, `keepa.com`, `selleramp.com` (see `links-and-assets.md`)

---

*(Older sessions will appear below as they happen.)*
