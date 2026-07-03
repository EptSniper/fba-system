# AI architecture — the two-database "sourcing brain" (agreed plan)

Synthesis of our plan + the video lessons + ChatGPT's input. This is the canonical spec.

## Principle
The AI sits **on top of** Keepa + SellerAmp + your judgment — it doesn't replace them.
**Keepa = data. SellerAmp = math. AI = reasoning, ranking, explanation, memory, workflow.**
It **recommends, scores, and explains; you approve the buy.** Human in the loop on every real decision.

## Two databases (Supabase = both)
### 1) Knowledge DB (vector / RAG) — "what are the rules?"
Holds text knowledge: transcripts, Amazon docs, the **structured SOPs** (`playbooks/field-sops.md`),
Keepa/SellerAmp rules, ungating, brand/retailer notes. Searched by *meaning* (embeddings).

```sql
-- pgvector
create extension if not exists vector;
create table documents (
  id text primary key, title text, source_type text, category text,
  source_path text, source_url text, content_hash text, version int default 1,
  status text default 'active', last_crawled_at date, created_at timestamptz default now());
create table document_chunks (
  id text primary key, document_id text references documents(id),
  chunk_text text, heading_path text[], chunk_index int, token_count int,
  citation text, category text, embedding vector(768));    -- BAAI/bge-base-en-v1.5
create index on document_chunks using ivfflat (embedding vector_cosine_ops);
```

### 2) Business DB (structured) — "what's happened in our store?"
Holds the real records. This is what makes the AI *remember* and eventually *learn*.

```sql
create table leads (
  id bigserial primary key, asin text, title text, brand text, category text,
  source_store text, source_url text, amazon_url text,
  buy_cost numeric, sell_price numeric, profit numeric, roi numeric,
  monthly_sales int, bsr int, offer_count int, amazon_present bool,
  ip_risk text, pl_risk text, gated_status text,
  score int, verdict text, reason text,                 -- buy / test / wait / pass + why
  found_by text, found_via text, created_at timestamptz default now());
create table keepa_snapshots (
  id bigserial primary key, asin text, captured_at timestamptz default now(),
  buybox_now numeric, buybox_90 numeric, rank_now int, rank_90 int,
  offers_now int, offers_90 int, amazon_share numeric, price_trend text,
  competition_trend text, seasonality text);
create table discounts (
  id bigserial primary key, lead_id bigint references leads(id), retailer text,
  coupon_code text, cashback_rate numeric, giftcard_discount numeric,
  signup_code text, free_ship_threshold numeric, expires date, worked bool);
create table decisions (
  id bigserial primary key, lead_id bigint references leads(id),
  decision text, suggested_qty int, bought_qty int, reason text,
  ai_confidence numeric, human_approved bool, decided_at timestamptz default now());
create table outcomes (                                  -- the learning loop
  id bigserial primary key, lead_id bigint references leads(id),
  bought_qty int, sold_qty int, avg_sale_price numeric, days_to_sell int,
  returns int, actual_profit numeric, actual_roi numeric,
  price_tanked bool, would_rebuy bool, lesson text, closed_at timestamptz);
create table storefronts (
  id bigserial primary key, seller_id text, seller_name text, brands text[],
  notes text, opportunity_score int, last_checked timestamptz);
```

## The agents (build one at a time, in this order)
1. **Deal Analyzer** *(≈ we already have it: the rater/scout)* — ASIN + costs → buy/test/wait/pass + profit/ROI/risk flags + Keepa explanation + suggested qty. **Build first; it prevents bad buys.**
2. **Knowledge agent** *(≈ the dashboard Ask)* — answers from the knowledge DB with citations.
3. **Storefront-stalking agent** — from a good ASIN/seller → pull their ASINs → filter → feed the Deal Analyzer.
4. **Keepa explainer** — turns a chart into plain-English reasoning (demand, offers trend, Amazon presence, seasonality, worst-case price, qty).
5. **Discount-stack agent** — finds every cost-lowering lever and recomputes the deal.
6. **Rebuy agent** — watches past winners (`outcomes`) and pings when the source price is good again. *(Easiest money once you have winners.)*
7. **VA-review agent** — grades VA-submitted leads against the rules (later, when you hire help).
8. **Mistake/competitor agent** — compares new leads to past bad buys; tracks productive storefronts.

## Build phases
1. **Knowledge base** → vector DB (Supabase pgvector) of transcripts + Amazon docs + the structured SOPs. *(We have the corpus; this hosts it.)*
2. **Deal checker** → the rater, writing each check to `leads`. *(We have the rater logic.)*
3. **Lead database** → store every lead, even passes (so the AI can later learn what bad looks like).
4. **Sourcing agents** → storefront, brand-mining, seasonal — one at a time.
5. **Dashboard pages** → leads, deal detail, Keepa analysis, storefront tracker, ungating, inventory, rebuy list, bad buys, VA queue.

## Compliance guardrails (keep these)
- No automated **logged-in Amazon scraping** or bulk re-use (ToS). Use Keepa (licensed) + SP-API (your creds).
- A **retailer-sale agent** must respect each retailer's ToS and **verify product matches** (UPC/size/count/variation/model) — a wrong match loses money. Keep it verification-heavy and low-priority.
- The AI **never auto-buys**. It recommends; you approve.

## Live infrastructure (2026-06-25)
- **Supabase project `oa-sourcing-brain`** (ref `cakbzcvtqhdtxfjuxstd`, us-east-1, free tier) — **created, schema applied, RLS on.** URL `https://cakbzcvtqhdtxfjuxstd.supabase.co`. See `knowledge-rag/SUPABASE-SETUP.md`.
- All 8 tables live + a `match_chunks()` semantic-search function.
- `knowledge-rag/upload_to_supabase.py` embeds locally with `BAAI/bge-base-en-v1.5` and fills the knowledge DB. `scout/db.py` logs leads/decisions/outcomes and is now called by `scout/pipeline.py`; it remains a no-op until the server-side service key is set.

## Status vs. this plan (today)
- ✅ Knowledge corpus (78 docs / 1,224 chunks) + the structured SOPs (`field-sops.md`), uploaded to Supabase and live-query verified on 2026-06-27.
- ✅ Deal Analyzer logic (scout + the dashboard rater) with the criteria/guards/prep/restriction checks.
- ✅ Supabase semantic retrieval (`match_chunks`), local CLI Ask, and the control-center Ask page. The UI calls a server-only Next.js route, embeds locally with `BAAI/bge-base-en-v1.5`, and returns six cited evidence passages with an honest local fallback.
- ✅ **Two-database backend (Supabase) — created + schema'd.**
- ⏳ To activate business memory: add the Supabase service key to the scout's private `.env`. The pipeline is already wired to log every real evaluated lead as `review` or `pass`.

The current Ask route starts a local Python process for each query, so it is reliable for
the local operator dashboard but not yet an efficient hosted architecture. A production
deployment should keep the embedding model warm in a persistent server worker/service.
Retrieval currently returns evidence passages; it deliberately does not invent a synthesized
answer when the corpus or runtime cannot support one.
