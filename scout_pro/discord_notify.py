"""
discord_notify.py — outbound product-lead alerts via Discord webhook.

Webhooks need no bot token. Each alert carries the paper's required fields: score,
reason summary, projected margin, competition summary, compliance-warning status,
calibrated confidence, model version, and a deep link back. Parses 429 rate-limit
responses and backs off rather than hard-coding timing.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

import config

AMAZON_DP = "https://www.amazon.com/dp/{asin}"
KEEPA_PRODUCT = "https://keepa.com/#!product/1-{asin}"


def _embed(p: Dict[str, Any]) -> Dict[str, Any]:
    asin = p.get("asin", "?")
    score = p.get("blended_score", p.get("rule_score", 0)) or 0
    proba = p.get("proba")
    color = 0x36D399 if score >= 85 else 0x22D3EE if score >= 75 else 0xF5B14C if score >= 65 else 0x8B9BB0

    def field(n, v, inline=True):
        return {"name": n, "value": f"{v}", "inline": inline}

    price = p.get("price")
    margin = p.get("margin_est")
    fields = [
        field("ASIN", f"`{asin}`"),
        field("Price", f"${price:.2f}" if isinstance(price, (int, float)) else "?"),
        field("Est. sales/mo", int(p.get("est_sales") or 0)),
        field("Proj. margin", f"{margin*100:.0f}%" if isinstance(margin, (int, float)) else "?"),
        field("Score", f"**{score}/100**"),
        field("Confidence", f"calibrated {proba:.2f}" if isinstance(proba, (int, float)) else "rule-only"),
    ]
    fields.append(field("Competition", f"{int(p.get('offer_count') or 0)} offers · "
                                       f"{int(p.get('review_count') or 0)} reviews · {p.get('rating','?')}★"))
    compliance = p.get("compliance_status", "clear")
    fields.append(field("Compliance", "⚠ " + compliance if compliance != "clear" else "✅ clear"))
    if p.get("expected_units") is not None:
        fields.append(field("Model units (P50)", int(p["expected_units"])))

    model_ver = p.get("model_version", "rule+model" if proba is not None else "rule-only")
    return {
        "title": (p.get("title") or f"Candidate {asin}")[:240],
        "url": AMAZON_DP.format(asin=asin),
        "description": ("**Why it's interesting:** " + (p.get("reason") or ""))[:1024],
        "color": color,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": f"scout_pro · {model_ver} · estimates — verify in Seller Central"},
    }


def post_pick(p: Dict[str, Any], webhook_url: Optional[str] = None,
              session: Optional[requests.Session] = None, max_retries: int = 3) -> bool:
    url = webhook_url or config.DISCORD_WEBHOOK_URL
    if not url:
        raise ValueError("No DISCORD_WEBHOOK_URL set (see .env).")
    sess = session or requests
    payload = {"username": "FBA Scout Pro", "embeds": [_embed(p)],
               "content": f"<{KEEPA_PRODUCT.format(asin=p.get('asin','?'))}>"}
    for _ in range(max_retries):
        resp = sess.post(url, json=payload, timeout=15)
        if resp.status_code == 429:
            try:
                retry = float(resp.json().get("retry_after", 1.0))
            except Exception:
                retry = 1.0
            time.sleep(retry + 0.25)
            continue
        if 200 <= resp.status_code < 300:
            return True
        print(f"[discord] HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    return False


def post_picks(products: List[Dict[str, Any]], webhook_url: Optional[str] = None,
               delay: float = 1.0) -> int:
    sess = requests.Session()
    sent = 0
    for p in products:
        if post_pick(p, webhook_url=webhook_url, session=sess):
            sent += 1
        time.sleep(delay)
    return sent


if __name__ == "__main__":
    demo = {"asin": "B0EXAMPLE0", "title": "Demo product", "price": 24.99, "est_sales": 410,
            "review_count": 220, "rating": 4.2, "offer_count": 7, "margin_est": 0.29,
            "blended_score": 83.0, "proba": 0.81, "compliance_status": "clear",
            "reason": "demo reason"}
    if config.have_discord():
        print("posted:", post_pick(demo))
    else:
        import json
        print(json.dumps(_embed(demo), indent=2))
