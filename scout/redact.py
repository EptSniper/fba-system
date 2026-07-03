"""
scout/redact.py — mask secrets out of any string before it leaves the process (Code Review
2026-07-02, Finding B5).

Multiple error paths carry raw exception text into places a human (or Discord) reads it:
Supabase `runs.error_summary`, the daily digest embed, the system_health alert, and any
logger/print of an exception. Several of those exceptions can legitimately contain a real
secret — Best Buy's API key rides in the request URL (deals/sources/bestbuy.py), Keepa's
client embeds its key in request URLs too, and a failed Discord POST's exception can echo the
webhook URL itself. redact() is the one function every one of those paths calls before the
string is logged, stored, or posted.

Two layers, applied to every string:
  1. Every *KEY*/*TOKEN*/*WEBHOOK* env var's ACTUAL VALUE (from os.environ), if it appears
     literally in the text, is masked — catches anything, regardless of what URL param name
     carried it.
  2. Generic patterns as a second line of defense for values redact() couldn't already know
     about from the environment: `key=...`/`apiKey=...`/`token=...` query params, and Discord
     webhook URLs (host + numeric id + token segment).
"""
from __future__ import annotations

import os
import re
from typing import Optional

_MASK = "***REDACTED***"

_ENV_NAME_PATTERN = re.compile(r"(KEY|TOKEN|WEBHOOK)", re.IGNORECASE)

_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|apikey|key|token|access[_-]?token|secret)=([^&\s\"'<>]+)"
)

_DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+"
)


def _sensitive_env_values() -> list:
    values = []
    for name, value in os.environ.items():
        if value and len(value) >= 6 and _ENV_NAME_PATTERN.search(name):
            values.append(value)
    # Longest first so a value that's a substring of a longer one doesn't get partially masked
    # in a way that leaves a fragment of the longer secret exposed.
    return sorted(set(values), key=len, reverse=True)


def redact(text: Optional[str]) -> Optional[str]:
    """Mask every known-secret env var value, generic key=/token= query params, and Discord
    webhook URLs found in `text`. None-safe (returns None unchanged) so callers can wrap an
    Optional[str] without an extra guard."""
    if not text:
        return text
    out = text
    for value in _sensitive_env_values():
        if value in out:
            out = out.replace(value, _MASK)
    out = _QUERY_PARAM_PATTERN.sub(lambda m: f"{m.group(1)}={_MASK}", out)
    out = _DISCORD_WEBHOOK_PATTERN.sub(_MASK, out)
    return out
