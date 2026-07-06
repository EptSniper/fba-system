"""
scout/drain_inbox.py — pull the cloud collector's raw-inbox mailbox into the real local Parquet
lake (DATA_ENGINE_PLAN.md hourly-collector era, Session 54).

scout/collect_hourly.py (running hourly in GitHub Actions, no persistent disk) uploads every raw
Keepa response it archives to the Supabase Storage bucket raw-inbox/ (scout/raw_inbox.py) instead
of writing local Parquet. This job — wired into the LOCAL daily housekeeping run
(run_daily.py) — is the other half: list the bucket, download + zstd-decompress + checksum-verify
each object, hand it to datalake.ingest_external_row() (preserving the row's ORIGINAL fetched_at/
content_hash/tokens_consumed/pipeline_context — never re-stamped), flush into the real lake, then
delete the drained objects from the bucket so it doesn't grow unbounded.

Bucket size is reported honestly either way: the digest gets a one-line "raw-inbox: X objects,
Y MB" summary, and a system_health warning fires at >= 700MB (the free tier caps at ~1GB) so
Mehmet notices well before the bucket fills, rather than discovering it when uploads start
failing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import datalake
import raw_inbox

log = logging.getLogger("scout.drain_inbox")

WARN_BYTES = 700 * 1024 * 1024  # 700MB — the honest early-warning line before the ~1GB free cap


def _verify_checksum(row: Dict[str, Any]) -> bool:
    """Re-hash the downloaded row's payload and confirm it matches the content_hash the cloud
    collector stamped at fetch time — catches truncated downloads/decompression corruption
    before it ever reaches the lake. A row missing either field fails closed (not ingested)."""
    payload = row.get("payload")
    stored = row.get("content_hash")
    if payload is None or not stored:
        return False
    return datalake.content_hash(payload) == stored


def drain(limit: int = 5000, run_id: str = "drain-inbox") -> Dict[str, Any]:
    """Drain up to `limit` objects. Returns an honest stats dict. NEVER raises — an
    unreachable bucket or a bad object degrades to a counted failure, never crashes the local
    daily run this is wired into."""
    stats = {"status": "ok", "listed": 0, "ingested": 0, "checksum_failed": 0,
            "download_failed": 0, "deleted": 0, "bucket_bytes_before": 0, "bucket_bytes_after": 0}
    if not raw_inbox._supa() or not raw_inbox._storage_headers().get("apikey"):
        stats["status"] = "disabled"
        stats["reason"] = "no Supabase env configured"
        return stats

    objects = raw_inbox.list_objects(limit=limit)
    stats["listed"] = len(objects)
    stats["bucket_bytes_before"] = sum(o.get("size", 0) for o in objects)
    if not objects:
        stats["bucket_bytes_after"] = 0
        return stats

    datalake.set_run_context(run_id)
    to_delete: List[str] = []
    for obj in objects:
        name = obj["name"]
        row = raw_inbox.download(name)
        if row is None:
            stats["download_failed"] += 1
            continue
        if not _verify_checksum(row):
            log.warning("drain_inbox: checksum mismatch for %s — NOT ingested, NOT deleted "
                       "(left in the bucket for manual review)", name)
            stats["checksum_failed"] += 1
            continue
        if datalake.ingest_external_row(row):
            stats["ingested"] += 1
        # A dedupe hit (already-drained duplicate) still counts as successfully processed —
        # safe to delete either way, since ingest_external_row's dedupe check is authoritative.
        to_delete.append(name)

    flushed = datalake.flush(run_id)
    stats["lake_digest"] = datalake.digest_line()

    if to_delete:
        stats["deleted"] = raw_inbox.delete(to_delete)

    remaining = raw_inbox.list_objects(limit=limit)
    stats["bucket_bytes_after"] = sum(o.get("size", 0) for o in remaining)
    stats["bucket_objects_after"] = len(remaining)
    if stats["bucket_bytes_after"] >= WARN_BYTES:
        stats["bucket_warning"] = (
            f"raw-inbox bucket is {stats['bucket_bytes_after'] / 1e6:.0f}MB — "
            f"approaching the ~1GB free-tier cap; drains may be falling behind uploads")
    return stats


def digest_line(stats: Dict[str, Any]) -> str:
    """One honest ops line for the daily digest."""
    if stats.get("status") == "disabled":
        return f"raw-inbox: disabled ({stats.get('reason')})"
    mb_after = stats.get("bucket_bytes_after", 0) / 1e6
    line = (f"raw-inbox: drained {stats.get('ingested', 0)}/{stats.get('listed', 0)} objects, "
           f"{stats.get('deleted', 0)} deleted, bucket now {mb_after:.1f}MB")
    if stats.get("checksum_failed") or stats.get("download_failed"):
        line += (f" (⚠ {stats.get('checksum_failed', 0)} checksum fail, "
                 f"{stats.get('download_failed', 0)} download fail — left in bucket)")
    return line


if __name__ == "__main__":
    import json
    print(json.dumps(drain(), indent=2, default=str))
