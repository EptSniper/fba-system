"""
scout/harvest.py — the idle-token harvester (DATA_ENGINE_PLAN.md Prompt V0 #4).

DISABLED ON THE KEEPA PRO TRICKLE — and honestly so, not silently absent. The Pro plan generates
1 token/minute with a 60-token bank; there is no idle surplus to bank (the daily hint-led scan
already drinks the drip). So this module is built and unit-tested but gated OFF behind
ai-brain.json `learning.harvesterEnabled` (default false); enabled() returns a "blocked-on-
upgrade" status with an honest reason. It comes alive only after an upgrade to the 20/min API
tier, where daily generation vastly exceeds what the scan spends and the surplus is worth banking
as raw training data.

WHEN ENABLED it:
  * runs ONLY after the daily pipeline finishes (run_daily calls it last, gated on `not dry_run`);
  * reads the ACTUAL refill rate + tokensLeft off live Keepa telemetry (never assumes a tier) to
    size the day's budget as `learning.harvestTokenShare` of the OBSERVED daily generation;
  * walks a PRIORITY queue over the ASIN universe — (1) active leads, (2) hint brands,
    (3) friendly-brand Product Finder survivors, (4) breadth (watched categories) — enriching each
    ASIN, which archives the RAW Keepa response into the data lake automatically (the archiving is
    already wired into keepa_client.find_candidates/enrich — the harvester just drives them under
    a budget);
  * is RESUMABLE: a tiny JSON state file records the day's spend + which tiers are done, so a
    crashed or next-day resume picks up where it left off and never re-spends on finished tiers.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

import config
import datalake
import discovery_hints
import keepa_client

log = logging.getLogger("scout.harvest")

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
DEFAULT_HARVEST_TOKEN_SHARE = 0.4
_MINUTES_PER_DAY = 1440
# Enrich in Keepa's max batch of 100 ASINs/request (1 token each with our stats/rating/buybox mix
# billed per ASIN) — the same batching find_candidates/enrich already use.
_ENRICH_BATCH = 100


def _brain_learning() -> Dict[str, Any]:
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            return (json.load(f) or {}).get("learning") or {}
    except Exception:
        return {}


def enabled() -> bool:
    """OFF by default (Keepa Pro trickle has no idle surplus). Flipped on only when
    ai-brain.json learning.harvesterEnabled is true — i.e. after upgrading to the API tier."""
    return bool(_brain_learning().get("harvesterEnabled", False))


def harvest_token_share() -> float:
    """Fraction of the OBSERVED daily token generation the harvester may spend (brain
    learning.harvestTokenShare, default 0.4). Clamped to [0, 1]."""
    v = _brain_learning().get("harvestTokenShare", DEFAULT_HARVEST_TOKEN_SHARE)
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return DEFAULT_HARVEST_TOKEN_SHARE


def _state_path() -> str:
    return os.path.join(datalake.lake_dir(), "_harvest_state.json")


def _load_state(today: str) -> Dict[str, Any]:
    """Resume state for TODAY only — a state file from a prior day is treated as a fresh start
    (the day's budget resets at midnight UTC)."""
    try:
        with open(_state_path(), encoding="utf-8") as f:
            st = json.load(f) or {}
        if st.get("date") == today:
            return st
    except Exception:
        pass
    return {"date": today, "spent": 0, "done_tiers": [], "enriched": 0}


def _save_state(st: Dict[str, Any]) -> None:
    try:
        os.makedirs(datalake.lake_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        log.warning("harvest state save failed (non-fatal): %s", e)


def observed_daily_generation(api, refill_per_min: Optional[float] = None) -> Optional[int]:
    """Tokens generated per day at the OBSERVED refill rate (never an assumed tier). Reads the
    per-minute refill off live Keepa telemetry defensively — the keepa lib exposes it under
    version-varying attribute names — and multiplies by 1440. Returns None when the rate can't be
    read (so the caller refuses to guess a budget rather than inventing one)."""
    if refill_per_min is None:
        for attr in ("tokens_per_minute", "refill_rate", "tokenflow", "tokens_left_refill"):
            v = getattr(api, attr, None)
            if isinstance(v, (int, float)) and v > 0:
                refill_per_min = float(v)
                break
    if refill_per_min is None or refill_per_min <= 0:
        return None
    return int(refill_per_min * _MINUTES_PER_DAY)


def _dedupe_keep_order(*asin_lists: List[str]) -> List[str]:
    seen, out = set(), []
    for lst in asin_lists:
        for a in lst or []:
            if a and a not in seen:
                seen.add(a)
                out.append(a)
    return out


def _default_active_lead_asins() -> List[str]:
    """ASINs of leads still awaiting/under a human decision (verdict review/watch). Free — read
    from Supabase business memory; degrades to [] when Supabase is off or the read fails."""
    try:
        import db
        rows = db.leads_with_outcomes() or []
        return [r.get("asin") for r in rows
                if r.get("asin") and (r.get("verdict") in ("review", "watch") or not r.get("verdict"))]
    except Exception:
        return []


def build_priority_queue(
    api,
    limit: int,
    active_lead_asins: Optional[Callable[[], List[str]]] = None,
) -> List[Dict[str, Any]]:
    """The ordered work list. Each item is {"tier", "kind", "asins"|"seeds"}. Tiers, highest
    priority first:
      1. active leads   — explicit ASINs (re-pull the products a human is deciding on)
      2. hint brands    — brand seeds from the nightly deal watch's fresh hints
      3. friendly brands— our known-good brand rotation (Product Finder survivors)
      4. breadth        — watched categories (broad, lowest priority)
    Brand/category tiers carry SEEDS that expand to ASINs via Product Finder at run time (that
    expansion IS part of the harvest spend); the active-leads tier carries ASINs directly."""
    get_leads = active_lead_asins or _default_active_lead_asins
    queue: List[Dict[str, Any]] = []

    lead_asins = _dedupe_keep_order(get_leads())
    if lead_asins:
        queue.append({"tier": 1, "kind": "leads", "asins": lead_asins})

    hint_seeds = []
    try:
        hint_seeds = discovery_hints.hinted_brand_seeds() or []
    except Exception:
        hint_seeds = []
    if hint_seeds:
        queue.append({"tier": 2, "kind": "hint_brands", "seeds": hint_seeds})

    friendly = []
    try:
        import brands
        friendly = brands.seed_brands(config.BRAND_SEED_LIMIT) or []
    except Exception:
        friendly = []
    # don't re-seed brands already covered by the hint tier
    friendly = [b for b in friendly if b not in set(hint_seeds)]
    if friendly:
        queue.append({"tier": 3, "kind": "friendly_brands", "seeds": friendly})

    breadth = list((config.active_criteria() or {}).get("watched_categories") or [])
    if breadth:
        queue.append({"tier": 4, "kind": "breadth", "seeds": breadth})

    return queue


def run_harvest(
    api=None,
    budget_tokens: Optional[int] = None,
    refill_per_min: Optional[float] = None,
    active_lead_asins: Optional[Callable[[], List[str]]] = None,
    per_finder_limit: int = 200,
) -> Dict[str, Any]:
    """Drive the priority queue under a token budget, archiving every raw response via the
    keepa_client boundary. NEVER raises — every failure degrades to an honest status dict so the
    harvester can never crash the tail of a daily run.

    Returns {"status", "reason"?, "spent", "budget", "enriched", "tiers_run": [...]}.
    """
    if not enabled():
        return {"status": "disabled",
                "reason": "blocked-on-upgrade: the Keepa Pro trickle (1 token/min, 60 bank) has no "
                          "idle surplus to harvest; enable learning.harvesterEnabled after moving to "
                          "the 20/min API tier",
                "spent": 0, "enriched": 0}
    try:
        api = api or keepa_client.get_client()
    except Exception as e:
        return {"status": "unavailable", "reason": str(e), "spent": 0, "enriched": 0}

    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    state = _load_state(today)

    if budget_tokens is None:
        daily = observed_daily_generation(api, refill_per_min=refill_per_min)
        if daily is None:
            return {"status": "refused",
                    "reason": "could not read the observed Keepa refill rate — refusing to guess a "
                              "harvest budget rather than assume a plan tier",
                    "spent": state.get("spent", 0), "enriched": state.get("enriched", 0)}
        budget_tokens = int(harvest_token_share() * daily)

    remaining = max(0, budget_tokens - int(state.get("spent", 0)))
    if remaining <= 0:
        return {"status": "budget_exhausted", "spent": state.get("spent", 0),
                "budget": budget_tokens, "enriched": state.get("enriched", 0),
                "tiers_run": state.get("done_tiers", [])}

    datalake.set_run_context(f"harvest-{today}")
    queue = build_priority_queue(api, per_finder_limit, active_lead_asins=active_lead_asins)
    tiers_run: List[str] = []

    def _spend_delta(before, after) -> int:
        d = keepa_client._delta(before, after)
        return d if isinstance(d, int) else 0

    for item in queue:
        kind = item["kind"]
        if kind in state.get("done_tiers", []):
            continue  # resumed: this tier already finished today
        if remaining <= 0:
            break

        # Expand brand/category seeds to ASINs via Product Finder (this spend is part of harvest).
        if item.get("asins") is not None:
            asins = item["asins"]
        else:
            before = keepa_client._tokens_consumed(api)
            try:
                asins = keepa_client.find_candidates(
                    api=api, limit=min(per_finder_limit, remaining),
                    brand_seeds=item.get("seeds") if kind != "breadth" else None)
            except Exception as e:
                log.warning("harvest finder failed for tier %s (non-fatal): %s", kind, e)
                asins = []
            after = keepa_client._tokens_consumed(api)
            # When the token counters aren't readable, charge Keepa's documented PF cost (10)
            # rather than 0 — an unbilled finder loop would otherwise drain the shared bucket
            # the nightly scan depends on (Review 2026-07-05).
            spent = _spend_delta(before, after)
            spent = spent if spent > 0 else 10
            state["spent"] = int(state.get("spent", 0)) + spent
            remaining -= spent

        # Enrich in batches until the budget runs out; each enrich archives the raw responses.
        i = 0
        while i < len(asins) and remaining > 0:
            take = min(_ENRICH_BATCH, remaining, len(asins) - i)
            batch = asins[i:i + take]
            before = keepa_client._tokens_consumed(api)
            try:
                enriched = keepa_client.enrich(batch, api=api)
            except Exception as e:
                log.warning("harvest enrich failed for tier %s (non-fatal): %s", kind, e)
                enriched = []
            after = keepa_client._tokens_consumed(api)
            spent = _spend_delta(before, after)
            state["spent"] = int(state.get("spent", 0)) + spent
            state["enriched"] = int(state.get("enriched", 0)) + len(enriched)
            remaining -= spent if spent > 0 else len(batch)  # fall back to batch size if untelemetered
            # Advance by what was actually TAKEN, not the full batch constant — advancing by
            # _ENRICH_BATCH after a remaining-capped slice silently skipped the un-sliced tail
            # of the tier's highest-priority ASINs (Review 2026-07-05).
            i += len(batch)
            _save_state(state)

        if remaining > 0:  # finished this tier within budget
            state.setdefault("done_tiers", []).append(kind)
        tiers_run.append(kind)
        _save_state(state)

    # Flush the day's harvested raw rows to the lake.
    datalake.flush(f"harvest-{today}")
    return {"status": "ok", "spent": int(state.get("spent", 0)), "budget": budget_tokens,
            "enriched": int(state.get("enriched", 0)), "tiers_run": tiers_run,
            "lake_digest": datalake.digest_line()}
