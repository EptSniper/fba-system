"""
scout/reflect.py — brand memory (Scout Agent Build Plan, Prompt S3).

Weekly job: finds brands with new decisions/outcomes/analyst-disagreements in the lookback
window, and for each one calls Claude to UPDATE that brand's memory note
(learning-hub/memory/brands/<slug>.md) — merging in genuinely new lessons, pruning stale
entries, and capping length (stale-memory poisoning is a documented failure mode; this file is
always REGENERATED from the current real rows, never just appended to forever). Notes feed
back into analyst.py's input for that brand via read_memory_note().

Never invents facts: the reflection prompt gets ONLY the brand's real lead/decision/outcome
rows, and a post-validator rejects any update mentioning an ASIN not present in those rows —
the same tabular-hallucination guard as analyst.py, applied to free text via a regex scan.

Requires ANTHROPIC_API_KEY (reuses analyst.configured()/analyst.MODEL). Absent -> every public
function degrades honestly (no-op / {"status": "unavailable"}). NOT verified against a live API
call in this repo (no key configured here yet) — tested against a mocked client.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any, Dict, List, Optional

import analyst
import db

HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY_DIR = os.path.join(HERE, "..", "learning-hub", "memory", "brands")
MAX_NOTE_LINES = 60
LOOKBACK_DAYS = 7

REFLECT_TOOL = {
    "name": "submit_note",
    "description": "Submit the updated brand memory note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "updated_note": {"type": "string",
                             "description": f"Markdown, at most {MAX_NOTE_LINES} lines total."},
        },
        "required": ["updated_note"],
    },
}

SYSTEM_PROMPT = (
    "You maintain a short, running memory note about ONE brand for an online-arbitrage "
    "sourcing system. You are given the brand's existing note (if any) and its real lead/"
    "decision/outcome rows from this week. Update the note: merge in genuinely new lessons, "
    "remove stale or superseded entries, and keep the WHOLE note under "
    f"{MAX_NOTE_LINES} lines, organized under '## Verdict history', '## Realized outcomes', "
    "'## Risk observations', '## Seasonal notes'. NEVER invent a fact, ASIN, or number that "
    "isn't in the provided rows — if you're unsure, leave it out rather than guess. Call "
    "submit_note with the full updated note text."
)


def slug(text: str) -> str:
    """Filesystem-safe brand-name slug (e.g. "Mrs. Meyer's" -> "mrs-meyer-s"). Public — also
    used by mcp_server.py to resolve the same memory-note filename when READING a note that
    reflect.py WROTE; this used to be duplicated byte-for-byte in both files (Code Review
    2026-07-02, nit)."""
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "unknown"


def _note_path(brand: str) -> str:
    return os.path.join(MEMORY_DIR, f"{slug(brand)}.md")


def read_memory_note(brand: Optional[str]) -> Optional[str]:
    """The current memory note text for a brand, or None if none exists yet. Called by
    pipeline.py to feed analyst.py's `memory_note` input."""
    if not brand:
        return None
    path = _note_path(brand)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _brands_with_recent_activity(leads: List[Dict[str, Any]], cutoff_iso: str) -> set:
    brands = set()
    for lead in leads:
        brand = lead.get("brand")
        if not brand:
            continue
        if any((d.get("decided_at") or "") >= cutoff_iso for d in (lead.get("decisions") or [])):
            brands.add(brand)
        elif any((o.get("closed_at") or "") >= cutoff_iso for o in (lead.get("outcomes") or [])):
            brands.add(brand)
        elif ((lead.get("explanation") or {}).get("analyst_note") or {}).get("disagrees_with_rules"):
            brands.add(brand)
    return brands


def _post_validate(updated_note: str, valid_asins: set) -> bool:
    """Reject an update mentioning an ASIN-shaped token not present in the real input rows —
    the tabular-hallucination guard, applied to free text via regex instead of structured
    fields (analyst.py's approach for structured claims)."""
    mentioned = set(re.findall(r"\bB0[A-Z0-9]{8}\b", updated_note))
    return not (mentioned - valid_asins)


def reflect_on_brand(brand: str, leads: List[Dict[str, Any]],
                     client: Optional[Any] = None) -> Dict[str, Any]:
    """Update one brand's memory note from its real rows. Never raises."""
    if not analyst.configured():
        return {"brand": brand, "status": "unavailable"}
    existing_note = read_memory_note(brand) or "(no existing note)"
    payload = {
        "brand": brand,
        "existing_note": existing_note,
        "rows": [{
            "asin": lead.get("asin"), "verdict": lead.get("verdict"),
            "decisions": lead.get("decisions"), "outcomes": lead.get("outcomes"),
            "analyst_note": (lead.get("explanation") or {}).get("analyst_note"),
        } for lead in leads],
    }
    try:
        cl = client or analyst.anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = cl.messages.create(
            model=analyst.MODEL, max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            tools=[REFLECT_TOOL],
            tool_choice={"type": "tool", "name": "submit_note"},
        )
    except Exception as e:
        return {"brand": brand, "status": "error", "reason": str(e)}

    updated_note = None
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_note":
            updated_note = block.input.get("updated_note")
    if updated_note is None:
        return {"brand": brand, "status": "error", "reason": "model did not return submit_note"}

    valid_asins = {lead.get("asin") for lead in leads if lead.get("asin")}
    if not _post_validate(updated_note, valid_asins):
        return {"brand": brand, "status": "rejected",
               "reason": "update mentioned an ASIN not present in the real rows"}

    lines = updated_note.splitlines()
    if len(lines) > MAX_NOTE_LINES:
        updated_note = "\n".join(lines[:MAX_NOTE_LINES])

    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(_note_path(brand), "w", encoding="utf-8") as f:
        f.write(updated_note)
    return {"brand": brand, "status": "updated"}


def run_weekly(days: int = LOOKBACK_DAYS) -> Dict[str, Any]:
    """The run_daily.py entry point (wrapped there in the same non-fatal try/except as every
    other weekly job). Honest no-op without a key; never raises."""
    if not analyst.configured():
        return {"status": "unavailable", "brands_updated": 0}
    leads = db.leads_with_outcomes()
    cutoff_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    brands = _brands_with_recent_activity(leads, cutoff_iso)
    results = []
    for brand in sorted(brands):
        brand_leads = db.leads_by_brand(brand)
        try:
            results.append(reflect_on_brand(brand, brand_leads))
        except Exception as e:
            results.append({"brand": brand, "status": "error", "reason": str(e)})
    updated = sum(1 for r in results if r.get("status") == "updated")
    return {"status": "ok", "brands_considered": len(brands), "brands_updated": updated, "results": results}


if __name__ == "__main__":
    print(json.dumps(run_weekly(), indent=2, default=str))
