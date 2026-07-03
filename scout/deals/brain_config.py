"""
scout/deals/brain_config.py — reads the Deal Finder's config from ai-brain.json's
`dealFinder` block. Same single-source-of-truth convention as scout/config.py's
_load_oa_criteria_from_brain(): both the scout and the control-center read the one file, so
feeding Claude new guidance updates both. Every reader here degrades to an empty dict/sane
default on any error — a missing or malformed brain file must never crash a source connector.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

_BRAIN_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "learning-hub", "data", "ai-brain.json")


def _load_brain() -> Dict[str, Any]:
    try:
        with open(_BRAIN_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def deal_finder_block() -> Dict[str, Any]:
    return _load_brain().get("dealFinder", {}) or {}


def source_config(name: str) -> Dict[str, Any]:
    """The `dealFinder.sources.<name>` block (feeds/categories/enabled/pollIntervalHours), or
    {} if the brain has none yet — callers fall back to their own hardcoded defaults."""
    return deal_finder_block().get("sources", {}).get(name, {}) or {}


def confidence_bands() -> Dict[str, float]:
    """Composite match-confidence routing thresholds (Build Plan sec 3, step 5):
    >= auto_accept -> straight to the scout's gates; [review, auto_accept) -> human review
    queue; below review -> discarded. Falls back to the plan's own defaults (0.90 / 0.60)."""
    bands = deal_finder_block().get("confidenceBands", {}) or {}
    return {
        "auto_accept": float(bands.get("autoAccept", 0.90)),
        "review": float(bands.get("review", 0.60)),
    }


def price_sanity_ratio() -> float:
    """If (Amazon price / retail deal price) exceeds this, suspect a pack/size mismatch
    rather than a genuine flip (Build Plan sec 3, step 5's price-sanity heuristic)."""
    ps = deal_finder_block().get("priceSanity", {}) or {}
    return float(ps.get("maxAmazonToRetailRatio", 3.0))


def discount_stack(retailer: str) -> Dict[str, float]:
    """Manually-maintained cashback/gift-card discount for a retailer (no API exists for
    these rates — see ai-brain.json dealFinder.discountStack's source note). A retailer with
    no entry yet, or explicit nulls, means "no stack known" -> 0%, never a fabricated default."""
    stack = deal_finder_block().get("discountStack", {}).get(retailer, {}) or {}
    return {
        "cashback_pct": stack.get("cashbackPct") or 0.0,
        "giftcard_pct": stack.get("giftCardPct") or 0.0,
    }
