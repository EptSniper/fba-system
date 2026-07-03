# transcripts/ — watch folder

Drop YouTube transcript files here (any `.txt` / `.md`). `fetch_transcripts.py` writes them here
automatically, named `<videoId>__<slug>.txt` with a small header (title, channel, url, date).

The next daily research run ingests every new file here: distills the actionable lessons into
`../research-insights.md`, stages a corpus entry in `../corpus-staging.jsonl`, records it in
`../research-manifest.json`, then moves the file to `processed/`.

You can also drop transcripts you obtained any other way — the run treats them the same.
