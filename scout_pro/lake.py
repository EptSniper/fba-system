"""
lake.py — raw-history object store (Parquet).

The paper recommends Parquet in object storage for cheap analytical backfills and
offline training, alongside the operational DB. We append daily snapshot rows to
date-partitioned Parquet. pyarrow/pandas are optional — if unavailable, ingestion
still writes to the DB and simply skips the lake.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import config

try:
    import pandas as pd
    _PANDAS = True
except Exception:  # pragma: no cover
    _PANDAS = False


def available() -> bool:
    return _PANDAS


def write_snapshots(rows: List[Dict[str, Any]], dataset: str = "asin_snapshot_daily") -> str | None:
    """Append rows to data_lake/<dataset>/date=YYYY-MM-DD/part.parquet. Returns path or None."""
    if not _PANDAS or not rows:
        return None
    date = str(rows[0].get("snapshot_date", ""))
    out_dir = os.path.join(config.DATA_LAKE_DIR, dataset, f"date={date}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "part.parquet")
    df = pd.DataFrame(rows)
    # raw JSON column -> string so parquet is happy
    if "raw" in df.columns:
        df["raw"] = df["raw"].apply(lambda v: str(v) if v is not None else None)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception:
        # pyarrow/fastparquet engine missing — degrade gracefully
        return None


def read_dataset(dataset: str = "asin_snapshot_daily"):
    """Read the full partitioned dataset back as a DataFrame (or None)."""
    if not _PANDAS:
        return None
    root = os.path.join(config.DATA_LAKE_DIR, dataset)
    if not os.path.isdir(root):
        return None
    try:
        return pd.read_parquet(root)
    except Exception:
        return None
