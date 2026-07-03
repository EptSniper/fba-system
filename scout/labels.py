"""
labels.py — assemble the training table for the learning loop (System Blueprint Prompt 3.1).

Two REAL capture surfaces feed this, combined by ASIN:
  1. Supabase leads -> decisions -> outcomes (the scout's automated path; db.leads_with_outcomes()).
     Leads written after migration 001 carry a `features_snapshot` (the pre-decision inputs) and
     an `explanation` (the scout's own judgment, for audit only — never a feature).
  2. The local operator ledger (control-center's /api/capture -> learning-hub/data/events.jsonl),
     how the Find page's "Save as lead" and the Log page capture human decisions/outcomes when
     the scout never scored the ASIN. These rows have NO pre-decision feature snapshot (the
     capture form only stores product/asin/roi/status/notes) — they can confirm an ASIN was
     labeled, but cannot themselves train a feature-based model. Kept in the label COUNT for
     honesty, excluded from the TRAINABLE set.

LEAKAGE PREVENTION (non-negotiable, stated twice on purpose): only the fields in
db.PRE_DECISION_FEATURES ever reach `rows[i]["features"]`. The scout's own verdict/score/reason
is NEVER read back as a label — a label comes ONLY from a realized outcome (what actually
happened after a human decision), never from the scout's own prediction about itself.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import db

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
EVENTS_PATH = os.path.join(HERE, "..", "learning-hub", "data", "events.jsonl")
DEFAULT_MIN_LABELED_ROWS = 30


def min_labeled_rows() -> int:
    """ai-brain.json learning.minLabeledRows, single-sourced like every other threshold."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        v = (brain.get("learning") or {}).get("minLabeledRows")
        if isinstance(v, (int, float)):
            return int(v)
    except Exception:
        pass
    return DEFAULT_MIN_LABELED_ROWS


def label_from_outcome(outcome: Dict[str, Any]) -> Optional[bool]:
    """A realized outcome -> a boolean success label, or None if there's nothing to judge yet.
    Prefers an explicit would_rebuy flag (Supabase outcomes schema); falls back to realized
    profitability (profit > 0 and the price didn't tank). Accepts both the Supabase snake_case
    columns (actual_profit, price_tanked) and the local ledger's camelCase (actualProfit)."""
    if outcome.get("would_rebuy") is not None:
        return bool(outcome["would_rebuy"])
    profit = outcome.get("actual_profit")
    if profit is None:
        profit = outcome.get("actualProfit")
    if profit is None:
        return None
    tanked = bool(outcome.get("price_tanked"))
    try:
        return float(profit) > 0 and not tanked
    except (TypeError, ValueError):
        return None


def _from_supabase() -> List[Dict[str, Any]]:
    rows = []
    for lead in db.leads_with_outcomes():
        outcomes = lead.get("outcomes") or []
        if not outcomes:
            continue
        outcome = sorted(outcomes, key=lambda o: o.get("closed_at") or "", reverse=True)[0]
        label = label_from_outcome(outcome)
        if label is None:
            continue
        snapshot = lead.get("features_snapshot") or {}
        # Leakage guard #1: re-filter to the allowlist even though the write side already did —
        # a lead written before migration 001, or by any future code path, might carry extras.
        features = {k: snapshot.get(k) for k in db.PRE_DECISION_FEATURES} if snapshot else None
        rows.append({
            "asin": lead.get("asin"), "source": "supabase",
            "features": features if snapshot else None,
            "label": label,
        })
    return rows


def _read_events() -> List[Dict[str, Any]]:
    if not os.path.exists(EVENTS_PATH):
        return []
    events = []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _match_key(payload: Dict[str, Any]) -> Optional[str]:
    asin = (payload.get("asin") or "").strip().upper()
    if asin:
        return f"asin:{asin}"
    product = (payload.get("product") or "").strip().lower()
    return f"name:{product}" if product else None


def _from_local_ledger() -> List[Dict[str, Any]]:
    """The local ledger has no feature snapshot — see module docstring. `features` is always
    None here; these rows count toward the honest label total but never toward the trainable set."""
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for e in _read_events():
        payload = e.get("payload") or {}
        key = _match_key(payload)
        if not key:
            continue
        by_key.setdefault(key, []).append({"kind": e.get("kind"), "payload": payload, "ts": e.get("ts")})

    rows = []
    for key, entries in by_key.items():
        outcomes = [en for en in entries if en["kind"] == "outcome"]
        if not outcomes:
            continue
        latest = sorted(outcomes, key=lambda en: en.get("ts") or "", reverse=True)[0]["payload"]
        label = label_from_outcome(latest)
        if label is None:
            continue
        rows.append({"asin": latest.get("asin"), "source": "local_ledger", "features": None, "label": label})
    return rows


def assemble_training_rows() -> Dict[str, Any]:
    """The single entry point. Combines both sources, keeps only rows with BOTH a real
    pre-decision feature snapshot AND a realized-outcome label, and enforces the minimum from
    ai-brain.json. Never raises on missing data — an honest empty/refused result instead."""
    all_labeled = _from_supabase() + _from_local_ledger()
    trainable = [r for r in all_labeled if r.get("features")]

    n_pos = sum(1 for r in trainable if r["label"] is True)
    n_neg = sum(1 for r in trainable if r["label"] is False)
    min_rows = min_labeled_rows()

    refused = len(trainable) < min_rows or n_pos == 0 or n_neg == 0
    if len(trainable) < min_rows:
        reason = f"{len(trainable)} trainable labeled rows (< {min_rows} required) — running on the rule score alone"
    elif n_pos == 0 or n_neg == 0:
        reason = (f"{len(trainable)} trainable rows but only one class present "
                 f"({n_pos} positive / {n_neg} negative) — need both to calibrate")
    else:
        reason = f"{len(trainable)} trainable rows ({n_pos} positive / {n_neg} negative) — ready for calibration"

    return {
        "rows": trainable,
        "trainable_count": len(trainable),
        "labeled_count": len(all_labeled),  # includes local-ledger outcomes with no feature snapshot
        "positive": n_pos,
        "negative": n_neg,
        "min_required": min_rows,
        "refused": refused,
        "reason": reason,
    }


if __name__ == "__main__":
    result = assemble_training_rows()
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
