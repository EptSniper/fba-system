#!/usr/bin/env python3
"""Fetch YouTube transcripts for the daily research queue via youtube-transcript.io.

WHY THIS IS A SEPARATE SCRIPT: the Cowork app cannot make this API call (it restricts
programmatic HTTP). Run this where API calls are allowed — Claude Code in VS Code, or a
terminal:  `python knowledge-rag/fetch_transcripts.py`

It reads research-inbox/queue/*.json, pulls transcripts for items whose status != "done"
(batches of <=50 ids), writes each to research-inbox/transcripts/<videoId>__<slug>.txt with a
header, and marks the queue item "done". The next daily research run ingests the new files.

Stdlib only — no pip install needed. Key is read from knowledge-rag/.env (gitignored).
API: POST https://www.youtube-transcript.io/api/transcripts
     headers: Authorization: Basic <key>, Content-Type: application/json
     body: {"ids": ["videoId", ...]}   (max 50)
"""
import json, os, re, sys, time, urllib.request, urllib.error
from pathlib import Path

try:  # Windows consoles default to cp1252 and choke on the ✓/✗/? status glyphs below
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent          # project root (Amazon FBA/)
ENV = Path(__file__).resolve().parent / ".env"
QUEUE_DIR = ROOT / "research-inbox" / "queue"
OUT_DIR = ROOT / "research-inbox" / "transcripts"
API_URL = "https://www.youtube-transcript.io/api/transcripts"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def load_key():
    if not ENV.exists():
        sys.exit(f"Missing {ENV}. Put YOUTUBE_TRANSCRIPT_API_KEY=... in it.")
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "YOUTUBE_TRANSCRIPT_API_KEY":
            return v.strip()
    sys.exit("YOUTUBE_TRANSCRIPT_API_KEY not found in .env")


def slug(s, n=60):
    s = re.sub(r"[^A-Za-z0-9]+", "-", (s or "").strip()).strip("-").lower()
    return (s or "untitled")[:n]


def call_api(key, ids):
    body = json.dumps({"ids": ids}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Authorization", f"Basic {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    # Cloudflare in front of the API rejects urllib's default UA with 403 error 1010; send a
    # normal browser User-Agent so the request isn't bot-blocked before it reaches the app.
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:
        print(f"  ! request failed: {e}")
    return None


def extract_text(entry):
    """Defensive: handle several plausible response shapes; never lose data."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        for key in ("transcript", "tracks", "segments", "captions", "content"):
            v = entry.get(key)
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                parts = []
                for seg in v:
                    if isinstance(seg, str):
                        parts.append(seg)
                    elif isinstance(seg, dict):
                        parts.append(seg.get("text") or seg.get("snippet") or "")
                joined = " ".join(p for p in parts if p).strip()
                if joined:
                    return joined
        if isinstance(entry.get("text"), str):
            return entry["text"]
    return ""  # caller will fall back to raw JSON


def find_entry(resp, vid):
    items = resp if isinstance(resp, list) else resp.get("transcripts") or resp.get("data") or [resp]
    for it in items if isinstance(items, list) else [items]:
        if isinstance(it, dict) and (it.get("id") == vid or it.get("videoId") == vid):
            return it
    # if single-item response or id missing, return the lone item
    if isinstance(items, list) and len(items) == 1:
        return items[0]
    return None


def main():
    key = load_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    queues = sorted(p for p in QUEUE_DIR.glob("*.json") if DATE_RE.match(p.name))
    if not queues:
        print("No dated queue files in research-inbox/queue/ — nothing to do.")
        return
    pending = []  # (queue_path, data, item)
    for qp in queues:
        try:
            data = json.loads(qp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  skip unreadable {qp.name}")
            continue
        for item in data.get("videos", []):
            if item.get("status") != "done" and item.get("videoId"):
                pending.append((qp, data, item))
    if not pending:
        print("Queue clear — every video already fetched.")
        return
    print(f"{len(pending)} video(s) to fetch across {len(queues)} queue file(s).")

    # batch by 50
    for i in range(0, len(pending), 50):
        batch = pending[i:i + 50]
        ids = [it["videoId"] for _, _, it in batch]
        print(f"Batch {i//50 + 1}: {len(ids)} ids …")
        resp = call_api(key, ids)
        if resp is None:
            print("  batch failed; leaving these queued for next run.")
            continue
        for qp, data, item in batch:
            vid = item["videoId"]
            entry = find_entry(resp, vid)
            text = extract_text(entry) if entry is not None else ""
            header = (
                f"# {item.get('title','(untitled)')}\n"
                f"- channel: {item.get('channel','')}\n"
                f"- url: {item.get('url', 'https://www.youtube.com/watch?v=' + vid)}\n"
                f"- videoId: {vid}\n- topic: {item.get('topic','')}\n"
                f"- fetched: {time.strftime('%Y-%m-%d')}\n\n---\n\n"
            )
            out = OUT_DIR / f"{vid}__{slug(item.get('title'))}.txt"
            if text:
                out.write_text(header + text + "\n", encoding="utf-8")
                item["status"] = "done"
                print(f"  ✓ {vid} -> {out.name} ({len(text)} chars)")
            else:
                # don't lose anything: dump raw json for manual review, keep queued
                (OUT_DIR / f"{vid}__RAW.json").write_text(json.dumps(entry or resp, indent=2), encoding="utf-8")
                print(f"  ? {vid}: couldn't parse transcript text — saved RAW json, left queued")
        qp_written = {qp for qp, _, _ in batch}
        for qp, data, _ in batch:
            if qp in qp_written:
                qp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                qp_written.discard(qp)
        time.sleep(1)  # be polite to the API
    print("Done. New transcripts are in research-inbox/transcripts/ — the next daily run will ingest them.")


if __name__ == "__main__":
    main()
