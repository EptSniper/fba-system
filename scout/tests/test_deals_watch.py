"""
Tests for the Top-100 deal watch (TOP100_DEAL_WATCH_PLAN.md T1): tier scheduling, hint
derivation + the AVOID gate, the new registry-driven adapters (slickdeals_search / reddit_rss /
dealnews_rss / woot_api / clearance_page), and run_watch orchestration + digest. Zero live
network — every HTTP call is mocked, matching scout/tests/test_deals_sources.py's convention.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deals import hints as hints_mod  # noqa: E402
from deals import normalize, schedule  # noqa: E402
from deals.sources import clearance_page, dealnews_rss, reddit_rss, slickdeals_search, woot_api  # noqa: E402


# ---------------------------------------------------------------------------
# Tier scheduling — deterministic rotation, tier rules
# ---------------------------------------------------------------------------
def _reg():
    return {
        "tier1": [{"name": "T1a", "detect": ["sd-rss:t1a", "clr:https://t1a.com/sale"], "flags": []}],
        "tier2": [{"name": f"T2_{i}", "detect": ["sd-rss:x", "clr:https://x.com/s"], "flags": []} for i in range(14)],
        "tier3": [{"name": f"T3_{i}", "detect": ["sd-rss:y"], "flags": []} for i in range(14)],
    }


def test_rotation_day_is_deterministic():
    # Same name -> same day, EVERY call (would fail if it used Python's randomized hash()).
    assert schedule._rotation_day("Costco") == schedule._rotation_day("Costco")
    assert 0 <= schedule._rotation_day("Costco") <= 6


def test_tier1_fetched_daily_both_methods():
    for weekday in range(7):
        due = schedule.entries_due(_reg(), weekday)
        assert any(e["name"] == "T1a" for e in due["sd_rss"])
        assert any(e["name"] == "T1a" for e in due["clr"])


def test_tier2_sdrss_daily_but_clr_rotates():
    reg = _reg()
    # sd-rss every day for every Tier2 entry.
    for weekday in range(7):
        due = schedule.entries_due(reg, weekday)
        assert sum(1 for e in due["sd_rss"] if e["name"].startswith("T2_")) == 14
    # clr spread across the week — not all 14 on any single day, and total coverage over a week.
    clr_by_day = [sum(1 for e in schedule.entries_due(reg, wd)["clr"] if e["name"].startswith("T2_"))
                  for wd in range(7)]
    assert max(clr_by_day) < 14  # never all at once
    assert sum(clr_by_day) == 14  # each T2 clr fetched exactly once per week


def test_tier3_only_on_rotation_day():
    reg = _reg()
    counts = [sum(1 for e in schedule.entries_due(reg, wd)["sd_rss"] if e["name"].startswith("T3_"))
              for wd in range(7)]
    assert sum(counts) == 14 and max(counts) < 14  # spread, each exactly once/week


# ---------------------------------------------------------------------------
# Hint derivation — friendly-brand anchoring, AVOID gate, quality filter
# ---------------------------------------------------------------------------
FRIENDLY = ["Jellycat", "Yeti", "Crayola"]
AVOID = ["Nike", "Adidas", "Disney"]


def _row(title, retailer="Target", brand=None, price=10.0, disc=None, conf=0.9):
    return {"title_raw": title, "retailer": retailer, "brand": brand,
            "price_current": price, "discount_pct": disc, "extraction_confidence": conf}


def test_hint_from_friendly_brand_in_title():
    rows = [_row("Jellycat Bunny Plush $25")]
    hints = hints_mod.derive_hints(rows, FRIENDLY, AVOID)
    assert len(hints) == 1
    assert hints[0]["brand"] == "Jellycat" and hints[0]["store"] == "Target"


def test_avoid_brand_never_produces_a_hint():
    rows = [_row("Nike Air Max $99", brand="Nike"), _row("Nike Sale $80", retailer="Kohl's")]
    assert hints_mod.derive_hints(rows, FRIENDLY, AVOID) == []


def test_avoid_gate_holds_even_if_avoid_brand_is_also_on_friendly_list():
    # Defensive: a misconfiguration putting a brand on BOTH lists must still be BLOCKED.
    rows = [_row("Disney Plush $30", brand="Disney")]
    assert hints_mod.derive_hints(rows, ["Disney"], ["Disney"]) == []


def test_non_friendly_non_avoid_brand_produces_no_hint():
    rows = [_row("Generic Widget $5", brand="Acme")]
    assert hints_mod.derive_hints(rows, FRIENDLY, AVOID) == []


def test_low_confidence_or_no_price_deal_is_not_quality():
    rows = [_row("Yeti Cooler", brand="Yeti", price=None),          # no price
            _row("Yeti Tumbler $30", brand="Yeti", conf=0.3)]       # low confidence
    assert hints_mod.derive_hints(rows, FRIENDLY, AVOID) == []


def test_discount_weights_strength_higher():
    plain = hints_mod.derive_hints([_row("Yeti Cup $20", brand="Yeti")], FRIENDLY, AVOID)
    disc = hints_mod.derive_hints([_row("Yeti Cup $20", brand="Yeti", disc=40)], FRIENDLY, AVOID)
    assert disc[0]["strength"] > plain[0]["strength"]


# ---------------------------------------------------------------------------
# Adapters — mocked feeds / API / clearance page
# ---------------------------------------------------------------------------
def test_slickdeals_search_tags_retailer_from_entry():
    entries = [{"name": "Walmart", "detect": ["sd-rss:walmart"], "flags": []}]
    with patch.object(slickdeals_search._feeds, "fetch_rss",
                      return_value=[{"title": "Some deal $9.99", "link": "http://x"}]):
        rows = slickdeals_search.collect_for_entries(entries)
    assert len(rows) == 1
    assert rows[0]["retailer"] == "Walmart" and rows[0]["source_signal"] == "sd-rss"


def test_reddit_and_dealnews_guess_retailer_from_title():
    with patch.object(reddit_rss._feeds, "fetch_rss",
                      return_value=[{"title": "Target: Crayola $1.99", "link": "http://r"}]):
        rows = reddit_rss.collect(["http://reddit/r/deals/.rss"], known_retailers=["Target"])
    assert rows[0]["retailer"] == "Target" and rows[0]["source"] == "reddit"
    with patch.object(dealnews_rss._feeds, "fetch_rss",
                      return_value=[{"title": "Best Buy: Sony $49", "link": "http://d"}]):
        rows = dealnews_rss.collect(["http://dealnews/rss"], known_retailers=["Best Buy"])
    assert rows[0]["retailer"] == "Best Buy"


def test_woot_honest_no_op_without_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WOOT_API_KEY", None)
        assert woot_api.collect() == []


def test_woot_parses_items_when_keyed():
    payload = {"Items": [{"OfferId": 7, "Title": "Widget", "SalePrice": 10, "ListPrice": 20, "Url": "http://w"}]}
    resp = MagicMock(); resp.raise_for_status = MagicMock(); resp.json.return_value = payload
    with patch.dict(os.environ, {"WOOT_API_KEY": "k"}), patch.object(woot_api, "requests") as rq:
        rq.get.return_value = resp
        rows = woot_api.collect()
    assert rows[0]["price_current"] == 10 and rows[0]["discount_pct"] == 50.0


def test_clearance_page_obeys_robots_disallow():
    with patch.object(clearance_page, "_robots_allows", return_value=False):
        result = clearance_page.fetch_page("http://x.com/sale", "X", {})
    assert result["status"] == "skipped_robots" and result["rows"] == []


def test_clearance_page_304_not_modified_uses_conditional_headers():
    resp = MagicMock(status_code=304)
    sent_headers = {}

    def fake_get(url, headers=None, timeout=None):
        sent_headers.update(headers or {})
        return resp
    with patch.object(clearance_page, "_robots_allows", return_value=True), \
         patch.object(clearance_page, "requests") as rq:
        rq.get.side_effect = fake_get
        result = clearance_page.fetch_page(
            "http://x.com/sale", "X", {},
            http_cache_get=lambda u: {"etag": "abc", "last_modified": "Mon"})
    assert result["status"] == "not_modified"
    assert sent_headers.get("If-None-Match") == "abc"
    assert sent_headers.get("If-Modified-Since") == "Mon"


def test_clearance_page_extracts_jsonld_and_stores_validators():
    html = ('<html><script type="application/ld+json">'
            '{"@type":"Product","name":"Cool Toy","offers":{"price":"12.50"}}</script></html>')
    resp = MagicMock(status_code=200, text=html)
    resp.headers = {"ETag": "v2", "Last-Modified": "Tue"}
    stored = {}
    with patch.object(clearance_page, "_robots_allows", return_value=True), \
         patch.object(clearance_page, "requests") as rq:
        rq.get.return_value = resp
        result = clearance_page.fetch_page(
            "http://x.com/sale", "X", {},
            http_cache_get=lambda u: None,
            http_cache_set=lambda u, e, lm: stored.update({"etag": e, "lm": lm}))
    assert result["status"] == "ok"
    assert result["rows"][0]["title_raw"] == "Cool Toy" and result["rows"][0]["price_current"] == 12.5
    assert stored == {"etag": "v2", "lm": "Tue"}


# ---------------------------------------------------------------------------
# run_watch orchestration + digest
# ---------------------------------------------------------------------------
def test_run_watch_dry_run_makes_no_writes_but_derives_hints():
    import deals.run_watch as rw
    fake_rows = [_row("Jellycat Bear $25", retailer="Target", brand="Jellycat")]
    with patch.object(rw, "collect_all", return_value={"rows": fake_rows, "clr_results": [], "clr_skipped": []}), \
         patch.object(rw.db, "get_all_source_status", return_value={}), \
         patch.object(rw.db, "upsert_deal") as up_deal, \
         patch.object(rw.db, "upsert_deal_hint") as up_hint, \
         patch.object(rw, "_write_status"), \
         patch.object(rw.brands, "OA_FRIENDLY_BRANDS", ["Jellycat"]), \
         patch.object(rw.brands, "AVOID_BRANDS", ["Nike"]):
        summary = rw.run(weekday=0, dry_run=True, notify=False)
    up_deal.assert_not_called()       # dry run writes NOTHING
    up_hint.assert_not_called()
    assert summary["total_rows"] == 1
    assert len(summary["top_hints"]) == 1 and summary["top_hints"][0]["brand"] == "Jellycat"


def test_run_watch_hard_fails_on_invalid_registry():
    import deals.run_watch as rw
    with patch.object(rw.registry, "load_registry", return_value={"tier1": []}), \
         patch.object(rw.registry, "validate", return_value=["missing tier 'tier2'"]):
        try:
            rw.run(weekday=0, dry_run=True, notify=False)
        except ValueError as e:
            assert "missing tier" in str(e)
        else:
            raise AssertionError("run() must hard-fail on an invalid registry")


def test_digest_reports_broken_sources_and_hints():
    import deals.run_watch as rw
    summary = {
        "total_rows": 3, "upserted": 3, "hints_written": 1,
        "by_source": {"sd-rss": 3},
        "top_finds": [{"retailer": "Target", "title_raw": "Yeti Cup", "price_current": 20.0, "discount_pct": 40.0}],
        "top_hints": [{"brand": "Yeti", "store": "Target", "strength": 1.5}],
        "broken": [("http://dead.com/sale", "HTTP 500")],
        "newly_retired": ["http://forbidden.com/clearance"],
        "rate_limited": ["http://chewy.com/deals"],
    }
    embed = rw.format_digest(summary)[0]
    names = [f["name"] for f in embed["fields"]]
    assert any("New broken sources" in n for n in names)
    assert any("sd-rss-only" in n for n in names)   # retired transition surfaced
    assert any("Rate-limited" in n for n in names)  # 429s shown separately, not as broken
    assert any("brand hints" in n.lower() for n in names)
    assert "matching not yet built" in embed["footer"]["text"]


def test_digest_honest_when_nothing_found():
    import deals.run_watch as rw
    embed = rw.format_digest({"total_rows": 0, "upserted": 0, "hints_written": 0,
                              "by_source": {}, "top_finds": [], "top_hints": [], "broken": []})[0]
    assert "No parseable deals" in embed["description"]
    assert embed["color"] == 0x8B9BB0


# ---------------------------------------------------------------------------
# source_status — the retire/429/consecutive logic (the 2026-07-04 follow-up)
# ---------------------------------------------------------------------------
from deals import source_status  # noqa: E402


def test_403_retires_to_sd_rss_only_after_two_consecutive():
    s1 = source_status.next_state(None, "forbidden", has_sd_rss_fallback=True)
    assert s1 == {"mode": "active", "consecutive_403": 1, "retired_now": False}
    s2 = source_status.next_state(s1, "forbidden", has_sd_rss_fallback=True)
    assert s2["mode"] == "sd-rss-only" and s2["retired_now"] is True


def test_403_does_not_retire_without_sd_rss_fallback():
    """A clr-only store (no sd-rss) that 403s must NOT be retired — there's nothing covering it,
    so it keeps getting reported."""
    prev = {"mode": "active", "consecutive_403": 1}
    s = source_status.next_state(prev, "forbidden", has_sd_rss_fallback=False)
    assert s["mode"] == "active" and s["retired_now"] is False


def test_429_is_transient_never_retires_never_counts():
    prev = {"mode": "active", "consecutive_403": 1}
    s = source_status.next_state(prev, "rate_limited", has_sd_rss_fallback=True)
    assert s == {"mode": "active", "consecutive_403": 1, "retired_now": False}


def test_success_resets_the_403_streak():
    prev = {"mode": "active", "consecutive_403": 1}
    assert source_status.next_state(prev, "ok", has_sd_rss_fallback=True)["consecutive_403"] == 0


def test_non_consecutive_403s_do_not_retire():
    s1 = source_status.next_state(None, "forbidden", True)           # 1
    s2 = source_status.next_state(s1, "ok", True)                    # reset to 0
    s3 = source_status.next_state(s2, "forbidden", True)             # 1 again, not 2
    assert s3["mode"] == "active" and s3["retired_now"] is False


def test_apply_clr_status_skips_retired_and_filters_digest():
    """apply_clr_status: 403 with fallback that hits 2 -> retired (not in broken, in
    newly_retired); 429 -> rate_limited (not broken); a fresh 500 error -> broken."""
    import deals.run_watch as rw
    prev = {"http://a.com/clr": {"mode": "active", "consecutive_403": 1}}
    results = [
        {"url": "http://a.com/clr", "retailer": "A", "has_sd_rss": True, "status": "error", "status_code": 403, "detail": "HTTP 403"},
        {"url": "http://chewy.com/deals", "retailer": "Chewy", "has_sd_rss": False, "status": "error", "status_code": 429, "detail": "HTTP 429"},
        {"url": "http://b.com/clr", "retailer": "B", "has_sd_rss": True, "status": "error", "status_code": 500, "detail": "HTTP 500"},
    ]
    with patch.object(rw.db, "upsert_source_status") as up:
        report = rw.apply_clr_status(results, prev, dry_run=False)
    assert report["newly_retired"] == ["http://a.com/clr"]     # 2nd consecutive 403 -> retired
    assert report["rate_limited"] == ["http://chewy.com/deals"]  # 429 is not broken
    assert [u for u, _ in report["broken"]] == ["http://b.com/clr"]  # only the 500 is a broken report
    assert up.call_count == 3  # all three persisted


def test_apply_clr_status_dry_run_persists_nothing():
    import deals.run_watch as rw
    results = [{"url": "http://a.com/clr", "retailer": "A", "has_sd_rss": True, "status": "error", "status_code": 403, "detail": "x"}]
    with patch.object(rw.db, "upsert_source_status") as up:
        rw.apply_clr_status(results, {}, dry_run=True)
    up.assert_not_called()


def test_run_watch_skips_already_retired_clr_urls():
    """A URL already in sd-rss-only mode at run start must be in collect_all's skip_urls."""
    import deals.run_watch as rw
    captured = {}

    def fake_collect_all(reg, weekday, skip_urls=None):
        captured["skip_urls"] = skip_urls
        return {"rows": [], "clr_results": [], "clr_skipped": list(skip_urls or [])}

    with patch.object(rw.db, "get_all_source_status",
                      return_value={"http://dead.com/clr": {"mode": "sd-rss-only"}, "http://ok.com/clr": {"mode": "active"}}), \
         patch.object(rw, "collect_all", side_effect=fake_collect_all), \
         patch.object(rw, "_write_status"), \
         patch.object(rw.brands, "OA_FRIENDLY_BRANDS", []), patch.object(rw.brands, "AVOID_BRANDS", []):
        rw.run(weekday=0, dry_run=True, notify=False)
    assert captured["skip_urls"] == {"http://dead.com/clr"}  # only the retired one is skipped


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn(); passed += 1; print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
