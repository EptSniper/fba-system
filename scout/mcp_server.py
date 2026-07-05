"""
scout/mcp_server.py — read-only MCP server over the scout's Supabase brain (Scout Agent Build
Plan, Prompt S4). Registers in Claude Desktop/Code so "why did the scout pass on this?" is a
conversation instead of a SQL session.

READ-ONLY BY DESIGN: every tool function here only calls read functions on `db` (get_lead,
top_leads_raw, leads_by_brand, recent_runs) plus scout/search_log.py's due_searches() (itself
read-only) — never log_lead/log_decision/log_outcome/upsert_*/queue_*/cache_*/mark_*/start_run/
finish_run. Enforced by an AST-based guard test (tests/test_mcp_server.py), not just a comment.
It cannot corrupt the pipeline even if misused: it inherits the SAME .env/service-role access
as the rest of the scout, so treat it exactly as sensitive — never expose it beyond localhost.

REQUIRES Python 3.10+ and `pip install mcp` (the official MCP Python SDK). This dev
environment runs Python 3.9, where `pip install mcp` fails with "no matching distribution" —
a real, verified constraint of the package, not a bug here. The query functions below have
NO dependency on the `mcp` package and are fully tested against a mocked db layer; only
`build_server()` (and running this file directly) needs the real package installed. The
FastMCP `.tool()` registration pattern below matches Anthropic's published MCP quickstart docs
but has NOT been exercised against a real `mcp` install in this repo — flag that honestly if
something differs when Mehmet runs it on a Python 3.10+ machine.

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "fba-scout": {
          "command": "python",
          "args": ["C:/path/to/scout/mcp_server.py"]
        }
      }
    }

Claude Code (.mcp.json in the project root):
    {
      "mcpServers": {
        "fba-scout": {
          "command": "python",
          "args": ["scout/mcp_server.py"]
        }
      }
    }
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List, Optional

import db
import scoring
import search_log
from reflect import slug  # shared brand-name slugifier (Code Review 2026-07-02, nit — this used
                          # to be a byte-for-byte duplicate of reflect.py's own helper)

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - package/Python-version optional at import time
    FastMCP = None

HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY_BRANDS_DIR = os.path.join(HERE, "..", "learning-hub", "memory", "brands")


# ----------------------------------------------------------------------------
# Tool implementations — plain, testable functions. No `mcp` package dependency.
# ----------------------------------------------------------------------------
def get_lead(asin: str) -> Dict[str, Any]:
    """Full lead row (with its decisions + outcomes) for one ASIN."""
    lead = db.get_lead(asin)
    if not lead:
        return {"asin": asin, "found": False, "message": "No lead on file for this ASIN."}
    return {"asin": asin, "found": True, **lead}


def _triage_value(row: Dict[str, Any]) -> Optional[float]:
    """Exact triage value via scoring.triage_score() when a features_snapshot is present
    (post migration 001); otherwise an approximation from the leads table's own stored
    profit/monthly_sales/buy_cost columns (no weight_lb there, so fees aren't recomputed) —
    labeled honestly rather than silently treated as equivalent."""
    snapshot = row.get("features_snapshot")
    if isinstance(snapshot, dict) and snapshot:
        val = scoring.triage_score(snapshot, category=row.get("category"))
        if val is not None:
            return val
    profit, sales, buy_cost = row.get("profit"), row.get("monthly_sales"), row.get("buy_cost")
    if profit is None or sales is None or not buy_cost:
        return None
    try:
        return round(float(profit) * float(sales) / float(buy_cost), 3)
    except (TypeError, ZeroDivisionError):
        return None


def top_leads(n: int = 10) -> List[Dict[str, Any]]:
    """The N most recent leads, ranked by triage value (Scout Agent Build Plan sec 3.2)
    descending — unranked leads (missing profit/sales/cost data) sort last, never to a
    fabricated zero that would look like "worst candidate"."""
    rows = db.top_leads_raw(limit=max(n * 4, n))  # over-fetch so ranking has enough to sort
    for row in rows:
        row["triage_value"] = _triage_value(row)
    rows.sort(key=lambda r: (r["triage_value"] is not None, r["triage_value"] or 0), reverse=True)
    return rows[:n]


def why_rejected(asin: str) -> Dict[str, Any]:
    """The stored gates/adjustments/verdict for one ASIN, straight from explain_oa()'s output
    (never recomputed — this shows what the scout actually decided, not a fresh guess)."""
    lead = db.get_lead(asin)
    if not lead:
        return {"asin": asin, "found": False, "message": "No lead on file for this ASIN."}
    explanation = lead.get("explanation")
    if not explanation:
        return {"asin": asin, "found": True, "verdict": lead.get("verdict"),
                "score": lead.get("score"), "reason": lead.get("reason"),
                "message": "No structured explanation stored for this lead (pre-migration-001 "
                          "row, or it predates explain_oa())."}
    return {"asin": asin, "found": True, "verdict": explanation.get("verdict"),
           "score": explanation.get("score"),
           # "gates" fallback: rows persisted before the scored_checks rename (2026-07-02 S4)
           "scored_checks": explanation.get("scored_checks") or explanation.get("gates"),
           "adjustments": explanation.get("adjustments"),
           "hard_reject": explanation.get("hard_reject")}


def brand_history(brand: str) -> Dict[str, Any]:
    """Every lead seen for a brand, a verdict breakdown, and the brand's memory note (S3) if
    one exists yet."""
    leads = db.leads_by_brand(brand)
    if not leads:
        return {"brand": brand, "lead_count": 0, "message": "No leads on file for this brand yet."}
    outcomes = [o for lead in leads for o in (lead.get("outcomes") or [])]
    verdict_counts: Dict[str, int] = {}
    for lead in leads:
        v = lead.get("verdict") or "unknown"
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    memory_note = None
    memory_path = os.path.join(MEMORY_BRANDS_DIR, f"{slug(brand)}.md")
    if os.path.exists(memory_path):
        with open(memory_path, encoding="utf-8") as f:
            memory_note = f.read()
    return {"brand": brand, "lead_count": len(leads), "verdict_counts": verdict_counts,
           "outcome_count": len(outcomes), "memory_note": memory_note}


def run_stats(days: int = 7) -> Dict[str, Any]:
    """Runner telemetry over the last N days: run count, status breakdown, avg Keepa tokens
    consumed. Reads db.recent_runs() (already a read-only function) and filters client-side —
    that function has no date-range parameter of its own."""
    runs = db.recent_runs(limit=200)
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    recent = [r for r in runs if (r.get("started_at") or "") >= cutoff]
    if not recent:
        return {"days": days, "run_count": 0, "message": "No runs recorded in this window."}
    tokens = [r["tokens_consumed"] for r in recent if isinstance(r.get("tokens_consumed"), (int, float))]
    statuses: Dict[str, int] = {}
    for r in recent:
        s = r.get("status") or "unknown"
        statuses[s] = statuses.get(s, 0) + 1
    return {
        "days": days, "run_count": len(recent), "status_counts": statuses,
        "avg_tokens_consumed": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "note": "analyst-disagreement rate not tracked yet (Prompt S1's runs telemetry, if "
               "added, would extend this).",
    }


def search_log_due() -> List[Dict[str, Any]]:
    """Brands whose saved search is due for a Product Finder re-run (Scout Agent Build Plan
    sec 3.3). Execution stays Keepa-gated and manual — this only reports what's due."""
    return search_log.due_searches()


# ----------------------------------------------------------------------------
# MCP wiring — only touched when the real package is installed (Python 3.10+).
# ----------------------------------------------------------------------------
_TOOLS = (get_lead, top_leads, why_rejected, brand_history, run_stats, search_log_due)


def build_server():
    if FastMCP is None:
        raise ImportError(
            "The 'mcp' package is not installed (requires Python 3.10+; this repo's dev "
            "environment runs 3.9). Run: pip install mcp   on a 3.10+ interpreter."
        )
    server = FastMCP("fba-scout")
    for fn in _TOOLS:
        server.tool()(fn)
    return server


if __name__ == "__main__":
    build_server().run()
