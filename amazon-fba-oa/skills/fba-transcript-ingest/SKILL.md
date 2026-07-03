---
name: fba-transcript-ingest
description: >-
  Turns a raw transcript or document into structured insights and a RAG corpus entry for
  the knowledge base. Use this WHENEVER new source material needs to enter the system —
  "ingest this transcript", "add this video to the knowledge base", "distill insights from
  this", "update insights.md", "add this doc to the RAG corpus", "process the new
  transcripts". It extracts the durable, OA-actionable lessons (not filler), appends them to
  the right knowledge file, and prepares the document for the knowledge-rag pipeline so Ask
  can retrieve it with citations. Use it to keep the corpus and insights in sync. Do NOT use
  it to answer questions from the corpus (that's the control-center Ask / retrieval) or to
  edit ai-brain.json criteria (fba-brain-updater).
---

# FBA Transcript Ingest

The knowledge base is only as good as what enters it and how cleanly. Raw transcripts are mostly filler;
your job is to extract the few durable, *actionable* OA lessons and route both the distilled insight and the
source document into the system the way the existing pipeline expects, so the corpus stays consistent and
citable rather than drifting.

## Understand the pipeline first

Read `../../references/stack-map.md` (the knowledge-rag section) and, if reachable, `knowledge-rag/README.md`
and `knowledge-rag/ingest.py` / `build_index.py`. The corpus lives in `knowledge-rag/corpus/documents.jsonl`
and `chunks.jsonl`; sources are tracked in `knowledge-rag/sources/manifest.json`; distilled human-readable
insights live in `learning-hub/transcripts/insights.md` and the playbooks. Match whatever conventions are
already in those files — don't invent a new schema.

## Two outputs per source

1. **Distilled insight (human):** the actionable takeaways — sourcing tactics, Keepa/SAS rules, fee facts,
   eligibility lessons, thresholds — phrased so they could change a real decision. Drop hype, anecdotes, and
   repetition. Note if a claim is a creator opinion vs verifiable Amazon policy (per the source-of-truth order).
   Append to `insights.md` (or the most relevant playbook) following its existing format.
2. **Corpus entry (machine):** add the document to the RAG corpus via the project's ingestion path so it gets
   chunked and (when the upload step runs) embedded with `BAAI/bge-base-en-v1.5`. Update `sources/manifest.json`.
   Don't fabricate embeddings or chunk counts — run/trigger the real pipeline, or clearly mark the step as pending.

## Honesty about status

Distinguish what you actually ran from what you only prepared. If you appended insights and staged the document
but did not run the embed/upload, say "ingested to corpus JSONL; embedding/upload pending" — never imply the
chunk count or Supabase is updated when it isn't. This drift (README vs live counts) has bitten the project before.

## Output

```
INGESTED — [source title]
- Insights added to: [insights.md / playbook] — N takeaways (list the headlines)
- Corpus: document added to documents.jsonl (id __), ~N chunks [or "chunking pending"]
- Manifest updated: [yes/no]
- Embedding/upload: [done this session / PENDING — command to run]
- Source type: [maintained guidance / practitioner transcript — treat as input, not policy]
```

Offer to log the ingestion via fba-session-journal.
