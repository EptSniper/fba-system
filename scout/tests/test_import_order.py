"""
Regression test for Code Review 2026-07-02, Finding B1: db.py must never depend on some other
module happening to load .env first. SUPA/KEY are read at module-import time as plain
constants, so this can only be tested honestly in a FRESH subprocess — importing `db` again
within this same test process would hit Python's import cache and mask the exact bug (db.py
already loaded .env when some earlier test file imported it), which is precisely how this bug
went unnoticed until the code review actually executed the real run_daily.py import order.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCOUT_DIR = os.path.dirname(HERE)


def _run_fresh(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SCOUT_DIR, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    return result.stdout.strip()


def test_db_imported_alone_still_sees_env():
    """The exact scenario the bug hid in: `import db` with NOTHING else importing config
    first. Requires a real scout/.env with SUPABASE_URL set (this repo's dev environment has
    one) — skips honestly if not."""
    if not os.path.exists(os.path.join(SCOUT_DIR, ".env")):
        return  # nothing to verify against in an environment with no .env at all
    out = _run_fresh("import db; print(bool(db.SUPA), db.enabled())")
    assert out == "True True", f"db.py did not see .env when imported alone: {out!r}"


def test_run_daily_real_import_order_still_resolves_supabase():
    """The exact production entry point: `import run_daily` (which itself imports db before
    pipeline/config in the real file). This is the scenario the review empirically verified
    as broken before the fix."""
    if not os.path.exists(os.path.join(SCOUT_DIR, ".env")):
        return
    out = _run_fresh("import run_daily; print(run_daily.db.enabled())")
    assert out == "True", f"run_daily's real import order broke db.enabled(): {out!r}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
