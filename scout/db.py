"""
db.py — optional Supabase logging for the scout (the "memory" + learning loop).

Writes every lead, decision, and outcome to the `oa-sourcing-brain` Supabase project so the
system remembers what it saw and can later learn from realized results. Fully optional: if
SUPABASE_URL / SUPABASE_SERVICE_KEY aren't set, every function is a silent no-op, so the scout
runs exactly as before.

Setup (.env):
    SUPABASE_URL=https://cakbzcvtqhdtxfjuxstd.supabase.co
    SUPABASE_SERVICE_KEY=...   # dashboard -> Settings -> API -> service_role (secret, server-side only)

Tables: leads -> decisions -> outcomes (see learning-hub/ai-system/ai-architecture.md).
        runs (System Blueprint Prompt G1) — one row per scout cycle, for telemetry/heartbeat.
        deals -> deal_matches (Deal Finder Build Plan Prompt D1) — retail-deal feed rows and
        their candidate ASIN matches; a second discovery source feeding the same leads table.

IDEMPOTENCY (System Blueprint Prompt G1): leads/keepa_snapshots writes PREFER an upsert
(on_conflict) so re-running the scout on the same ASIN/day updates the existing row instead of
duplicating it. This requires the unique CONSTRAINTS in scout/db/migrations/
001_g1_runs_and_idempotency.sql (plain UNIQUE, not partial/expression indexes — PostgREST's
on_conflict= parameter cannot bind to those; see the migration file's own header note), which is
NOT applied automatically (schema changes need explicit human review). Every upsert falls back
to a plain insert if that migration hasn't landed yet — today's plain-insert behavior is
preserved either way, so nothing breaks while it's pending.

IMPORT-ORDER SAFETY (Code Review 2026-07-02, Finding B1 — verified): this module reads
SUPABASE_URL/SUPABASE_SERVICE_KEY from the environment AT IMPORT TIME (module-level constants
below), so if something imports `db` before anything has loaded `.env` (e.g. run_daily.py's
`import db` on its own line, ahead of `import pipeline` which is what actually triggers
config.py's load_dotenv()), SUPA/KEY silently bake in as empty strings and db.enabled() is
False for the rest of the process — the whole learning loop no-ops while everything upstream
looks healthy. Fix: load .env HERE too, so this module never depends on import order elsewhere.
"""
from __future__ import annotations

import datetime as _dt
import os
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import quote as _quote

import config

try:
    # See the IMPORT-ORDER SAFETY note above — this module must never depend on some other
    # module happening to load .env first. Idempotent: harmless if config.py (or anything
    # else) already called load_dotenv() in this process.
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv simply not installed
    pass

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

SUPA = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Pre-decision features ONLY — the leakage-prevention non-negotiable. Never add rule_score,
# blended_score, model_proba, verdict, or reason here: those are the scout's OWN judgment and
# must never become part of what a model is trained to predict from (self-confirmation).
PRE_DECISION_FEATURES = (
    "asin", "price", "weight_lb", "sales_rank", "est_sales", "offers", "brand", "category",
    "avg_price_90", "avg_offers_90", "avg_sales_rank_90", "oos_90", "buybox_seller", "amazon_bb_share",
)


def enabled() -> bool:
    return bool(SUPA and KEY and requests)


def feature_snapshot(p: Dict[str, Any]) -> Dict[str, Any]:
    """Curate the pre-decision-only fields of an enriched product for storage. Used by
    log_lead() and read back by labels.py — the single definition of "pre-decision" so the
    write side and the training-time read side can never drift apart."""
    return {k: p.get(k) for k in PRE_DECISION_FEATURES}


def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _post(table: str, row: Dict[str, Any],
         migration_only_fields: Optional[set] = None) -> Optional[int]:
    """Plain insert. If it fails AND `migration_only_fields` names keys present in `row`,
    retries ONCE with those keys stripped — a pending migration's not-yet-existing columns
    (e.g. leads.features_snapshot/explanation before migration 001) would otherwise make
    PostgREST reject the WHOLE insert ("column not found in schema cache"), silently losing
    the row entirely rather than degrading gracefully (Code Review 2026-07-02, Finding B2). A
    failure for an unrelated reason (network, auth) fails the retry too and is reported as-is
    — this never masks a different underlying problem, it only gives a pending-migration
    failure a real second chance to actually write the row."""
    if not enabled():
        return None
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/{table}",
            headers=_headers({"Prefer": "return=representation"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data[0]["id"] if data else None
    except Exception as e:  # never let logging break a run
        stale = migration_only_fields and (set(row) & migration_only_fields)
        if stale:
            print(f"[db] insert failed for {table} ({e}); retrying without pending-migration "
                  f"field(s) {sorted(stale)} (run "
                  f"scout/db/migrations/001_g1_runs_and_idempotency.sql to store them)")
            stripped = {k: v for k, v in row.items() if k not in migration_only_fields}
            try:
                r = requests.post(
                    f"{SUPA}/rest/v1/{table}",
                    headers=_headers({"Prefer": "return=representation"}),
                    json=stripped, timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return data[0]["id"] if data else None
            except Exception as e2:
                print(f"[db] supabase log failed ({table}) even without pending-migration fields: {e2}")
                return None
        print(f"[db] supabase log failed ({table}): {e}")
        return None


def _is_missing_constraint_error(response: Optional[Any]) -> bool:
    """True if `response`'s JSON body reports Postgres's 42P10 ("no unique or exclusion
    constraint matching the ON CONFLICT specification") — the specific, actionable "the
    migration hasn't landed yet" signal. Any other error (network down, auth failure, a
    malformed payload, an unrelated 400) is NOT this, and pointing at a migration file for
    those would misdirect troubleshooting (Code Review 2026-07-02, Finding S11). Takes the
    Response object directly (still in scope from the try block) rather than inspecting the
    exception's own .response attribute, which not every raised exception carries."""
    if response is None:
        return False
    try:
        return response.json().get("code") == "42P10"
    except Exception:
        return False


def _upsert(table: str, row: Dict[str, Any], on_conflict: str,
           migration_only_fields: Optional[set] = None) -> Optional[int]:
    """POST with an upsert (merge-duplicates on the given natural key). Falls back to a plain
    insert (itself degrading further per `_post`'s migration_only_fields handling) if the
    target unique index doesn't exist yet (migration not applied) or any other error occurs —
    idempotency degrades gracefully, it never breaks a run."""
    if not enabled():
        return None
    r = None
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data[0]["id"] if data else None
    except Exception as e:
        if _is_missing_constraint_error(r):
            print(f"[db] upsert unavailable for {table} ({e}); falling back to plain insert "
                  f"(run scout/db/migrations/001_g1_runs_and_idempotency.sql to enable idempotency)")
        else:
            print(f"[db] upsert failed for {table} ({e}); falling back to plain insert. This "
                  f"does NOT look like a missing-migration issue (no 42P10) — check network/"
                  f"auth/payload before assuming a migration will fix it.")
        return _post(table, row, migration_only_fields=migration_only_fields)


# Columns that only exist on `leads` after migration 001 lands — stripped from a fallback
# insert so a pending migration degrades gracefully instead of losing the row entirely
# (Code Review 2026-07-02, Finding B2; see _post()'s migration_only_fields handling).
LEADS_MIGRATION_ONLY_FIELDS = {"features_snapshot", "explanation"}


def log_lead(p: Dict[str, Any], score: float, verdict: str, reason: str,
             found_via: str = "scout", explanation: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Upsert a lead row (idempotent on asin+found_via once migration 001 is applied; a plain
    insert otherwise) from an enriched+scored product dict. Returns the lead id.

    explanation: the structured {verdict, score, gates, adjustments} from scoring.explain_oa() —
    stored for human review/audit ONLY. It is never read back as a training feature (see
    PRE_DECISION_FEATURES / labels.py) — the scout's own judgment must never become its own label.
    """
    # amazon_present mirrors scoring.py's own hard-reject condition (Amazon currently holds the
    # Buy Box, OR its win-share is at/above the rotation threshold) — NOT "any measurable Amazon
    # presence at all," which would fire on a 1% share and misrepresent what the gate actually
    # means (Code Review 2026-07-02, Finding S10).
    bb_share = p.get("amazon_bb_share")
    amazon_present = (p.get("buybox_seller") == config.AMAZON_SELLER_ID) or (
        isinstance(bb_share, (int, float)) and bb_share >= config.OA_AMAZON_SHARE_MAX
    )
    row = {
        "asin": p.get("asin"), "title": p.get("title"), "brand": p.get("brand"),
        "category": p.get("category"),
        "amazon_url": f"https://www.amazon.com/dp/{p.get('asin')}" if p.get("asin") else None,
        "buy_cost": p.get("buy_cost"), "sell_price": p.get("price"),
        "profit": p.get("oa_profit"), "roi": p.get("oa_roi"),
        "monthly_sales": p.get("est_sales"), "bsr": p.get("sales_rank"),
        "offer_count": p.get("offers"),
        "amazon_present": amazon_present,
        "score": round(score) if score is not None else None,
        "verdict": verdict, "reason": reason,
        "found_by": "scout", "found_via": found_via,
        "features_snapshot": feature_snapshot(p),
        "explanation": explanation,
    }
    if p.get("asin"):
        return _upsert("leads", row, on_conflict="asin,found_via",
                       migration_only_fields=LEADS_MIGRATION_ONLY_FIELDS)
    return _post("leads", row,  # no ASIN -> nothing to key an upsert on
                migration_only_fields=LEADS_MIGRATION_ONLY_FIELDS)


def upsert_keepa_snapshot(p: Dict[str, Any]) -> Optional[int]:
    """Idempotent (asin + LOCAL day) snapshot of a Keepa read, once migration 001 is applied.
    Mirrors keepa_snapshots' real columns; unmapped fields are simply omitted.

    snapshot_date is sent explicitly as today's LOCAL calendar date (Code Review 2026-07-02,
    Finding S7) — migration 001 no longer derives it from captured_at via a generated column,
    because that would bucket by UTC date and mis-file a late-evening local run into
    "tomorrow." This is the single place that decides what "today" means for this table."""
    row = {
        "asin": p.get("asin"),
        "buybox_now": p.get("price"), "buybox_90": p.get("avg_price_90"),
        "rank_now": p.get("sales_rank"), "offers_now": p.get("offers"),
        "offers_90": p.get("avg_offers_90"), "amazon_share": p.get("amazon_bb_share"),
        "snapshot_date": _dt.date.today().isoformat(),
    }
    if not row.get("asin"):
        return None
    return _upsert("keepa_snapshots", row, on_conflict="asin,snapshot_date")


def log_decision(lead_id: int, decision: str, suggested_qty: Optional[int] = None,
                 reason: Optional[str] = None, ai_confidence: Optional[float] = None,
                 human_approved: bool = False, brand: Optional[str] = None) -> Optional[int]:
    """Record buy / test / wait / pass for a lead. When decision == "buy" and a brand is given,
    also queues that brand for periodic re-mining (Scout Agent Build Plan sec 3.3's
    brand-growth loop) — a human-approved buy is what triggers it, never an automatic scan."""
    result = _post("decisions", {
        "lead_id": lead_id, "decision": decision, "suggested_qty": suggested_qty,
        "reason": reason, "ai_confidence": ai_confidence, "human_approved": human_approved,
    })
    if decision == "buy" and brand:
        queue_brand_search(brand)
    return result


def log_outcome(lead_id: int, **fields) -> Optional[int]:
    """Record the realized result of a bought lead — this is the learning signal.
    Fields: bought_qty, sold_qty, avg_sale_price, days_to_sell, returns, actual_profit,
            actual_roi, price_tanked (bool), would_rebuy (bool), lesson (str)."""
    fields["lead_id"] = lead_id
    return _post("outcomes", fields)


# ----------------------------------------------------------------------------
# runs — one row per scout cycle (System Blueprint Prompt G1/G2). Degrades to a silent no-op
# (like every other function here) if Supabase isn't configured OR the `runs` table doesn't
# exist yet (migration 001 not applied) — _post already swallows that as a caught exception.
# ----------------------------------------------------------------------------
def start_run(host: Optional[str] = None) -> Optional[int]:
    """Call at the very start of a scout cycle. Returns the run id (None if unavailable)."""
    return _post("runs", {
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "status": "running",
        "host": host or socket.gethostname(),
    })


def finish_run(run_id: Optional[int], status: str, **counts) -> None:
    """Call in a finally-block at the end of a scout cycle — including on failure.
    counts: asins_scanned, candidates_gated, leads_upserted, tokens_consumed, tokens_left_end,
    error_summary. No-ops if run_id is None (start_run() already failed/was unavailable)."""
    if run_id is None or not enabled():
        return
    payload = {"finished_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "status": status}
    payload.update({k: v for k, v in counts.items() if v is not None})
    try:
        r = requests.patch(
            f"{SUPA}/rest/v1/runs?id=eq.{run_id}",
            headers=_headers({"Prefer": "return=minimal"}),
            json=payload, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[db] failed to finalize run {run_id}: {e}")


def recent_runs(limit: int = 14) -> List[Dict[str, Any]]:
    """Last N run rows, newest first. Empty list if unavailable — used by the drift/heartbeat
    checks and the tuning report, never assumed to exist."""
    if not enabled():
        return []
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/runs?select=*&order=started_at.desc&limit={int(limit)}",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] recent_runs failed: {e}")
        return []


def get_lead(asin: str) -> Optional[Dict[str, Any]]:
    """The most recent lead row for an ASIN, embedding its decisions + outcomes. None if
    unavailable, no key, or not found — read-only; used by scout/mcp_server.py (Prompt S4)."""
    if not enabled() or not asin:
        return None
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/leads?asin=eq.{_quote(asin, safe='')}"
            f"&select=*,decisions(*),outcomes(*)&order=created_at.desc&limit=1",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[db] get_lead failed ({asin}): {e}")
        return None


def top_leads_raw(limit: int = 10, since_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    """Most recent lead rows (optionally created_at >= since_iso), newest first, [] if
    unavailable. No ranking applied here — the caller (scout/mcp_server.py's top_leads() tool)
    orders by the triage formula; this is I/O only, matching db.py's role for every other table."""
    if not enabled():
        return []
    try:
        url = f"{SUPA}/rest/v1/leads?select=*&order=created_at.desc&limit={int(limit)}"
        if since_iso:
            url += f"&created_at=gte.{_quote(since_iso, safe='')}"
        r = requests.get(url, headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] top_leads_raw failed: {e}")
        return []


def leads_by_brand(brand: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Every lead row for a brand (case-insensitive exact match), embedding decisions +
    outcomes, newest first. [] if unavailable, no key, or no matches."""
    if not enabled() or not brand:
        return []
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/leads?brand=ilike.{_quote(brand, safe='')}"
            f"&select=*,decisions(*),outcomes(*)&order=created_at.desc&limit={int(limit)}",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] leads_by_brand failed ({brand}): {e}")
        return []


def leads_with_outcomes(limit: int = 500) -> List[Dict[str, Any]]:
    """Leads joined to their decision + outcome (if any), for labels.py. Uses PostgREST's
    embedded-resource syntax; returns [] if unavailable (no Supabase, or the tables/columns
    aren't there yet) rather than raising — the label builder must degrade honestly, not crash."""
    if not enabled():
        return []
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/leads?select=*,decisions(*),outcomes(*)&limit={int(limit)}",
            headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] leads_with_outcomes failed: {e}")
        return []


# ----------------------------------------------------------------------------
# SP-API restriction cache (System Blueprint Prompt G3) — account-specific eligibility is
# slow-changing; cache 7 days to respect the 5 req/s Listings Restrictions rate limit and avoid
# re-checking an ASIN we already know about every single cycle. Degrades to "no cache" (always
# checks live) if the table doesn't exist yet — migration 002 is not applied automatically.
# ----------------------------------------------------------------------------
RESTRICTION_CACHE_DAYS = 7


def get_cached_restriction(asin: str) -> Optional[Dict[str, Any]]:
    """A cached restriction result younger than RESTRICTION_CACHE_DAYS, or None (cache miss,
    unavailable, or the table doesn't exist yet — all treated the same: check live instead)."""
    if not enabled() or not asin:
        return None
    try:
        cutoff = (_dt.datetime.now(_dt.timezone.utc)
                 - _dt.timedelta(days=RESTRICTION_CACHE_DAYS)).isoformat()
        r = requests.get(
            f"{SUPA}/rest/v1/spapi_restrictions_cache"
            f"?asin=eq.{asin}&checked_at=gte.{cutoff}&select=*",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception:
        return None  # table absent or any other issue -> just check live, don't break the run


def cache_restriction(asin: str, result: Dict[str, Any]) -> None:
    """Upsert a fresh restriction result. Silent no-op on any failure (cache is an optimization,
    never a dependency — a failed cache write must never fail a restriction check)."""
    if not enabled() or not asin:
        return
    row = {
        "asin": asin, "status": result.get("status"),
        "reasons": result.get("reasons"), "links": result.get("links"),
        "checked_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    _upsert("spapi_restrictions_cache", row, on_conflict="asin")


# ----------------------------------------------------------------------------
# deals — raw retail-deal feed rows (Deal Finder Build Plan, Prompt D1). Idempotent on
# (retailer, sku, price_current, day) once migration 003 is applied; falls back to a plain
# insert for skuless rows (most Slickdeals items) or if the migration hasn't landed yet —
# same graceful-degrade convention as leads/keepa_snapshots.
# ----------------------------------------------------------------------------
def upsert_deal(row: Dict[str, Any]) -> Optional[int]:
    """Upsert one normalized deal row from a source connector (scout/deals/sources/). Bumps
    last_seen on every re-poll; first_seen is never included here so a re-sighting can't
    overwrite the original DB-default first_seen timestamp.

    seen_date is sent explicitly as today's LOCAL calendar date — migration 003's deals table
    can't derive it via a generated column (Postgres rejects timestamptz->date casts as
    non-immutable, 42P17), so this is the single place that decides what "today" means for the
    idempotent (retailer, sku, price_current, seen_date) key, matching the same explicit-date
    convention already used by upsert_keepa_snapshot()."""
    row = dict(row)
    row["last_seen"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    row.setdefault("seen_date", _dt.date.today().isoformat())
    if row.get("sku"):
        return _upsert("deals", row, on_conflict="retailer,sku,price_current,seen_date")
    return _post("deals", row)


# ----------------------------------------------------------------------------
# search_log — the brand-growth loop scaffolding (Scout Agent Build Plan, Prompt S2 sec 3.3).
# Idempotent enqueue (a brand queued twice is a no-op, never resets last_run_at); business
# logic (what's "due") lives in scout/search_log.py, this is I/O only, matching db.py's role
# for every other table. Degrades to no-op/[] if migration 004 isn't applied yet.
# ----------------------------------------------------------------------------
def queue_brand_search(brand: str, query_params: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Insert a search_log row for a brand if one doesn't already exist (ignore-duplicates on
    the brand unique index) — never overwrites an existing row's last_run_at.

    Normalizes `brand` to lowercase before writing (Code Review 2026-07-02, Finding B3): the
    unique index on search_log.brand is now a PLAIN column index (PostgREST's on_conflict=
    can't bind to an expression index like lower(brand)), so case-insensitive dedup has to
    happen here instead of in the index."""
    if not enabled() or not brand:
        return None
    row = {"brand": brand.strip().lower(), "query_params": query_params}
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/search_log?on_conflict=brand",
            headers=_headers({"Prefer": "resolution=ignore-duplicates,return=representation"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data[0]["id"] if data else None
    except Exception as e:
        print(f"[db] queue_brand_search failed ({brand}): {e}")
        return None


def all_search_log_rows() -> List[Dict[str, Any]]:
    """Every search_log row, for scout/search_log.py's due-date computation. [] if unavailable
    (no Supabase, or migration 004 hasn't landed) — never raises."""
    if not enabled():
        return []
    try:
        r = requests.get(f"{SUPA}/rest/v1/search_log?select=*", headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] all_search_log_rows failed: {e}")
        return []


def mark_search_run(search_id: Optional[int]) -> None:
    """Bump last_run_at to now after a search_log entry is actually re-run. Silent no-op on any
    failure — the search log is a scheduling aid, never a hard dependency."""
    if not enabled() or search_id is None:
        return
    try:
        r = requests.patch(
            f"{SUPA}/rest/v1/search_log?id=eq.{search_id}",
            headers=_headers({"Prefer": "return=minimal"}),
            json={"last_run_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[db] mark_search_run failed ({search_id}): {e}")
