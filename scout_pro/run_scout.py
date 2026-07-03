#!/usr/bin/env python3
"""
run_scout.py — discovery CLI.

    python run_scout.py --once                  # ingest, score, alert top-N
    python run_scout.py --once --dry-run        # print alerts, post nothing
    python run_scout.py --once --retrain        # gated retrain, then discover
    python run_scout.py --loop --interval 360   # every 6h (retrains each cycle)

Requires a paid KEEPA_KEY to ingest; DISCORD_WEBHOOK_URL to post.
"""
from __future__ import annotations

import argparse
import logging
import time


def _log(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                        datefmt="%H:%M:%S")


def main() -> None:
    ap = argparse.ArgumentParser(description="FBA Scout Pro — discovery")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=float, default=360, help="minutes between loop cycles")
    ap.add_argument("--retrain", action="store_true", help="gated retrain before discovery")
    ap.add_argument("--dry-run", action="store_true", help="score + print, post/persist nothing")
    ap.add_argument("--no-post", action="store_true", help="record picks but don't post to Discord")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    _log(args.verbose)

    import pipeline
    import retrain

    def cycle():
        if args.retrain:
            print("retrain:", retrain.run())
        return pipeline.run_discovery(post=not args.no_post, dry_run=args.dry_run)

    if args.once:
        try:
            print(cycle())
        except Exception as e:
            logging.getLogger("scout_pro").error("%s", e)
            raise SystemExit(1)
        return

    interval_s = max(60.0, args.interval * 60.0)
    logging.getLogger("scout_pro").info("Looping every %.0f min. Ctrl-C to stop.", args.interval)
    try:
        while True:
            try:
                print(cycle())
            except Exception as e:
                logging.getLogger("scout_pro").exception("cycle failed: %s", e)
            time.sleep(interval_s)
    except KeyboardInterrupt:
        logging.getLogger("scout_pro").info("stopped by user")


if __name__ == "__main__":
    main()
