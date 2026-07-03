"""
scout/deals/normalize.py — attribute extraction for the Deal Finder (Deal Finder Build Plan,
2026-07-02, Prompt D1 / matching cascade step 1).

Pack-count mismatch (retail 1-pack matched to an Amazon 2-pack) is the #1 documented OA
matching killer (the build plan's research citations). Extracting {brand, core_title,
pack_count, size_value, size_unit, variant} from BOTH sides of a match candidate BEFORE
comparing defuses most of it deterministically with plain regex — the long tail that regex
can't parse falls through to an optional LLM fallback (wired by the matcher in Prompt D2,
not here; this module never calls a model itself).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

# Ordered so more specific phrasings ("pack of N") are tried before bare "N-pack"/"Npk" forms
# that could otherwise false-match a stray number elsewhere in a title.
_PACK_PATTERNS = [
    re.compile(r'\bpack\s+of\s+(\d+)\b', re.I),
    re.compile(r'\b(\d+)\s*-?\s*pack\b', re.I),
    re.compile(r'\b(\d+)\s*-?\s*pk\b', re.I),
    re.compile(r'\b(\d+)\s*-?\s*ct\b', re.I),
    re.compile(r'\b(\d+)\s*count\b', re.I),
]

_SIZE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(fl\.?\s?oz|fl\.?\s?ounces?|ounces?|oz\.?|ml|milliliters?|liters?|ltr|l\b|'
    r'pounds?|lbs?\.?|grams?|g\b|kg|kilograms?)',
    re.I,
)

_UNIT_NORMALIZE = {
    "fl oz": "fl_oz", "fl. oz": "fl_oz", "fl.oz": "fl_oz", "fl ounce": "fl_oz",
    "fl ounces": "fl_oz", "fl. ounce": "fl_oz", "fl. ounces": "fl_oz",
    "oz": "oz", "oz.": "oz", "ounce": "oz", "ounces": "oz",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "ltr": "l",
    "lb": "lb", "lbs": "lb", "lbs.": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
}


def extract_pack_count(title: str) -> Optional[int]:
    """The multipack count if the title states one, else None (meaning "not stated" — the
    caller decides whether that defaults to 1, since a bare title usually IS a single unit
    but an absence isn't proof of it)."""
    for pat in _PACK_PATTERNS:
        m = pat.search(title)
        if m:
            try:
                n = int(m.group(1))
            except ValueError:
                continue
            if n > 0:
                return n
    return None


def extract_size(title: str) -> tuple[Optional[float], Optional[str]]:
    """(value, normalized_unit) of the first size/weight/volume mention, or (None, None)."""
    m = _SIZE_RE.search(title)
    if not m:
        return None, None
    try:
        value = float(m.group(1))
    except ValueError:
        return None, None
    unit_raw = re.sub(r'\.', '', m.group(2).lower()).strip()
    unit_raw = re.sub(r'\s+', ' ', unit_raw)
    unit = _UNIT_NORMALIZE.get(unit_raw) or _UNIT_NORMALIZE.get(unit_raw.replace(" ", ""))
    return value, unit


def core_title(title: str, brand: Optional[str] = None) -> str:
    """Title with pack/size phrases and the brand name stripped, for downstream embedding/
    cosine comparison — two listings for "the same" product often differ only in these
    boilerplate bits, which otherwise dilute the similarity signal."""
    t = title
    for pat in _PACK_PATTERNS:
        t = pat.sub(" ", t)
    t = _SIZE_RE.sub(" ", t)
    if brand:
        t = re.sub(re.escape(brand), " ", t, flags=re.I)
    t = re.sub(r'[,\-|]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extract_attributes(title: str, brand: Optional[str] = None,
                       llm_fallback: Optional[Callable[[str, Optional[str]], Optional[Dict[str, Any]]]] = None
                       ) -> Dict[str, Any]:
    """The full attribute set for one side of a match candidate.

    pack_count defaults to 1 when the title doesn't state one (the common case — most
    listings are single units). size_value/size_unit stay None when absent rather than
    guessing. llm_fallback is a pluggable hook (Claude Haiku structured extraction, wired by
    the matcher in Prompt D2) invoked ONLY when regex found neither a pack count nor a size —
    the long tail regex can't parse. Any llm_fallback error is swallowed; a failed fallback
    degrades to the regex-only result rather than crashing the match.
    """
    pack_count = extract_pack_count(title)
    size_value, size_unit = extract_size(title)
    attrs: Dict[str, Any] = {
        "brand": brand,
        "core_title": core_title(title, brand),
        "pack_count": pack_count if pack_count is not None else 1,
        "size_value": size_value,
        "size_unit": size_unit,
        "variant": None,
    }
    if pack_count is None and size_value is None and llm_fallback is not None:
        try:
            fallback = llm_fallback(title, brand)
        except Exception:
            fallback = None
        if isinstance(fallback, dict):
            for key in ("brand", "core_title", "pack_count", "size_value", "size_unit", "variant"):
                if fallback.get(key) is not None:
                    attrs[key] = fallback[key]
    return attrs
