#!/usr/bin/env python3
"""
run_scout.py — CLI entrypoint for the Product Scout.

Examples:
    python run_scout.py --once                  # one cycle, post to Discord
    python run_scout.py --once --dry-run        # one cycle, print picks, post nothing
    python run_scout.py --once --no-retrain     # skip the retrain step
    python run_scout.py --loop --interval 360   # run every 6 hours

Requires a paid KEEPA_KEY (and DISCORD_WEBHOOK_URL to actually post) in .env.
"""
from __future__ import annotations

import argparse
import logging
import time


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Amazon FBA Product Scout")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="run a single cycle and exit")
    mode.add_argument("--loop", action="store_true", help="run continuously on a schedule")
    ap.add_argument("--interval", type=float, default=360,
                    help="minutes between cycles in --loop mode (default 360 = 6h)")
    ap.add_argument("--threshold", type=float, default=None, help="override score threshold")
    ap.add_argument("--top-n", type=int, default=None, help="override max picks per cycle")
    ap.add_argument("--no-retrain", action="store_true", help="skip the model retrain step")
    ap.add_argument("--dry-run", action="store_true", help="score + print, but post nothing and record nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    _setup_logging(args.verbose)
    # import after logging is configured; pipeline pulls in keepa/sklearn guards
    import pipeline

    def cycle():
        return pipeline.run_once(
            threshold=args.threshold,
            top_n=args.top_n,
            retrain=not args.no_retrain,
            post=not args.dry_run,
            dry_run=args.dry_run,
        )

    if args.once:
        try:
            summary = cycle()
        except Exception as e:
            logging.getLogger("scout").error("%s", e)
            raise SystemExit(1)
        print(summary)
        return

    # --loop
    interval_s = max(60.0, args.interval * 60.0)
    logging.getLogger("scout").info("Looping every %.0f min. Ctrl-C to stop.", args.interval)
    try:
        while True:
            try:
                print(cycle())
            except Exception as e:  # keep the loop alive across transient errors
                logging.getLogger("scout").exception("cycle failed: %s", e)
            time.sleep(interval_s)
    except KeyboardInterrupt:
        logging.getLogger("scout").info("stopped by user")


if __name__ == "__main__":
    main()
