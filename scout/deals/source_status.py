"""
scout/deals/source_status.py — the pure state machine for clearance-URL health
(TOP100_DEAL_WATCH_PLAN.md follow-up). No I/O: db.py reads/writes the source_status rows; this
module decides how a fetch RESULT changes a URL's state, so the logic is unit-testable without
Supabase.

The rules the user asked for:
  - a clr URL that returns 403 on 2 CONSECUTIVE runs retires to "sd-rss-only" (future runs skip
    its clr fetch) — but ONLY if the store has a sd-rss fallback, so retiring costs zero
    coverage. A clr-only store that 403s keeps getting reported (no fallback to fall back to).
  - a 429 is TRANSIENT (rate-limited): no counter change, never retires, re-tried next run.
  - any clr success (ok/empty/not_modified) resets the consecutive-403 counter to 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MODE_ACTIVE = "active"
MODE_SD_RSS_ONLY = "sd-rss-only"

# fetch status labels (clearance_page.fetch_page returns these)
OK_STATUSES = {"ok", "empty", "not_modified"}
FORBIDDEN = "forbidden"      # HTTP 403
RATE_LIMITED = "rate_limited"  # HTTP 429
ERROR = "error"              # anything else (5xx, timeout, ...)

RETIRE_AFTER = 2  # consecutive 403s


def classify(status_code: Optional[int], generic_status: str) -> str:
    """Map an HTTP status code to a source-status label. generic_status is fetch_page's own
    label for the non-HTTP cases (skipped_robots/not_modified/ok/empty) — passed through when
    there's no distinguishing code."""
    if status_code == 403:
        return FORBIDDEN
    if status_code == 429:
        return RATE_LIMITED
    return generic_status


def next_state(prev: Optional[Dict[str, Any]], status_label: str, has_sd_rss_fallback: bool) -> Dict[str, Any]:
    """Given the prior row (or None for a first-ever sighting) and this run's status, return the
    new {mode, consecutive_403, retired_now}. retired_now is True ONLY on the transition into
    sd-rss-only (so the caller reports it once, then never again)."""
    prev_mode = (prev or {}).get("mode") or MODE_ACTIVE
    prev_403 = int((prev or {}).get("consecutive_403") or 0)

    # Already retired: stay retired (we don't even fetch it, so this is just defensive).
    if prev_mode == MODE_SD_RSS_ONLY:
        return {"mode": MODE_SD_RSS_ONLY, "consecutive_403": prev_403, "retired_now": False}

    if status_label == FORBIDDEN:
        c403 = prev_403 + 1
        if c403 >= RETIRE_AFTER and has_sd_rss_fallback:
            return {"mode": MODE_SD_RSS_ONLY, "consecutive_403": c403, "retired_now": True}
        return {"mode": MODE_ACTIVE, "consecutive_403": c403, "retired_now": False}

    if status_label == RATE_LIMITED:
        # Transient — do NOT touch the consecutive-403 counter (a 429 isn't a 403), never retire.
        return {"mode": MODE_ACTIVE, "consecutive_403": prev_403, "retired_now": False}

    if status_label in OK_STATUSES:
        return {"mode": MODE_ACTIVE, "consecutive_403": 0, "retired_now": False}

    # Other errors (5xx, timeout, DNS): don't retire (not a 403), don't reset the 403 streak.
    return {"mode": MODE_ACTIVE, "consecutive_403": prev_403, "retired_now": False}
