"""
scout/deals/goldset.py — precision/recall of matcher.py's scoring math against a hand-labeled
gold set (Deal Finder Build Plan Prompt D2 step 7). Runs fully offline: no Keepa/Anthropic calls,
no Supabase — it re-scores the (deal, candidate) pairs a human already labeled, using the exact
same normalize -> attribute-agreement -> composite_confidence path matcher.match_deal() uses
live, minus the LLM step (a gold-set pair has no live candidate list to escalate from; scoring
it with llm_result=None is the honest offline equivalent — see evaluate()'s docstring).

fixtures/gold_matches.jsonl ships with a small SYNTHETIC seed (see that file's own header row)
so this module and its tests have something to run against; it is NOT the real 30+ pair
hand-verified set the Build Plan calls for (that's Mehmet's task, sec 5). Every report this
module produces says so explicitly when n is small — never a bare, unqualified percentage.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import normalize
from .matcher import _attr_agreement, _title_similarity, _price_sane, composite_confidence, route

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "gold_matches.jsonl")
MIN_TRUSTWORTHY_N = 30  # Build Plan sec 3's own "never 100%... review queue is part of the
                        # design" framing plus Prompt D2 step 7's 30-pair starting target.


def load_gold_set(path: str = None) -> List[Dict[str, Any]]:
    """Every labeled row (skips the fixture's own header/provenance row, identified by having
    no "deal" key). [] if the file is missing or empty — never raises."""
    rows = []
    try:
        with open(path or DEFAULT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if "deal" in row and "candidate" in row:
                    rows.append(row)
    except Exception:
        return []
    return rows


def score_pair(deal: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Score one (deal, candidate) pair exactly as matcher.match_deal() would for a single
    candidate, offline (no LLM — llm_result is always None here, matching the honest "no live
    escalation available for an offline pair" scoping note in the module docstring). Returns
    {confidence, route, predicted_match} where predicted_match = (route != "discard")."""
    deal_attrs = normalize.extract_attributes(deal.get("title_raw") or "", deal.get("brand"))
    cand_attrs = normalize.extract_attributes(candidate.get("title") or "", candidate.get("brand"))
    brand_match, pack_match, size_match = _attr_agreement(deal_attrs, cand_attrs)
    similarity = _title_similarity(deal_attrs.get("core_title"), cand_attrs.get("core_title"))
    price_sane = _price_sane(deal.get("price_current"), candidate.get("price"))
    # Method is always "title" here — an offline gold-set pair has no UPC lookup to have gone
    # through; this scores the (currently live) title path's honesty, which is the point.
    confidence = composite_confidence("title", brand_match, pack_match, size_match, similarity,
                                      price_sane, llm_result=None)
    r = route(confidence)
    return {"confidence": confidence, "route": r, "predicted_match": r != "discard"}


def evaluate(path: str = None) -> Dict[str, Any]:
    """Precision/recall of "route != discard" as a same-product predictor, against the gold
    set's expected_match labels. Returns an honest dict — n, precision, recall, and a
    `trustworthy` flag (False when n < MIN_TRUSTWORTHY_N, per the Build Plan's own 30-pair
    starting target) so a caller can't accidentally quote a 6-pair percentage as if it meant
    something. {"n": 0, ...} with trustworthy=False if the fixture is empty/missing."""
    rows = load_gold_set(path)
    if not rows:
        return {"n": 0, "precision": None, "recall": None, "trustworthy": False,
               "note": "no labeled pairs found"}

    tp = fp = fn = tn = 0
    details = []
    for row in rows:
        result = score_pair(row["deal"], row["candidate"])
        expected = bool(row["expected_match"])
        predicted = result["predicted_match"]
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1
        details.append({**result, "expected_match": expected, "note": row.get("note")})

    precision = round(tp / (tp + fp), 3) if (tp + fp) else None
    recall = round(tp / (tp + fn), 3) if (tp + fn) else None
    n = len(rows)
    return {
        "n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall,
        "trustworthy": n >= MIN_TRUSTWORTHY_N,
        "note": (f"n={n} — below the Build Plan's own {MIN_TRUSTWORTHY_N}-pair starting target; "
                "treat this as a smoke test of the scoring code, not a real accuracy measurement"
                if n < MIN_TRUSTWORTHY_N else "n meets the Build Plan's starting target"),
        "details": details,
    }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=2))
    print(f"\n{'PAIR':<60} {'EXPECT':<8} {'PRED':<8} CONF")
    for d in result.get("details", []):
        print(f"{(d.get('note') or '')[:58]:<60} {str(d['expected_match']):<8} "
             f"{str(d['predicted_match']):<8} {d['confidence']}")
