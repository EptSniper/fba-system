"""
exam.py — knowledge-exam harness for the OA scorer (Code Review 2026-07-04 ask). Runs every
case in learning-hub/evals/deal-exam/*.json through scoring.explain_oa() exactly as
pipeline._evaluate() does (explain_oa already calls oa_hard_reject() internally), and diffs
the actual output against each case's HAND-COMPUTED expected_* fields — the expected values
were worked out independently against the documented formulas/thresholds (oa-criteria.md,
config.py's live-resolved constants) before this harness ever ran, so a mismatch can mean
either a real scorer bug or a genuine documented-behavior change; it never means "the code
agrees with itself" (that would make the exam meaningless).

This is knowledge-drift MONITORING, not a pass/fail gate: running this script always exits 0
(never blocks a build) — a wrong verdict here deserves a human's attention, not a failed CI
run. The one thing this DOES fail loudly on is a REGRESSION vs the last recorded run (see
compare_to_last()) — run_all_tests.py surfaces that as a warning without failing the suite.

Case schema (see any learning-hub/evals/deal-exam/*.json for real examples):
    id                              unique string
    facts                           the full pre-computed candidate dict scoring.explain_oa() takes
    expected_verdict                "review" | "pass"  (explain_oa()'s own vocabulary)
    expected_hard_reject            bool — whether oa_hard_reject() must return non-None
    expected_hard_reject_keyword    string|null — required lowercase substring of the hard_reject text
    expected_adjustment_names       [str] — adjustment "name"s that MUST appear (subset check)
    expected_failed_check_names     [str] — scored_checks names that MUST have passed=False (subset check)
    expected_profit_approx          float, optional — checked within `tolerance` (default 0.05)
    expected_roi_approx             float, optional — checked within `tolerance`
    trap_type                       string label (e.g. "boundary:roi-lower", "hard-reject:ip-cliff")
    source                          citation: transcript file+timestamp / chart-guide / "handcrafted"
    difficulty                      "easy" | "medium" | "hard"
"""
from __future__ import annotations

import glob
import json
import os
import statistics as stats
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import scoring
import analyst_exam

HERE = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(HERE, "..", "learning-hub", "evals", "deal-exam")
REPORT_PATH = os.path.join(HERE, "..", "learning-hub", "evals", "deal-exam-report.md")
LAST_SCORES_PATH = os.path.join(HERE, "..", "learning-hub", "evals", ".last-exam-scores.json")

MIN_N_FOR_RATE = 10  # refuse to report a bare percentage below this — show it, but flagged


@dataclass
class CaseResult:
    id: str
    trap_type: str
    difficulty: str
    source: str
    verdict_match: bool
    hard_reject_match: bool
    reason_match: bool
    profit_roi_match: bool
    errors: List[str] = field(default_factory=list)

    @property
    def full_match(self) -> bool:
        return self.verdict_match and self.hard_reject_match and self.reason_match and self.profit_roi_match


def load_cases() -> List[Dict[str, Any]]:
    cases = []
    for path in sorted(glob.glob(os.path.join(CASE_DIR, "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def run_case(case: Dict[str, Any]) -> CaseResult:
    """Runs the case's facts through scoring.explain_oa() — the SAME function
    pipeline._evaluate() calls — and diffs the result against the case's expectations."""
    facts = case["facts"]
    explanation = scoring.explain_oa(facts)
    hard_reject = explanation.get("hard_reject")
    errors: List[str] = []

    verdict_match = explanation["verdict"] == case["expected_verdict"]
    if not verdict_match:
        errors.append(f"verdict: expected {case['expected_verdict']!r}, got {explanation['verdict']!r}")

    expected_hr = bool(case.get("expected_hard_reject", False))
    hard_reject_match = bool(hard_reject) == expected_hr
    if not hard_reject_match:
        errors.append(f"hard_reject presence: expected {expected_hr}, got {hard_reject!r}")

    reason_ok = True
    kw = case.get("expected_hard_reject_keyword")
    if kw:
        if not hard_reject or kw.lower() not in hard_reject.lower():
            reason_ok = False
            errors.append(f"hard_reject_keyword: expected substring {kw!r} in {hard_reject!r}")

    adj_names = {a["name"] for a in explanation.get("adjustments", [])}
    for expected_adj in case.get("expected_adjustment_names", []):
        if expected_adj not in adj_names:
            reason_ok = False
            errors.append(f"missing expected adjustment {expected_adj!r} (got {sorted(adj_names)})")

    failed_names = {c["name"] for c in explanation.get("scored_checks", []) if not c["passed"]}
    for expected_fail in case.get("expected_failed_check_names", []):
        if expected_fail not in failed_names:
            reason_ok = False
            errors.append(f"expected check {expected_fail!r} to have failed, but it passed")

    profit_roi_match = True
    tol = case.get("tolerance", 0.05)
    if "expected_profit_approx" in case:
        actual = explanation.get("profit")
        if actual is None or abs(actual - case["expected_profit_approx"]) > tol:
            profit_roi_match = False
            errors.append(f"profit: expected ~{case['expected_profit_approx']} (+/-{tol}), got {actual}")
    if "expected_roi_approx" in case:
        actual = explanation.get("roi")
        if actual is None or abs(actual - case["expected_roi_approx"]) > tol:
            profit_roi_match = False
            errors.append(f"roi: expected ~{case['expected_roi_approx']} (+/-{tol}), got {actual}")

    return CaseResult(
        id=case["id"], trap_type=case.get("trap_type", "unlabeled"),
        difficulty=case.get("difficulty", "unknown"), source=case.get("source", "unknown"),
        verdict_match=verdict_match, hard_reject_match=hard_reject_match,
        reason_match=reason_ok, profit_roi_match=profit_roi_match, errors=errors,
    )


def wilson_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a proportion — better-behaved than a normal
    approximation at small n (which is most of what this exam has, honestly)."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _rate_line(label: str, successes: int, n: int) -> str:
    if n == 0:
        return f"{label}: n=0 (no cases)"
    pct = 100 * successes / n
    lo, hi = wilson_interval(successes, n)
    line = f"{label}: {successes}/{n} = {pct:.0f}% (95% CI {lo*100:.0f}-{hi*100:.0f}%)"
    if n < MIN_N_FOR_RATE:
        line += f"  [n<{MIN_N_FOR_RATE} — too small to trust this rate, shown for visibility only]"
    return line


def compare_to_last(current: Dict[str, float]) -> List[str]:
    """Loads the last recorded run's scores and flags any REGRESSION (a rate that dropped).
    Never flags an improvement or a new metric — only drops. Missing/corrupt last-scores file
    means nothing to compare against, not a regression."""
    try:
        with open(LAST_SCORES_PATH, "r", encoding="utf-8") as f:
            last = json.load(f)
    except Exception:
        return []
    regressions = []
    for key, cur_val in current.items():
        prev_val = last.get(key)
        if isinstance(prev_val, (int, float)) and cur_val < prev_val - 1e-9:
            regressions.append(f"REGRESSION: {key} dropped from {prev_val:.3f} to {cur_val:.3f}")
    return regressions


def save_scores(current: Dict[str, float]) -> None:
    os.makedirs(os.path.dirname(LAST_SCORES_PATH), exist_ok=True)
    with open(LAST_SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, sort_keys=True)
        f.write("\n")


def run_exam() -> Tuple[List[CaseResult], Dict[str, float], List[str]]:
    cases = load_cases()
    results = [run_case(c) for c in cases]

    n = len(results)
    verdict_ok = sum(r.verdict_match for r in results)
    reason_ok = sum(r.reason_match for r in results)
    full_ok = sum(r.full_match for r in results)

    scores = {
        "n_cases": n,
        "verdict_accuracy": verdict_ok / n if n else 0.0,
        "reason_match_rate": reason_ok / n if n else 0.0,
        "full_match_rate": full_ok / n if n else 0.0,
    }

    # Per-trap-type breakdown feeds both the report and regression tracking (a specific trap
    # category regressing matters even if the OVERALL rate looks stable).
    by_trap: Dict[str, List[CaseResult]] = {}
    for r in results:
        by_trap.setdefault(r.trap_type, []).append(r)
    for trap, rs in by_trap.items():
        scores[f"trap:{trap}:full_match_rate"] = sum(x.full_match for x in rs) / len(rs)

    regressions = compare_to_last(scores)
    return results, scores, regressions


def render_report(results: List[CaseResult], scores: Dict[str, float], regressions: List[str]) -> str:
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n = scores["n_cases"]
    lines = [
        "# Deal-exam report (knowledge-drift monitor, not a pass/fail gate)",
        "",
        f"Generated by `scout/exam.py`, {now}. Runs every case in "
        "`learning-hub/evals/deal-exam/*.json` through the SAME `scoring.explain_oa()` "
        "pipeline._evaluate() calls, and diffs the result against each case's hand-computed "
        "expectations. A wrong answer here means the scorer disagrees with documented OA "
        "domain knowledge (a transcript-cited decision, a handcrafted boundary, or a "
        "chart-guide scenario) — it is a signal to investigate, not a build failure.",
        "",
        f"**{n} case(s) run.**",
        "",
        "## Overall",
        "",
        _rate_line("Verdict accuracy", sum(r.verdict_match for r in results), n),
        "",
        _rate_line("Reason-match rate (expected gates/adjustments actually appeared)",
                   sum(r.reason_match for r in results), n),
        "",
        _rate_line("Full match (verdict + reasons + profit/roi where asserted)",
                   sum(r.full_match for r in results), n),
        "",
    ]

    if regressions:
        lines.append("## WARNING: Regressions vs the last recorded run")
        lines.append("")
        for r in regressions:
            lines.append(f"- {r}")
        lines.append("")
    else:
        lines.append("## Regressions vs the last recorded run")
        lines.append("")
        lines.append("None detected.")
        lines.append("")

    lines.append("## Per-trap-type breakdown")
    lines.append("")
    by_trap: Dict[str, List[CaseResult]] = {}
    for r in results:
        by_trap.setdefault(r.trap_type, []).append(r)
    for trap in sorted(by_trap):
        rs = by_trap[trap]
        lines.append(_rate_line(f"`{trap}`", sum(x.full_match for x in rs), len(rs)))
    lines.append("")

    boundary_results = [r for r in results if r.trap_type.startswith("boundary:")]
    lines.append("## Boundary-sensitivity report")
    lines.append("")
    if not boundary_results:
        lines.append("No boundary-tagged cases in this run.")
    else:
        lines.append(_rate_line("Boundary cases overall", sum(r.full_match for r in boundary_results), len(boundary_results)))
        lines.append("")
        for r in sorted(boundary_results, key=lambda x: x.id):
            status = "PASS" if r.full_match else "FAIL"
            lines.append(f"- `{r.id}` ({r.trap_type}): **{status}**")
            for e in r.errors:
                lines.append(f"  - {e}")
    lines.append("")

    failures = [r for r in results if not r.full_match]
    lines.append(f"## Failures ({len(failures)})")
    lines.append("")
    if not failures:
        lines.append("None — every case matched its expectation.")
    else:
        for r in failures:
            lines.append(f"### `{r.id}` — {r.trap_type} ({r.difficulty})")
            lines.append(f"Source: {r.source}")
            for e in r.errors:
                lines.append(f"- {e}")
            lines.append("")
    lines.append("")

    lines.append("## Case bank composition")
    lines.append("")
    by_difficulty: Dict[str, int] = {}
    for r in results:
        by_difficulty[r.difficulty] = by_difficulty.get(r.difficulty, 0) + 1
    for d in sorted(by_difficulty):
        lines.append(f"- {d}: {by_difficulty[d]}")
    lines.append("")

    lines.append(analyst_exam.render_section(analyst_exam.run_analyst_exam()))

    return "\n".join(lines)


def write_report() -> str:
    results, scores, regressions = run_exam()
    report = render_report(results, scores, regressions)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    save_scores(scores)
    return report


if __name__ == "__main__":
    print(write_report())
