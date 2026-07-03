"""
discord_notify.py — build + post scout-pick embeds via the "scout_picks" Discord channel.

Posting now routes through discord_router.py (Cowork Session 23's multi-channel webhooks) —
rate-limit handling (HTTP 429 + Retry-After, one retry) and batching live there. An explicit
`webhook_url` argument (legacy/manual override) still posts directly to that URL, bypassing
stream resolution, for backward compatibility with any existing manual usage.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import config
import discord_router

AMAZON_DP = "https://www.amazon.com/dp/{asin}"
KEEPA_PRODUCT = "https://keepa.com/#!product/1-{asin}"


def _embed_for(product: Dict[str, Any]) -> Dict[str, Any]:
    asin = product.get("asin", "?")
    score = product.get("blended_score", product.get("rule_score", 0)) or 0

    # colour ramps green as score rises
    if score >= 85:
        color = 0x36D399
    elif score >= 75:
        color = 0x22D3EE
    elif score >= 65:
        color = 0xF5B14C
    else:
        color = 0x8B9BB0

    def field(name, value, inline=True):
        return {"name": name, "value": f"{value}", "inline": inline}

    price = product.get("price")
    roi = product.get("oa_roi")
    profit = product.get("oa_profit")
    fields = [
        field("ASIN", f"`{asin}`"),
        field("Price", f"${price:.2f}" if isinstance(price, (int, float)) else "?"),
        field("BSR", f"{product.get('sales_rank', '?')}"),
        field("Est. sales/mo", product.get("est_sales", "?")),
        field("Offers", product.get("offers", "?")),
        field("Score", f"**{score}/100**"),
    ]
    if isinstance(roi, (int, float)):
        fields.append(field("Est. ROI", f"{roi*100:.0f}%"))
    if isinstance(profit, (int, float)):
        fields.append(field("Est. profit/unit", f"${profit:.2f}"))
    margin = product.get("margin_est")
    if isinstance(margin, (int, float)):
        fields.append(field("Est. net margin", f"{margin*100:.0f}%"))
    fields.append(field("Marketplace", config.KEEPA_DOMAIN))

    risks = product.get("risks") or []
    if risks:
        fields.append(field("⚠ Risks", "\n".join(f"• {r}" for r in risks[:6]), inline=False))

    # Explain-why: every named scoring adjustment with its point delta (scoring.explain_oa).
    adjustments = ((product.get("explanation") or {}).get("adjustments")) or []
    if adjustments:
        lines = [f"• {a['name']} ({a['points']:+.0f}): {a['reason']}" for a in adjustments[:6]]
        fields.append(field("Why (adjustments)", "\n".join(lines)[:1024], inline=False))

    model_ver = "rule+model" if product.get("model_proba") is not None else "rule-only"

    return {
        "title": (product.get("title") or f"Candidate {asin}")[:240],
        "url": AMAZON_DP.format(asin=asin),
        "description": ("**Why it's interesting:** " + product.get("reason", ""))[:1024],
        "color": color,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": f"FBA Scout · {model_ver} · estimates — verify in Seller Central"},
    }


def post_pick(product: Dict[str, Any], webhook_url: Optional[str] = None,
              session: Optional[requests.Session] = None,
              max_retries: int = 3) -> bool:
    """Post a single product as a rich embed to the "scout_picks" stream (or directly to
    `webhook_url` if explicitly given — a legacy/manual override that bypasses stream
    resolution). `max_retries` is unused now (the router does exactly one 429 retry) — kept
    as a parameter for call-site compatibility."""
    embed = _embed_for(product)
    content = f"<{KEEPA_PRODUCT.format(asin=product.get('asin', '?'))}>"
    if webhook_url:
        return discord_router.send_to_url(webhook_url, embed, username="FBA Scout",
                                          session=session, content=content)
    return discord_router.send("scout_picks", embed, username="FBA Scout",
                               session=session, content=content)


def post_picks(products: List[Dict[str, Any]], webhook_url: Optional[str] = None,
               delay: float = 1.0) -> int:
    """Post several picks. Routes through the "scout_picks" stream, batched into as few
    Discord messages as possible (discord_router's 10-embeds-per-message limit) — returns the
    full count on success, 0 if the batch send failed (a partial-chunk failure inside a large
    batch is not separately counted; this is a simplification, not per-embed granularity).
    An explicit `webhook_url` keeps the old one-embed-per-message + `delay` behavior, for
    manual/legacy direct use."""
    if not products:
        return 0
    if webhook_url:
        sess = requests.Session()
        sent = 0
        for p in products:
            if post_pick(p, webhook_url=webhook_url, session=sess):
                sent += 1
            time.sleep(delay)  # be polite; webhooks allow ~30 msgs/min
        return sent
    embeds = [_embed_for(p) for p in products]
    ok = discord_router.send("scout_picks", embeds, username="FBA Scout")
    return len(products) if ok else 0


if __name__ == "__main__":
    # quick smoke test of the embed shape (won't post unless "scout_picks" or the fallback
    # webhook actually resolves — checks discord_router directly, not the legacy single-var
    # config.have_discord(), which doesn't know about the per-channel routing).
    demo = {
        "asin": "B0EXAMPLE0", "title": "Demo Silicone Stretch Lids (12-pack)",
        "price": 18.99, "est_sales": 410, "reviews": 230, "rating": 4.2,
        "margin_est": 0.29, "blended_score": 83.0,
        "reason": "Demo reason string — not a real product.",
    }
    if discord_router._resolve_url("scout_picks"):
        print("Posting demo embed:", post_pick(demo))
    else:
        import json
        print("No scout_picks webhook (or fallback) configured; embed preview:")
        print(json.dumps(_embed_for(demo), indent=2))
