# AI & database upgrade plan — what the videos teach + how we use it

Distilled 2026-06-25 from the AI/sourcing videos you added. For each lesson: what they do, and the **concrete change for our system**.

---

## A) Databases for AI (the part you flagged) — biggest upgrade for us

**What the videos teach**
- *Build the Perfect AI Knowledge Base (Supabase + n8n)* and *Chat With Your Files (Pinecone)*: a real assistant doesn't stuff everything into one file — it stores knowledge in a **vector database** and retrieves by *meaning*. They use **Supabase (pgvector)** or **Pinecone** as the store, **OpenAI `text-embedding-3-small`** for the embeddings, and **n8n** to load documents in **automatically** (a "self-learning" KB that re-embeds new files on a trigger).
- Rule they repeat: a **single PDF is fine only for tiny/simple** knowledge (<10 pages); anything real → a vector store. And **data quality matters** — a messy KB gives wrong answers.

**What we do about it**
1. **Move our RAG from local FAISS → a hosted Supabase pgvector database.** This is exactly what our own RAG-plan PDF specified (Postgres + pgvector), and it fixes the biggest limitation we hit: a self-contained dashboard can't carry the whole 1,209-chunk corpus. With a hosted vector DB, the **deployed Ask queries Supabase live** — no more inlining 600KB, and it scales to thousands of chunks.
2. **Self-updating KB:** wire our existing **daily refresh job** to `ingest.py` → embed new/changed chunks → **upsert into Supabase** (keyed on `source_path` + `content_hash`, which I just made stable). New transcripts/Amazon docs flow in automatically — the "self-learning knowledge base" they demo.
3. We already do the quality basics they stress: section-aware chunking, citations, categories. Keep that.

> I have a **Supabase connector available right now** — I can stand up the project + pgvector table this session if you want (you'd add one embedding API key to fill it).

## B) Using AI for the store (Claude Cowork video — literally us)

**What they do:** the *Claude Cowork* video frames it as **agent-based AI = an employee, not a chatbot** — an *orchestrator* that runs multi-step jobs. Their method: **export your data** (he used a Helium 10 keyword export), hand it to Claude with **context**, and Claude produces a full product plan + financial model. Key point: *"it's all about context"* and Claude is strongest at **data analysis** (even has a native Excel plugin; handles messy data).

**What we do about it**
- This validates our Ask + Rate tools. The upgrade is a **"drop your data" research flow**: let you paste/upload a **SellerAmp or Keepa export** (or a list of ASINs) and have the assistant analyze the batch and rank them — instead of typing one product's numbers at a time into the rater.
- Lean into Claude-for-analysis: a "build my buy list" action that takes a CSV of candidates and returns scored picks with reasons + the FBA-eligibility check.

## C) The Boxem / "New AI Method" sourcing workflow (concrete tactic)

**What they do:** **Boxem** is an AI **auto-ungating checker** — paste an ASIN, it tells you if your account is auto-approved. Their loop: find an **auto-ungated ASIN → Google the ASIN to find a supplier → confirm on SellerAmp + Keepa → check Buy-Box stats / FBM share → monitor stock counts** (decreasing stock = it's selling). *"All you need is SellerAmp + Keepa + Boxem."*

**What we do about it**
- Add this as a named play in the **sourcing playbook**: *reverse-source from an auto-ungated ASIN* + *stock-count monitoring* as a velocity proxy.
- The scout already scores SellerAmp/Keepa criteria + Buy-Box share; add **Boxem** to the tools list (we have it) and, later, a **gating pre-check** (SP-API Listings Restrictions) so the scout only surfaces ASINs you can actually sell.

## D) AI agents: n8n vs Python, APIs, MCPs (architecture)

**What they teach**
- *AI Agents Are Here (8-figure sellers)*: distinguish **chatbot (reactive)** vs **automation (fixed workflow)** vs **agent (has context, like a teammate)**; **keep a human in the loop**; only automate where the **ROI** is worth it.
- *n8n vs Python*: **n8n** for integration-heavy internal tools, prototypes, and team use (visual, low learning curve, tons of pre-built integrations like Postgres/Drive); **Python** when you need to **scale and have flexibility**. Common path: prototype in n8n → move to Python.
- *3 Ways to Make a Custom AI Assistant*: **RAG vs Tools vs Fine-tuning** — RAG for knowledge that changes, tools for actions, fine-tuning for style. (We already chose **RAG**, which is correct for policy/fee data that changes.)

**What we do about it**
- Our **scout is the Python agent** — the right call for the core engine (scales, flexible). Keep it.
- Use **n8n (or our scheduled tasks)** to *prototype* the **deal-sourcing pipeline** (deal-API → score → Discord alert) and the **KB auto-ingest** — fast, visual, easy to maintain.
- **MCP**: expose the scout + RAG as tools the assistant can call (the dashboard already calls Cowork MCP tools). This is how the Ask could *actively* run a rating or a Keepa lookup instead of just answering from text.

---

## Priority order (what's worth doing, highest ROI first)
1. **Supabase pgvector KB** → unlocks live full-corpus Ask in the deployed app + a self-updating database. *(I can start now.)*
2. **"Drop your data" batch rater** → upload SellerAmp/Keepa CSV → scored buy list (the Cowork method).
3. **Gating pre-check (SP-API Listings Restrictions) in the scout** → only show ASINs you can sell (needs your SP-API creds).
4. **Boxem + reverse-source + stock-monitor** added to the sourcing playbook and the scout roadmap.
5. **n8n prototype** of the deal-sourcing + auto-ingest pipelines.

**The one I'd do first:** stand up the Supabase vector database and move the knowledge base onto it — it's the "build a real database for AI" step these videos push, it matches our own plan, and it removes the wall we kept hitting (the corpus is too big to live inside a single dashboard file).
