"""
tuning_report.py — weekly threshold-tuning suggestions (System Blueprint Prompt 3.1).

Compares realized outcomes against each named scored-check/adjustment from the scout's own explain-why
output (scoring.explain_oa(), stored in Supabase leads.explanation) and suggests brain threshold
changes for HUMAN review. Writes to learning-hub/tracking/threshold-tuning-report.md.

NEVER edits ai-brain.json — this module has NO write path to that file (see the guard test in
tests/test_labels_and_reports.py, which greps this file's source for "ai-brain.json" and asserts
it never appears next to an open()/write call). Applying a suggestion is a separate, human-
initiated step via the fba-brain-updater conventions.
"""
from __future__ import annotations

import collections
import datetime as dt
import os
from typing import Any, Dict, List

import db
import labels

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "threshold-tuning-report.md")

# Only flag a pattern with a genuinely meaningful sample — small-n noise is explicitly NOT a
# suggestion (this is exactly the "small-data rule" from SYSTEM_BLUEPRINT.md §4.5).
MIN_SAMPLE_FOR_SUGGESTION = 4
LOSS_RATE_FLAG_THRESHOLD = 0.75


def _outcome_label(lead: Dict[str, Any]):
    outcomes = lead.get("outcomes") or []
    if not outcomes:
        return None
    outcome = sorted(outcomes, key=lambda o: o.get("closed_at") or "", reverse=True)[0]
    return labels.label_from_outcome(outcome)


def check_and_adjustment_stats(leads: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """{check_name: {"wins": n, "losses": n}} across every scored-check + adjustment name that
    appears in a lead's stored explanation, counted only for leads with a realized outcome.
    "check:" entries are scoring.py's SCORED checks (bsr/sales/offers/roi/profit/buybox) — never
    one of the 5 real hard rejects, which never vary per-lead since they're unconditional
    (Code Review 2026-07-02, Finding S4 — this was misleadingly named gate_and_adjustment_stats
    with a "gate:" key prefix, implying these were pass/fail cutoffs)."""
    stats: Dict[str, Dict[str, int]] = collections.defaultdict(lambda: {"wins": 0, "losses": 0})
    for lead in leads:
        label = _outcome_label(lead)
        if label is None:
            continue
        explanation = lead.get("explanation") or {}
        # "gates" is the pre-rename key (explain_oa() called them gates until Code Review
        # 2026-07-02 S4) — rows persisted before the rename must still count toward learning.
        for check in explanation.get("scored_checks") or explanation.get("gates") or []:
            key = f"check:{check.get('name')}={'pass' if check.get('passed') else 'fail'}"
            stats[key]["wins" if label else "losses"] += 1
        for adj in explanation.get("adjustments", []):
            key = f"adjustment:{adj.get('name')}"
            stats[key]["wins" if label else "losses"] += 1
    return stats


def generate_report() -> str:
    leads = db.leads_with_outcomes()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## {now} — threshold-tuning check", ""]

    with_explanation = [l for l in leads if l.get("explanation")]
    with_outcome = [l for l in with_explanation if _outcome_label(l) is not None]

    if not with_outcome:
        lines.append(f"No realized outcomes with a stored explanation yet ({len(leads)} leads "
                     f"total, {len(with_explanation)} carry an explanation). Nothing to analyze — "
                     f"this is expected until real decisions/outcomes accumulate.")
        lines.append("")
        return "\n".join(lines)

    stats = check_and_adjustment_stats(with_outcome)
    lines.append(f"Analyzed {len(with_outcome)} leads with both an explanation and a realized outcome.")
    lines.append("")
    lines.append("| check | wins | losses | sample size |")
    lines.append("|---|---|---|---|")
    suggestions = []
    for key, s in sorted(stats.items()):
        n = s["wins"] + s["losses"]
        lines.append(f"| {key} | {s['wins']} | {s['losses']} | {n} |")
        if n >= MIN_SAMPLE_FOR_SUGGESTION and s["losses"] / n >= LOSS_RATE_FLAG_THRESHOLD:
            suggestions.append(f"- `{key}` lost {s['losses']}/{n} times — consider reviewing this "
                               f"in ai-brain.json (sample size {n}; human judgment call).")
    lines.append("")
    if suggestions:
        lines.append("**Suggestions for human review (ai-brain.json is NOT changed by this report):**")
        lines.extend(suggestions)
    else:
        lines.append(f"No pattern crosses the suggestion bar yet (need >={MIN_SAMPLE_FOR_SUGGESTION} "
                     f"samples at >={LOSS_RATE_FLAG_THRESHOLD*100:.0f}% loss rate on a single check) — "
                     f"everything currently reads as noise, not signal.")
    lines.append("")
    return "\n".join(lines)


def write_report() -> str:
    block = generate_report()
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    header = ("# Threshold-tuning report (append-only)\n\n"
             "Generated by `scout/tuning_report.py` (System Blueprint Prompt 3.1). Suggestions "
             "only — this file NEVER writes to ai-brain.json. To apply a suggestion, tell Claude "
             "'apply this tuning suggestion' and it will make the edit via the fba-brain-updater "
             "conventions (source line, provenance, hub-data re-sync) after you approve it.\n\n")
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(header)
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")
    return block


if __name__ == "__main__":
    print(write_report())
