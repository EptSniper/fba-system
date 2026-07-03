"""
propose_updates.py — continuous self-improvement: PROPOSALS only, applied ONLY by a human
(System Blueprint Prompt G5).

Run automatically at the end of every daily runner cycle (run_daily.py). Generates three kinds
of proposals and appends them, dated, to learning-hub/tracking/brain-proposals.md:

  (a) outcome-driven — realized wins/losses per gate/adjustment (reuses tuning_report.py's
      stats function so the logic can't drift between the two reports), but reports EVERY
      finding with an honest confidence label instead of suppressing small samples — "too
      small to act" is itself the honest finding at n=1-3, per the example in the prompt.
  (b) data-driven — run telemetry vs the brain: dead/toothless gates (100% reject rate at a
      real sample size), brands repeatedly IP-cliff-flagged, Keepa token-cost drift vs the
      System Blueprint's assumed ~7,500/day budget.
  (c) knowledge-driven — best-effort: run a knowledge-rag check for current OA thresholds and
      point at it for manual comparison. Free-text answers are NOT auto-diffed against
      ai-brain.json — judged too unreliable to propose a specific value change from directly.
      Degrades honestly to "unavailable this run" on any failure (missing deps, timeout, corpus
      not built, etc.) rather than breaking the rest of the proposal run.

NEVER writes ai-brain.json — this script has no open()/write path to that file (see the
AST-based guard test in tests/test_propose_updates.py, matching tuning_report.py's own guard).
Applying a proposal is a separate, human-initiated fba-brain-updater step.

Also posts a SHORT heads-up (count + top finding, not the whole report) to Discord's
"brain_proposals" stream via discord_router.py (Cowork Session 23) — wired into
write_report_with_count() so a single run computes the proposals once and both writes the
report and notifies. A notify failure never blocks the report write.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from typing import Any, Dict, List

import db
import discord_router
import tuning_report

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "tracking", "brain-proposals.md")
ASK_PY = os.path.join(HERE, "..", "knowledge-rag", "ask.py")

# System Blueprint §3's assumed daily budget — flag if actual usage drifts meaningfully.
ASSUMED_DAILY_TOKENS = 7500
TOKEN_DRIFT_FLAG_RATIO = 0.5  # flag if actual is <50% or >150% of assumed


def confidence_label(n: int) -> str:
    if n < 4:
        return "too small to act"
    if n < 10:
        return "worth reviewing"
    return "strong signal"


def outcome_driven_proposals() -> List[Dict[str, Any]]:
    """Every gate/adjustment with at least one realized outcome — reported honestly regardless
    of sample size (small samples ARE the finding at this stage, per SYSTEM_BLUEPRINT.md §4.5)."""
    leads = db.leads_with_outcomes()
    with_explanation = [l for l in leads if l.get("explanation")]
    stats = tuning_report.gate_and_adjustment_stats(with_explanation)
    proposals = []
    for key, s in sorted(stats.items()):
        n = s["wins"] + s["losses"]
        if n == 0:
            continue
        loss_rate = s["losses"] / n
        proposals.append({
            "kind": "outcome-driven",
            "finding": f"`{key}` — {s['losses']}/{n} realized losses ({loss_rate*100:.0f}%)",
            "sample_size": n, "confidence": confidence_label(n), "ai_brain_key": None,
        })
    return proposals


def data_driven_proposals() -> List[Dict[str, Any]]:
    """Dead/toothless gates + repeated IP-cliff brands + Keepa token-cost drift, from recent
    run telemetry and stored explanations. Honestly reports 'no data yet' where nothing exists."""
    proposals = []
    runs = db.recent_runs(limit=14)
    if not runs:
        proposals.append({
            "kind": "data-driven",
            "finding": "No run telemetry yet (runs table empty or unavailable) — nothing to "
                      "compare against the assumed Keepa token budget.",
            "sample_size": 0, "confidence": "no data", "ai_brain_key": None,
        })
    else:
        consumed = [r.get("tokens_consumed") for r in runs if isinstance(r.get("tokens_consumed"), (int, float))]
        if consumed:
            avg = sum(consumed) / len(consumed)
            lo, hi = ASSUMED_DAILY_TOKENS * TOKEN_DRIFT_FLAG_RATIO, ASSUMED_DAILY_TOKENS * (2 - TOKEN_DRIFT_FLAG_RATIO)
            if avg < lo or avg > hi:
                proposals.append({
                    "kind": "data-driven",
                    "finding": f"Average Keepa token usage over {len(consumed)} run(s) is "
                              f"{avg:.0f}/day, vs the System Blueprint's assumed ~{ASSUMED_DAILY_TOKENS}/day.",
                    "sample_size": len(consumed), "confidence": confidence_label(len(consumed)),
                    "ai_brain_key": None,
                })

    leads = db.leads_with_outcomes()
    with_explanation = [l for l in leads if l.get("explanation")]
    if with_explanation:
        stats = tuning_report.gate_and_adjustment_stats(with_explanation)
        for key, s in stats.items():
            if not key.startswith("gate:"):
                continue
            n = s["wins"] + s["losses"]
            if n >= 5 and s["losses"] == n:
                proposals.append({
                    "kind": "data-driven",
                    "finding": f"`{key}` rejected 100% of {n} outcomes seen — possibly toothless or mis-set.",
                    "sample_size": n, "confidence": confidence_label(n), "ai_brain_key": None,
                })

        ip_cliff_brands: Dict[str, int] = {}
        for lead in with_explanation:
            adjustments = (lead.get("explanation") or {}).get("adjustments", [])
            if any(a.get("name") == "ip-cliff" for a in adjustments):
                brand = (lead.get("brand") or "unknown").strip()
                ip_cliff_brands[brand] = ip_cliff_brands.get(brand, 0) + 1
        for brand, count in ip_cliff_brands.items():
            if count >= 2:
                proposals.append({
                    "kind": "data-driven",
                    "finding": f"Brand '{brand}' has been IP-cliff-flagged {count} time(s) — "
                              f"candidate for ai-brain.json brands.avoid.",
                    "sample_size": count, "confidence": confidence_label(count),
                    "ai_brain_key": "brands.avoid",
                })
    return proposals


def knowledge_driven_proposals() -> List[Dict[str, Any]]:
    """Best-effort: run a knowledge-rag check for current OA thresholds via a subprocess call
    to knowledge-rag/ask.py. Degrades to a single honest 'unavailable' entry on ANY failure
    (missing deps, timeout, corpus not built, etc.) — explicitly optional, must never break the
    rest of the proposal run."""
    if not os.path.exists(ASK_PY):
        return [{"kind": "knowledge-driven", "finding": "knowledge-rag/ask.py not found — skipped.",
                 "sample_size": 0, "confidence": "unavailable", "ai_brain_key": None}]
    try:
        # encoding="utf-8" (not just text=True): ask.py's cited answers contain non-ASCII
        # characters, and Windows subprocess pipes otherwise decode with the console's cp1252
        # codepage and crash — the same class of bug the project hit before with ask.py's own
        # stdout (fixed there via sys.stdout.reconfigure(encoding="utf-8")); this is the
        # equivalent fix on the READING side.
        result = subprocess.run(
            [sys.executable, ASK_PY, "--json", "--limit", "3",
             "current BSR ROI profit threshold for online arbitrage"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, cwd=os.path.dirname(ASK_PY),
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError((result.stderr or "no output")[:200])
        # Free-text answers are NOT auto-diffed against ai-brain.json — judged too unreliable to
        # propose a specific value change from without a human reading it.
        return [{
            "kind": "knowledge-driven",
            "finding": "Ran a knowledge-base check for current OA thresholds — read the RAG "
                      "answer directly (`python knowledge-rag/ask.py \"current BSR ROI profit "
                      "threshold\"`) and compare by eye against ai-brain.json.",
            "sample_size": 0, "confidence": "manual review suggested", "ai_brain_key": None,
        }]
    except Exception as e:
        return [{"kind": "knowledge-driven", "finding": f"Knowledge-base check unavailable this run: {e}",
                 "sample_size": 0, "confidence": "unavailable", "ai_brain_key": None}]


def collect_proposals() -> List[Dict[str, Any]]:
    """Run all three proposal generators ONCE. Callers that need both the report text and the
    count (run_daily.py) should call this once and pass the result to render_report(), rather
    than calling generate_report()+pending_count() separately — that would re-run the
    knowledge-driven check's subprocess call twice for no reason."""
    return outcome_driven_proposals() + data_driven_proposals() + knowledge_driven_proposals()


def render_report(all_proposals: List[Dict[str, Any]]) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## {now} — proposal run", ""]
    if not all_proposals:
        lines.append("No proposals this run.")
        lines.append("")
        return "\n".join(lines)
    for p in all_proposals:
        key_bit = f", key: `{p['ai_brain_key']}`" if p.get("ai_brain_key") else ""
        lines.append(f"- **[{p['kind']}]** {p['finding']} "
                     f"(sample size: {p['sample_size']}, confidence: {p['confidence']}{key_bit})")
    lines.append("")
    lines.append(f"**{len(all_proposals)} proposal(s) pending human review.** "
                 f"ai-brain.json was NOT changed by this script.")
    lines.append("")
    return "\n".join(lines)


def generate_report() -> str:
    """Convenience wrapper (also used by the CLI / older callers): collect + render in one call."""
    return render_report(collect_proposals())


def pending_count() -> int:
    """How many proposals a fresh run would generate. NOTE: this re-runs all three generators
    (including the knowledge-driven subprocess call) — callers that also need the report text
    should use collect_proposals() once instead (see write_report_with_count())."""
    return len(collect_proposals())


def notify_brain_proposals(proposals: List[Dict[str, Any]]) -> bool:
    """Post a SHORT embed (count + top finding) to the "brain_proposals" Discord stream — the
    full report stays in learning-hub/tracking/brain-proposals.md; this is just a heads-up.
    No-op (returns False, never posts) when there are no proposals this run."""
    if not proposals:
        return False
    top = proposals[0]
    embed = {
        "title": f"{len(proposals)} new brain proposal(s)",
        "description": f"**[{top['kind']}]** {top['finding']}"[:400],
        "color": 0xF5B14C,
        "footer": {"text": "see learning-hub/tracking/brain-proposals.md for the full report"},
    }
    return discord_router.send("brain_proposals", embed)


def write_report_with_count() -> "tuple[str, int]":
    """Single computation for run_daily.py: one collect_proposals() call feeds both the
    written report, the returned pending count, and the brain_proposals notification —
    avoids running the knowledge-driven subprocess check twice in the same cycle. The Discord
    notify is wrapped so a failure there never prevents the report from being written."""
    proposals = collect_proposals()
    block = render_report(proposals)
    _append_block(block)
    try:
        notify_brain_proposals(proposals)
    except Exception as e:
        print(f"[propose_updates] brain_proposals notify failed (non-fatal): {e}")
    return block, len(proposals)


def _append_block(block: str) -> None:
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    header = (
        "# Brain proposals (append-only)\n\n"
        "Generated by `scout/propose_updates.py` (System Blueprint Prompt G5), run at the end "
        "of every `run_daily.py` cycle. Proposals ONLY — this file NEVER writes to ai-brain.json.\n\n"
        "**To apply a proposal:** tell Claude (any session) \"apply proposal <describe it>\" — "
        "the fba-brain-updater skill makes the edit with provenance, bumps `updated`, re-syncs "
        "`control-center/hub-data/`, and you should then mark the proposal applied here with "
        "today's date.\n\n"
    )
    if not os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(header)
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(block + "\n---\n\n")


def write_report() -> str:
    """Single-shot convenience for direct/manual runs (`python propose_updates.py`) and tests
    that only care about the report text. run_daily.py uses write_report_with_count() instead
    to avoid computing the proposals twice in one cycle."""
    block, _count = write_report_with_count()
    return block


if __name__ == "__main__":
    print(write_report())
