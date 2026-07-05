"""
scout/deals/run_watch.py — the nightly Top-100 deal watch (TOP100_DEAL_WATCH_PLAN.md T1 step 6
+ T2). Standalone entry point: registry -> tier-scheduled adapters -> idempotent deals upserts
-> brand-anchored hints -> ONE Discord digest -> optional heartbeat.

Runs with ONLY SUPABASE_URL, SUPABASE_SERVICE_KEY, DISCORD_WEBHOOK_RETAIL_DEALS (+ optional
WOOT/BESTBUY keys, + optional HEALTHCHECK_URL_DEALWATCH). NO Keepa, NO Anthropic — it never
imports pipeline/keepa_client/model/analyst, so the cloud runner's requirements stay tiny
(requests + python-dotenv; see scout/requirements-dealwatch.txt). Designed for the free
GitHub Actions runner at 9 PM ET (T2), but fully runnable locally as a fallback.

Usage:
    python -m deals.run_watch            # real run
    python -m deals.run_watch --dry-run  # fetch + derive, but NO Supabase writes / Discord post
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

# Bare-name imports work when run as `python -m deals.run_watch` from scout/ (the package
# parent is on sys.path); the sources adapters use relative imports within the deals package.
import brands
import db
import discord_router
import redact

from . import hints as hints_mod
from . import normalize, registry, schedule, source_status
from .sources import bestbuy, clearance_page, dealnews_rss, reddit_rss, slickdeals_search, woot_api
from .sources import _feeds

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

log = logging.getLogger("scout.deals.run_watch")

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(HERE, "..", "..", "learning-hub", "data", "top100-status.json")
TOP_FINDS_IN_DIGEST = 8


def _aggregate(reg: Dict[str, Any], name_contains: str) -> Dict[str, Any]:
    for a in reg.get("aggregates", []) or []:
        if name_contains.lower() in (a.get("name") or "").lower():
            return a
    return {}


def collect_all(reg: Dict[str, Any], weekday: int, skip_urls=None) -> Dict[str, Any]:
    """Fetch every source due today. skip_urls = clr URLs already retired to sd-rss-only (not
    re-fetched). Returns {"rows": [...], "clr_results": [...], "clr_skipped": [...]}. Pure
    collection — no source_status/deals WRITES — so it's testable without Supabase (it does read
    the HTTP cache, injected)."""
    due = schedule.entries_due(reg, weekday)
    known_retailers = [e.get("name") for e in registry.all_entries(reg) if e.get("name")]
    rows: List[Dict[str, Any]] = []

    # Per-store Slickdeals search (Tier 1+2 daily, Tier 3 rotation).
    rows.extend(slickdeals_search.collect_for_entries(due["sd_rss"]))

    # Polite clearance pages (conditional GET via Supabase-backed HTTP cache; retired ones skipped).
    clr = clearance_page.collect_for_entries(
        due["clr"], http_cache_get=db.get_source_http_cache, http_cache_set=db.set_source_http_cache,
        skip_urls=skip_urls)
    rows.extend(clr["rows"])

    # Aggregates (cover the long tail via retailer-guessing; run every night).
    frontpage = _aggregate(reg, "frontpage").get("url")
    if frontpage:
        for it in _feeds.fetch_rss(frontpage):
            rows.append(normalize.normalize_rss_item(
                title=it["title"], url=it.get("link"), source="slickdeals",
                source_signal="sd-rss", known_retailers=known_retailers))
    rows.extend(reddit_rss.collect(_aggregate(reg, "reddit").get("urls", []), known_retailers))
    dealnews = _aggregate(reg, "dealnews")
    dealnews_urls = [dealnews["url"]] if dealnews.get("url") else []
    rows.extend(dealnews_rss.collect(dealnews_urls, known_retailers))

    # Official APIs (key-gated — honest no-op without a key).
    rows.extend(woot_api.collect())
    rows.extend(bestbuy.collect())

    return {"rows": rows, "clr_results": clr["results"], "clr_skipped": clr["skipped"]}


def apply_clr_status(clr_results: List[Dict[str, Any]], prev_status: Dict[str, Any],
                     dry_run: bool = False) -> Dict[str, Any]:
    """Turn this run's clr fetch results into source_status transitions + the report buckets.
    Returns {"broken": [(url, detail)], "newly_retired": [urls], "rate_limited": [urls]} —
    'broken' is NEW/active breakages only (already-retired URLs were never fetched, so they
    can't appear here); 429s go to rate_limited (transient), not broken. Persists each URL's new
    state unless dry_run."""
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    broken: List[tuple] = []
    newly_retired: List[str] = []
    rate_limited: List[str] = []
    for res in clr_results:
        url = res["url"]
        label = source_status.classify(res.get("status_code"), res["status"])
        prev = prev_status.get(url)
        state = source_status.next_state(prev, label, res.get("has_sd_rss", False))
        retired_at = now_iso if state["retired_now"] else (prev or {}).get("retired_at")
        if not dry_run:
            db.upsert_source_status(url, state["mode"], state["consecutive_403"],
                                    label, res.get("status_code"), retired_at=retired_at)
        if state["retired_now"]:
            # Reported once, as a retirement — NOT also as a generic breakage (no double-report).
            newly_retired.append(url)
        elif label == source_status.RATE_LIMITED:
            rate_limited.append(url)
        elif label in (source_status.FORBIDDEN, source_status.ERROR):
            broken.append((url, res.get("detail")))
    return {"broken": broken, "newly_retired": newly_retired, "rate_limited": rate_limited}


def _write_status(reg: Dict[str, Any], rows: List[Dict[str, Any]], clr_report: Dict[str, Any],
                  sd_rss_only: List[str]) -> None:
    """Write top100-status.json: VERIFY resolution, NEW clr breakages, the rate-limited (retry)
    set, and the full sd-rss-only retired set. Best-effort — a status-file write failure must
    never fail the run (the Discord digest carries the same signal). Ephemeral on the cloud
    runner; useful on local runs."""
    produced = {r.get("retailer") for r in rows if r.get("retailer") not in (None, "unknown")}
    verify_names = [e.get("name") for e in registry.all_entries(reg) if "VERIFY" in (e.get("flags") or [])]
    status = {
        "updated": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "note": ("Written by scout/deals/run_watch.py each run. verify_resolved = a "
                 "VERIFY-flagged registry source produced >=1 row this run. broken_clr = NEW/"
                 "active clr breakages (already-retired sd-rss-only URLs are skipped, not "
                 "re-listed). rate_limited = 429'd this run (transient, retried tomorrow). "
                 "sd_rss_only = clr URLs retired after 2 consecutive 403s — their Slickdeals "
                 "per-store feed still covers the store, so zero coverage loss. Ephemeral on "
                 "the cloud runner; the Discord digest carries the same signal."),
        "verify_resolved": sorted(n for n in verify_names if n in produced),
        "verify_unresolved": sorted(n for n in verify_names if n not in produced),
        "broken_clr": [{"url": u, "detail": d} for u, d in clr_report["broken"]],
        "rate_limited": sorted(clr_report["rate_limited"]),
        "newly_retired_to_sd_rss_only": sorted(clr_report["newly_retired"]),
        "sd_rss_only": sorted(sd_rss_only),
    }
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
            f.write("\n")
    except Exception as e:
        log.warning("could not write top100-status.json (non-fatal): %s", e)


def format_digest(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One Discord embed for the retail_deals stream: top finds by discount, per-source counts,
    broken-source warnings, hint summary. Honest when nothing was found."""
    total = summary["total_rows"]
    top = summary["top_finds"]
    if top:
        lines = []
        for d in top:
            disc = f" ({d['discount_pct']:.0f}% off)" if d.get("discount_pct") is not None else ""
            price = f"${d['price_current']:.2f}" if d.get("price_current") is not None else "?"
            lines.append(f"- {d['retailer']}: {d['title_raw'][:80]} {price}{disc}")
        description = "\n".join(lines)
    else:
        description = "No parseable deals this run (feeds may have been quiet or unreachable)."

    fields = [
        {"name": "Total collected", "value": str(total), "inline": True},
        {"name": "Upserted", "value": str(summary["upserted"]), "inline": True},
        {"name": "Hints derived", "value": str(summary["hints_written"]), "inline": True},
    ]
    by_source = summary.get("by_source") or {}
    if by_source:
        fields.append({"name": "By source",
                       "value": ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items())),
                       "inline": False})
    if summary.get("top_hints"):
        fields.append({"name": "\U0001F9ED Top brand hints (feed the scout)",
                       "value": ", ".join(f"{h['brand']}"
                                          + (f"@{h['store']}" if h.get("store") else "")
                                          + f" ({h['strength']:g})" for h in summary["top_hints"][:6]),
                       "inline": False})
    if summary.get("broken"):
        # NEW/active breakages only — already-retired sd-rss-only URLs were never fetched, so
        # they can't appear here (they stop being re-listed nightly once retired).
        fields.append({"name": "⚠ New broken sources",
                       "value": "\n".join(f"- {redact.redact(u)}: {redact.redact(str(d))[:80]}"
                                          for u, d in summary["broken"][:6]),
                       "inline": False})
    if summary.get("newly_retired"):
        fields.append({"name": "🗂️ Retired to sd-rss-only (2× 403)",
                       "value": "\n".join(f"- {redact.redact(u)}" for u in summary["newly_retired"][:6])
                                + "\n(Slickdeals per-store feed still covers these stores — zero coverage loss.)",
                       "inline": False})
    if summary.get("rate_limited"):
        fields.append({"name": "⏳ Rate-limited (retry tomorrow)",
                       "value": ", ".join(redact.redact(u) for u in summary["rate_limited"][:6]),
                       "inline": False})
    embed = {
        "title": "\U0001F6D2 Top-100 deal watch",
        "description": description,
        "color": 0x36D399 if total else 0x8B9BB0,
        "fields": fields,
        "footer": {"text": "matching not yet built — these feed the scout as hints, not buys"},
    }
    return [embed]


def _ping_heartbeat(ok: bool) -> None:
    url = os.getenv("HEALTHCHECK_URL_DEALWATCH")
    if not url or not requests:
        return
    try:
        requests.get(url if ok else url.rstrip("/") + "/fail", timeout=10)
    except Exception as e:
        log.warning("deal-watch heartbeat failed: %s", e)


def run(weekday: Optional[int] = None, dry_run: bool = False, notify: bool = True) -> Dict[str, Any]:
    reg = registry.load_registry()
    problems = registry.validate(reg)
    if problems:
        # The registry is the single source — an invalid one is a hard failure, not a
        # degrade-to-empty (unlike a dead feed). Surface EVERY problem at once.
        raise ValueError("top100-sources.json failed validation:\n  - " + "\n  - ".join(problems))

    weekday = weekday if weekday is not None else _dt.date.today().weekday()

    # Load clr health BEFORE fetching, so we skip URLs already retired to sd-rss-only (their
    # Slickdeals feed covers the store) and can detect CONSECUTIVE 403s across runs.
    prev_status = db.get_all_source_status()
    skip_urls = {u for u, row in prev_status.items() if row.get("mode") == source_status.MODE_SD_RSS_ONLY}

    collected = collect_all(reg, weekday, skip_urls=skip_urls)
    rows = collected["rows"]
    clr_report = apply_clr_status(collected["clr_results"], prev_status, dry_run=dry_run)

    upserted = 0
    if not dry_run:
        for r in rows:
            if db.upsert_deal(r) is not None:
                upserted += 1

    hint_list = hints_mod.derive_hints(rows, brands.OA_FRIENDLY_BRANDS, brands.AVOID_BRANDS)
    hints_written = 0
    if not dry_run:
        for h in hint_list:
            if db.upsert_deal_hint(h["brand"], h["store"], h["category"], h["strength"]) is not None:
                hints_written += 1

    # The full sd-rss-only set = previously-retired + anything retired this run.
    sd_rss_only = sorted(skip_urls | set(clr_report["newly_retired"]))
    _write_status(reg, rows, clr_report, sd_rss_only)

    by_source: Dict[str, int] = {}
    for r in rows:
        by_source[r.get("source_signal") or "?"] = by_source.get(r.get("source_signal") or "?", 0) + 1
    priced = [r for r in rows if r.get("price_current") is not None]
    top_finds = sorted(priced, key=lambda r: (r.get("discount_pct") or 0), reverse=True)[:TOP_FINDS_IN_DIGEST]

    summary = {
        "total_rows": len(rows), "upserted": upserted, "hints_written": hints_written,
        "by_source": by_source, "top_finds": top_finds, "top_hints": hint_list,
        "broken": clr_report["broken"], "newly_retired": clr_report["newly_retired"],
        "rate_limited": clr_report["rate_limited"], "clr_skipped": collected["clr_skipped"],
        "weekday": weekday, "dry_run": dry_run,
    }

    if notify and not dry_run:
        try:
            discord_router.send("retail_deals", format_digest(summary))
        except Exception as e:
            log.warning("retail_deals digest post failed (non-fatal): %s", redact.redact(str(e)))
    if not dry_run:
        _ping_heartbeat(ok=True)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run the nightly Top-100 deal watch.")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch + derive hints, but make NO Supabase writes and post NOTHING to Discord")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    printable = {k: v for k, v in result.items() if k not in ("top_finds", "top_hints")}
    printable["top_finds"] = len(result["top_finds"])
    printable["top_hints"] = len(result["top_hints"])
    print(json.dumps(printable, indent=2, default=str))
    sys.exit(0)
