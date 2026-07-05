"""
predictions.py — the OA scorer's forward-looking claims, made falsifiable (Code Review
2026-07-04 ask). scoring.py's soft signals are all implicitly FORECASTS: a price-spike
adjustment is a bet the price reverts; offers-rising is a bet the price tanks; every
candidate's est_sales is a bet on demand holding. Nothing recorded these as claims to check
later, so there was no way to know if the scorer's own instincts are actually right. This
module writes one row per predictable signal when a candidate is scored, then scores MATURED
predictions against fresh Keepa stats.

KEEPA-GATED SCAFFOLD: recording a prediction is pure bookkeeping (no Keepa call, works today).
Scoring a matured prediction needs a fresh Keepa re-fetch per ASIN, which needs a paid
KEEPA_KEY (HUMAN_TODO.md item #2) — not configured yet. score_matured_predictions() honestly
reports "unavailable" rather than fabricating a hit rate; nothing here pretends this is live.

Reuses db.py's enabled()/_headers()/_post() — this is a second table in the SAME Supabase
project, not a new connection story.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import db

log = logging.getLogger(__name__)

# Days from made_at until each claim type matures — chosen to match reasoning already in this
# codebase (FBA's ~2-week fulfillment delay is cited elsewhere for why a price spike is brutal;
# offer-count shifts play out on a similar timescale; monthly sales velocity needs a full month
# to fairly re-check).
HORIZON_DAYS = {"price_reversion": 14, "offer_trend": 14, "velocity": 30}


def _price_reversion_claim(p: Dict[str, Any], explanation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A price-spike or price-caution adjustment is a bet the price reverts toward its 90-day
    average. threshold = avg_price_90 (the level we're claiming it reverts toward)."""
    names = {a["name"] for a in explanation.get("adjustments", [])}
    avg_price_90 = p.get("avg_price_90")
    if not avg_price_90 or avg_price_90 <= 0:
        return None
    if "price-spike" in names:
        return {"claim_type": "price_reversion", "threshold": avg_price_90,
               "context": {"signal": "price-spike", "price_at_prediction": p.get("price")}}
    if "price-caution" in names:
        return {"claim_type": "price_reversion", "threshold": avg_price_90,
               "context": {"signal": "price-caution", "price_at_prediction": p.get("price")}}
    return None


def _offer_trend_claim(p: Dict[str, Any], explanation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """offers-rising / ip-cliff is a bet the offer count keeps moving the same direction (more
    sellers piling in, or the cliff not recovering). threshold = current offer count — the
    claim is whether the fresh count has moved further AWAY from the 90-day average, not back
    toward it."""
    names = {a["name"] for a in explanation.get("adjustments", [])}
    offers = p.get("offers")
    if offers is None:
        return None
    if "offers-rising" in names:
        return {"claim_type": "offer_trend", "threshold": offers,
               "context": {"signal": "offers-rising", "avg_offers_90": p.get("avg_offers_90")}}
    if explanation.get("hard_reject") and "offer count collapsed" in (explanation["hard_reject"] or "").lower():
        return {"claim_type": "offer_trend", "threshold": offers,
               "context": {"signal": "ip-cliff", "avg_offers_90": p.get("avg_offers_90")}}
    return None


def _velocity_claim(p: Dict[str, Any], explanation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Every scored candidate implicitly bets its estimated monthly sales holds — threshold is
    a 70%-of-estimate floor (a full re-fetch a month later showing a HUGE drop is the failure
    mode this actually wants to catch, not sub-day noise)."""
    est_sales = p.get("est_sales")
    if est_sales is None or est_sales <= 0:
        return None
    return {"claim_type": "velocity", "threshold": round(est_sales * 0.7, 1),
           "context": {"est_sales_at_prediction": est_sales}}


_CLAIM_BUILDERS: List[Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]] = [
    _price_reversion_claim, _offer_trend_claim, _velocity_claim,
]


def build_predictions_for(p: Dict[str, Any], explanation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure function: derives 0-3 falsifiable claims from one scored candidate's facts +
    explain_oa() output. No I/O — testable without Supabase."""
    claims = []
    for builder in _CLAIM_BUILDERS:
        claim = builder(p, explanation)
        if claim:
            claim["horizon_days"] = HORIZON_DAYS[claim["claim_type"]]
            claims.append(claim)
    return claims


def record_predictions_for(asin: str, lead_id: Optional[int], p: Dict[str, Any],
                           explanation: Dict[str, Any]) -> int:
    """Writes every derived claim as a predictions row. Every pipeline verdict (review AND
    pass) gets checked — a pass candidate's price NOT reverting is just as informative for
    calibrating the scorer's own soft signals as a review candidate's price reverting.
    Returns the count actually written; a disabled/misconfigured Supabase writes nothing and
    returns 0 (never raises — this must never block a scoring cycle)."""
    if not db.enabled():
        return 0
    claims = build_predictions_for(p, explanation)
    written = 0
    for claim in claims:
        row = {"asin": asin, "lead_id": lead_id, **claim}
        if db._post("predictions", row, migration_only_fields={"lead_id", "context"}) is not None:
            written += 1
    return written


def fetch_unresolved(matured_only: bool = True) -> Optional[List[Dict[str, Any]]]:
    """Unresolved prediction rows, optionally filtered to only those past their horizon.
    None (not []) if Supabase is unavailable or the query fails."""
    if not db.enabled():
        return None
    try:
        import requests
        query = "predictions?select=*&resolved_at=is.null&order=made_at.asc"
        r = requests.get(f"{db.SUPA}/rest/v1/{query}", headers=db._headers(), timeout=15)
        r.raise_for_status()
        rows = r.json() or []
    except Exception as e:
        log.warning("predictions.fetch_unresolved failed: %s", e)
        return None
    if not matured_only:
        return rows
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    matured = []
    for row in rows:
        made_at = dt.datetime.fromisoformat(row["made_at"].replace("Z", "+00:00"))
        if (now - made_at).days >= row["horizon_days"]:
            matured.append(row)
    return matured


def score_matured_predictions(fetch_fresh_stats: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Scores every matured, unresolved prediction against a fresh Keepa re-fetch.

    `fetch_fresh_stats(asin) -> {"price": ..., "offers": ..., "est_sales": ...} | None` is
    injected rather than hardcoded to keepa_client — keeps this module Keepa-call-free and
    trivially mockable in tests. Without a real KEEPA_KEY there is no live fetch function to
    pass in, so this honestly reports "unavailable" — it never fabricates a hit rate from
    stale or synthetic data."""
    if fetch_fresh_stats is None:
        return {"status": "unavailable",
               "reason": "No live Keepa re-fetch function available (KEEPA_KEY not configured — "
                        "see HUMAN_TODO.md item #2).", "scored": 0, "hits": 0}
    if not db.enabled():
        return {"status": "unavailable", "reason": "Supabase not configured.", "scored": 0, "hits": 0}

    matured = fetch_unresolved(matured_only=True)
    if matured is None:
        return {"status": "error", "reason": "Could not read the predictions table.", "scored": 0, "hits": 0}
    if not matured:
        return {"status": "ok", "scored": 0, "hits": 0, "by_claim_type": {}}

    by_claim_type: Dict[str, Dict[str, int]] = {}
    hits = 0
    for row in matured:
        fresh = fetch_fresh_stats(row["asin"])
        if fresh is None:
            continue
        actual = _actual_value_for(row["claim_type"], fresh)
        if actual is None:
            continue
        hit = _resolve_hit(row["claim_type"], row["threshold"], actual)
        _mark_resolved(row["id"], hit, actual)
        bucket = by_claim_type.setdefault(row["claim_type"], {"scored": 0, "hits": 0})
        bucket["scored"] += 1
        if hit:
            bucket["hits"] += 1
            hits += 1
    scored_total = sum(b["scored"] for b in by_claim_type.values())
    return {"status": "ok", "scored": scored_total, "hits": hits, "by_claim_type": by_claim_type}


def _actual_value_for(claim_type: str, fresh: Dict[str, Any]) -> Optional[float]:
    return {"price_reversion": fresh.get("price"), "offer_trend": fresh.get("offers"),
           "velocity": fresh.get("est_sales")}.get(claim_type)


def _resolve_hit(claim_type: str, threshold: float, actual: float) -> bool:
    if claim_type == "price_reversion":
        return actual <= threshold * 1.1  # reverted to within 10% of the 90-day average
    if claim_type == "offer_trend":
        return actual >= threshold  # count kept moving the same direction (didn't recover)
    if claim_type == "velocity":
        return actual >= threshold  # sales held at/above the 70%-of-estimate floor
    return False


def _mark_resolved(prediction_id: int, hit: bool, actual_value: float) -> None:
    if not db.enabled():
        return
    try:
        import requests
        requests.patch(
            f"{db.SUPA}/rest/v1/predictions?id=eq.{prediction_id}",
            headers=db._headers({"Prefer": "return=minimal"}),
            json={"resolved_at": "now()", "outcome": "hit" if hit else "miss", "actual_value": actual_value},
            timeout=15,
        )
    except Exception as e:
        log.warning("predictions._mark_resolved failed (id=%s): %s", prediction_id, e)


def hit_rate_summary(fetch_fresh_stats: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None) -> str:
    """One-paragraph markdown summary for ops-report.md. Honestly empty until Keepa exists."""
    result = score_matured_predictions(fetch_fresh_stats)
    if result["status"] != "ok":
        return f"- **Prediction hit rates**: not available — {result['reason']}"
    if result["scored"] == 0:
        return "- **Prediction hit rates**: no matured predictions to score yet."
    lines = [f"- **Prediction hit rates** ({result['scored']} matured, {result['hits']} hit "
            f"= {100*result['hits']/result['scored']:.0f}%):"]
    for claim_type, bucket in sorted(result["by_claim_type"].items()):
        n = bucket["scored"]
        pct = 100 * bucket["hits"] / n if n else 0
        lines.append(f"  - `{claim_type}`: {bucket['hits']}/{n} = {pct:.0f}%")
    return "\n".join(lines)
