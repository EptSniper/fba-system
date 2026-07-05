"""
Tests for scripts/pre-commit.py's pure logic (THIS_WEEK.md Prompt W2) — placeholder filtering
and secret-pattern classification, mocked against fixture content rather than real git state
(the actual block/pass-through behavior was also verified live against this repo's real git
index on 2026-07-04 — see the journal entry for that manual verification).
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCOUT_DIR = ROOT.parent / "scout"
sys.path.insert(0, str(SCOUT_DIR))

SPEC = importlib.util.spec_from_file_location("pre_commit_hook", ROOT / "pre-commit.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class PlaceholderFilterTests(unittest.TestCase):
    def test_bracketed_placeholder_is_excluded(self):
        with patch.object(MODULE.redact, "_sensitive_env_values", return_value=["<FILL_ME>"]):
            self.assertEqual(MODULE._real_secret_values(), [])

    def test_short_value_is_excluded(self):
        with patch.object(MODULE.redact, "_sensitive_env_values", return_value=["abc12"]):
            self.assertEqual(MODULE._real_secret_values(), [])

    def test_real_looking_secret_is_included(self):
        real = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        with patch.object(MODULE.redact, "_sensitive_env_values", return_value=["<FILL_ME>", real]):
            self.assertEqual(MODULE._real_secret_values(), [real])


class ScanStagedFilesTests(unittest.TestCase):
    def test_flags_a_matching_env_secret_value(self):
        with patch.object(MODULE, "_staged_files", return_value=["some/file.py"]), \
             patch.object(MODULE, "_staged_content", return_value="the_key = 'sk-real-secret-value-123456'"), \
             patch.object(MODULE, "_real_secret_values", return_value=["sk-real-secret-value-123456"]):
            findings = MODULE.scan_staged_files()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][0], "some/file.py")
        self.assertNotIn("sk-real-secret-value-123456", findings[0][1])  # never leak the value

    def test_flags_a_discord_webhook_url(self):
        content = "webhook = 'https://discord.com/api/webhooks/1234567890123/AbCdEf-123_XyZ'"
        with patch.object(MODULE, "_staged_files", return_value=["f.py"]), \
             patch.object(MODULE, "_staged_content", return_value=content), \
             patch.object(MODULE, "_real_secret_values", return_value=[]):
            findings = MODULE.scan_staged_files()
        self.assertEqual(len(findings), 1)
        self.assertIn("webhook", findings[0][1])

    def test_flags_a_jwt_shaped_string(self):
        content = ("SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                  "eyJpc3MiOiJzdXBhYmFzZSJ9.AbCdEf1234567890signature'")
        with patch.object(MODULE, "_staged_files", return_value=["f.py"]), \
             patch.object(MODULE, "_staged_content", return_value=content), \
             patch.object(MODULE, "_real_secret_values", return_value=[]):
            findings = MODULE.scan_staged_files()
        self.assertEqual(len(findings), 1)
        self.assertIn("JWT", findings[0][1])

    def test_clean_file_is_not_flagged(self):
        with patch.object(MODULE, "_staged_files", return_value=["f.py"]), \
             patch.object(MODULE, "_staged_content", return_value="def add(a, b):\n    return a + b\n"), \
             patch.object(MODULE, "_real_secret_values", return_value=["sk-some-real-secret"]):
            findings = MODULE.scan_staged_files()
        self.assertEqual(findings, [])

    def test_placeholder_content_never_flagged_false_positive(self):
        """Regression guard for the exact bug caught live 2026-07-04: a template placeholder
        like KEEPA_KEY=<FILL_ME> must never block a commit."""
        content = "KEEPA_KEY=<FILL_ME>\nANTHROPIC_API_KEY=<FILL_ME>\n"
        with patch.object(MODULE, "_staged_files", return_value=["API_KEYS.env.example"]), \
             patch.object(MODULE.redact, "_sensitive_env_values", return_value=["<FILL_ME>"]), \
             patch.object(MODULE, "_staged_content", return_value=content):
            findings = MODULE.scan_staged_files()
        self.assertEqual(findings, [])

    def test_binary_or_unreadable_file_is_skipped_not_crashed(self):
        with patch.object(MODULE, "_staged_files", return_value=["image.png"]), \
             patch.object(MODULE, "_staged_content", return_value=None), \
             patch.object(MODULE, "_real_secret_values", return_value=["sk-some-real-secret"]):
            findings = MODULE.scan_staged_files()
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
