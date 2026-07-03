# Scout memory (Scout Agent Build Plan, Prompt S3)

Per-brand (and, in future, per-category) running notes maintained by `scout/reflect.py` — a
weekly job that reads the week's real decisions/outcomes/analyst-disagreements and rewrites each
affected brand's note: merging in new lessons, deduplicating, and pruning stale entries (capped
at ~60 lines) rather than appending forever. These notes feed back into `scout/analyst.py`'s
input for that brand on future runs, via `reflect.read_memory_note(brand)`.

- `brands/<slug>.md` — one file per brand that's had recent activity. Machine-written by
  `reflect.py`, but plain markdown — read or hand-edit it any time.
- `categories/` — reserved for category-level notes (not yet populated; brand-level notes are
  built first per the build plan's own sequencing).

**Honesty note (Scout Agent Build Plan sec 4):** no published research covers whether this kind
of memory measurably improves analyst accuracy for online arbitrage specifically. `scout/
memory_report.py` is the honest A/B measurement harness — it reports "not enough data yet"
until at least 15 realized-outcome leads exist in BOTH the with-memory and without-memory
groups, and never assumes memory helps just because the code exists.

Every note is regenerated from real Supabase rows only — a post-validator in `reflect.py`
rejects any update that mentions an ASIN not present in those rows, so a note can never
accumulate a fabricated "fact."
