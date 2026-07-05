"""
scout/datalake.py — the raw data lake (DATA_ENGINE_PLAN.md Prompt V0).

THE PRINCIPLE: archive every EXTERNAL response RAW at the moment we receive it (ephemeral data
is unrecoverable; Keepa data is re-fetchable but re-costs precious tokens), and store NOTHING
derivable. Features/scores/verdicts live in Supabase ONLY — the lake holds raw payloads +
provenance pointers, so every derived table is regenerable from it. One copy of truth per
layer.

Storage: append-only Parquet, zstd-compressed, Hive-partitioned
<root>/<source>/date=YYYY-MM-DD/part-*.parquet. Batch writes per run (one file per source per
run, NEVER per row). A sqlite dedupe manifest keyed (source, entity_id, endpoint) skips
re-storing an identical payload (its last_seen just updates — cheap); a changed payload appends.

CRITICAL contract: archiving MUST NEVER break the pipeline. Every public entry point swallows
its own errors and counts them in telemetry — a broken lake writer loses data, it never loses a
scout run.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
from typing import Any, Dict, List, Optional

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover - pyarrow optional; archiving no-ops without it
    pa = None
    pq = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = r"C:\fba-data-lake"  # OUTSIDE the OneDrive-synced project on purpose (see below)
_ZSTD_LEVEL = int(os.getenv("DATALAKE_ZSTD_LEVEL", "12"))
# HTML clearance bodies are big + low-value; only archive them when the parse was poor or the
# page changed (env-tunable). Everything else archives unconditionally.
_HTML_CONF_THRESHOLD = float(os.getenv("DATALAKE_HTML_CONF_THRESHOLD", "0.5"))

_lock = threading.Lock()
# buffered rows keyed by source (flushed one-file-per-source per run)
_buffer: Dict[str, List[Dict[str, Any]]] = {}
_stats = {"buffered": 0, "deduped": 0, "written": 0, "bytes": 0, "failures": 0}
# the current run's id, set once per run by the pipeline so boundary call sites (keepa_client,
# deals/sources, analyst) don't each have to thread run_id through their signatures.
_run_context: Dict[str, Any] = {"run_id": None}


def enabled() -> bool:
    """Archiving is ON by default in production (a silent no-op would be exactly the data loss
    V0 exists to prevent). The test suite sets DATALAKE_ENABLED=0 (scout/tests/conftest.py) so
    unit tests never touch the real lake on disk; datalake's own tests re-enable it against a
    temp dir. Read live (not import-time-cached) so conftest can flip it before collection."""
    return os.environ.get("DATALAKE_ENABLED", "1").lower() not in ("0", "false", "no", "")


def set_run_context(run_id: Optional[Any]) -> None:
    """Called once per run by the pipeline; archive() uses it as the default run_id."""
    with _lock:
        _run_context["run_id"] = run_id


def lake_dir() -> str:
    return os.environ.get("DATA_LAKE_DIR", DEFAULT_ROOT)


def _is_inside_onedrive_project(root: str) -> bool:
    """True if `root` is inside this OneDrive-synced project tree — a foot-gun (the lake grows
    to many GB and would sync-thrash + burn cloud storage). Compared case-insensitively on the
    real, absolute paths."""
    try:
        root_abs = os.path.realpath(root).lower()
        project_abs = os.path.realpath(os.path.join(HERE, "..")).lower()
        return root_abs == project_abs or root_abs.startswith(project_abs + os.sep)
    except Exception:
        return False


def _warn_if_onedrive(root: str) -> None:
    if _is_inside_onedrive_project(root):
        print("[datalake] *** WARNING: DATA_LAKE_DIR is INSIDE the OneDrive project folder "
              f"({root}). The lake grows to many GB and will sync-thrash your cloud + disk. "
              r"Point DATA_LAKE_DIR at a local path OUTSIDE OneDrive (e.g. C:\fba-data-lake).")


def content_hash(payload: Any) -> str:
    return hashlib.sha256(_as_text(payload).encode("utf-8", "replace")).hexdigest()


def params_hash(params: Optional[Any]) -> str:
    if params is None:
        return ""
    try:
        return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]
    except Exception:
        return ""


def _as_text(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode("utf-8", "replace")
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, default=str, sort_keys=True)
    except Exception:
        return str(payload)


# --- provenance, computed once per process ---------------------------------
def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                              capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _brain_hash() -> str:
    try:
        with open(os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return "unknown"


_GIT_SHA = _git_sha()
_BRAIN_HASH = _brain_hash()


# --- dedupe manifest (sqlite) ----------------------------------------------
def _manifest_path() -> str:
    return os.path.join(lake_dir(), "_manifest.sqlite")


_manifest_lock = threading.Lock()
_manifest_cache: Dict[str, Any] = {"path": None, "conn": None}


def _manifest_conn() -> sqlite3.Connection:
    """Cached per-process connection (reopened if DATA_LAKE_DIR changes — tests repoint it).
    A fresh open + CREATE TABLE per archive() call cost a full sqlite connection lifecycle per
    ASIN on a 200-ASIN enrich (Review 2026-07-05). check_same_thread=False is safe because every
    use is serialized under _manifest_lock."""
    path = _manifest_path()
    if _manifest_cache["conn"] is None or _manifest_cache["path"] != path:
        if _manifest_cache["conn"] is not None:
            try:
                _manifest_cache["conn"].close()
            except Exception:
                pass
        os.makedirs(lake_dir(), exist_ok=True)
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS manifest ("
            "  source TEXT, entity_id TEXT, endpoint TEXT, content_hash TEXT, last_seen TEXT,"
            "  PRIMARY KEY (source, entity_id, endpoint))"
        )
        _manifest_cache["path"] = path
        _manifest_cache["conn"] = conn
    return _manifest_cache["conn"]


def _is_duplicate_and_touch(source: str, entity_id: str, endpoint: str, chash: str) -> bool:
    """True if (source, entity_id, endpoint) already holds this EXACT content_hash — in which
    case we only bump last_seen (no re-store). A new/changed hash returns False and records the
    new hash. Any manifest error degrades to 'not a duplicate' (store it — never lose data over
    a manifest hiccup)."""
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        with _manifest_lock:
            conn = _manifest_conn()
            row = conn.execute(
                "SELECT content_hash FROM manifest WHERE source=? AND entity_id=? AND endpoint=?",
                (source, entity_id, endpoint),
            ).fetchone()
            if row and row[0] == chash:
                conn.execute(
                    "UPDATE manifest SET last_seen=? WHERE source=? AND entity_id=? AND endpoint=?",
                    (now, source, entity_id, endpoint),
                )
                conn.commit()
                return True
            conn.execute(
                "INSERT INTO manifest (source, entity_id, endpoint, content_hash, last_seen) "
                "VALUES (?,?,?,?,?) ON CONFLICT(source, entity_id, endpoint) "
                "DO UPDATE SET content_hash=excluded.content_hash, last_seen=excluded.last_seen",
                (source, entity_id, endpoint, chash, now),
            )
            conn.commit()
            return False
    except Exception as e:
        # drop the cached conn — it may be the broken piece (deleted temp dir, disk error)
        with _manifest_lock:
            _manifest_cache["conn"] = None
        print(f"[datalake] manifest check failed ({source}/{entity_id}): {e}")
        return False


# --- the one-line archive helper -------------------------------------------
def archive(source: str, entity_id: Optional[str], endpoint: str, payload: Any,
            tokens_consumed: Optional[int] = None, params: Optional[Any] = None,
            run_id: Optional[Any] = None) -> bool:
    """Buffer one raw external response for the current run's batch flush. Returns True if newly
    buffered, False if it was a dedupe hit / an error occurred. NEVER raises — a lake failure is
    counted (telemetry()['failures']) and swallowed, so it can't break a scout run."""
    if pa is None or not enabled():
        return False
    if run_id is None:
        run_id = _run_context.get("run_id")
    try:
        text = _as_text(payload)
        chash = content_hash(text)
        eid = str(entity_id) if entity_id is not None else ""
        if _is_duplicate_and_touch(source, eid, endpoint, chash):
            with _lock:
                _stats["deduped"] += 1
            return False
        row = {
            "source": source, "entity_id": eid, "endpoint": endpoint,
            "params_hash": params_hash(params),
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "tokens_consumed": int(tokens_consumed) if tokens_consumed is not None else None,
            "content_hash": chash, "payload": text,
            "pipeline_context": json.dumps(
                {"run_id": run_id, "git_sha": _GIT_SHA, "brain_hash": _BRAIN_HASH}, default=str),
        }
        with _lock:
            _buffer.setdefault(source, []).append(row)
            _stats["buffered"] += 1
        return True
    except Exception as e:
        with _lock:
            _stats["failures"] += 1
        print(f"[datalake] archive failed ({source}/{entity_id}): {e}")
        return False


def archive_clearance_html(url: str, body: str, extraction_confidence: float,
                           changed: Optional[bool] = None,
                           run_id: Optional[Any] = None) -> bool:
    """Clearance-page HTML is big and low-value — archive its (raw) body ONLY when the parse was
    poor (below DATALAKE_HTML_CONF_THRESHOLD) or the page changed. `changed` is tri-state:
    False = caller KNOWS it's unchanged (skip when the parse was clean); None = unknown — the
    dedupe manifest is the change detector (an identical body dedupes to a last_seen bump, a
    changed body archives). The previous bool-only signature let the one real call site pass a
    constant True, making the confidence gate dead code (Review 2026-07-05)."""
    if not enabled():
        return False
    if changed is False and extraction_confidence >= _HTML_CONF_THRESHOLD:
        return False
    return archive("clearance_html", url, "GET", body, run_id=run_id)


def flush(run_id: Optional[Any] = None) -> Dict[str, Any]:
    """Write all buffered rows — one Parquet file per source — into today's partition, then
    clear the buffer. Returns a stats dict for the digest. NEVER raises (a flush failure is
    counted, the buffer is preserved for a retry, and the run continues)."""
    if pa is None:
        return dict(_stats)
    root = lake_dir()
    _warn_if_onedrive(root)
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        sources = list(_buffer.items())
        _buffer.clear()
    for source, rows in sources:
        if not rows:
            continue
        try:
            partition = os.path.join(root, source, f"date={today}")
            os.makedirs(partition, exist_ok=True)
            # part filename is unique per flush via a content hash of the batch (no clock needed
            # for uniqueness beyond the run); collisions across runs on the same day append new files.
            part_id = hashlib.sha256(
                (str(run_id) + rows[0]["fetched_at"] + str(len(rows))).encode()).hexdigest()[:12]
            path = os.path.join(partition, f"part-{part_id}.parquet")
            table = pa.Table.from_pylist(rows)
            pq.write_table(table, path, compression="zstd", compression_level=_ZSTD_LEVEL)
            with _lock:
                _stats["written"] += len(rows)
                _stats["bytes"] += os.path.getsize(path)
        except Exception as e:
            with _lock:
                _stats["failures"] += 1
                _buffer.setdefault(source, []).extend(rows)  # preserve for retry
            print(f"[datalake] flush failed for source {source}: {e}")
    return dict(_stats)


def telemetry() -> Dict[str, Any]:
    with _lock:
        return dict(_stats)


def reset_stats() -> None:
    with _lock:
        for k in _stats:
            _stats[k] = 0
        _buffer.clear()


def total_size_bytes() -> int:
    """Total bytes on disk under the lake root (for the 'total Y GB' digest line). 0 if the lake
    doesn't exist yet."""
    root = lake_dir()
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def digest_line() -> str:
    """One honest ops line for the daily digest: rows/bytes written this run, running total,
    dedupe rate."""
    s = telemetry()
    seen = s["buffered"] + s["deduped"]
    dedupe_rate = (100 * s["deduped"] / seen) if seen else 0
    total_gb = total_size_bytes() / 1e9
    return (f"lake: +{s['written']} rows, +{s['bytes'] / 1e6:.1f} MB, total {total_gb:.2f} GB, "
            f"dedupe {dedupe_rate:.0f}%" + (f", ⚠{s['failures']} archive failures" if s["failures"] else ""))


def integrity_check(sample_per_partition: int = 1) -> Dict[str, Any]:
    """Weekly read-back check (called from run_daily's Monday branch): re-open a sample of
    Parquet files under each source, re-hash each row's payload, and confirm it matches the
    stored content_hash. Returns {checked, ok, mismatches: [...], unreadable: [...]}. Never
    raises."""
    root = lake_dir()
    result = {"checked": 0, "ok": 0, "mismatches": [], "unreadable": []}
    if pa is None or not os.path.isdir(root):
        return result
    for source in os.listdir(root):
        src_dir = os.path.join(root, source)
        if not os.path.isdir(src_dir):
            continue
        for dirpath, _dirs, files in os.walk(src_dir):
            parquet_files = [f for f in files if f.endswith(".parquet")]
            for fname in parquet_files[:sample_per_partition]:
                fpath = os.path.join(dirpath, fname)
                try:
                    table = pq.read_table(fpath, columns=["payload", "content_hash"])
                    for payload, stored in zip(table.column("payload").to_pylist(),
                                               table.column("content_hash").to_pylist()):
                        result["checked"] += 1
                        if content_hash(payload) == stored:
                            result["ok"] += 1
                        else:
                            result["mismatches"].append(fpath)
                            break
                except Exception as e:
                    result["unreadable"].append(f"{fpath}: {e}")
    return result
