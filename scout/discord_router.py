"""
scout/discord_router.py — routes every notification stream to its own Discord channel webhook
(Cowork Session 23 provisioned 7 channel webhooks into scout/.env).

Resolution order per stream: the stream's own env var -> DISCORD_WEBHOOK_FALLBACK -> an honest
logged skip. Never crashes the pipeline over a missing/misconfigured webhook, never fakes a
successful send. Respects Discord's rate limits (one retry on HTTP 429, honoring
Retry-After) and batches multiple embeds into as few messages as possible (Discord allows up
to 10 embeds per message).

STREAMS registry — the single source of truth for stream -> env var. "review_queue" (S1
disagreements + Deal Finder Prompt D2 gray-zone matches) and "outcomes" (Phase 3) are
registered here as forward-looking stubs: no caller sends to them yet, but future prompts can
route to them with zero redesign.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Union

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import redact

log = logging.getLogger("scout.discord_router")

STREAMS: Dict[str, str] = {
    "daily_digest": "DISCORD_WEBHOOK_DAILY_DIGEST",
    "scout_picks": "DISCORD_WEBHOOK_SCOUT_PICKS",
    "retail_deals": "DISCORD_WEBHOOK_RETAIL_DEALS",
    "review_queue": "DISCORD_WEBHOOK_REVIEW_QUEUE",   # stub: no caller yet (S1 disagreements / D2 gray-zone)
    "brain_proposals": "DISCORD_WEBHOOK_BRAIN_PROPOSALS",
    "system_health": "DISCORD_WEBHOOK_SYSTEM_HEALTH",
    "outcomes": "DISCORD_WEBHOOK_OUTCOMES",           # stub: no caller yet (Phase 3)
}
FALLBACK_ENV_VAR = "DISCORD_WEBHOOK_FALLBACK"
MAX_EMBEDS_PER_MESSAGE = 10  # Discord's own per-message embed cap
DEFAULT_USERNAME = "FBA Scout"

_TELEMETRY: Dict[str, int] = {"sent": 0, "skipped": 0, "failed": 0}


def telemetry() -> Dict[str, int]:
    """Per-process send counts (sent/skipped/failed), for a run's summary telemetry."""
    return dict(_TELEMETRY)


def reset_telemetry() -> None:
    _TELEMETRY.update(sent=0, skipped=0, failed=0)


def _resolve_url(stream: str) -> Optional[str]:
    """The stream's own webhook URL if set, else DISCORD_WEBHOOK_FALLBACK, else None."""
    env_var = STREAMS.get(stream)
    if env_var:
        url = os.getenv(env_var)
        if url:
            return url
    return os.getenv(FALLBACK_ENV_VAR) or None


def has_webhook(stream: str) -> bool:
    """Public check: does this stream (or its fallback) currently resolve to a real webhook
    URL? Callers outside this module (pipeline.py, discord_notify.py) used to reach into the
    private `_resolve_url()` directly (Code Review 2026-07-02, nit) — this is the intended public
    surface for "should I bother posting" checks; `send()` still does its own resolution
    internally for the actual post."""
    return bool(_resolve_url(stream))


def _post_with_retry(url: str, payload: Dict[str, Any], session: Optional[Any] = None) -> bool:
    """POST once; on HTTP 429, sleep for the server's Retry-After and try exactly ONE more
    time (never an unbounded retry loop against a webhook). Any other error is logged and
    returns False without a second attempt."""
    sess = session or requests
    if sess is None:
        log.warning("discord_router: requests not installed; cannot send.")
        return False
    headers = {"Content-Type": "application/json"}
    try:
        r = sess.post(url, json=payload, timeout=15, headers=headers)
    except Exception as e:
        # Code Review 2026-07-02, Finding B5: a connection-error exception can legitimately
        # embed the request URL (the webhook URL itself) in its message — redact it before
        # it reaches any log.
        log.error("discord_router: post failed: %s", redact.redact(str(e)))
        return False

    if r.status_code == 429:
        try:
            retry_after = float(r.json().get("retry_after", 1.0))
        except Exception:
            retry_after = 1.0
        time.sleep(retry_after + 0.25)
        try:
            r = sess.post(url, json=payload, timeout=15, headers=headers)
        except Exception as e:
            log.error("discord_router: retry post failed: %s", redact.redact(str(e)))
            return False

    if 200 <= r.status_code < 300:
        return True
    log.error("discord_router: post failed HTTP %s: %s", r.status_code,
             redact.redact(str(getattr(r, "text", ""))[:200]))
    return False


def _chunks(embeds: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    return [embeds[i:i + MAX_EMBEDS_PER_MESSAGE] for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)]


def send_to_url(url: str, embed_or_text: Union[str, Dict[str, Any], List[Dict[str, Any]]],
               username: str = DEFAULT_USERNAME, session: Optional[Any] = None,
               content: Optional[str] = None) -> bool:
    """Send directly to an explicit webhook URL, bypassing stream resolution — used for
    backward-compatible explicit-webhook overrides (e.g. discord_notify.post_pick's legacy
    `webhook_url` argument). Same batching/retry/telemetry behavior as send(). `content` adds a
    plain-text line alongside embeds (Discord embeds only linkify their title; a separate
    `content` line is how discord_notify.py adds a second clickable Keepa link) — ignored when
    `embed_or_text` is itself plain text."""
    if isinstance(embed_or_text, str):
        payloads = [{"username": username, "content": embed_or_text}]
    elif isinstance(embed_or_text, dict):
        payload = {"username": username, "embeds": [embed_or_text]}
        if content:
            payload["content"] = content
        payloads = [payload]
    else:
        embeds = list(embed_or_text)
        if not embeds:
            _TELEMETRY["skipped"] += 1
            return False
        payloads = [{"username": username, "embeds": chunk} for chunk in _chunks(embeds)]
        if content:
            payloads[0]["content"] = content

    all_ok = True
    for payload in payloads:
        if _post_with_retry(url, payload, session=session):
            _TELEMETRY["sent"] += 1
        else:
            _TELEMETRY["failed"] += 1
            all_ok = False
    return all_ok


def send(stream: str, embed_or_text: Union[str, Dict[str, Any], List[Dict[str, Any]]],
        username: str = DEFAULT_USERNAME, session: Optional[Any] = None,
        content: Optional[str] = None) -> bool:
    """Send one item (text, a single embed, or a list of embeds — batched into as few messages
    as Discord's 10-embeds-per-message limit allows) to a named stream. Resolution order:
    stream's env var -> DISCORD_WEBHOOK_FALLBACK -> an honest logged skip (never raises, never
    fakes success)."""
    url = _resolve_url(stream)
    if not url:
        log.warning("discord_router: no webhook resolved for stream=%r (and no fallback set) "
                   "— skipping.", stream)
        _TELEMETRY["skipped"] += 1
        return False
    return send_to_url(url, embed_or_text, username=username, session=session, content=content)
