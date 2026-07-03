"""
Tests for Deal Finder Build Plan Prompt D1: scout/deals/collect.py's orchestrator.

Zero live network calls — every source connector and db.upsert_deal are mocked/patched.
SAFETY: real DISCORD_WEBHOOK_RETAIL_DEALS lives in scout/.env, so tests that don't care about
the Discord notify pass notify=False (never touches discord_router at all); tests that DO
exercise the notify path explicitly mock collect.discord_router (see test_run_daily.py's
module docstring for the incident that established this rule).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deals import collect  # noqa: E402


def _row(retailer="Target", sku=None):
    return {"retailer": retailer, "source": "test", "sku": sku, "title_raw": "X", "price_current": 1.0}


def test_collect_all_aggregates_row_counts_and_upserts():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row(), _row()], "b": lambda: [_row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal", return_value=1) as mock_upsert:
        summary = collect.collect_all(notify=False)
    assert summary["sources"] == {"a": 2, "b": 1}
    assert summary["total_rows"] == 3
    assert summary["upserted"] == 3
    assert mock_upsert.call_count == 3


def test_collect_all_dry_run_never_writes():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row(), _row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal") as mock_upsert, \
         patch.object(collect, "discord_router") as mock_router:
        summary = collect.collect_all(dry_run=True)
    assert summary["total_rows"] == 2
    assert summary["upserted"] == 0
    mock_upsert.assert_not_called()
    mock_router.send.assert_not_called()  # a dry run must post NOTHING externally


def test_collect_all_survives_a_failing_source():
    def boom():
        raise RuntimeError("feed down")

    with patch.dict(collect.SOURCES, {"a": boom, "b": lambda: [_row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal", return_value=1):
        summary = collect.collect_all(notify=False)
    assert summary["sources"]["a"] == 0
    assert summary["sources"]["b"] == 1
    assert summary["total_rows"] == 1


def test_collect_all_respects_explicit_source_list():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row()], "b": lambda: [_row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal", return_value=1):
        summary = collect.collect_all(sources=["a"], notify=False)
    assert summary["sources"] == {"a": 1}


def test_collect_all_skips_disabled_sources_from_brain_when_no_explicit_list():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row()], "b": lambda: [_row()]}, clear=True), \
         patch.object(collect.brain_config, "source_config",
                     side_effect=lambda name: {"enabled": False} if name == "b" else {}), \
         patch.object(collect.db, "upsert_deal", return_value=1):
        summary = collect.collect_all(notify=False)
    assert "a" in summary["sources"]
    assert "b" not in summary["sources"]


# ---------------------------------------------------------------------------
# notify_retail_deals — short stats embed to "retail_deals"
# ---------------------------------------------------------------------------

def test_notify_retail_deals_noop_when_nothing_found():
    with patch.object(collect, "discord_router") as mock_router:
        ok = collect.notify_retail_deals({"sources": {}, "total_rows": 0, "upserted": 0})
    assert ok is False
    mock_router.send.assert_not_called()


def test_notify_retail_deals_sends_stats_embed():
    with patch.object(collect, "discord_router") as mock_router:
        mock_router.send.return_value = True
        ok = collect.notify_retail_deals({"sources": {"slickdeals": 5}, "total_rows": 5, "upserted": 4})
    assert ok is True
    stream, embed = mock_router.send.call_args[0]
    assert stream == "retail_deals"
    assert "slickdeals: 5" in embed["description"]


def test_collect_all_notifies_by_default_when_rows_found():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal", return_value=1), \
         patch.object(collect, "discord_router") as mock_router:
        mock_router.send.return_value = True
        collect.collect_all()
    mock_router.send.assert_called_once()
    assert mock_router.send.call_args[0][0] == "retail_deals"


def test_collect_all_survives_notify_failure():
    with patch.dict(collect.SOURCES, {"a": lambda: [_row()]}, clear=True), \
         patch.object(collect.db, "upsert_deal", return_value=1), \
         patch.object(collect, "notify_retail_deals", side_effect=RuntimeError("boom")):
        summary = collect.collect_all()  # must not raise
    assert summary["total_rows"] == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
