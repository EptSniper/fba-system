"""
Tests for server.py — the warm knowledge server (THIS_WEEK.md Prompt W1).

Uses FastAPI's TestClient (no real socket, no real model load, no real Supabase call) — every
test that would otherwise hit ask.py's real embed()/retrieve()/rerank()/synthesize() monkeypatches
those functions on the `ask` MODULE object directly (server.py calls `ask.embed(...)` etc., not
a copied reference, so patching `ask.embed` is visible to server.py too). Fixture-based and
fast, per THIS_WEEK.md's "tests: /embed and /ask against fixtures" ask.
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # so `import ask` inside server.py resolves to THIS instance
    assert spec.loader
    spec.loader.exec_module(module)
    return module


ask = _load("ask", "ask.py")
server = _load("server", "server.py")


def _fake_row(text, citation, similarity=0.7, category="Fundamentals"):
    return {"id": citation, "chunk_text": text, "citation": citation,
            "category": category, "similarity": similarity}


class EmbedEndpointTests(unittest.TestCase):
    def test_embed_returns_one_vector_per_text(self):
        with patch.object(ask, "embed", side_effect=lambda t: [0.1, 0.2, 0.3]):
            client = TestClient(server.app)
            res = client.post("/embed", json={"texts": ["hello", "world"]})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["vectors"]), 2)
        self.assertEqual(body["vectors"][0], [0.1, 0.2, 0.3])

    def test_embed_empty_texts_returns_empty_vectors(self):
        with patch.object(ask, "embed", side_effect=lambda t: [0.1]):
            client = TestClient(server.app)
            res = client.post("/embed", json={"texts": []})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["vectors"], [])


class AskEndpointTests(unittest.TestCase):
    def test_ask_returns_same_shape_as_cli_json(self):
        """The server's /ask response must match ask.py's own --json output contract exactly
        (question/count/answer/matches) — server.py is documented as reusing ask.py's own
        functions, never forking the logic, so this pins that contract."""
        rows = [_fake_row("Ungating requires an invoice.", "learning-hub/playbooks/ungating-playbook.md")]
        with patch.object(ask, "retrieve", return_value=rows) as mock_retrieve, \
             patch.object(ask, "rerank", wraps=ask.rerank) as mock_rerank:
            client = TestClient(server.app)
            res = client.post("/ask", json={"question": "how do I get ungated?", "limit": 3})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body.keys()), {"question", "count", "answer", "matches"})
        self.assertEqual(body["question"], "how do I get ungated?")
        self.assertEqual(body["count"], len(body["matches"]))
        mock_retrieve.assert_called_once()
        mock_rerank.assert_called_once()

    def test_ask_clamps_limit_to_1_20_range(self):
        with patch.object(ask, "retrieve", return_value=[]) as mock_retrieve:
            client = TestClient(server.app)
            client.post("/ask", json={"question": "q", "limit": 999})
        _, kwargs = mock_retrieve.call_args
        self.assertLessEqual(kwargs["k"], 20)

    def test_ask_no_matches_returns_empty_list_not_error(self):
        with patch.object(ask, "retrieve", return_value=[]):
            client = TestClient(server.app)
            res = client.post("/ask", json={"question": "an unanswerable question"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["matches"], [])


class HealthEndpointTests(unittest.TestCase):
    def test_health_reports_model_loaded_and_cached_corpus_counts(self):
        with patch.object(ask, "health", return_value={"ready": True, "fastembed": True, "supabase": True}):
            client = TestClient(server.app)
            res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("model_loaded", body)
        self.assertIn("uptime_seconds", body)
        self.assertIn("corpus", body)
        # Cached (not live) counts, per server._corpus_counts()'s own honesty rule — verified
        # live against this project 2026-07-04: the read-only key ask.py uses has no direct
        # SELECT grant on documents/document_chunks, so a live count would always misreport 0.
        self.assertNotEqual(body["corpus"].get("source"), "")

    def test_corpus_counts_never_fabricates_zero_on_read_failure(self):
        """If ai-brain.json can't be read, corpus counts must be None (unknown), never a
        fabricated 0 that would look like a genuinely empty knowledge base."""
        with patch.object(server, "_BRAIN_PATH", "/nonexistent/path/ai-brain.json"):
            counts = server._corpus_counts()
        self.assertIsNone(counts["documents"])
        self.assertIsNone(counts["chunks"])


class LoopbackBindingTests(unittest.TestCase):
    def test_host_constant_is_loopback_only(self):
        """The literal, most direct assertion of the security requirement: HOST must be
        127.0.0.1, never 0.0.0.0 or empty (which uvicorn treats as all-interfaces)."""
        self.assertEqual(server.HOST, "127.0.0.1")

    def test_run_server_passes_loopback_host_to_uvicorn(self):
        """Verifies the ACTUAL argument passed to uvicorn.run(), not just that the constant
        exists unused somewhere — monkeypatches uvicorn.run to capture its kwargs without
        really binding a socket."""
        captured = {}

        def fake_run(app, **kwargs):
            captured.update(kwargs)

        with patch("uvicorn.run", side_effect=fake_run):
            server.run_server()
        self.assertEqual(captured.get("host"), "127.0.0.1")
        self.assertNotEqual(captured.get("host"), "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
