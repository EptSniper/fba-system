"""
brands.py — brand knowledge that feeds scout_pro's OA-mode gates/scoring.

Mirrors scout/brands.py so both systems apply the same brand discipline from
the same source of truth. Seeded from the transcripts and
../learning-hub/playbooks/brands-and-sources.md.

Two jobs:
  1. HARD-EXCLUDE brands that are hard-gated / IP-aggressive for beginners
     (used by gates.oa_hard_gates / scoring's OA path).
  2. Give friendly brands a small score nudge.

Keep this list in sync with the knowledge base as we learn more (mentor + transcripts).
"""
from __future__ import annotations

# OA-friendly, resellable name brands repeatedly cited as winners in the transcripts.
OA_FRIENDLY_BRANDS = [
    "Jellycat", "Crocs", "Yeti", "Stanley", "Crayola", "Elmer's", "Monster Jam",
    "LEGO", "Hot Wheels", "Pokemon", "Sunny Angels", "Owala", "Gap", "Nautica",
    "Carter's", "Under Armour", "New Balance", "Hoka", "Mrs. Meyer's", "Native",
    "Milwaukee", "DJI", "Fancy Feast", "Makeup by Mario", "Puma", "Cuddle Duds",
    "Stafford", "Frontier Co-op", "Tonies",
]

# Hard-gated for beginners and/or known for aggressive IP complaints. Conservative
# on purpose — better to skip than risk account health. Edit as the mentor advises.
AVOID_BRANDS = [
    "Nike", "Adidas", "Jordan", "Yeezy", "Apple", "Sony", "Disney",
]


# SINGLE SOURCE OF TRUTH: if learning-hub/data/ai-brain.json exists, its brand lists
# override the defaults above. That file is also read by scout/brands.py and the
# control center — so when Mehmet feeds Claude new info and the brain is updated,
# every consumer updates from one place. Falls back to the built-in lists if the
# file is absent.
def _load_from_brain():
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "learning-hub", "data", "ai-brain.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            b = json.load(f).get("brands", {})
        return b.get("friendly") or None, b.get("avoid") or None
    except Exception:
        return None, None


_brain_friendly, _brain_avoid = _load_from_brain()
if _brain_friendly:
    OA_FRIENDLY_BRANDS = _brain_friendly
if _brain_avoid:
    AVOID_BRANDS = _brain_avoid


def _norm(b) -> str:
    return (b or "").strip().lower()


def _tokens(b) -> set:
    return set(_norm(b).replace("-", " ").replace(".", " ").split())


def is_avoided(brand) -> bool:
    """True if the brand is hard-gated / IP-risky for beginners."""
    if not brand:
        return False
    b, toks = _norm(brand), _tokens(brand)
    return any(_norm(a) == b or _norm(a) in toks for a in AVOID_BRANDS)


def is_friendly(brand) -> bool:
    """True if the brand is on our known-good OA list."""
    if not brand:
        return False
    b = _norm(brand)
    return any(b == _norm(f) or b.startswith(_norm(f) + " ") for f in OA_FRIENDLY_BRANDS)


def seed_brands(limit: int | None = None) -> list:
    """Known-good brands to aim discovery at."""
    return OA_FRIENDLY_BRANDS[:limit] if limit else list(OA_FRIENDLY_BRANDS)
