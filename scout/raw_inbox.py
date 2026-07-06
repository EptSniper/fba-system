"""
scout/raw_inbox.py — the cloud-side raw-response mailbox (DATA_ENGINE_PLAN.md hourly-collector
era, Session 54).

GitHub Actions runners are ephemeral — nothing written to local disk survives past job end, so
scout/collect_hourly.py (running in .github/workflows/keepa-collect.yml) can't write to the real
Parquet lake (scout/datalake.py, which lives on Mehmet's own machine). Instead, every raw response
the cloud collector archives goes here: one zstd-compressed JSON blob per row, uploaded to the
Supabase Storage bucket `raw-inbox/`, preserving datalake.py's EXACT row schema (source, entity_id,
endpoint, params_hash, fetched_at, tokens_consumed, content_hash, payload, pipeline_context) so the
local scout/drain_inbox.py job can hand each object straight to datalake.ingest_external_row()
without any reshaping — one lake, two collection paths, no parallel schema to drift.

datalake.py's own flush() calls upload_buffered() here automatically when DATALAKE_CLOUD_INBOX=1
is set (keepa-collect.yml sets it) — every archive() call site elsewhere in the codebase (keepa_
client.py, analyst.py, deals/sources/*) is completely UNCHANGED; only the flush destination moves.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

BUCKET = "raw-inbox"
_ZSTD_LEVEL = int(os.getenv("DATALAKE_ZSTD_LEVEL", "12"))
_LIST_PAGE = 100


def enabled() -> bool:
    """Cloud-inbox mode is OFF by default (local runs write straight to the real Parquet lake).
    keepa-collect.yml sets DATALAKE_CLOUD_INBOX=1 since its runner has no persistent disk."""
    return os.environ.get("DATALAKE_CLOUD_INBOX", "0") not in ("0", "false", "False", "")


def _storage_headers() -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _supa() -> str:
    return os.getenv("SUPABASE_URL", "").rstrip("/")


def _ensure_bucket() -> None:
    import requests
    try:
        r = requests.post(f"{_supa()}/storage/v1/bucket", headers=_storage_headers(),
                          json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=15)
        if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
            print(f"[raw_inbox] bucket create: HTTP {r.status_code} (continuing)")
    except Exception as e:
        print(f"[raw_inbox] bucket create failed (continuing): {type(e).__name__}")


def upload_buffered(buffer: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Upload every buffered row (datalake.py's own _buffer, keyed by source) as one
    zstd-compressed JSON object each. Object name: <source>/<fetched_at>-<content_hash
    prefix>.json.zst (sortable by time, unique by hash — collisions just overwrite via
    x-upsert, harmless since it'd be the identical payload). Returns {"uploaded", "bytes",
    "failures"} — the same shape vocabulary datalake.flush()'s local stats use. Never raises;
    an upload failure here means that row's raw data is genuinely lost for this run (counted
    honestly, never silently swallowed)."""
    import requests
    import zstandard
    stats = {"uploaded": 0, "bytes": 0, "failures": 0}
    supa = _supa()
    if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("[raw_inbox] no Supabase env — buffered rows NOT uploaded (would be silently lost)")
        stats["failures"] = sum(len(rows) for rows in buffer.values())
        return stats
    _ensure_bucket()
    cctx = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)
    for source, rows in buffer.items():
        for row in rows:
            try:
                blob = cctx.compress(json.dumps(row, default=str).encode("utf-8"))
                fetched = (row.get("fetched_at") or "").replace(":", "").replace("+", "_")
                chash = (row.get("content_hash") or "nohash")[:16]
                name = f"{source}/{fetched}-{chash}.json.zst"
                r = requests.post(
                    f"{supa}/storage/v1/object/{BUCKET}/{name}",
                    headers={**_storage_headers(), "x-upsert": "true",
                             "Content-Type": "application/zstd"},
                    data=blob, timeout=30,
                )
                r.raise_for_status()
                stats["uploaded"] += 1
                stats["bytes"] += len(blob)
            except Exception as e:
                stats["failures"] += 1
                print(f"[raw_inbox] upload failed ({source}): {type(e).__name__}")
    return stats


def list_objects(limit: int = 5000) -> List[Dict[str, Any]]:
    """Every object currently in raw-inbox/ as {"name": "<source>/<file>", "size": bytes},
    recursively across the per-source sub-folders (Supabase Storage's list endpoint is
    per-prefix, non-recursive, so this lists the top level for folder names first, then lists
    inside each). [] if unavailable or empty. Never raises."""
    import requests
    supa = _supa()
    if not supa or not os.getenv("SUPABASE_SERVICE_KEY"):
        return []
    out: List[Dict[str, Any]] = []
    try:
        r = requests.post(f"{supa}/storage/v1/object/list/{BUCKET}",
                          headers=_storage_headers(),
                          json={"prefix": "", "limit": _LIST_PAGE}, timeout=15)
        r.raise_for_status()
        top = r.json() or []
        prefixes = [e["name"] for e in top if e.get("id") is None]  # folders: id is null
        for prefix in prefixes:
            offset = 0
            while len(out) < limit:
                r = requests.post(
                    f"{supa}/storage/v1/object/list/{BUCKET}",
                    headers=_storage_headers(),
                    json={"prefix": f"{prefix}/", "limit": _LIST_PAGE, "offset": offset},
                    timeout=15,
                )
                r.raise_for_status()
                page = r.json() or []
                if not page:
                    break
                for e in page:
                    if e.get("id"):  # a real object, not a nested folder
                        out.append({"name": f"{prefix}/{e['name']}",
                                   "size": (e.get("metadata") or {}).get("size", 0)})
                offset += len(page)
                if len(page) < _LIST_PAGE:
                    break
    except Exception as e:
        print(f"[raw_inbox] list_objects failed: {type(e).__name__}")
    return out[:limit]


def download(name: str) -> Optional[Dict[str, Any]]:
    """Download + zstd-decompress one object -> the original row dict. None on any failure
    (never raises) — the caller (drain_inbox.py) treats None as 'skip, don't delete yet'."""
    import requests
    import zstandard
    supa = _supa()
    try:
        r = requests.get(f"{supa}/storage/v1/object/{BUCKET}/{name}",
                         headers=_storage_headers(), timeout=30)
        r.raise_for_status()
        raw = zstandard.ZstdDecompressor().decompress(r.content)
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"[raw_inbox] download failed ({name}): {type(e).__name__}")
        return None


def delete(names: List[str]) -> int:
    """Bulk-delete objects after they've been successfully drained into the local lake. Returns
    the count actually requested for deletion (Supabase's bulk endpoint doesn't itemize
    per-object success) — 0 on any failure/empty list. Never raises."""
    import requests
    supa = _supa()
    if not names:
        return 0
    try:
        r = requests.delete(f"{supa}/storage/v1/object/{BUCKET}",
                            headers=_storage_headers(), json={"prefixes": names}, timeout=30)
        r.raise_for_status()
        return len(names)
    except Exception as e:
        print(f"[raw_inbox] delete failed: {type(e).__name__}")
        return 0


def total_bytes() -> int:
    """Sum of every object's size in the bucket — for the digest's bucket-size line + the
    700MB system_health warning. 0 if unavailable/empty. Never raises."""
    return sum(o.get("size", 0) for o in list_objects(limit=100000))
