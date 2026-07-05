"""
Tests for Code Review 2026-07-02, Finding S14: scout_pro/config.py's DISCORD_WEBHOOK_URL must
prefer DISCORD_WEBHOOK_SCOUT_PICKS (the already-provisioned channel ../scout/discord_router.py's
"scout_picks" stream posts to) over a bare DISCORD_WEBHOOK_URL that no real .env file sets.

config.py reads env vars at MODULE IMPORT time, so each scenario needs a fresh reload with the
env patched beforehand — a plain re-call wouldn't see a different environment.
"""
import importlib
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402


class TestDiscordWebhookPrecedence(unittest.TestCase):
    def _reload_with_env(self, env: dict):
        with patch.dict(os.environ, env, clear=False):
            for stale in ("DISCORD_WEBHOOK_SCOUT_PICKS", "DISCORD_WEBHOOK_URL"):
                if stale not in env:
                    os.environ.pop(stale, None)
            importlib.reload(config)
            return config.DISCORD_WEBHOOK_URL

    def tearDown(self):
        # Always leave the real module state (real .env, if any) restored for later tests.
        os.environ.pop("DISCORD_WEBHOOK_SCOUT_PICKS", None)
        os.environ.pop("DISCORD_WEBHOOK_URL", None)
        importlib.reload(config)

    def test_prefers_scout_picks_stream_when_both_set(self):
        url = self._reload_with_env({
            "DISCORD_WEBHOOK_SCOUT_PICKS": "https://discord.com/api/webhooks/scout-picks",
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/legacy",
        })
        self.assertEqual(url, "https://discord.com/api/webhooks/scout-picks")

    def test_falls_back_to_bare_url_when_scout_picks_unset(self):
        url = self._reload_with_env({"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/legacy"})
        self.assertEqual(url, "https://discord.com/api/webhooks/legacy")

    def test_none_when_neither_set(self):
        url = self._reload_with_env({})
        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
