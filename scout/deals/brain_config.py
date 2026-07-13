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


def d3_enabled() -> bool:
    """Reads the `dealFinder.d3Enabled` flag from ai-brain.json — a PRE-BUILT safety switch for
    Prompt D3 (deal-first, gate-checked lead creation), reserved ahead of that mechanism actually
    existing.

    CORRECTED (code review, 2026-07-13 — a fabricated-build finding): Prompt D3 itself has NOT
    been built. There is no `_create_deal_first_lead()` (or any deal-first lead-creation code)
    anywhere in this codebase — see scout/deals/matcher.py's module docstring ("Prompt D3's
    runner integration ... OUT OF SCOPE this session") and scout/db.py's update_lead_source()
    docstring ("deal-first LEAD CREATION is out of scope here"). As of this writing this function
    has ZERO call sites in the repo (matcher.py, db.py, scoring.py, run_daily.py, or anywhere
    else) — nothing reads it. That means BOTH `true` and `false` are currently indistinguishable
    no-ops: this is dead code, not a verified-safe, exercised gate. Do not cite this function or
    its docstring as evidence that deal-first lead creation exists, was reviewed, or was tested.

    When Prompt D3's real write path is eventually designed and built (via fba-architect/
    fba-coder, with an adversarial hard-gate-bypass review before it ever ships), that new code
    MUST call this function and refuse to create a lead when it returns False — that real call
    site is what will make this flag meaningful. Until then, treat `d3Enabled` as inert."""
    return bool(deal_finder_block().get("d3Enabled", False))


def discount_stack(retailer: str) -> Dict[str, float]:
    """Manually-maintained cashback/gift-card discount for a retailer (no API exists for
    these rates — see ai-brain.json dealFinder.discountStack's source note). A retailer with
    no entry yet, or explicit nulls, means "no stack known" -> 0%, never a fabricated default.

    Matched case-insensitively (code review, 2026-07-13): the brain's discountStack keys are
    hand-typed ("Walmart", "Best Buy", ...) while a `retailer` value at the call site can come
    from a source connector or normalize.guess_retailer(), whose casing isn't guaranteed to
    match exactly — an exact-string miss here silently returns "no stack known" (0%) rather
    than erroring, which would understate a lead's real profit/ROI with no signal it happened."""
    stack_block = deal_finder_block().get("discountStack", {}) or {}
    retailer_key = (retailer or "").strip().lower()
    stack = {}
    for key, value in stack_block.items():
        if isinstance(value, dict) and key.strip().lower() == retailer_key:
            stack = value
            break
    return {
        "cashback_pct": stack.get("cashbackPct") or 0.0,
        "giftcard_pct": stack.get("giftCardPct") or 0.0,
    }
