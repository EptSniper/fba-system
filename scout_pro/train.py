#!/usr/bin/env python3
"""
train.py — labeling + gated retraining CLI (the feedback loop).

Record an outcome (strong label) for a pick, then retrain:
    python train.py --label B0XXXXXXXX --decision approve  --notes "sold ~300/mo @30%"
    python train.py --label B0YYYYYYYY --decision reject    --notes "fees ate margin"
    python train.py --label B0ZZZZZZZZ --decision compliance_issue
    python train.py --realized B0XXXXXXXX --margin 0.31 --units 420 --fo 0.8 --returns 0.05

Retrain (gated champion/challenger) from accumulated labels:
    python train.py --retrain
    python train.py --status

Decisions: approve | reject | defer | supplier_issue | compliance_issue | margin_issue | false_positive
"""
from __future__ import annotations

import argparse
import json

import config
import database as db
import labels


def main() -> None:
    ap = argparse.ArgumentParser(description="FBA Scout Pro — labels + retrain")
    ap.add_argument("--label", metavar="ASIN", help="ASIN to label via an analyst decision")
    ap.add_argument("--decision", help="analyst decision (see module docstring)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--realized", metavar="ASIN", help="ASIN to label with realized account data")
    ap.add_argument("--margin", type=float, help="realized contribution margin fraction (e.g. 0.31)")
    ap.add_argument("--units", type=int, help="realized units sold over the horizon")
    ap.add_argument("--fo", type=float, help="featured-offer share (0-1)")
    ap.add_argument("--returns", type=float, help="return rate (0-1)")
    ap.add_argument("--compliance", action="store_true", help="mark realized row compliance-blocked")
    ap.add_argument("--retrain", action="store_true", help="gated champion/challenger retrain")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    db.init_db()

    if args.status:
        rows = labels.training_rows()
        strong = sum(1 for r in rows if r.get("weight", 1) >= 3)
        print(f"Training rows: {len(rows)} ({strong} strong / {len(rows)-strong} weak). "
              f"Need >= {config.MIN_LABELS_TO_TRAIN} with both classes to train.")
        champ = db.registry_champion("classifier")
        if champ:
            print(f"Champion classifier: v{champ['version']} "
                  f"PR-AUC={champ.get('metrics',{}).get('pr_auc_cv')}")
        else:
            print("No champion yet — discovery runs on the rule score.")
        return

    if args.label:
        if not args.decision:
            ap.error("--label requires --decision")
        print(labels.record_outcome(args.label, decision=args.decision, notes=args.notes))

    if args.realized:
        realized = {"contribution_margin": args.margin, "units_sold": args.units,
                    "featured_offer_share": args.fo, "return_rate": args.returns,
                    "compliance_flag": args.compliance}
        print(labels.record_outcome(args.realized, realized=realized))

    if args.retrain or args.label or args.realized:
        import retrain
        print(json.dumps(retrain.run(force=True), indent=2, default=str))


if __name__ == "__main__":
    main()
