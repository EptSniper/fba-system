# Update job — keeping the knowledge base current (a coverage program, not a one-time scrape)

Amazon changes rules constantly, so "ingest every document" is an ongoing program:
**complete as observable under approved access, continuously monitored, versioned, and
measurable.** This file defines the refresh cadence and the change-tracking model.

## Cadence
| Frequency | What | Why |
|---|---|---|
| **Daily** | High-risk pages: restricted products, FBA restrictions, dangerous goods, **fees**, account health, listing restrictions | These change without notice and carry the most account risk |
| **Weekly** | General Seller University / "Learn how to sell" educational pages | Slower-moving fundamentals |
| **On change** | Re-chunk only the changed document, re-embed only those chunks, keep the old version | Cheap, auditable updates |

## Change tracking (versioning)
Each refresh re-hashes a document's text (`content_hash`). If it differs from the stored
hash, write a `source_events` row and bump `version`:

```text
source_events
  id
  document_id
  old_hash
  new_hash
  changed_at
  summary_of_change
```

The assistant can then say *"this rule changed on <date>"* and never serves stale policy.

## Compliance guardrails (must stay true)
- **Only approved access.** Public pages may be crawled politely (respect robots.txt,
  identify the agent). Login-gated Seller Central pages are **manual export only** — no
  automated logged-in scraping (Amazon ToS). SP-API data uses your own credentials.
- **No bulk re-utilization** of Amazon content; store what's needed to answer + cite,
  and prefer fetching Amazon's own pages on demand (see `sources/manifest.json`).
- **Crawler stack** (when you wire it): Trafilatura/BeautifulSoup for normal HTML,
  Playwright only for JS-rendered public pages, a PDF parser for PDFs, a transcript
  importer for Seller University videos.

## Running it
```bash
# 1) (re)build the chunk corpus from everything we own
python ingest.py

# 2) embed the chunks into the vector index
python build_index.py build

# 3) ask a question (retrieval + cited answer)
python build_index.py ask "Can I sell this Target deal on Amazon FBA?"
```

## Optional: schedule it
Ask the control center / Claude to *"refresh the Amazon knowledge base every morning"*
to register a daily job that re-runs `ingest.py` + `build_index.py build` and reports any
`source_events` (changed documents) from the last day.
