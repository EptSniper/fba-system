# research-inbox — daily knowledge pipeline

A daily scheduled task (7:00 AM) finds new high-quality learning material on Amazon FBA / online
arbitrage and on building the AI / dashboard / control-center, then stages it here and feeds distilled
insights into the project. YouTube transcripts come in via a small script (because the Cowork environment
can't call the transcript API directly — Claude Code / your terminal can).

## The daily flow

1. **Discover** — the task searches YouTube, blogs, Amazon Help docs, and research papers across the topics
   in `research-manifest.json → topics`, capped at ~10 new items/day, skipping anything already in the
   manifest or in `learning-hub/transcripts/`.
2. **Text sources** (Amazon docs, blogs, articles, papers) → fetched and saved to `text-sources/<date>/`,
   then distilled into `research-insights.md` and staged for the RAG in `corpus-staging.jsonl`.
3. **YouTube** → added to `queue/<date>.json` (video id, title, channel, url, topic, why it matters).
4. **Transcripts** → when `fetch_transcripts.py` drops `.txt` files into `transcripts/`, the next run
   distills them (via the `fba-transcript-ingest` skill), appends insights, stages corpus entries, and
   moves the file to `transcripts/processed/`.
5. **Log** — every run appends to `research-log.md` and writes a `digests/<date>.md` summary, and updates
   `research-manifest.json`.

## Getting YouTube transcripts (the one manual-ish step)

The Cowork app can't make the transcript API call, so run this where it's allowed (Claude Code in VS Code,
or a terminal):

```
python knowledge-rag/fetch_transcripts.py
```

It reads today's `queue/*.json`, calls youtube-transcript.io with the key in `knowledge-rag/.env`, writes
transcripts into `transcripts/`, and marks the queue items done. The next daily run ingests them. You can
also run it on your own schedule (e.g. Windows Task Scheduler) for full automation.

## Staging vs the live corpus (on purpose)

New material is **staged** in `corpus-staging.jsonl` and `research-insights.md` rather than auto-written
into `knowledge-rag/corpus/`. This keeps the live knowledge base clean. To merge, review the staging file
and run the real `knowledge-rag` ingestion/embedding pipeline (needs the Supabase key) — a deliberate,
reviewed step, per the project's honesty rules.

## Folders

- `queue/` — dated YouTube queues for `fetch_transcripts.py`.
- `transcripts/` — drop transcripts here (auto-ingested); `processed/` holds done ones.
- `text-sources/` — saved text of fetched docs/blogs/papers, by date.
- `digests/` — daily summaries.
- `research-manifest.json` — the index + dedup list + topic config.
- `research-log.md` / `research-insights.md` — running log and distilled takeaways.
