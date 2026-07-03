"""
scout/smoke_test_discord.py — live, one-time (or re-run-anytime) verification that every
Discord channel webhook from Cowork Session 23 actually works.

Posts ONE clearly-labeled test message directly to each of the 7 provisioned streams AND to
DISCORD_WEBHOOK_FALLBACK, reporting the real HTTP status per channel. This is a LIVE script —
it actually posts to real Discord channels. Run it deliberately; it is intentionally NOT part
of the automated test suite (which mocks discord_router everywhere).

Usage:
    python smoke_test_discord.py
"""
from __future__ import annotations

import datetime as dt
import os

try:
    # discord_router.py deliberately reads os.environ directly (no config.py dependency), so
    # this standalone script must load .env itself — every other entry point (run_daily.py,
    # pipeline.py) gets this for free by transitively importing config.py, which already does.
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv simply not installed
    pass

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import discord_router


def run() -> dict:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    results = {}
    if requests is None:
        for stream in list(discord_router.STREAMS) + ["fallback (direct)"]:
            results[stream] = "SKIPPED (requests not installed)"
        return results

    for stream, env_var in discord_router.STREAMS.items():
        url = os.getenv(env_var)
        if not url:
            results[stream] = "SKIPPED (no webhook configured)"
            continue
        payload = {"username": "FBA Scout — Router Smoke Test",
                  "content": f"router smoke test — {stream} — {now}"}
        try:
            r = requests.post(url, json=payload, timeout=15)
            results[stream] = f"HTTP {r.status_code}"
        except Exception as e:
            results[stream] = f"ERROR: {e}"

    fallback_url = os.getenv(discord_router.FALLBACK_ENV_VAR)
    if fallback_url:
        payload = {"username": "FBA Scout — Router Smoke Test",
                  "content": f"router smoke test — fallback (direct) — {now}"}
        try:
            r = requests.post(fallback_url, json=payload, timeout=15)
            results["fallback (direct)"] = f"HTTP {r.status_code}"
        except Exception as e:
            results["fallback (direct)"] = f"ERROR: {e}"
    else:
        results["fallback (direct)"] = "SKIPPED (no fallback configured)"

    return results


if __name__ == "__main__":
    outcome = run()
    print("Discord router smoke test results:")
    for name, status in outcome.items():
        print(f"  {name:20s} {status}")
