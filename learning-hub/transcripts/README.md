# Video Transcripts — Knowledge Source

This folder is where I drop **video transcripts** (courses, YouTube, mentor calls)
for me *and* the AI we're building to learn from. They expand our depth of
understanding beyond the fundamentals.

## How to add one
1. Save the transcript here as a text/markdown file.
2. Name it: `YYYY-MM-DD_topic_creator.md`
   (e.g. `2026-06-20_online-arbitrage-sourcing_johndoe.md`).
3. Tell me it's here (or just drop it) — I'll process it.

## What I (Claude) do with each transcript
1. **Read it fully.**
2. **Distill** the useful, non-obvious points into [`insights.md`](insights.md),
   with attribution and how it changes our approach.
3. **Update the knowledge base** where warranted — fundamentals, the
   [glossary](../fundamentals/04-glossary.md), the
   [buy/no-buy checklist](../ai-system/product-research-template.md), or the
   scout's scoring criteria.
4. **Log it** in [`../tracking/links-and-assets.md`](../tracking/links-and-assets.md)
   and [`../tracking/session-archive.md`](../tracking/session-archive.md), and add it
   to [`../knowledge-index.json`](../knowledge-index.json).

## Quality rule
Course/YouTube advice is **practitioner signal, not platform fact**. I'll mark
anything that contradicts Amazon's own rules or the verified fees in
[`../../01_research_brief.md`](../../01_research_brief.md), and flag hype or
"guru math." We keep what's useful and testable.

> Status (2026-07-01): **51 transcripts** now in this folder (45 original + 6 merged in today via the
> daily research pipeline — Keepa/reverse-sourcing/storefront-stalking videos). All 51 are in the
> local RAG corpus (`knowledge-rag/corpus/` — 85 documents); the Supabase vector DB the live Ask/
> scout/control-center actually query is still at the prior 78-document/1,224-chunk snapshot pending
> a service-key upload (see `knowledge-rag/upload_to_supabase.py`). `insights.md` currently has
> detailed per-video breakdowns for the first **17** only — the other **34** (the 28 added
> 2026-06-25 plus these 6) are in the corpus for retrieval but not yet distilled into `insights.md`
> itself. That distillation pass is still outstanding.
