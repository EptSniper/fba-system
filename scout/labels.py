"""
labels.py — assemble the training table for the learning loop (System Blueprint Prompt 3.1).

Two REAL capture surfaces feed this, combined by ASIN:
  1. Supabase leads -> decisions -> outcomes (the scout's automated path; db.leads_with_outcomes()).
     Leads written after migration 001 carry a `features_snapshot` (the pre-decision inputs) and
     an `explanation` (the scout's own judgment, for audit only — never a feature).
  2. The local operator ledger (control-center's /api/capture -> learning-hub/data/events.jsonl),
     how the Find page's "Save as lead" and the Log page capture human decisions/outcomes when
     the scout never scored the ASIN. These rows have NO pre-decision feature snapshot (the
     capture form only stores product/asin/roi/status/notes) — they can confirm an ASIN was
     labeled, but cannot themselves train a feature-based model. Kept in the label COUNT for
     honesty, excluded from the TRAINABLE set.

LEAKAGE PREVENTION (non-negotiable, stated twice on purpose): only the fields in
db.PRE_DECISION_FEATURES ever reach `rows[i]["features"]`. The scout's own verdict/score/reason
is NEVER read back as a label — a label comes ONLY from a realized outcome (what actually
happened after a human decision), never from the scout's own prediction about itself.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import backtest
import db

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_PATH = os.path.join(HERE, "..", "learning-hub", "data", "ai-brain.json")
EVENTS_PATH = os.path.join(HERE, "..", "learning-hub", "data", "events.jsonl")
DEFAULT_MIN_LABELED_ROWS = 30


def min_labeled_rows() -> int:
    """ai-brain.json learning.minLabeledRows, single-sourced like every other threshold."""
    try:
        with open(BRAIN_PATH, encoding="utf-8") as f:
            brain = json.load(f) or {}
        v = (brain.get("learning") or {}).get("minLabeledRows")
        if isinstance(v, (int, float)):
            return int(v)
    except Exception:
        pass
    return DEFAULT_MIN_LABELED_ROWS


def label_from_outcome(outcome: Dict[str, Any]) -> Optional[bool]:
    """A realized outcome -> a boolean success label, or None if there's nothing to judge yet.
    Prefers an explicit would_rebuy flag (Supabase outcomes schema); falls back to realized
    profitability (profit > 0 and the price didn't tank). Accepts both the Supabase snake_case
    columns (actual_profit, price_tanked) and the local ledger's camelCase (actualProfit)."""
    if outcome.get("would_rebuy") is not None:
        return bool(outcome["would_rebuy"])
    profit = outcome.get("actual_profit")
    if profit is None:
        profit = outcome.get("actualProfit")
    if profit is None:
        return None
    tanked = bool(outcome.get("price_tanked"))
    try:
        return float(profit) > 0 and not tanked
    except (TypeError, ValueError):
        return None


def _from_supabase() -> List[Dict[str, Any]]:
    rows = []
    for lead in db.leads_with_outcomes():
        outcomes = lead.get("outcomes") or []
        if not outcomes:
            continue
        outcome = sorted(outcomes, key=lambda o: o.get("closed_at") or "", reverse=True)[0]
        label = label_from_outcome(outcome)
        if label is None:
            continue
        snapshot = lead.get("features_snapshot") or {}
        # Leakage guard #1: re-filter to the allowlist even though the write side already did —
        # a lead written before migration 001, or by any future code path, might carry extras.
        features = {k: snapshot.get(k) for k in db.PRE_DECISION_FEATURES} if snapshot else None
        rows.append({
            "asin": lead.get("asin"), "source": "supabase",
            "features": features if snapshot else None,
            "label": label,
            "label_quality": "gold",  # a REALIZED outcome — the strongest label
        })
    return rows


def _from_shadow() -> List[Dict[str, Any]]:
    """SILVER labels — the shadow-outcome tracker's proxy outcomes (DATA_ENGINE_PLAN.md V1). Each
    completed shadow row carries the ORIGINAL pre-decision feature snapshot and a
    would_have_profited label computed at the original landed cost. HONEST CAVEAT: a shadow label
    ignores execution and sell-through (we never actually bought/sold), so it is weaker than a
    gold outcome and is reported as its own tier — never blended silently into gold."""
    rows = []
    for s in db.all_shadow_outcomes():
        label = s.get("would_have_profited")
        if label is None:
            continue
        snapshot = s.get("features_snapshot") or {}
        # Leakage guard: re-filter to the pre-decision allowlist at read time too.
        features = {k: snapshot.get(k) for k in db.PRE_DECISION_FEATURES} if snapshot else None
        rows.append({
            "asin": s.get("asin"), "source": "shadow",
            "features": features if snapshot else None,
            "label": bool(label),
            "label_quality": "silver",
            "checkpoint_day": s.get("checkpoint_day"),
        })
    return rows


def _from_bronze_decisions() -> List[Dict[str, Any]]:
    """BRONZE — a human's OWN buy/pass decision on a lead, recorded BEFORE any outcome is known
    (DATA_ENGINE_PLAN.md: "each verdict = a bronze label... bronze bootstraps"). This is
    OPERATOR JUDGMENT, not a market-realized result.

    Mehmet's directive (Session 55): bronze labels must NEVER enter the ranker's relevance
    target. Training on "did the operator say buy" instead of "did it actually profit" would
    just teach the model to imitate the human's own pre-existing verdict — a circular,
    self-confirming signal, not a lesson about what makes money. assemble_training_rows() below
    keeps these rows in a SEPARATE list (never merged into `rows`/`all_labeled`); train_ranker.py
    scores them through the fitted model only as an auxiliary "agreement with operator" metric,
    reported alongside results at zero training weight."""
    rows = []
    for lead in db.leads_with_outcomes():
        if lead.get("outcomes"):
            continue  # a REAL outcome exists — that's gold (_from_supabase), not bronze
        decisions = lead.get("decisions") or []
        if not decisions:
            continue
        latest = sorted(decisions, key=lambda d: d.get("created_at") or "", reverse=True)[0]
        decision = latest.get("decision")
        if decision not in ("buy", "pass"):
            continue  # test/wait carry no clear binary signal — skip, never fabricate
        snapshot = lead.get("features_snapshot") or {}
        features = {k: snapshot.get(k) for k in db.PRE_DECISION_FEATURES} if snapshot else None
        rows.append({
            "asin": lead.get("asin"), "source": "supabase_decision",
            "features": features if snapshot else None,
            "label": decision == "buy",
            "label_quality": "bronze",
        })
    return rows


def _from_backtest() -> List[Dict[str, Any]]:
    """BACKTEST labels — the 4th and WEAKEST tier (DATA_ENGINE_PLAN.md V2): hindsight simulations
    on historical Keepa data with a simulated buy cost, no execution, no sell-through. Included in
    training only when a caller explicitly opts in (V3's ranker); the calibration diagnostic keeps
    them OUT and reports their count as a separate tier line, never blended into gold/silver.

    sample_source/ip_risk are carried through from db.all_backtest_rows() (review fix,
    2026-07-06 — a seam test caught these being silently dropped here even though the write side,
    scout/backtest.py's build_rows_for_asin, always sets them): without this,
    train_ranker.source_breakdown() would group every backtest row under 'n/a' and the Session
    55 sampling overhaul's onpolicy-vs-explore-vs-dealfeed report section could never render.

    ML rigor directive (2026-07-13): the label is now RECOMPUTED at read time via
    backtest.consistent_label(est_profit, landed_cost, category) instead of trusting the row's
    own stored would_have_profited column directly. Rows written before the 2026-07-13 label fix
    (Session 64) carry a would_have_profited value computed under the OLD `est_profit > 0`
    definition; reading them as-is would mix two label versions in the same training set — the
    exact cohort-mixing artifact Codex's audit found had inflated the first walk-forward's AUC.
    Recomputing from est_profit/landed_cost (both stored per row, present since backtest_rows'
    original migration) gives every row the SAME, current definition without an in-place UPDATE
    on the live table — a bulk production-data mutation that was considered and explicitly
    declined in favor of this read-time approach."""
    rows = []
    for b in db.all_backtest_rows():
        label = backtest.consistent_label(b.get("est_profit"), b.get("landed_cost"), b.get("category"))
        if label is None:
            continue
        snapshot = b.get("features_snapshot") or {}
        features = {k: snapshot.get(k) for k in db.PRE_DECISION_FEATURES} if snapshot else None
        rows.append({
            "asin": b.get("asin"), "source": "backtest",
            "features": features if snapshot else None,
            "label": bool(label),
            "label_quality": "backtest",
            "simulation_date": b.get("simulation_date"),
            "sample_source": b.get("sample_source"),
            "category": b.get("category"),
            "ip_risk": b.get("ip_risk"),
        })
    return rows


def _read_events() -> List[Dict[str, Any]]:
    if not os.path.exists(EVENTS_PATH):
        return []
    events = []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _match_key(payload: Dict[str, Any]) -> Optional[str]:
    asin = (payload.get("asin") or "").strip().upper()
    if asin:
        return f"asin:{asin}"
    product = (payload.get("product") or "").strip().lower()
    return f"name:{product}" if product else None


def _from_local_ledger() -> List[Dict[str, Any]]:
    """The local ledger has no feature snapshot — see module docstring. `features` is always
    None here; these rows count toward the honest label total but never toward the trainable set."""
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for e in _read_events():
        payload = e.get("payload") or {}
        key = _match_key(payload)
        if not key:
            continue
        by_key.setdefault(key, []).append({"kind": e.get("kind"), "payload": payload, "ts": e.get("ts")})

    rows = []
    for key, entries in by_key.items():
        outcomes = [en for en in entries if en["kind"] == "outcome"]
        if not outcomes:
            continue
        latest = sorted(outcomes, key=lambda en: en.get("ts") or "", reverse=True)[0]["payload"]
        label = label_from_outcome(latest)
        if label is None:
            continue
        rows.append({"asin": latest.get("asin"), "source": "local_ledger", "features": None,
                     "label": label, "label_quality": "gold"})  # a realized outcome, just no snapshot
    return rows


def _tier_counts(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Per-quality-tier breakdown of trainable rows — the honesty requirement: calibration
    performance MUST be reported per tier, never with silver silently blended into gold."""
    tiers: Dict[str, Dict[str, int]] = {}
    for r in rows:
        q = r.get("label_quality", "unknown")
        t = tiers.setdefault(q, {"total": 0, "positive": 0, "negative": 0})
        t["total"] += 1
        t["positive" if r["label"] else "negative"] += 1
    return tiers


def assemble_training_rows(include_silver: bool = True, include_backtest: bool = False) -> Dict[str, Any]:
    """The single entry point. Combines gold (realized outcomes) and, by default, silver (shadow
    proxy outcomes); backtest (hindsight) rows are OPT-IN (V3's ranker) and OUT of the calibration
    diagnostic. Keeps only rows with BOTH a pre-decision feature snapshot AND a label, and enforces
    the minimum from ai-brain.json. by_tier is always returned so reports show performance per
    quality tier separately (the weaker-tier caveats). Never raises on missing data.

    include_silver=False -> gold only; include_backtest=True -> add the backtest tier (V3)."""
    gold = _from_supabase() + _from_local_ledger()
    silver = _from_shadow() if include_silver else []
    backtest = _from_backtest() if include_backtest else []
    # BRONZE (decision-only, no outcome yet) is ALWAYS computed but deliberately EXCLUDED from
    # all_labeled/trainable — Mehmet's directive (Session 55): it must never enter the ranker's
    # relevance target. Kept as its own list for train_ranker.py's auxiliary "agreement with
    # operator" metric only, at zero training weight.
    bronze = _from_bronze_decisions()
    all_labeled = gold + silver + backtest
    trainable = [r for r in all_labeled if r.get("features")]
    bronze_rows = [r for r in bronze if r.get("features")]

    n_pos = sum(1 for r in trainable if r["label"] is True)
    n_neg = sum(1 for r in trainable if r["label"] is False)
    min_rows = min_labeled_rows()
    by_tier = _tier_counts(trainable)
    silver_n = by_tier.get("silver", {}).get("total", 0)
    bronze_tier = _tier_counts(bronze_rows).get("bronze", {"total": 0, "positive": 0, "negative": 0})
    # backtest rows exist even when not mixed in — surface the count so a report can show the tier
    # line honestly ("backtest available, held separate") without blending them into the diagnostic.
    backtest_available = db.count_backtest_rows() if not include_backtest else by_tier.get("backtest", {}).get("total", 0)

    refused = len(trainable) < min_rows or n_pos == 0 or n_neg == 0
    if len(trainable) < min_rows:
        reason = f"{len(trainable)} trainable labeled rows (< {min_rows} required) — running on the rule score alone"
    elif n_pos == 0 or n_neg == 0:
        reason = (f"{len(trainable)} trainable rows but only one class present "
                 f"({n_pos} positive / {n_neg} negative) — need both to calibrate")
    else:
        reason = f"{len(trainable)} trainable rows ({n_pos} positive / {n_neg} negative) — ready for calibration"

    return {
        "rows": trainable,   # gold + silver + (opt) backtest ONLY — the ranker's relevance target
        "trainable_count": len(trainable),
        "labeled_count": len(all_labeled),  # includes local-ledger outcomes with no feature snapshot
        "positive": n_pos,
        "negative": n_neg,
        "min_required": min_rows,
        "refused": refused,
        "reason": reason,
        "by_tier": by_tier,           # {gold: {total,positive,negative}, silver: {...}, backtest: {...}}
        "silver_count": silver_n,
        "backtest_available": backtest_available,  # count held separate unless include_backtest=True
        "silver_caveat": ("Silver (shadow) labels ignore execution and sell-through — we never "
                          "actually bought or sold. Report their tier separately; never treat a "
                          "silver-trained metric as if validated by realized outcomes."),
        # BRONZE — decision-only rows, deliberately EXCLUDED from `rows`/relevance target above
        # (Mehmet's directive, Session 55). bronze_rows carries pre-decision features so
        # train_ranker.py can score them through the FITTED model as an auxiliary "agreement with
        # operator" comparison only — never used to fit/validate anything.
        "bronze_rows": bronze_rows,
        "bronze_tier": bronze_tier,
        "bronze_caveat": ("Bronze (operator decision, no outcome yet) is OPERATOR JUDGMENT, not a "
                         "market result — weight ZERO in training. Never blended into `rows`; "
                         "reported only as a separate agreement-with-operator auxiliary metric."),
    }


if __name__ == "__main__":
    result = assemble_training_rows()
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
