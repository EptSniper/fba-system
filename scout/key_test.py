"""
scout/key_test.py — live, minimal connection tests for API keys managed via the control-center
Settings page. Each test is a cheap, read-only, non-consuming call:
  - Keepa's token-balance endpoint doesn't cost a product token.
  - Anthropic's GET /v1/models doesn't consume generation tokens.
  - Best Buy / Supabase / Discord / healthchecks.io / SP-API's LWA refresh are all free calls
    by nature of those APIs (Discord's IS a real posted message, though — see test_discord_webhook).

SECRET HANDLING: the value(s) under test are read from environment variables the CALLER (the
Next.js API route) sets ONLY for this one subprocess — never passed as a CLI argument (which
would appear in this machine's process list) and never read back from a real .env file (so a
value can be tested before it's ever saved to disk). Every returned "detail" string is passed
through redact.py before being printed, as defense in depth against an exception echoing a raw
value (e.g. a failed request's exception text including the full URL).

Usage:
    TEST_KEY_VALUE=<value> python key_test.py <provider>
    TEST_KEY_VALUE=<client_id> TEST_KEY_VALUE_2=<secret> TEST_KEY_VALUE_3=<refresh_token> \\
        python key_test.py spapi

Always prints exactly one JSON line to stdout: {"ok": bool, "detail": str}. Exit code is always
0 — a bug in this script itself is caught and reported as ok:false via the JSON, so the caller
never has to disambiguate "key invalid" from "test script crashed."
"""
from __future__ import annotations

import json
import os
import sys

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact

TIMEOUT = 10


def _value(n: int = 1) -> str:
    suffix = "" if n == 1 else f"_{n}"
    return os.environ.get(f"TEST_KEY_VALUE{suffix}", "")


def _ok(detail: str) -> dict:
    return {"ok": True, "detail": redact.redact(detail)}


def _fail(detail: str) -> dict:
    return {"ok": False, "detail": redact.redact(detail)}


def test_keepa() -> dict:
    key = _value()
    if not key:
        return _fail("no key given")
    try:
        r = requests.get("https://api.keepa.com/token", params={"key": key}, timeout=TIMEOUT)
        data = r.json() if r.content else {}
        if isinstance(data, dict) and "tokensLeft" in data:
            return _ok(f"valid — {data['tokensLeft']} tokens left")
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else None
        return _fail(msg or f"key rejected (HTTP {r.status_code})")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_anthropic() -> dict:
    key = _value()
    if not key:
        return _fail("no key given")
    try:
        r = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            n = len((r.json() or {}).get("data", []))
            return _ok(f"valid — {n} model(s) visible")
        return _fail(f"HTTP {r.status_code}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_supabase() -> dict:
    url, key = _value(1), _value(2)
    if not url or not key:
        return _fail("URL and service key both required")
    try:
        r = requests.get(
            f"{url.rstrip('/')}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 404):
            return _ok("reachable, key accepted")
        return _fail(f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_bestbuy() -> dict:
    key = _value()
    if not key:
        return _fail("no key given")
    try:
        r = requests.get(
            "https://api.bestbuy.com/v1/products(onSale=true)",
            params={"apiKey": key, "format": "json", "pageSize": 1},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return _ok("valid")
        return _fail(f"HTTP {r.status_code}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_discord_webhook() -> dict:
    url = _value()
    if not url:
        return _fail("no webhook URL given")
    try:
        r = requests.post(
            url,
            json={"username": "FBA Center — Key Test", "content": "settings page connection test — this key works ✅"},
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 204):
            return _ok("posted a real test message to the channel — check Discord")
        return _fail(f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_healthcheck() -> dict:
    url = _value()
    if not url:
        return _fail("no URL given")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code < 400:
            return _ok("reachable")
        return _fail(f"HTTP {r.status_code}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_spapi() -> dict:
    client_id, client_secret, refresh_token = _value(1), _value(2), _value(3)
    if not (client_id and client_secret and refresh_token):
        return _fail("client id, secret, and refresh token are all required")
    try:
        r = requests.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 200 and "access_token" in (r.json() or {}):
            return _ok("LWA token refresh succeeded")
        return _fail(f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        return _fail(f"request failed: {e}")


def test_youtube_transcript() -> dict:
    # No documented free "account status" endpoint for this provider — validate presence only
    # rather than risk spending a real transcript-fetch credit on a guessed test call.
    key = _value()
    if not key:
        return _fail("no key given")
    return _ok("saved (live verification isn't run for this provider — it has no known free "
              "test endpoint, and guessing one risks spending a real transcript credit)")


PROVIDERS = {
    "keepa": test_keepa,
    "anthropic": test_anthropic,
    "supabase": test_supabase,
    "bestbuy": test_bestbuy,
    "discord_webhook": test_discord_webhook,
    "healthcheck": test_healthcheck,
    "spapi": test_spapi,
    "youtube_transcript": test_youtube_transcript,
}


def main() -> None:
    provider = sys.argv[1] if len(sys.argv) > 1 else ""
    if requests is None:
        print(json.dumps({"ok": False, "detail": "requests package not installed"}))
        return
    fn = PROVIDERS.get(provider)
    if fn is None:
        print(json.dumps({"ok": False, "detail": f"unknown provider {provider!r}"}))
        return
    try:
        result = fn()
    except Exception as e:  # a bug here must never look like a crash to the caller
        result = _fail(f"test script error: {e}")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
