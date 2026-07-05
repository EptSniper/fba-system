"""
scout/ops_report.py — weekly operations KPI report (Scout Agent Build Plan, Prompt S2 sec 3.7).

Computes what Supabase's leads/outcomes data actually supports against ai-brain.json's
operations.kpis targets — honestly, including "not trackable" where no data exists to compute
a KPI (profitPerReviewHour has no source of review-hour logging anywhere in this repo yet).
Writes to learning-hub/tracking/ops-report.md. Read-only — never changes ai-brain.json or any
scout data.
"""
from __future__ import annotations

import datetime as dt
import os
import statistics
from typing import Any, Dict, List, Optional

import config
import db
import predictions

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "ops-report.md")


def _outcome_pairs(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every {lead, outcome} pair across all leads with at least one realized outcome."""
    pairs = []
    for lead in leads:
        for outcome in (lead.get("outcomes") or []):
            pairs.append({"lead": lead, "outcome": outcome})
    return pairs


def sell_through_stats(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    ratios = []
    for pair in pairs:
        o = pair["outcome"]
        bought, sold = o.get("bought_qty"), o.get("sold_qty")
        if isinstance(bought, (int, float)) and bought > 0 and isinstance(sold, (int, float)):
            ratios.append(sold / bought)
    if not ratios:
        return None
    return {"mean": round(statistics.mean(ratios), 2), "n": len(ratios)}


def turns_estimate(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Rough turns/year estimate — 365 / avg days_to_sell on fully-sold lots (sold_qty >=
    bought_qty). A real turns figure needs actual inventory-holding-period data this repo
    doesn't track yet; this is an honest approximation, labeled as such in the report."""
    days = []
    for pair in pairs:
        o = pair["outcome"]
        bought, sold, d = o.get("bought_qty"), o.get("sold_qty"), o.get("days_to_sell")
        if (isinstance(bought, (int, float)) and isinstance(sold, (int, float))
                and bought > 0 and sold >= bought and isinstance(d, (int, float)) and d > 0):
            days.append(d)
    if not days:
        return None
    avg_days = statistics.mean(days)
    return {"turns_per_year": round(365.0 / avg_days, 1), "n": len(days),
            "avg_days_to_sell": round(avg_days, 1)}


def roi_gap_stats(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """mean(estimated_roi - actual_roi) — positive means the pre-buy estimate ran optimistic
    vs what was realized (the published 2026 expectation: ~10-20% realized vs 30%+ estimated)."""
    gaps = []
    for pair in pairs:
        lead, o = pair["lead"], pair["outcome"]
        est, actual = lead.get("roi"), o.get("actual_roi")
        if isinstance(est, (int, float)) and isinstance(actual, (int, float)):
            gaps.append(est - actual)
    if not gaps:
        return None
    return {"mean_gap": round(statistics.mean(gaps), 3), "n": len(gaps)}


def generate_report(fetch_fresh_stats=None) -> str:
    """`fetch_fresh_stats`: optional live-Keepa-refetch callback, forwarded to
    predictions.hit_rate_summary() (Code Review 2026-07-04) — omit it (the default) for an
    honest "unavailable" prediction section until a real KEEPA_KEY exists."""
    leads = db.leads_with_outcomes()
    pairs = _outcome_pairs(leads)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    kpis = config.OPERATIONS.get("kpis", {}) if isinstance(config.OPERATIONS, dict) else {}
    lines = [f"## {now} — weekly ops report", ""]

    if not pairs:
        lines.append(f"No realized outcomes yet ({len(leads)} leads total, 0 with an outcome). "
                     f"Nothing to compute — expected until real buy/sell cycles are recorded.")
        lines.append("")
        lines.append(predictions.hit_rate_summary(fetch_fresh_stats))
        lines.append("")
        return "\n".join(lines)

    st = sell_through_stats(pairs)
    target = kpis.get("sellThrough90Target", 3)
    if st:
        verdict = "meets" if st["mean"] >= target else "below"
        lines.append(f"- **Sell-through** (sold/bought ratio, n={st['n']}): {st['mean']} — "
                     f"{verdict} target {target}.")
    else:
        lines.append("- **Sell-through**: not computable yet (no outcome has both bought_qty "
                     "and sold_qty).")

    turns = turns_estimate(pairs)
    floor = kpis.get("turnsFloor", 6)
    if turns:
        verdict = "meets" if turns["turns_per_year"] >= floor else "below"
        lines.append(f"- **Turns estimate** (365/avg days_to_sell on fully-sold lots, "
                     f"n={turns['n']}): ~{turns['turns_per_year']}/yr (avg "
                     f"{turns['avg_days_to_sell']} days) — {verdict} floor {floor}. "
                     f"Approximation, not real inventory-turn accounting.")
    else:
        lines.append("- **Turns estimate**: not computable yet (need days_to_sell on a "
                     "fully-sold lot).")

    gap = roi_gap_stats(pairs)
    if gap:
        lines.append(f"- **Realized-vs-estimated ROI gap** (n={gap['n']}): "
                     f"{gap['mean_gap']:+.1%} (positive = estimates ran optimistic vs realized).")
    else:
        lines.append("- **Realized-vs-estimated ROI gap**: not computable yet (need actual_roi "
                     "on an outcome).")

    lines.append("- **Profit per review-hour**: NOT TRACKABLE — no review-hour logging exists "
                 "anywhere in this repo yet; this KPI needs a new capture mechanism before it "
                 "can be reported honestly.")
    lines.append(predictions.hit_rate_summary(fetch_fresh_stats))
    lines.append("")
    return "\n".join(lines)


def write_report() -> str:
    block = generate_report()
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    header = ("# Weekly ops report (append-only)\n\n"
             "Generated by `scout/ops_report.py` (Scout Agent Build Plan Prompt S2 sec 3.7), "
             "run weekly from run_daily.py. Read-only — computes KPIs from realized Supabase "
             "outcomes against ai-brain.json's operations.kpis targets; never edits "
             "ai-brain.json or any scout data.\n\n")
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(header)
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")
    return block


if __name__ == "__main__":
    print(write_report())
