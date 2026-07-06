"""
test_signals_ebay.py — scout/signals/ebay.py (Session 55, key-gated optional eBay sold-comps).

All network calls mocked. The core property under test: EVERY function degrades to an honest
skip when EBAY_APP_ID isn't configured — never an error, never a fabricated comp.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals import ebay  # noqa: E402


class EnabledFlagTest(unittest.TestCase):
    def test_disabled_without_app_id(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EBAY_APP_ID", None)
            self.assertFalse(ebay.enabled())

    def test_enabled_with_app_id(self):
        with mock.patch.dict(os.environ, {"EBAY_APP_ID": "x"}):
            self.assertTrue(ebay.enabled())


class SoldCompsSkipTest(unittest.TestCase):
    def test_skips_honestly_without_app_id(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EBAY_APP_ID", None)
            result = ebay.sold_comps("012345678905")
        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["sold_count"])
        self.assertIn("HUMAN_TODO", result["reason"])

    def test_skips_honestly_without_cert_id(self):
        with mock.patch.dict(os.environ, {"EBAY_APP_ID": "x"}, clear=False):
            os.environ.pop("EBAY_CERT_ID", None)
            result = ebay.sold_comps("012345678905")
        self.assertEqual(result["status"], "skipped")

    def test_never_raises_on_token_request_failure(self):
        with mock.patch.dict(os.environ, {"EBAY_APP_ID": "x", "EBAY_CERT_ID": "y"}), \
             mock.patch.object(ebay, "_get_access_token", return_value=None):
            result = ebay.sold_comps("012345678905")
        self.assertEqual(result["status"], "error")


class SoldCompsLiveShapeTest(unittest.TestCase):
    def test_computes_sold_count_and_median_price(self):
        fake_resp = mock.Mock(status_code=200)
        fake_resp.json.return_value = {"itemSummaries": [
            {"price": {"value": "10.00"}}, {"price": {"value": "12.00"}}, {"price": {"value": "20.00"}},
        ]}
        fake_resp.raise_for_status = lambda: None
        with mock.patch.dict(os.environ, {"EBAY_APP_ID": "x", "EBAY_CERT_ID": "y"}), \
             mock.patch("requests.get", return_value=fake_resp):
            result = ebay.sold_comps("012345678905", token="fake-token")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sold_count"], 3)
        self.assertEqual(result["median_price"], 12.0)

    def test_never_raises_on_request_error(self):
        with mock.patch.dict(os.environ, {"EBAY_APP_ID": "x", "EBAY_CERT_ID": "y"}), \
             mock.patch("requests.get", side_effect=RuntimeError("network down")):
            result = ebay.sold_comps("012345678905", token="fake-token")
        self.assertEqual(result["status"], "error")


class EbayFeaturesTest(unittest.TestCase):
    def test_ratio_computed_when_ok(self):
        with mock.patch.object(ebay, "sold_comps", return_value={
            "status": "ok", "sold_count": 5, "median_price": 15.0, "listings": []}):
            feats = ebay.ebay_features("012345678905", amazon_price=20.0)
        self.assertEqual(feats["ebay_sold_count_30d"], 5)
        self.assertEqual(feats["median_sold_price_vs_amazon_ratio"], 0.75)
        self.assertFalse(feats["ebay_stale"])

    def test_nullable_and_stale_when_skipped(self):
        with mock.patch.object(ebay, "sold_comps", return_value={
            "status": "skipped", "sold_count": None, "median_price": None, "listings": []}):
            feats = ebay.ebay_features("012345678905", amazon_price=20.0)
        self.assertIsNone(feats["ebay_sold_count_30d"])
        self.assertIsNone(feats["median_sold_price_vs_amazon_ratio"])
        self.assertTrue(feats["ebay_stale"])

    def test_ratio_none_when_amazon_price_missing(self):
        with mock.patch.object(ebay, "sold_comps", return_value={
            "status": "ok", "sold_count": 5, "median_price": 15.0, "listings": []}):
            feats = ebay.ebay_features("012345678905", amazon_price=None)
        self.assertIsNone(feats["median_sold_price_vs_amazon_ratio"])


if __name__ == "__main__":
    unittest.main()
