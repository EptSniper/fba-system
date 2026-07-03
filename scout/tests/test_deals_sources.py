"""
Tests for Deal Finder Build Plan Prompt D1: scout/deals/sources/slickdeals.py + bestbuy.py.

Zero live network calls — `requests` is mocked throughout, matching the project's existing
convention (see scout/tests/test_spapi.py). Validates the LOGIC (RSS parsing, price/retailer
guessing, Best Buy pagination + honest no-key no-op); neither connector has been exercised
against the real live API yet.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deals.sources import bestbuy, slickdeals  # noqa: E402

# ---------------------------------------------------------------------------
# Slickdeals RSS
# ---------------------------------------------------------------------------

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Target: Crayola Crayons 24ct $1.99 (Reg. $3.99)</title>
  <link>https://slickdeals.net/f/1111-crayola</link>
</item>
<item>
  <title>Best Buy: Sony Headphones $49.99</title>
  <link>https://slickdeals.net/f/2222-sony</link>
</item>
<item>
  <title>Free Shipping Sitewide</title>
  <link>https://slickdeals.net/f/3333-noprice</link>
</item>
</channel></rss>"""


def _mock_rss_response(body: str):
    r = MagicMock()
    r.content = body.encode("utf-8")
    r.raise_for_status = MagicMock()
    return r


def test_fetch_feed_parses_items():
    with patch.object(slickdeals, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_rss_response(_SAMPLE_RSS)
        items = slickdeals.fetch_feed("https://example.test/rss")
    assert len(items) == 3
    assert items[0]["title"].startswith("Target: Crayola")


def test_fetch_feed_degrades_to_empty_on_network_error():
    with patch.object(slickdeals, "requests") as mock_requests:
        mock_requests.get.side_effect = Exception("timeout")
        items = slickdeals.fetch_feed("https://example.test/rss")
    assert items == []


def test_fetch_feed_degrades_to_empty_on_malformed_xml():
    with patch.object(slickdeals, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_rss_response("<not><valid</xml>")
        items = slickdeals.fetch_feed("https://example.test/rss")
    assert items == []


def test_guess_retailer_from_title():
    assert slickdeals._guess_retailer("Target: Crayola Crayons $1.99") == "Target"
    assert slickdeals._guess_retailer("Best Buy: Sony Headphones $49.99") == "Best Buy"
    assert slickdeals._guess_retailer("Some obscure boutique deal") == "unknown"


def test_parse_prices_current_and_regular():
    current, original = slickdeals._parse_prices("Target: Crayola Crayons 24ct $1.99 (Reg. $3.99)")
    assert current == 1.99
    assert original == 3.99


def test_parse_prices_single_price_no_original():
    current, original = slickdeals._parse_prices("Best Buy: Sony Headphones $49.99")
    assert current == 49.99
    assert original is None


def test_parse_prices_no_price_at_all():
    current, original = slickdeals._parse_prices("Free Shipping Sitewide")
    assert current is None
    assert original is None


def test_normalize_items_computes_discount_pct():
    items = [{"title": "Target: Crayola Crayons 24ct $1.99 (Reg. $3.99)",
              "link": "https://slickdeals.net/f/1111"}]
    rows = slickdeals.normalize_items(items)
    assert len(rows) == 1
    row = rows[0]
    assert row["retailer"] == "Target"
    assert row["source"] == "slickdeals"
    assert row["price_current"] == 1.99
    assert row["price_original"] == 3.99
    assert row["discount_pct"] == 50.1
    assert row["sku"] is None and row["upc"] is None


def test_collect_uses_brain_config_feeds_when_none_passed():
    with patch.object(slickdeals.brain_config, "source_config", return_value={"feeds": ["https://brain-feed.test/rss"]}), \
         patch.object(slickdeals, "fetch_feed", return_value=[]) as mock_fetch:
        slickdeals.collect()
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args[0][0] == "https://brain-feed.test/rss"


def test_collect_explicit_feeds_overrides_brain_config():
    with patch.object(slickdeals, "fetch_feed", return_value=[]) as mock_fetch:
        slickdeals.collect(feeds=["https://explicit.test/rss"])
    mock_fetch.assert_called_once_with("https://explicit.test/rss", timeout=15)


# ---------------------------------------------------------------------------
# Best Buy Products API
# ---------------------------------------------------------------------------

def test_configured_false_without_api_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BESTBUY_API_KEY", None)
        assert bestbuy.configured() is False


def test_collect_honest_no_op_without_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BESTBUY_API_KEY", None)
        rows = bestbuy.collect()
    assert rows == []


def _mock_bestbuy_page(products, total_pages=1):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {"products": products, "totalPages": total_pages}
    return r


def test_collect_parses_products_when_configured():
    products = [{
        "sku": 123456, "name": "Widget Gadget", "manufacturer": "Acme",
        "upc": "012345678905", "salePrice": 19.99, "regularPrice": 39.99,
        "url": "https://bestbuy.com/site/123456.p",
    }]
    with patch.dict(os.environ, {"BESTBUY_API_KEY": "fake-key"}), \
         patch.object(bestbuy, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_bestbuy_page(products)
        rows = bestbuy.collect()
    assert len(rows) == 1
    row = rows[0]
    assert row["retailer"] == "Best Buy"
    assert row["sku"] == "123456"
    assert row["upc"] == "012345678905"
    assert row["price_current"] == 19.99
    assert row["price_original"] == 39.99
    assert row["discount_pct"] == 50.0


def test_collect_stops_pagination_at_total_pages():
    page1 = _mock_bestbuy_page([{"sku": 1, "name": "A", "salePrice": 10, "regularPrice": 20}], total_pages=2)
    page2 = _mock_bestbuy_page([{"sku": 2, "name": "B", "salePrice": 5, "regularPrice": 10}], total_pages=2)
    with patch.dict(os.environ, {"BESTBUY_API_KEY": "fake-key"}), \
         patch.object(bestbuy, "requests") as mock_requests:
        mock_requests.get.side_effect = [page1, page2]
        rows = bestbuy.collect(max_pages=5)
    assert len(rows) == 2
    assert mock_requests.get.call_count == 2


def test_collect_survives_a_failed_category():
    with patch.dict(os.environ, {"BESTBUY_API_KEY": "fake-key"}), \
         patch.object(bestbuy, "requests") as mock_requests:
        mock_requests.get.side_effect = Exception("HTTP 500")
        rows = bestbuy.collect()
    assert rows == []


def test_collect_no_discount_pct_when_prices_missing():
    products = [{"sku": 9, "name": "No Price Item"}]
    with patch.dict(os.environ, {"BESTBUY_API_KEY": "fake-key"}), \
         patch.object(bestbuy, "requests") as mock_requests:
        mock_requests.get.return_value = _mock_bestbuy_page(products)
        rows = bestbuy.collect()
    assert rows[0]["discount_pct"] is None


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
