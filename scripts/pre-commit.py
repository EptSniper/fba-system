"""
scripts/pre-commit.py — the git pre-commit guard (THIS_WEEK.md Prompt W2).

Runs on every `git commit`, before the commit is created:
  1. A secrets scan of every STAGED file's INDEX content (what's actually about to be
     committed, not the working tree, which may have since been re-edited after `git add`) —
     reuses scout/redact.py's OWN patterns directly (its query-param regex, Discord webhook
     regex, JWT regex, and its env-secret-value detection) rather than forking a second copy
     that could silently drift from what redact() actually masks at runtime.
  2. The FAST test files (scoring + db idempotency + discord router — ~1s total, well under
     the 30s budget) via `python -m pytest`.

Blocks the commit (non-zero exit) with a clear message on either failure — never prints an
actual secret VALUE, only which staged file it was found in and why.

Bypass in a genuine emergency: `git commit --no-verify` skips BOTH checks. If you do this,
re-run `python scripts/pre-commit.py` manually right after and fix anything it finds — don't
let a skipped check become a silently-never-checked one.

This file is the tracked, reviewable source of truth; `.git/hooks/pre-commit` (untracked — git
never syncs anything under .git/hooks/ across clones) is a one-line stub that execs this
script, so the actual logic lives somewhere `git log`/review can see it.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCOUT_DIR = REPO_ROOT / "scout"
sys.path.insert(0, str(SCOUT_DIR))

import redact  # noqa: E402 — reuses redact.py's own regex objects/env-scan directly (see
                # module docstring); reaching into its "private" (_-prefixed) internals here is
                # intentional sharing of the single source of truth, not a layering violation.

FAST_TEST_FILES = ["tests/test_scoring.py", "tests/test_db_idempotency.py", "tests/test_discord_router.py"]

# Values shorter than this, or wrapped in angle brackets, are almost certainly template
# placeholders (this repo's own convention: KEEPA_KEY=<FILL_ME>) — never real secrets. Without
# this guard, every commit touching HUMAN_TODO.md / API_KEYS.env's template would be a false
# positive: confirmed live 2026-07-04 that "<FILL_ME>" is 10 chars, clears redact.py's own
# len>=6 threshold, and appears in multiple tracked files.
_MIN_REAL_SECRET_LEN = 12
_PLACEHOLDER_RE = re.compile(r"^<.+>$")

# These two files' ENTIRE PURPOSE is embedding intentionally-fake secret-shaped literals (a
# fake API key, a Discord webhook with id 1234567890123, a fake JWT) to prove redact.py / this
# scanner actually catch that shape — excluding them from the scan doesn't
# weaken real-secret detection anywhere else; scanning them would just self-flag every commit
# that touches this test suite (found live 2026-07-05, Session 52). Any REAL secret elsewhere
# in the diff is still caught normally.
_KNOWN_TEST_FIXTURE_FILES = {"scout/tests/test_redact.py", "scripts/tests/test_pre_commit.py"}


def _real_secret_values():
    """The subset of redact.py's currently-loaded env-secret values that are long enough and
    not placeholder-shaped to be worth scanning for."""
    return [v for v in redact._sensitive_env_values()
            if len(v) >= _MIN_REAL_SECRET_LEN and not _PLACEHOLDER_RE.match(v)]


def _staged_files():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True, cwd=str(REPO_ROOT),
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _staged_content(path: str):
    """The INDEX version of a file (git's stage 0) — what will actually be committed, not
    necessarily what's currently on disk. Returns None for anything unreadable as text
    (binary files, or a path git can't show for any reason) — nothing to scan, not an error."""
    try:
        result = subprocess.run(
            ["git", "show", f":{path}"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def scan_staged_files():
    """Returns [(path, reason), ...] for every staged file that looks like it contains a real
    secret. Never includes the secret VALUE itself, only where it was found and why."""
    findings = []
    secret_values = _real_secret_values()
    for path in _staged_files():
        if path in _KNOWN_TEST_FIXTURE_FILES:
            continue
        content = _staged_content(path)
        if content is None:
            continue
        if any(value in content for value in secret_values):
            findings.append((path, "matches a currently-configured secret env var's value"))
        elif redact._DISCORD_WEBHOOK_PATTERN.search(content):
            findings.append((path, "contains a Discord webhook URL"))
        elif redact._JWT_PATTERN.search(content):
            findings.append((path, "contains a JWT-shaped string (e.g. a Supabase key)"))
        elif redact._QUERY_PARAM_PATTERN.search(content):
            findings.append((path, "contains a KEY/TOKEN/SECRET-style query parameter"))
    return findings


def run_fast_tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *FAST_TEST_FILES, "-q"],
        cwd=str(SCOUT_DIR), capture_output=True, text=True,
    )
    return result.returncode == 0, result.stdout + result.stderr


def main() -> int:
    print("[pre-commit] scanning staged files for secrets...")
    findings = scan_staged_files()
    if findings:
        print("\n[pre-commit] BLOCKED -- possible secret(s) in staged files:")
        for path, reason in findings:
            print(f"  - {path}: {reason}")
        print("\nRemove the secret from the staged content (git reset <file>, edit, re-add "
             "the real value only to your local .env), or if this is a genuine false "
             "positive, commit with --no-verify and tell a human.")
        return 1
    print("[pre-commit] no secrets found in staged files.")

    print("[pre-commit] running fast tests (scoring, db idempotency, discord router)...")
    ok, output = run_fast_tests()
    if not ok:
        print("\n[pre-commit] BLOCKED -- fast tests failed:")
        print(output)
        return 1
    print("[pre-commit] fast tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
