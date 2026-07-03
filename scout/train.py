#!/usr/bin/env python3
"""
train.py — the feedback-loop CLI.

This is how the scout "learns": you label how past picks actually performed, then
retrain the model on those labels. Two uses:

  1) Add a label (your honest outcome for a pick):
        python train.py --label B0XXXXXXXX --good  --notes "sold ~300/mo, 30% margin"
        python train.py --label B0YYYYYYYY --bad   --notes "fees ate margin, returns high"

  2) Retrain the model from all accumulated labels:
        python train.py
        python train.py --status        # just show how many labels you have

With fewer than config.MIN_LABELS_TO_TRAIN labels (default 20), retraining is
skipped and the scout keeps running on the transparent rule score. There is no
magic — the model only gets better as you add honest labels.
"""
from __future__ import annotations

import argparse

import config
import model as model_mod
import storage


def main() -> None:
    ap = argparse.ArgumentParser(description="Label outcomes and retrain the scout model")
    ap.add_argument("--label", metavar="ASIN", help="ASIN to label with an outcome")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--good", action="store_true", help="mark the pick as a winner (1)")
    g.add_argument("--bad", action="store_true", help="mark the pick as a dud (0)")
    ap.add_argument("--notes", default="", help="free-text note for the outcome")
    ap.add_argument("--status", action="store_true", help="show label count and exit")
    ap.add_argument("--no-train", action="store_true", help="after labeling, don't retrain")
    args = ap.parse_args()

    storage.init_db()

    if args.status:
        n = storage.label_count()
        pending = storage.unlabeled_picks()
        print(f"Labels recorded: {n}")
        print(f"Picks awaiting your label: {len(pending)}")
        for p in pending[:20]:
            print(f"  - {p['asin']}  {str(p.get('title') or '')[:60]!r}  score={p.get('score')}")
        return

    # 1) optional labeling
    if args.label:
        if not (args.good or args.bad):
            ap.error("--label requires --good or --bad")
        label = 1 if args.good else 0
        storage.add_outcome(args.label, label, args.notes)
        print(f"Recorded outcome: {args.label} -> {'GOOD(1)' if label else 'BAD(0)'}"
              + (f'  ({args.notes})' if args.notes else ''))
        if args.no_train:
            return

    # 2) retrain
    if not model_mod.available():
        print("scikit-learn not installed; install it to enable the learning model "
              "(pip install scikit-learn joblib). Scout still runs on the rule score.")
        return

    rows = storage.training_rows()
    report = model_mod.train(rows)
    if report.get("trained"):
        print(f"Trained {report['model']} on {report['n_samples']} labels "
              f"({report['n_good']} good / {report['n_bad']} bad). "
              f"Train accuracy {report['train_accuracy']}. Saved to {report['path']}.")
    else:
        print(f"Did not train: {report.get('reason')}")
        print(f"(You have {storage.label_count()} labels; "
              f"need >= {config.MIN_LABELS_TO_TRAIN} with both classes.)")


if __name__ == "__main__":
    main()
