"""
scout/analyst.py — the LLM analyst pass (Scout Agent Build Plan, Prompt S1).

A second, qualitative opinion over gate-survivors — NEVER a decider. The 2026 consensus this
implements: a nightly scoring pass is a workflow, not an agent; deterministic code computes
every number and enforces every gate, and the LLM sits on top as an analyst whose judgment is
structured, evidence-bound, and never decisive on its own.

Anti-sycophancy (the reason this file is careful about what it shows the model): finance-LLM
research documents that models tend to agree with whatever score they're shown. build_input()
therefore DELIBERATELY EXCLUDES the composite score/verdict — only pre-computed gates,
adjustments, and raw metrics go in. A deterministic post-validator then rejects any claim
citing a field the model wasn't actually given (the documented #1 tabular-hallucination
failure mode) — "UNKNOWN, not background knowledge" is an explicit system-prompt instruction:
the model may not use what it "knows" about a brand from training.

This module NEVER touches scoring/gates/ai-brain.json and has no write path to any of them —
enforced by an AST-based guard test (tests/test_analyst.py), not just this docstring.

Requires ANTHROPIC_API_KEY in scout/.env. Absent (or the `anthropic` package missing) -> every
public function degrades honestly ({"status": "unavailable", ...}) — same pattern as
spapi.py/keepa_client.py. NOT verified against a live API call in this repo (no key is
configured here yet) — call_analyst()'s request-shape is built from the anthropic SDK's real,
installed signature (messages.create(..., tools=..., tool_choice=...)), and its response
parsing is exercised only against mocked SDK objects.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import datalake  # V0 raw data lake — archive() never raises and no-ops when disabled/absent

try:
    import anthropic
except Exception:  # pragma: no cover - package optional at import time
    anthropic = None

# A real, current Claude model id (per this project's own environment info) — a Sonnet-class
# model is the deliberate choice for the analyst's qualitative-judgment step (the build plan's
# own cost/quality rationale), not the cheaper Haiku tier used for the deal-matcher (Prompt D2).
MODEL = os.getenv("ANALYST_MODEL", "claude-sonnet-5")
MAX_TOKENS = 1024

# Facts the analyst is NEVER shown, even if present on the candidate dict — the anti-sycophancy
# non-negotiable. If a caller passes a dict containing these, build_input() strips them anyway.
_EXCLUDED_FIELDS = {"rule_score", "blended_score", "model_proba", "verdict", "score"}

SYSTEM_PROMPT = (
    "You are an online-arbitrage sourcing analyst reviewing ONE candidate product that has "
    "already passed every hard eligibility/profitability gate in a rule-based system. You are "
    "a SECOND OPINION, not the decision-maker — a human and a separate rule engine make the "
    "actual call. You are given pre-computed facts: scored-check results, named scoring "
    "adjustments with their point values, raw Keepa-derived metrics, and (when available) a "
    "memory note "
    "about this brand's history. You are DELIBERATELY NOT shown any composite score or verdict "
    "— form your own qualitative judgment from the raw facts instead of agreeing with a number.\n\n"
    "Hard rule: if a fact is not present in the input, you do not know it. Never use background "
    "knowledge about this brand, product, or category from your training — if you don't have a "
    "fact in the input, list it under `unknowns` instead of asserting it. Every claim in "
    "`top_risks` must cite the exact input field name(s) that support it in `evidence_fields`; "
    "a claim citing a field not present in the input will be discarded by an automated "
    "validator, so only cite fields that are actually there.\n\n"
    "Call the submit_analysis tool with your structured analysis."
)

ANALYST_TOOL = {
    "name": "submit_analysis",
    "description": "Submit your qualitative risk analysis for this OA candidate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "qualitative_risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "disagrees_with_rules": {
                "type": "boolean",
                "description": "True if your qualitative read conflicts with what the gates/adjustments imply.",
            },
            "top_risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "evidence_fields": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["claim", "evidence_fields"],
                },
            },
            "narrative": {"type": "string", "description": "<=120 words."},
            "unknowns": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["qualitative_risk", "disagrees_with_rules", "top_risks", "narrative", "unknowns"],
    },
}


def configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and anthropic is not None


def build_input(p: Dict[str, Any], category: Optional[str] = None,
                memory_note: Optional[str] = None) -> Dict[str, Any]:
    """PRE-COMPUTED facts only, for one candidate — the anti-sycophancy input contract. Reads
    the SAME dict shape pipeline._evaluate() produces (post scoring.explain_oa()), but never
    the score/verdict itself, even if it's present on `p`."""
    explanation = p.get("explanation") or {}
    facts = {
        "asin": p.get("asin"), "title": p.get("title"), "brand": p.get("brand"),
        "category": category or p.get("category"),
        "price": p.get("price"), "weight_lb": p.get("weight_lb"),
        "sales_rank": p.get("sales_rank"), "avg_sales_rank_90": p.get("avg_sales_rank_90"),
        "est_sales": p.get("est_sales"), "offers": p.get("offers"),
        "avg_offers_90": p.get("avg_offers_90"), "avg_price_90": p.get("avg_price_90"),
        "amazon_bb_share": p.get("amazon_bb_share"),
        "oa_profit": p.get("oa_profit"), "oa_roi": p.get("oa_roi"),
        # "gates" fallback: rows persisted before the scored_checks rename (2026-07-02 S4)
        "scored_checks": explanation.get("scored_checks") or explanation.get("gates"),
        "adjustments": explanation.get("adjustments"),
        "risk_flags": p.get("risks"),
    }
    if memory_note:
        facts["brand_memory_note"] = memory_note
    return {k: v for k, v in facts.items() if v is not None and k not in _EXCLUDED_FIELDS}


def _post_validate(analysis: Dict[str, Any], input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Deterministic guard against tabular hallucination: drop any top_risks entry whose
    evidence_fields aren't ALL present in the actual input keys. Returns (cleaned, rejected_count)."""
    input_keys = set(input_data.keys())
    risks = analysis.get("top_risks") or []
    kept, rejected = [], 0
    for risk in risks:
        fields = set(risk.get("evidence_fields") or [])
        if fields and fields <= input_keys:
            kept.append(risk)
        else:
            rejected += 1
    cleaned = dict(analysis)
    cleaned["top_risks"] = kept
    return cleaned, rejected


def call_analyst(input_data: Dict[str, Any], client: Optional[Any] = None) -> Dict[str, Any]:
    """One Claude call -> the post-validated structured analysis, or an honest degraded dict.
    NEVER raises — a missing key/package, an API error, or a malformed response all degrade to
    a {"status": ...} dict so an analyst failure can never crash a pipeline cycle."""
    if not configured():
        return {"status": "unavailable",
               "reason": "ANTHROPIC_API_KEY not set or the anthropic package is missing"}
    try:
        cl = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = cl.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(input_data, default=str)}],
            tools=[ANALYST_TOOL],
            tool_choice={"type": "tool", "name": "submit_analysis"},
        )
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_analysis":
            cleaned, rejected = _post_validate(block.input, input_data)
            cleaned["status"] = "ok"
            cleaned["rejected_risk_count"] = rejected
            # Archive the EXACT input JSON + raw model output (the training record for the
            # judgment layer). tokens_consumed is Anthropic usage, not Keepa — the row's source
            # column ('analyst') keeps the two token economies distinguishable. Never raises.
            usage = getattr(response, "usage", None)
            out_tokens = None
            if usage is not None:
                out_tokens = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)
            datalake.archive("analyst", input_data.get("asin"), "analyst",
                             {"input": input_data, "output": block.input, "model": MODEL},
                             tokens_consumed=out_tokens)
            return cleaned
    return {"status": "error", "reason": "model did not return the expected tool_use block"}


def analyze(p: Dict[str, Any], category: Optional[str] = None,
           memory_note: Optional[str] = None, client: Optional[Any] = None) -> Dict[str, Any]:
    """The public entry point pipeline.py calls per gate-survivor."""
    input_data = build_input(p, category=category, memory_note=memory_note)
    return call_analyst(input_data, client=client)
