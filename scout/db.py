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
#
# Session 55 additions (free signal-type features — scout/signals/): every new field is
# NULLABLE and carries its own stale/status companion where the source can go stale (Trends,
# eBay) — a missing/degraded signal must never silently look like a real zero. calendar.*
# fields are pure functions of the row's own as-of date (never stale — see
# scout/signals/calendar.py); upc is Keepa-sourced, feeding scout/signals/ebay.py.
PRE_DECISION_FEATURES = (
    "asin", "price", "weight_lb", "sales_rank", "est_sales", "offers", "brand", "category",
    "avg_price_90", "avg_offers_90", "avg_sales_rank_90", "oos_90", "buybox_seller", "amazon_bb_share",
    "upc",
    # calendar (scout/signals/calendar.py) — pure functions of the row's as-of date
    "days_to_prime_day", "weeks_to_q4_arrival_deadline", "days_to_nearest_major_holiday",
    "nearest_major_holiday_name", "is_bts_window", "day_of_week",
    # brand/category Trends (scout/signals/trends.py) — nullable, stale-flagged
    "brand_trend_ratio", "brand_trend_slope", "brand_trend_seasonal_z", "brand_trend_spike",
    "brand_trend_stale",
    "category_trend_ratio", "category_trend_slope", "category_trend_seasonal_z",
    "category_trend_spike", "category_trend_stale",
    # eBay active-listing comps (scout/signals/ebay.py) — key-gated, LIVE-ONLY (not
    # backfillable), nullable. Named "active", not "sold": the Browse API this module calls has
    # no sold/completed-item filter — true sold-comps need eBay's separate, invitation-gated
    # Marketplace Insights API (review fix, 2026-07-06 — was misleadingly named ebay_sold_count_30d).
    "ebay_active_listing_count", "median_active_price_vs_amazon_ratio", "ebay_stale",
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


def _count_exact(path_and_query: str) -> int:
    """Row count via PostgREST's `Prefer: count=exact` + a zero-row Range — the count comes
    back in the Content-Range header ("0-0/N" or "*/0"), exact no matter how large the table
    grows. Fetch-all-and-len() silently truncates at the server's max-rows cap (default 1000)
    and undercounts with no error (Code Review 2026-07-03, Finding #5). Raises on any failure —
    callers decide how to degrade."""
    r = requests.get(
        f"{SUPA}/rest/v1/{path_and_query}",
        headers=_headers({"Prefer": "count=exact", "Range": "0-0"}),
        timeout=15,
    )
    r.raise_for_status()
    content_range = r.headers.get("Content-Range", "")
    total = content_range.rsplit("/", 1)[-1]
    if not total.isdigit():
        raise ValueError(f"unparseable Content-Range: {content_range!r}")
    return int(total)


def queue_pending_counts() -> Optional[Dict[str, int]]:
    """Counts for the control-center's Review Queue (CC1) — leads scout marked "review" with
    no decision recorded yet, and deal_matches still awaiting a human verdict. Uses the SAME
    PostgREST anti-join filter as control-center/lib/supabase-server.ts's
    getUndecidedReviewLeads() (left join + decisions=is.null — verified live against this
    project's PostgREST), so the digest's count and the /queue page select identical row sets.
    None (not a zero dict) if Supabase is unavailable or either query fails — a failed read
    must never be misreported as an honestly empty queue."""
    if not enabled():
        return None
    try:
        pending_leads = _count_exact(
            "leads?select=id,decisions!left(lead_id)&decisions=is.null&verdict=eq.review"
        )
        pending_matches = _count_exact("deal_matches?select=id&human_verdict=is.null")
        return {"leads": pending_leads, "deal_matches": pending_matches}
    except Exception as e:
        print(f"[db] queue_pending_counts failed: {e}")
        return None


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
        # Review fix (2026-07-08, live incident): cutoff (a tz-aware ISO timestamp, e.g.
        # "...+00:00") was interpolated raw/unquoted. PostgREST's query-string parser decodes an
        # unescaped '+' as a space (the historic application/x-www-form-urlencoded convention),
        # corrupting the UTC offset so Postgres rejects the whole filter with a 400 ("invalid
        # input syntax for type timestamp with time zone"). Live-reproduced against production
        # and confirmed fixed by _quote()ing the timestamp, matching every other timestamp/string
        # filter value in this file (e.g. due_shadow_checkpoints() below, top_leads_raw()).
        r = requests.get(
            f"{SUPA}/rest/v1/spapi_restrictions_cache"
            f"?asin=eq.{_quote(asin, safe='')}&checked_at=gte.{_quote(cutoff, safe='')}&select=*",
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
# Columns that only exist on `deals` after migration 007 lands — stripped from a fallback
# insert so a pre-007 write degrades gracefully instead of losing the whole row (same pattern
# as LEADS_MIGRATION_ONLY_FIELDS; see _post()'s migration_only_fields handling).
DEALS_MIGRATION_ONLY_FIELDS = {"source_signal", "extraction_confidence"}


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
        return _upsert("deals", row, on_conflict="retailer,sku,price_current,seen_date",
                       migration_only_fields=DEALS_MIGRATION_ONLY_FIELDS)
    return _post("deals", row, migration_only_fields=DEALS_MIGRATION_ONLY_FIELDS)


def get_deals_by_status(status: str = "new", limit: int = 200) -> List[Dict[str, Any]]:
    """Deals awaiting a match attempt (default status='new'), oldest first — the matcher's
    (scout/deals/matcher.py) work queue. [] if unavailable; never raises."""
    if not enabled():
        return []
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/deals?select=*&status=eq.{_quote(status, safe='')}"
            f"&order=first_seen.asc&limit={int(limit)}",
            headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] get_deals_by_status failed: {e}")
        return []


def update_deal_status(deal_id: int, status: str) -> bool:
    """PATCH one deal's status ('new' | 'matched' | 'discarded') after the matcher has processed
    it, so a re-run of matcher.run() doesn't re-attempt the same deal forever. Returns whether
    the write succeeded — best-effort; a failure here doesn't lose the deal_matches row already
    written, it just means this deal may be re-attempted next run (idempotent — upsert_deal_match
    below dedupes on (deal_id, asin) at the application level)."""
    if not enabled():
        return False
    try:
        r = requests.patch(
            f"{SUPA}/rest/v1/deals?id=eq.{int(deal_id)}",
            headers=_headers({"Prefer": "return=minimal"}),
            json={"status": status}, timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[db] update_deal_status failed (deal {deal_id}): {e}")
        return False


# ----------------------------------------------------------------------------
# deal_matches — one row per candidate ASIN the matcher (scout/deals/matcher.py, Deal Finder
# Build Plan Prompt D2) proposes for a deal. Migration 003 defines the table WITHOUT a unique
# constraint on it (unlike deals/deal_hints), so idempotency here is APPLICATION-level: find_
# deal_match() below is checked before every write rather than relying on an on_conflict upsert.
# ----------------------------------------------------------------------------
def find_deal_match(deal_id: int, asin: str) -> Optional[Dict[str, Any]]:
    """The existing deal_matches row for this (deal_id, asin) pair, if the matcher already
    proposed it on a prior run — None if not found or unavailable. Callers use this to avoid
    writing duplicate candidate rows when matcher.run() re-processes (idempotency has no DB
    constraint to lean on here, see the section note above)."""
    if not enabled() or not asin:
        return None
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/deal_matches?deal_id=eq.{int(deal_id)}"
            f"&asin=eq.{_quote(asin, safe='')}&select=*&limit=1",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[db] find_deal_match failed (deal {deal_id}, {asin}): {e}")
        return None


def upsert_deal_match(deal_id: int, asin: Optional[str], confidence: Optional[float],
                      method: Optional[str], pack_match: Optional[bool] = None,
                      llm_reason: Optional[str] = None) -> Optional[int]:
    """Record one candidate ASIN for a deal. Checks find_deal_match() first and PATCHes the
    existing row instead of inserting a duplicate when the matcher has already proposed this
    exact (deal_id, asin) pair (e.g. a re-run after a new source signal). Returns the row id, or
    None if unavailable/failed. human_verdict is intentionally never set here — that column is
    written only by the control-center's human review action (recordDealMatchVerdict in
    supabase-server.ts), never by the matcher itself."""
    if not enabled() or not asin:
        return None
    existing = find_deal_match(deal_id, asin)
    row = {
        "deal_id": deal_id, "asin": asin, "confidence": confidence,
        "method": method, "pack_match": pack_match, "llm_reason": llm_reason,
    }
    if existing:
        try:
            r = requests.patch(
                f"{SUPA}/rest/v1/deal_matches?id=eq.{existing['id']}",
                headers=_headers({"Prefer": "return=minimal"}),
                json=row, timeout=10,
            )
            r.raise_for_status()
            return existing["id"]
        except Exception as e:
            print(f"[db] upsert_deal_match update failed (deal {deal_id}, {asin}): {e}")
            return None
    return _post("deal_matches", row)


def get_deal_matches_ready_to_apply(min_confidence: float, limit: int = 200) -> List[Dict[str, Any]]:
    """deal_matches rows a human has approved, OR whose algorithmic confidence already cleared
    the brain's auto-accept band, embedding the parent deal (retailer/price_current/url) — the
    read side of Phase 2.3's "populate the lead's real fields" bridge
    (scout/deals/matcher.apply_verified_matches()). Whether each one has ALREADY been applied to
    its lead is decided by the caller (checking the target lead's own source_store), not here —
    this function is I/O only. [] if unavailable."""
    if not enabled():
        return []
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/deal_matches"
            f"?select=*,deals(*)"
            f"&or=(human_verdict.eq.approve,confidence.gte.{min_confidence})"
            f"&order=created_at.asc&limit={int(limit)}",
            headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] get_deal_matches_ready_to_apply failed: {e}")
        return []


def update_lead_source(asin: str, buy_cost: float, source_store: Optional[str],
                       source_url: Optional[str], profit: Optional[float],
                       roi: Optional[float]) -> bool:
    """PATCH an existing lead with a REAL buy cost + source (Sourcing plan Phase 2.3) once the
    deal-finder matcher has verified where to actually buy it, replacing the OA_COGS_FRACTION
    50%-of-price assumption for this one lead. profit/roi must already be recomputed from the
    real buy_cost by the caller (scoring.estimate_oa_profit_roi with an explicit cogs_fraction —
    this function never computes fee math itself, matching the single-source-of-truth rule).
    Returns whether the write succeeded. Only ever narrows toward truth: this never creates a
    lead, only enriches one that already exists (found via scout's own normal Keepa discovery
    and already gate-checked) — see matcher.apply_verified_matches()'s docstring for why
    deal-first LEAD CREATION is out of scope here."""
    if not enabled() or not asin:
        return False
    row = {"buy_cost": buy_cost, "source_store": source_store, "source_url": source_url}
    if profit is not None:
        row["profit"] = profit
    if roi is not None:
        row["roi"] = roi
    try:
        r = requests.patch(
            f"{SUPA}/rest/v1/leads?asin=eq.{_quote(asin, safe='')}",
            headers=_headers({"Prefer": "return=minimal"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[db] update_lead_source failed ({asin}): {e}")
        return False


# ----------------------------------------------------------------------------
# deal_hints + source_http_cache — the nightly deal watch's "look here first" signal and the
# polite clearance-page fetcher's cross-run HTTP cache (migration 007, TOP100_DEAL_WATCH_PLAN).
# Every function here degrades to a no-op / [] / None if migration 007 hasn't landed yet —
# nothing breaks by waiting, the scout just gets no hints and clearance pages skip conditional
# GET. I/O only; the AVOID gate + strength math live in scout/deals/run_watch.py.
# ----------------------------------------------------------------------------
def _hint_key(brand: Optional[str], store: Optional[str], category: Optional[str]) -> str:
    """Normalized single natural key for a hint, so the upsert has one non-null column to
    conflict on (NULL-in-unique-index would treat every partial hint as distinct)."""
    return "|".join((part or "").strip().lower() for part in (brand, store, category))


def upsert_deal_hint(brand: Optional[str], store: Optional[str], category: Optional[str],
                     strength: float, ttl_hours: int = 72) -> Optional[int]:
    """Upsert one hint (idempotent on the normalized brand|store|category key once migration
    007 is applied). Bumps last_seen + strength + expiry on every re-derivation; first_seen is
    never sent so a re-sighting preserves the original. Returns the row id (None if unavailable
    or the write failed). Callers MUST have already excluded AVOID brands — this is I/O, it
    does not re-check the avoid list."""
    if not enabled():
        return None
    now = _dt.datetime.now(_dt.timezone.utc)
    row = {
        "hint_key": _hint_key(brand, store, category),
        "brand": brand, "store": store, "category": category,
        "strength": strength,
        "last_seen": now.isoformat(),
        "expires_at": (now + _dt.timedelta(hours=ttl_hours)).isoformat(),
    }
    return _upsert("deal_hints", row, on_conflict="hint_key")


def fresh_deal_hints(min_strength: float = 0.0) -> List[Dict[str, Any]]:
    """Non-expired hints at or above min_strength, strongest first. [] if unavailable or the
    table is absent — the scout treats an empty list as 'no fresh hints, self-directed
    discovery', never an error (scout/discovery_hints.py). Expiry is filtered server-side
    against now() so a stale hint can never leak into a discovery pass."""
    if not enabled():
        return []
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/deal_hints",
            headers=_headers(),
            params={"select": "*", "expires_at": f"gt.{now_iso}",
                    "strength": f"gte.{min_strength}", "order": "strength.desc"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] fresh_deal_hints failed: {e}")
        return []


def get_source_http_cache(source_key: str) -> Optional[Dict[str, Any]]:
    """Prior ETag/Last-Modified validators for a source_key (for a conditional GET), or None if
    none stored / unavailable / the table is absent."""
    if not enabled() or not source_key:
        return None
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/source_http_cache",
            headers=_headers(),
            params={"select": "etag,last_modified", "source_key": f"eq.{source_key}", "limit": "1"},
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception as e:
        print(f"[db] get_source_http_cache failed ({source_key}): {e}")
        return None


def set_source_http_cache(source_key: str, etag: Optional[str], last_modified: Optional[str]) -> None:
    """Store the latest validators after a 200 response. Silent no-op on any failure — the HTTP
    cache is a politeness optimization, never a hard dependency.

    Does its OWN merge-duplicates POST rather than reusing _upsert(): source_http_cache's PK is
    `source_key` (no `id` column), and _upsert() reads data[0]["id"] from the returned row,
    which KeyErrors here and falls back to a plain insert that then 409s on the existing PK
    (seen live 2026-07-04). return=minimal avoids reading any column back."""
    if not enabled() or not source_key:
        return
    row = {
        "source_key": source_key, "etag": etag, "last_modified": last_modified,
        "last_fetched": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/source_http_cache?on_conflict=source_key",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[db] set_source_http_cache failed ({source_key}): {e}")


# ----------------------------------------------------------------------------
# source_status — per-clearance-URL health state (migration 008, TOP100_DEAL_WATCH follow-up).
# I/O only; the retire/reset transition logic lives in scout/deals/source_status.py. Degrades
# to {}/no-op if migration 008 hasn't landed. Keyed by url (no `id` column) — the write does
# its own merge-duplicates POST for the same reason set_source_http_cache does (return=minimal,
# so _upsert's data[0]["id"] can't KeyError -> 409, the bug caught live 2026-07-04).
# ----------------------------------------------------------------------------
def get_all_source_status() -> Dict[str, Dict[str, Any]]:
    """Every source_status row, as {url: row}. {} if unavailable or the table is absent — the
    caller treats an unknown URL as 'active, 0 consecutive 403s' (the safe default)."""
    if not enabled():
        return {}
    try:
        r = requests.get(f"{SUPA}/rest/v1/source_status?select=*", headers=_headers(), timeout=10)
        r.raise_for_status()
        return {row["url"]: row for row in (r.json() or []) if row.get("url")}
    except Exception as e:
        print(f"[db] get_all_source_status failed: {e}")
        return {}


def upsert_source_status(url: str, mode: str, consecutive_403: int, last_status: Optional[str],
                         last_status_code: Optional[int], retired_at: Optional[str] = None) -> None:
    """Persist a clr URL's health after a run. Silent no-op on any failure — source status is a
    scheduling aid, never a hard dependency."""
    if not enabled() or not url:
        return
    row = {
        "url": url, "mode": mode, "consecutive_403": consecutive_403,
        "last_status": last_status, "last_status_code": last_status_code,
        "last_checked": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "retired_at": retired_at,
    }
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/source_status?on_conflict=url",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=row, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[db] upsert_source_status failed ({url}): {e}")


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


# ----------------------------------------------------------------------------
# shadow_outcomes — proxy ("silver") training labels (migration 009, DATA_ENGINE_PLAN.md V1).
# I/O only; the enqueue/recheck logic lives in scout/shadow_outcomes.py. Degrades to no-op/[]
# if migration 009 hasn't landed. Idempotent enqueue via merge-duplicates on the natural key
# (asin, candidate_run_id, checkpoint_day) — return=minimal so a PK-only conflict can't hit the
# data[0]["id"] KeyError->409 bug (same fix as source_status).
# ----------------------------------------------------------------------------
def enqueue_shadow_outcome(row: Dict[str, Any]) -> bool:
    """Insert one (asin, candidate_run_id, checkpoint_day) shadow row if absent; a duplicate
    enqueue is a no-op (ignore-duplicates), never resetting the frozen 'then' snapshot. Returns
    True only when the write actually succeeded, so callers can count honestly instead of
    reporting phantom enqueues (Review 2026-07-05). Never raises."""
    return enqueue_shadow_outcomes([row]) == 1


def enqueue_shadow_outcomes(rows: List[Dict[str, Any]]) -> int:
    """Batch enqueue — ONE bulk POST for the whole run's shadow rows instead of 2 sequential
    round-trips per survivor (400 POSTs on a 200-survivor night). Returns the number of rows
    actually sent (0 on failure/disabled) — the caller's honest count. Never raises."""
    rows = [r for r in (rows or []) if r.get("asin")]
    if not enabled() or not rows:
        return 0
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/shadow_outcomes?on_conflict=asin,candidate_run_id,checkpoint_day",
            headers=_headers({"Prefer": "resolution=ignore-duplicates,return=minimal"}),
            json=rows, timeout=30,
        )
        r.raise_for_status()
        return len(rows)
    except Exception as e:
        print(f"[db] enqueue_shadow_outcomes failed ({len(rows)} rows): {e}")
        return 0


def due_shadow_checkpoints(now_iso: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """Pending shadow rows whose checkpoint has come due (due_at <= now), oldest first. [] if
    unavailable or migration 009 hasn't landed — never raises."""
    if not enabled():
        return []
    now_iso = now_iso or _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        # Review fix (2026-07-08, live incident): now_iso (a tz-aware ISO timestamp, e.g.
        # "...+00:00") was interpolated raw/unquoted — the ONE filter value in this file that
        # broke its own established _quote() convention (get_lead/top_leads_raw/leads_by_brand
        # all quote their string/timestamp filters). PostgREST's query-string parser decodes an
        # unescaped '+' as a space (the historic application/x-www-form-urlencoded convention),
        # corrupting the UTC offset so Postgres rejected the WHOLE filter with a 400 every single
        # time this ran ("invalid input syntax for type timestamp with time zone") — tier 1
        # (shadow rechecks) silently did zero real work on every hourly burst since this was
        # written. Live-reproduced against production and confirmed fixed by _quote()ing now_iso.
        r = requests.get(
            f"{SUPA}/rest/v1/shadow_outcomes?status=eq.pending&due_at=lte.{_quote(now_iso, safe='')}"
            f"&order=due_at.asc&limit={int(limit)}",
            headers=_headers(), timeout=10,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] due_shadow_checkpoints failed: {e}")
        return []


def complete_shadow_checkpoint(row_id: int, fields: Dict[str, Any]) -> None:
    """Fill a shadow row's 'now' snapshot + would_have_profited at recheck time. Silent no-op on
    any failure — never blocks the weekly job."""
    if not enabled() or row_id is None:
        return
    try:
        r = requests.patch(
            f"{SUPA}/rest/v1/shadow_outcomes?id=eq.{int(row_id)}",
            headers=_headers({"Prefer": "return=minimal"}),
            json=fields, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[db] complete_shadow_checkpoint failed ({row_id}): {e}")


def _get_paged(path_and_query: str, limit: int, page_size: int = 1000) -> List[Dict[str, Any]]:
    """Range-header pagination for large reads. PostgREST silently caps a single response at the
    server's max-rows (default 1000) — a plain `limit=60000` request would return 2% of a 50k-row
    corpus WITH NO ERROR (Review 2026-07-05). Raises on failure; callers decide how to degrade."""
    out: List[Dict[str, Any]] = []
    offset = 0
    while offset < limit:
        take = min(page_size, limit - offset)
        r = requests.get(
            f"{SUPA}/rest/v1/{path_and_query}",
            headers=_headers({"Range": f"{offset}-{offset + take - 1}"}), timeout=30,
        )
        r.raise_for_status()
        page = r.json() or []
        out.extend(page)
        if len(page) < take:
            break
        offset += take
    return out


def all_shadow_outcomes(limit: int = 20000) -> List[Dict[str, Any]]:
    """Every completed shadow row (status=done, would_have_profited not null), for labels.py's
    silver tier. Paginated past PostgREST's 1000-row response cap. [] if unavailable or
    migration 009 hasn't landed — never raises."""
    if not enabled():
        return []
    try:
        return _get_paged(
            "shadow_outcomes?status=eq.done&would_have_profited=not.is.null&select=*&order=id.asc",
            limit=limit)
    except Exception as e:
        print(f"[db] all_shadow_outcomes failed: {e}")
        return []


# ----------------------------------------------------------------------------
# backtest_rows — the backtest engine's derived training rows (migration 010, V2). I/O only; the
# windowing/leakage/labeling logic lives in scout/backtest.py. Degrades to no-op/[]/0 if migration
# 010 hasn't landed. Idempotent upsert on (asin, simulation_date) so a re-run overwrites a window
# rather than duplicating it.
# ----------------------------------------------------------------------------
# Columns that only exist on `backtest_rows` after migration 011 lands (Session 55's sampling
# overhaul) — stripped from a fallback insert/select so a pending migration degrades gracefully
# (row collection keeps working exactly as before) instead of the whole batch/read failing.
BACKTEST_ROWS_MIGRATION_ONLY_FIELDS = {"sample_source", "category", "ip_risk"}


def upsert_backtest_rows(rows: List[Dict[str, Any]]) -> int:
    """Batch-upsert backtest rows (merge-duplicates on asin+simulation_date, return=minimal so the
    PK-only shape can't hit the data[0]['id'] 409 bug). Returns the count sent, or 0 on any
    failure/disabled. Retries once WITHOUT sample_source/category/ip_risk if migration 011 hasn't
    landed yet (PostgREST rejects the whole batch on an unknown column) — never raises."""
    if not enabled() or not rows:
        return 0
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/backtest_rows?on_conflict=asin,simulation_date",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=rows, timeout=30,
        )
        r.raise_for_status()
        return len(rows)
    except Exception as e:
        stale = BACKTEST_ROWS_MIGRATION_ONLY_FIELDS & set().union(*(row.keys() for row in rows))
        if stale:
            print(f"[db] upsert_backtest_rows failed ({len(rows)} rows): {e}; retrying without "
                 f"pending-migration field(s) {sorted(stale)} (run scout/db/migrations/"
                 "011_backtest_sampling_columns.sql to store them)")
            stripped = [{k: v for k, v in row.items() if k not in BACKTEST_ROWS_MIGRATION_ONLY_FIELDS}
                       for row in rows]
            try:
                r = requests.post(
                    f"{SUPA}/rest/v1/backtest_rows?on_conflict=asin,simulation_date",
                    headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                    json=stripped, timeout=30,
                )
                r.raise_for_status()
                return len(rows)
            except Exception as e2:
                print(f"[db] upsert_backtest_rows failed even without pending-migration fields "
                     f"({len(rows)} rows): {e2}")
                return 0
        print(f"[db] upsert_backtest_rows failed ({len(rows)} rows): {e}")
        return 0


_BACKTEST_ROWS_SELECT_NEW = ("asin,simulation_date,features_snapshot,would_have_profited,"
                             "est_profit,label_quality,sample_source,category,ip_risk")
_BACKTEST_ROWS_SELECT_OLD = ("asin,simulation_date,features_snapshot,would_have_profited,"
                             "est_profit,label_quality")


def all_backtest_rows(limit: int = 60000) -> List[Dict[str, Any]]:
    """Every backtest row, for labels.py's backtest tier / V3's ranker. Paginated past
    PostgREST's 1000-row response cap (a flat request would silently truncate the 50k-row
    corpus). Column-restricted to what training actually reads. Retries once with the
    pre-migration-011 column list if sample_source/category/ip_risk don't exist yet (an unknown
    column fails the WHOLE select, not just those fields) — [] if unavailable entirely. Never
    raises."""
    if not enabled():
        return []
    try:
        return _get_paged(f"backtest_rows?select={_BACKTEST_ROWS_SELECT_NEW}&order=id.asc",
                          limit=limit)
    except Exception as e:
        print(f"[db] all_backtest_rows: new-column select failed ({e}); retrying without "
             "sample_source/category/ip_risk (run scout/db/migrations/"
             "011_backtest_sampling_columns.sql to enable them)")
        try:
            return _get_paged(f"backtest_rows?select={_BACKTEST_ROWS_SELECT_OLD}&order=id.asc",
                              limit=limit)
        except Exception as e2:
            print(f"[db] all_backtest_rows failed: {e2}")
            return []


def all_backtest_rows_for_backfill(limit: int = 60000) -> List[Dict[str, Any]]:
    """EVERY column of every backtest row (unlike all_backtest_rows()'s training-only column
    subset) — scout/signals/trends_backfill.py needs the FULL row so it can patch
    features_snapshot with newly-computed signal features and re-upsert the whole row back via
    upsert_backtest_rows() on the SAME (asin, simulation_date) natural key, never touching
    would_have_profited/est_profit/etc. [] if unavailable — never raises."""
    if not enabled():
        return []
    try:
        return _get_paged("backtest_rows?select=*&order=id.asc", limit=limit)
    except Exception as e:
        print(f"[db] all_backtest_rows_for_backfill failed: {e}")
        return []


def backtest_rows_by_source() -> Dict[str, int]:
    """Row count per sample_source (dealfeed/explore/onpolicy) — feeds the digest's sampling-
    composition line and the ranker report's onpolicy-vs-explore breakdown. Rows written before
    migration 011 (or by a caller not yet passing sample_source) have it NULL, reported as
    'unknown' rather than silently dropped. {} if unavailable or the migration hasn't landed —
    never raises."""
    if not enabled():
        return {}
    try:
        out: Dict[str, int] = {}
        for src in ("dealfeed", "explore", "onpolicy"):
            out[src] = _count_exact(f"backtest_rows?select=id&sample_source=eq.{src}")
        total = count_backtest_rows()
        known = sum(out.values())
        if total > known:
            out["unknown"] = total - known
        return out
    except Exception as e:
        print(f"[db] backtest_rows_by_source failed: {e}")
        return {}


def count_backtest_rows() -> int:
    """Exact backtest_rows count (for resume + the honest per-tier report line). 0 if unavailable
    or migration 010 hasn't landed — never raises."""
    if not enabled():
        return 0
    try:
        return _count_exact("backtest_rows?select=id")
    except Exception as e:
        print(f"[db] count_backtest_rows failed: {e}")
        return 0


# ----------------------------------------------------------------------------
# hourly-collector telemetry (scout/collect_hourly.py, keepa-collect.yml, Session 54). I/O
# only; used by run_daily.py's local housekeeping run to report "hourly-collection totals" in
# the daily digest, since scanning itself moved to the hourly cloud collector.
# ----------------------------------------------------------------------------
def hourly_runs_today() -> List[Dict[str, Any]]:
    """Every collect_hourly.py run (host='github-actions-hourly', start_run()'s own host label)
    since UTC midnight today. [] if unavailable — never raises."""
    if not enabled():
        return []
    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT00:00:00")
    try:
        r = requests.get(
            f"{SUPA}/rest/v1/runs?host=eq.github-actions-hourly&started_at=gte.{today}&select=*",
            headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] hourly_runs_today failed: {e}")
        return []


# ----------------------------------------------------------------------------
# trends_series (migration 012, Session 55 free signal-type features) — weekly Google Trends
# interest points per brand/category term. I/O only; scout/signals/trends.py owns fetching +
# feature computation (interest_now_vs_90d_avg, slope_4wk, seasonal_z, spike_flag).
# ----------------------------------------------------------------------------
def recent_brand_vocabulary(limit: int = 200) -> List[str]:
    """Distinct brands seen recently in leads + deal_hints — trends.py's rolling brand
    vocabulary (Session 55: 'every brand seen in deals/leads'). Most-recently-seen first
    (per source, then merged — not a perfect global time interleave across both tables, which
    is fine for a capped discovery vocabulary), deduped case-insensitively, capped at `limit`.
    [] if unavailable — never raises."""
    if not enabled():
        return []
    try:
        out: List[str] = []
        seen = set()
        for path in (
            f"leads?select=brand,id&brand=not.is.null&order=id.desc&limit={limit * 2}",
            f"deal_hints?select=brand,id&brand=not.is.null&order=id.desc&limit={limit * 2}",
        ):
            r = requests.get(f"{SUPA}/rest/v1/{path}", headers=_headers(), timeout=15)
            r.raise_for_status()
            for row in r.json() or []:
                b = (row.get("brand") or "").strip()
                key = b.lower()
                if b and key not in seen:
                    seen.add(key)
                    out.append(b)
        return out[:limit]
    except Exception as e:
        print(f"[db] recent_brand_vocabulary failed: {e}")
        return []


def upsert_trends_series(rows: List[Dict[str, Any]]) -> int:
    """Batch-upsert weekly trend points (merge-duplicates on term+week_start). Returns the count
    sent, or 0 on any failure/disabled/migration-not-landed — never raises."""
    if not enabled() or not rows:
        return 0
    try:
        r = requests.post(
            f"{SUPA}/rest/v1/trends_series?on_conflict=term,week_start",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=rows, timeout=30,
        )
        r.raise_for_status()
        return len(rows)
    except Exception as e:
        print(f"[db] upsert_trends_series failed ({len(rows)} rows): {e}")
        return 0


def trends_series_for(term: str, before: Optional[str] = None, limit: int = 400) -> List[Dict[str, Any]]:
    """A term's weekly series, oldest first. `before` (an ISO date) restricts to week_start <
    before — the leakage-safe read backfill uses so a historical row only ever sees Trends data
    strictly before its own as-of date. [] if unavailable or migration 012 hasn't landed."""
    if not enabled():
        return []
    try:
        q = f"trends_series?term=eq.{_quote(term)}&select=week_start,interest&order=week_start.asc&limit={limit}"
        if before:
            q += f"&week_start=lt.{before}"
        r = requests.get(f"{SUPA}/rest/v1/{q}", headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[db] trends_series_for failed ({term}): {e}")
        return []


_TRENDS_BULK_CHUNK = 150  # PostgREST's in.() filter in one request; well above any real per-run
                         # distinct-term count (collect_hourly's DEFAULT_HINT_SCAN_LIMIT=60,
                         # backtest's _ENRICH_BATCH=100) so one run almost never needs a 2nd chunk


def trends_series_bulk(terms: List[str], limit_per_term: int = 400) -> Dict[str, List[Dict[str, Any]]]:
    """Every listed term's weekly series, grouped by term, in ONE request per _TRENDS_BULK_CHUNK
    terms (PostgREST `term=in.(...)`) instead of one request PER term.

    Review fix (2026-07-06): collect_hourly.py's _attach_signal_features() and backtest.py's
    _fetch_trend_series() each called trends_series_for() once per distinct brand/category term
    seen in a batch — up to ~70-200+ sequential live HTTP round trips per hourly burst once
    there were real candidates to score. That N+1 pattern was the root cause of the hourly
    collector silently hanging past keepa-collect.yml's 10-minute job timeout (every run since
    the Keepa bank recovered from its overdraw got force-killed mid-flight, never reaching
    finish_run() — the Supabase `runs` row stuck at status='running' forever). This bulk read
    is what both callers now use to pre-fetch a whole batch's terms in one round trip.

    {} (every term maps to []) if unavailable, migration 012 hasn't landed, or the request
    fails — never raises; callers already treat an empty series as stale=True, same as a
    genuinely untracked term."""
    out: Dict[str, List[Dict[str, Any]]] = {t: [] for t in terms if t}
    if not enabled() or not out:
        return out
    uniq = sorted(out.keys())
    try:
        for start in range(0, len(uniq), _TRENDS_BULK_CHUNK):
            chunk = uniq[start:start + _TRENDS_BULK_CHUNK]
            in_list = ",".join(_quote(t) for t in chunk)
            q = (f"trends_series?term=in.({in_list})&select=term,week_start,interest"
                f"&order=term.asc,week_start.asc")
            rows = _get_paged(q, limit=limit_per_term * len(chunk))
            for r in rows:
                term = r.get("term")
                if term in out:
                    out[term].append(r)
        return out
    except Exception as e:
        print(f"[db] trends_series_bulk failed ({len(terms)} terms): {e}")
        return {t: [] for t in terms if t}


# Columns that only exist once migrations 014/015 are applied — record_ranker_run strips these
# and retries when PostgREST rejects the insert, so a pre-migration database loses only these
# keys, never the whole run row (the same NOT-APPLIED-tolerant pattern upsert_backtest_rows
# uses for migration 011's columns).
RANKER_RUNS_MIGRATION_ONLY_FIELDS = {
    "concentration",                                            # 014
    "content_hash", "time_split_champion_auc",                  # 015
    "time_split_challenger_auc", "time_split_val_rows", "promotion_gate",
}


def record_ranker_run(**fields: Any) -> bool:
    """One row per non-skipped scout/train_ranker.py run — trained AND refused (refused rows are
    deliberately recorded: promotion_gate's consecutive-wins streak treats them as
    streak-breaking evidence via _run_won); only skip-if-unchanged ticks write nothing
    (migrations 013/014/015). The durable, queryable record that ranker-report.md and the
    Discord post never were; the control-center's training-history chart reads it back. Never
    raises; returns False on any failure/disabled, same degrade-gracefully convention as every
    other write in this module."""
    if not enabled():
        return False
    for attempt_fields in (fields,
                          {k: v for k, v in fields.items()
                           if k not in RANKER_RUNS_MIGRATION_ONLY_FIELDS}):
        try:
            r = requests.post(
                f"{SUPA}/rest/v1/ranker_runs",
                headers=_headers({"Prefer": "return=minimal"}),
                json=attempt_fields, timeout=15,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            if attempt_fields is not fields:
                print(f"[db] record_ranker_run failed (non-fatal, ranker-report.md/Discord "
                     f"still get this run's result): {e}")
                return False
            print(f"[db] record_ranker_run: full insert failed ({e}); retrying without "
                 f"migration-014/015 columns (run scout/db/migrations/014+015 to enable them)")
    return False


def recent_ranker_runs(limit: int = 5) -> List[Dict[str, Any]]:
    """Last N ranker_runs rows, newest first — the promotion-consistency check (ML de-bias audit,
    2026-07-09): a single run's challenger win can be small-sample noise (e.g. run 4 flipped from
    losing to winning on only ~186 val rows as the corpus de-biased), so train_ranker.py checks
    whether the challenger has ALSO won recently, not just this run. Selects the migration-015
    gate-evidence columns (content_hash for the streak-padding dedup, time-split AUCs for the
    both-axes win check) and falls back to the pre-015 column list on a 400 so a pre-migration
    database still gets the basic streak read. [] if unavailable/disabled — never raises, same
    degrade-gracefully convention as every other read in this module."""
    if not enabled():
        return []
    selects = (
        "trained_at,refused,champion_auc,challenger_auc,verdict,content_hash,"
        "time_split_champion_auc,time_split_challenger_auc",
        "trained_at,refused,champion_auc,challenger_auc,verdict",  # pre-015 fallback
    )
    for i, select in enumerate(selects):
        try:
            r = requests.get(
                f"{SUPA}/rest/v1/ranker_runs?select={select}&order=trained_at.desc&limit={limit}",
                headers=_headers(), timeout=15,
            )
            r.raise_for_status()
            return r.json() or []
        except Exception as e:
            if i == len(selects) - 1:
                print(f"[db] recent_ranker_runs failed (non-fatal): {e}")
    return []
