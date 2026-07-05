"""
run_all_tests.py — discovers and runs every test file across scout/, scout_pro/, and
knowledge-rag/, then prints ONE aggregate pass/fail line (Code Review 2026-07-02, Finding S12).

Each project directory is run as its own `python -m pytest <dir>` invocation (not one combined
run) because each has its own module-search-path assumptions baked into its test files'
`sys.path.insert(...)` lines — mixing them into a single pytest session risks import collisions
between same-named test modules across the three directories.

Usage:
    python scout/run_all_tests.py

Exit code is 0 only if every suite passed; non-zero (the count of failing suites) otherwise, so
this is safe to wire into a pre-commit hook or CI step later without extra parsing.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

SUITES = [
    ("scout", HERE / "tests"),
    ("scout_pro", ROOT / "scout_pro" / "tests"),
    ("knowledge-rag", ROOT / "knowledge-rag" / "tests"),
    ("scripts", ROOT / "scripts" / "tests"),  # scripts/pre-commit.py (THIS_WEEK.md Prompt W2)
]

# pytest's summary line orders counts "N failed, M passed, K skipped" (failures FIRST) — an
# ordered single regex that expects "passed" before "failed" parses passed=0 on exactly the
# runs that fail, which is when the aggregate line matters most (Code Review 2026-07-03,
# Finding #10). Search each count independently instead.
def _count(kind: str, line: str) -> int:
    m = re.search(rf"(\d+) {kind}", line)
    return int(m.group(1)) if m else 0


def _run_suite(name: str, path: Path) -> dict:
    if not path.is_dir():
        return {"name": name, "status": "missing", "passed": 0, "failed": 0, "errors": 0, "output": ""}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q"],
        capture_output=True, text=True, cwd=str(path.parent),
    )
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    passed = _count("passed", tail)
    failed = _count("failed", tail)
    errors = _count("error", tail)
    ok = result.returncode == 0
    return {
        "name": name, "status": "ok" if ok else "FAIL", "passed": passed, "failed": failed,
        "errors": errors, "output": result.stdout + result.stderr,
    }


def _run_deal_exam() -> None:
    """Knowledge-drift monitor, not a test suite — never affects run_all_tests.py's exit code
    (Code Review 2026-07-04's own framing: "knowledge drift != test failure"). The one thing
    this DOES surface loudly is a REGRESSION vs the last recorded run (a rate that dropped),
    which exam.py already detects; everything else is just informational."""
    try:
        import exam
        results, scores, regressions = exam.run_exam()
        n = scores["n_cases"]
        pct = 100 * scores["verdict_accuracy"]
        print(f"[deal-exam] {n} case(s), verdict accuracy {pct:.0f}% "
             f"(full report: learning-hub/evals/deal-exam-report.md)")
        exam.write_report()
        if regressions:
            print("[deal-exam] WARNING: REGRESSIONS DETECTED (see report for detail):")
            for r in regressions:
                print(f"  - {r}")
    except Exception as e:
        print(f"[deal-exam] SKIPPED - {e}")


def main() -> int:
    results = [_run_suite(name, path) for name, path in SUITES]

    total_passed = sum(r["passed"] for r in results)
    total_failed = sum(r["failed"] + r["errors"] for r in results)
    failing_suites = 0

    for r in results:
        if r["status"] == "missing":
            print(f"[{r['name']}] SKIPPED - directory not found")
            continue
        marker = "OK" if r["status"] == "ok" else "FAIL"
        print(f"[{r['name']}] {marker} - {r['passed']} passed, {r['failed'] + r['errors']} failed")
        if r["status"] != "ok":
            failing_suites += 1
            print(r["output"])

    print()
    print(f"TOTAL: {total_passed} passed, {total_failed} failed across "
          f"{sum(1 for r in results if r['status'] != 'missing')} suite(s)"
          + (f" - {failing_suites} suite(s) FAILED" if failing_suites else " - all green"))

    print()
    _run_deal_exam()

    return failing_suites


if __name__ == "__main__":
    sys.exit(main())
