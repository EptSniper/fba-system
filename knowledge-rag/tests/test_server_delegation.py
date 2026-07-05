"""
Tests for ask.py's warm-server delegation (THIS_WEEK.md Prompt W1, item 2): "if the local
server responds on /health, delegate to it (fast path); else current cold run. Zero behavior
change for callers." This file exercises exactly that fallback contract — real network calls
against a port nothing is listening on (the "server absent" case every caller hits until
someone starts server.py), plus mocked-present-server cases so both branches are covered
without needing a real running process.
"""
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("knowledge_ask", ROOT / "ask.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

# A port astronomically unlikely to have anything real bound to it in a test environment.
_DEAD_PORT = "18787"


class ServerAbsentFallbackTests(unittest.TestCase):
    """The common case until someone starts server.py: nothing is listening. Every function
    here must degrade silently (False / None) — never raise, never hang past its own timeout."""

    def setUp(self):
        self._old_port = os.environ.get("KNOWLEDGE_SERVER_PORT")
        os.environ["KNOWLEDGE_SERVER_PORT"] = _DEAD_PORT

    def tearDown(self):
        if self._old_port is None:
            os.environ.pop("KNOWLEDGE_SERVER_PORT", None)
        else:
            os.environ["KNOWLEDGE_SERVER_PORT"] = self._old_port

    def test_server_available_is_false_when_nothing_listens(self):
        self.assertFalse(MODULE.server_available(timeout=0.5))

    def test_ask_via_server_returns_none_when_nothing_listens(self):
        result = MODULE.ask_via_server("any question", limit=3, timeout=0.5)
        self.assertIsNone(result)

    def test_base_url_uses_the_configured_port(self):
        self.assertEqual(MODULE._server_base_url(), f"http://127.0.0.1:{_DEAD_PORT}")

    def test_base_url_defaults_to_8787_when_unset(self):
        os.environ.pop("KNOWLEDGE_SERVER_PORT", None)
        self.assertEqual(MODULE._server_base_url(), "http://127.0.0.1:8787")


class ServerPresentMockedTests(unittest.TestCase):
    """Mocked "server IS up" cases — covers the happy path's actual code (URL/payload/timeout
    handling) without needing a real bound socket in this test."""

    def test_server_available_true_when_health_reports_model_loaded(self):
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"model_loaded": True}
        with patch.object(MODULE.requests, "get", return_value=fake_response) as mock_get:
            self.assertTrue(MODULE.server_available())
        called_url = mock_get.call_args[0][0]
        self.assertTrue(called_url.startswith("http://127.0.0.1:"))
        self.assertTrue(called_url.endswith("/health"))

    def test_server_available_false_when_model_not_yet_loaded(self):
        """A server that's up but still mid-startup (model_loaded=False) must NOT be treated
        as available — delegating to it would just be a slower round-trip to an unready
        process, worse than the cold path."""
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"model_loaded": False}
        with patch.object(MODULE.requests, "get", return_value=fake_response):
            self.assertFalse(MODULE.server_available())

    def test_ask_via_server_returns_the_response_json_on_200(self):
        expected = {"question": "q", "count": 1, "answer": {}, "matches": [{"id": "x"}]}
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = expected
        with patch.object(MODULE.requests, "post", return_value=fake_response) as mock_post:
            result = MODULE.ask_via_server("q", limit=5, category="Fundamentals")
        self.assertEqual(result, expected)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"question": "q", "limit": 5, "category": "Fundamentals"})

    def test_ask_via_server_returns_none_on_non_200(self):
        fake_response = Mock(status_code=500)
        with patch.object(MODULE.requests, "post", return_value=fake_response):
            self.assertIsNone(MODULE.ask_via_server("q"))


if __name__ == "__main__":
    unittest.main()
