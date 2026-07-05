"""
scout/deals/registry.py — loads and validates the Top-100 OA deal-source registry
(learning-hub/data/top100-sources.json), the SINGLE source for the nightly deal watch
(TOP100_DEAL_WATCH_PLAN.md Prompt T1).

The registry is DATA, not code: 100 ranked stores in 3 tiers, each with a free/ToS-clean
detection method (a `detect` list of `code:arg` strings), cancel-risk/IP flags, plus a
separate `aggregates` list (Slickdeals firehose, Reddit/DealNews RSS, Woot API). This module
turns that data into a validated, queryable object the generic adapters consume — it never
fetches anything itself.

THE ONE NON-NEGOTIABLE (guardrails.md — humans approve purchases; hard gates outside ML):
an `AVOID`-flagged entry (a brand on ai-brain.json's avoid list, e.g. Nike/adidas) is
SIGNAL-ONLY. Its deals may appear in the digest as market signal, but it must NEVER become a
hint, a buy candidate, or a source the scout is steered toward. `non_avoid_entries()` and
`assert_no_avoid()` enforce that here so the hint-derivation path (run_watch) and the
consumption path (discovery_hints) can both lean on one guarantee instead of re-checking.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "..", "..", "learning-hub", "data", "top100-sources.json")

TIERS = ("tier1", "tier2", "tier3")
# The detection-method vocabulary the registry's own $comment documents. Anything else is a
# typo that would silently route an entry to no adapter.
DETECT_CODES = {"sd-rss", "clr", "api", "aff", "nl", "none"}
KNOWN_FLAGS = {"C", "AVOID", "VERIFY", "IP"}
REQUIRED_ENTRY_FIELDS = {"rank", "name", "domain", "cats", "edge", "detect", "flags"}

# detect codes that a machine can actually FETCH (the rest — nl/none — are manual/human-only,
# so an entry whose ONLY detect codes are those is not machine-collectable).
FETCHABLE_CODES = {"sd-rss", "clr", "api", "aff"}


def load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    """Read + parse the registry JSON. Raises on a missing/unparseable file — the deal watch
    genuinely cannot run without its single source, so this is a hard failure, not a
    degrade-to-empty (unlike the network adapters, where empty is a valid 'nothing new')."""
    with open(path or DEFAULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_detect(code_str: str) -> Tuple[str, Optional[str]]:
    """'sd-rss:walmart' -> ('sd-rss', 'walmart'); 'nl' -> ('nl', None); 'clr:https://x' ->
    ('clr', 'https://x'). Splits on the FIRST colon only so URL args keep their own colons."""
    if ":" in code_str:
        code, arg = code_str.split(":", 1)
        return code.strip(), arg.strip()
    return code_str.strip(), None


def all_entries(reg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every tier's entries flattened, in tier-then-rank order."""
    out: List[Dict[str, Any]] = []
    for tier in TIERS:
        out.extend(reg.get(tier, []) or [])
    return out


def entry_is_avoid(entry: Dict[str, Any]) -> bool:
    return "AVOID" in (entry.get("flags") or [])


def non_avoid_entries(reg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every entry that is NOT AVOID-flagged — the only entries allowed to steer sourcing
    (produce hints / be a buy candidate). AVOID entries are excluded here at the source."""
    return [e for e in all_entries(reg) if not entry_is_avoid(e)]


def assert_no_avoid(entries: List[Dict[str, Any]]) -> None:
    """HARD gate (TOP100_DEAL_WATCH_PLAN.md T1): raise if any AVOID-flagged entry reached a
    sourcing path. Called by the hint-derivation code so an AVOID brand can never silently
    become a hint even if an upstream filter regresses — belt to non_avoid_entries()'s
    suspenders."""
    offenders = [e.get("name") for e in entries if entry_is_avoid(e)]
    if offenders:
        raise AssertionError(
            f"AVOID-flagged sources reached a sourcing path (must be signal-only, never "
            f"sourced): {offenders}"
        )


def fetchable_entries(reg: Dict[str, Any], tier: Optional[str] = None) -> List[Dict[str, Any]]:
    """Entries that have at least one machine-fetchable detect code (sd-rss/clr/api/aff).
    Includes AVOID entries — their deals are collectable as market signal; the AVOID gate is
    applied later, at hint derivation, NOT at collection (see the module docstring)."""
    src = reg.get(tier, []) if tier else all_entries(reg)
    out = []
    for e in src or []:
        codes = {parse_detect(d)[0] for d in (e.get("detect") or [])}
        if codes & FETCHABLE_CODES:
            out.append(e)
    return out


def detect_args(entry: Dict[str, Any], code: str) -> List[str]:
    """Every arg for a given detect code on an entry (e.g. all 'clr:' URLs), skipping the
    placeholder 'VERIFY' sentinel (an unverified URL/network — not a real target to hit)."""
    out = []
    for d in entry.get("detect") or []:
        c, arg = parse_detect(d)
        if c == code and arg and arg != "VERIFY":
            out.append(arg)
    return out


def validate(reg: Dict[str, Any]) -> List[str]:
    """Structural + vocabulary checks. Returns a list of human-readable problems ([] == valid)
    — callers decide whether to hard-fail (run_watch does) or just warn. Deliberately does NOT
    raise, so a caller can report ALL problems at once instead of dying on the first."""
    problems: List[str] = []

    for tier in TIERS:
        if tier not in reg:
            problems.append(f"missing tier '{tier}'")
    if reg.get("$comment") is None:
        problems.append("missing '$comment' provenance block")

    entries = all_entries(reg)
    if len(entries) != 100:
        problems.append(f"expected 100 entries, found {len(entries)}")

    ranks = [e.get("rank") for e in entries]
    seen_ranks = set()
    for r in ranks:
        if r in seen_ranks:
            problems.append(f"duplicate rank {r}")
        seen_ranks.add(r)
    missing_ranks = sorted(set(range(1, len(entries) + 1)) - {r for r in ranks if isinstance(r, int)})
    if missing_ranks and len(entries) == 100:
        problems.append(f"missing ranks: {missing_ranks}")

    domains = {}
    for e in entries:
        name = e.get("name", "<unnamed>")
        missing_fields = REQUIRED_ENTRY_FIELDS - set(e.keys())
        if missing_fields:
            problems.append(f"'{name}' missing field(s): {sorted(missing_fields)}")
        for fl in e.get("flags") or []:
            if fl not in KNOWN_FLAGS:
                problems.append(f"'{name}' has unknown flag '{fl}'")
        for d in e.get("detect") or []:
            code, _ = parse_detect(d)
            if code not in DETECT_CODES:
                problems.append(f"'{name}' has unknown detect code '{code}' (in '{d}')")
        dom = e.get("domain")
        if dom:
            if dom in domains:
                problems.append(f"duplicate domain '{dom}' ({domains[dom]} and {name})")
            domains[dom] = name

    return problems
