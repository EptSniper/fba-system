#!/usr/bin/env python3
"""
backfill.py — build snapshot history (run daily to accumulate longitudinal data).

Windowed features (rank slope/volatility, review velocity, seasonality) only become
meaningful once you have multiple days of snapshots. Schedule this daily (cron /
Task Scheduler) so the feature store deepens over time.

    python backfill.py --finder                 # Product Finder candidates
    python backfill.py --category "home storage" # category best-sellers
"""
from __future__ import annotations

import argparse

import config
import database as db


def main() -> None:
    ap = argparse.ArgumentParser(description="FBA Scout Pro — snapshot backfill")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--finder", action="store_true", help="use Product Finder criteria")
    src.add_argument("--category", metavar="QUERY", help="category best-sellers by search term")
    args = ap.parse_args()

    db.init_db()
    if not config.have_keepa():
        raise SystemExit("No KEEPA_KEY set (paid Keepa subscription required).")

    import ingest_keepa
    api = ingest_keepa.get_client()
    if args.finder:
        asins = ingest_keepa.find_candidates(api=api)
    else:
        asins = ingest_keepa.find_candidates_by_category(args.category, api=api)
    rows = ingest_keepa.snapshot(asins, api=api)
    print(f"Snapshotted {len(rows)} ASINs into {config.DATABASE_URL} "
          f"(+ Parquet lake at {config.DATA_LAKE_DIR}/).")


if __name__ == "__main__":
    main()
