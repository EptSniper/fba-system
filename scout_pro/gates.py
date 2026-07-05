"""
gates.py — hard, rules-first business gates (compliance & viability).

The paper is explicit: build compliance and policy filters FIRST. These gates
REJECT a candidate regardless of any model score — they encode "never buy"
constraints (hazmat/restricted category, margin floor, severe offer crowding,
oversize, impossible lead time). A learned model should never override them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import brands
import config


def compliance_risk(row: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Return (risk in {0.0,1.0}, matched_terms). Scans title/category/brand for
    forbidden substrings (hazmat, lithium, supplement, weapon, ...). Treat
    suspicious matches as a RISK signal, never a positive growth signal.
    """
    terms = [t.strip() for t in config.GATES["forbidden_category_terms"] if t.strip()]
    haystack = " ".join(str(row.get(k, "") or "") for k in ("title", "category_id", "brand")).lower()
    hits = [t for t in terms if t and t in haystack]
    return (1.0 if hits else 0.0), hits


def hard_gates(feature_row: Dict[str, Any], snapshot_row: Dict[str, Any] | None = None,
               lead_time_days: float | None = None) -> Tuple[bool, List[str]]:
    """
    Evaluate non-negotiable gates. Returns (passed, rejection_reasons).
    passed=False => never alert/source, regardless of model probability.

    DELIBERATELY stricter than ../scout/scoring.py (Code Review 2026-07-02, Finding S14 — see
    README.md's "Deliberate divergences" section for the full rationale, not a bug to fix):
    margin here is a HARD reject at GATE_MARGIN_FLOOR, where scout/ scores ROI/profit as two of
    six soft signals; "grocery" is hard-blocked via GATE_FORBIDDEN_CATEGORIES by default, where
    scout/ explicitly allows it with a relaxed ROI bar (ai-brain.json's groceryMinRoi).
    """
    g = config.GATES
    reasons: List[str] = []
    snap = snapshot_row or {}

    margin = feature_row.get("margin_est")
    if margin is not None and margin < g["margin_floor"]:
        reasons.append(f"margin {margin*100:.0f}% < floor {g['margin_floor']*100:.0f}%")

    offers = feature_row.get("offer_count")
    if offers is not None and offers > g["max_offers"]:
        reasons.append(f"offer crowding {int(offers)} > {g['max_offers']}")

    weight = feature_row.get("weight_lb")
    if weight is not None and weight > g["max_weight_lb"]:
        reasons.append(f"weight {weight}lb > {g['max_weight_lb']}lb (oversize risk)")

    if lead_time_days is not None and lead_time_days > g["max_lead_time_days"]:
        reasons.append(f"lead time {lead_time_days}d > {g['max_lead_time_days']}d")

    risk, hits = compliance_risk({**snap, "title": snap.get("title", "")})
    if risk >= 1.0:
        reasons.append("compliance/restricted: " + ",".join(hits))

    return (len(reasons) == 0), reasons


# =============================================================================
# Online-Arbitrage (OA) hard gates — additive "OA mode" alongside hard_gates()
# above. Mirrors scout/scoring.py::oa_hard_reject() exactly (same order, same
# semantics): Amazon-holds-Buy-Box, Amazon-Buy-Box-share, avoid-brand, IP-cliff,
# missing-price. Kept OUTSIDE the trainable model per the project's non-negotiable
# "hard gates stay outside ML" rule. Callable from the same pre-model gate path
# as hard_gates() — call both before any ML scoring.
# =============================================================================
def _amazon_has_buybox(p: Dict[str, Any]) -> bool:
    seller = p.get("buybox_seller")
    return isinstance(seller, str) and seller == config.AMAZON_SELLER_ID


def _amazon_share(p: Dict[str, Any]) -> Optional[float]:
    """Amazon's Buy-Box win share (0-1) over the period, or None if unknown."""
    s = p.get("amazon_bb_share")
    return s if isinstance(s, (int, float)) and s >= 0 else None


def _amazon_rotates_buybox(p: Dict[str, Any]) -> bool:
    """True if Amazon wins the Buy Box at least OA_AMAZON_SHARE_MAX of the time
    (rotation) even when it isn't the current holder -> it keeps stealing sales."""
    s = _amazon_share(p)
    return bool(s is not None and s >= config.OA_AMAZON_SHARE_MAX)


def _ip_cliff(p: Dict[str, Any]) -> bool:
    """Approximate the IP-complaint 'cliff': a healthy listing whose offer count
    has COLLAPSED — e.g. 56 sellers -> 1 — and not recovered. Usually means the
    brand filed IP complaints; worse than a price drop because it dents account
    health. Heuristic from current offers far below a once-crowded 90-day average;
    always confirm on Keepa's all-time offer-count chart."""
    cur, avg = p.get("offers"), p.get("avg_offers_90")
    return bool(cur is not None and avg and avg >= 8 and cur <= 2)


def oa_hard_gates(p: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """OA hard gate — reasons to NEVER post an OA pick regardless of score.
    Mirrors scout/scoring.py::oa_hard_reject() checked in this exact order:
    (1) Amazon currently holds the Buy Box, (2) Amazon's Buy-Box win-share >=
    OA_AMAZON_SHARE_MAX, (3) brand is in the avoid-list, (4) IP-cliff fingerprint,
    (5) no price data at all. Returns (passed, rejection_reasons); passed=False
    means never alert/source regardless of model probability."""
    reasons: List[str] = []

    if _amazon_has_buybox(p):
        reasons.append("Amazon holds the Buy Box → can't compete")
        return False, reasons

    if _amazon_rotates_buybox(p):
        share = _amazon_share(p) or 0
        reasons.append(f"Amazon wins the Buy Box ~{share*100:.0f}% of the time → can't compete")
        return False, reasons

    if brands.is_avoided(p.get("brand")):
        reasons.append("Brand hard-gated / IP-risky for beginners")
        return False, reasons

    if _ip_cliff(p):
        reasons.append("Offer count collapsed (IP-complaint cliff) → account-health risk")
        return False, reasons

    price = p.get("price")
    if not price or price <= 0:
        reasons.append("No price data")
        return False, reasons

    return True, reasons
