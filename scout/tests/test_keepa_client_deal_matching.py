"""
Tests for keepa_client.search_by_term() and keepa_client.upc_lookup() — the two Keepa lookup
primitives added for the Deal Finder matcher (scout/deals/matcher.py, Prompt D2; Sourcing &
Review-Queue Plan Phase 2.2, 2026-07-13). Zero live network calls.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keepa_client  # noqa: E402


class FakeApi:
    """Minimal keepa.Keepa stand-in with a controllable token bank (mirrors
    test_keepa_client_guard.py's FakeApi)."""
    def __init__(self, tokens_left=60):
        self.tokens_left = tokens_left

    def update_status(self):
        pass


def _mock_search_response(products):
    r = mock.MagicMock()
    r.json.return_value = {"products": products, "tokensConsumed": len(products) * 10}
    return r


class SearchByTermTest(unittest.TestCase):
    def setUp(self):
        self._keepa_patch = mock.patch.object(keepa_client, "_KEEPA", True)
        self._keepa_patch.start()
        self._key_patch = mock.patch.object(keepa_client.config, "KEEPA_KEY", "fake-key")
        self._key_patch.start()
        keepa_client.reset_guard_telemetry()

    def tearDown(self):
        self._keepa_patch.stop()
        self._key_patch.stop()

    def test_empty_term_returns_empty_list_without_any_call(self):
        with mock.patch("requests.get") as m_get:
            result = keepa_client.search_by_term("   ", api=FakeApi())
        self.assertEqual(result, [])
        m_get.assert_not_called()

    def test_returns_asins_from_the_search_endpoint(self):
        api = FakeApi(tokens_left=60)
        with mock.patch("requests.get", return_value=_mock_search_response(
                [{"asin": "B001", "title": "t1", "brand": "Acme"},
                 {"asin": "B002", "title": "t2", "brand": "Acme"}])):
            result = keepa_client.search_by_term("acme widget", limit=10, api=api)
        self.assertEqual(result, ["B001", "B002"])

    def test_no_keepa_key_returns_empty_list(self):
        with mock.patch.object(keepa_client.config, "KEEPA_KEY", ""), \
             mock.patch("requests.get") as m_get:
            result = keepa_client.search_by_term("acme widget", api=FakeApi())
        self.assertEqual(result, [])
        m_get.assert_not_called()

    def test_bank_cant_cover_flat_cost_skips_entirely(self):
        api = FakeApi(tokens_left=2)  # SEARCH_TOKENS_PER_TERM is 10
        with mock.patch("requests.get") as m_get:
            result = keepa_client.search_by_term("acme widget", api=api)
        self.assertEqual(result, [])
        m_get.assert_not_called()
        self.assertEqual(keepa_client.guard_telemetry()["skips"], 1)


class UpcLookupTest(unittest.TestCase):
    def setUp(self):
        self._keepa_patch = mock.patch.object(keepa_client, "_KEEPA", True)
        self._keepa_patch.start()
        self._key_patch = mock.patch.object(keepa_client.config, "KEEPA_KEY", "fake-key")
        self._key_patch.start()
        keepa_client.reset_guard_telemetry()

    def tearDown(self):
        self._keepa_patch.stop()
        self._key_patch.stop()

    def test_empty_codes_returns_empty_dict(self):
        with mock.patch("requests.get") as m_get:
            result = keepa_client.upc_lookup([], api=FakeApi())
        self.assertEqual(result, {})
        m_get.assert_not_called()

    def test_single_code_maps_unambiguously_even_without_echoed_upc_list(self):
        """The one-code-in-the-request case is unambiguous even if Keepa's response doesn't
        echo the identifier back on the product."""
        with mock.patch("requests.get", return_value=_mock_search_response(
                [{"asin": "B001", "title": "t1", "brand": "Acme"}])):
            result = keepa_client.upc_lookup(["012345678905"], api=FakeApi())
        self.assertEqual(result, {"012345678905": ["B001"]})

    def test_multi_code_batch_with_echoed_upc_list_maps_correctly(self):
        products = [
            {"asin": "B001", "title": "t1", "upcList": ["111"]},
            {"asin": "B002", "title": "t2", "upcList": ["222"]},
        ]
        with mock.patch("requests.get", return_value=_mock_search_response(products)):
            result = keepa_client.upc_lookup(["111", "222"], api=FakeApi())
        self.assertEqual(result, {"111": ["B001"], "222": ["B002"]})

    def test_multi_code_batch_without_echoed_upc_list_stays_unattributed(self):
        """A multi-code batch with no echoed identifier must NOT guess a 1:1 order
        correspondence — an honest miss beats a silent mismatch feeding a wrong ASIN downstream."""
        products = [{"asin": "B001", "title": "t1"}, {"asin": "B002", "title": "t2"}]
        with mock.patch("requests.get", return_value=_mock_search_response(products)):
            result = keepa_client.upc_lookup(["111", "222"], api=FakeApi())
        self.assertEqual(result, {})

    def test_no_keepa_key_returns_empty_dict(self):
        with mock.patch.object(keepa_client.config, "KEEPA_KEY", ""), \
             mock.patch("requests.get") as m_get:
            result = keepa_client.upc_lookup(["111"], api=FakeApi())
        self.assertEqual(result, {})
        m_get.assert_not_called()

    def test_bank_cant_cover_batch_skips_entirely(self):
        api = FakeApi(tokens_left=0)
        with mock.patch("requests.get") as m_get:
            result = keepa_client.upc_lookup(["111", "222"], api=api)
        self.assertEqual(result, {})
        m_get.assert_not_called()

    def test_failed_request_degrades_to_empty_dict(self):
        with mock.patch("requests.get", side_effect=RuntimeError("network down")):
            result = keepa_client.upc_lookup(["111"], api=FakeApi())
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
