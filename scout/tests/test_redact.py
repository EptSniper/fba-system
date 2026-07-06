"""
Tests for Code Review 2026-07-02, Finding B5: scout/redact.py — masking secrets out of any
string before it leaves the process (logs, Supabase runs.error_summary, Discord posts).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redact  # noqa: E402


def test_redact_none_and_empty_are_safe():
    assert redact.redact(None) is None
    assert redact.redact("") == ""


def test_redact_masks_env_var_value_wherever_it_appears():
    with patch.dict(os.environ, {"SOME_FAKE_API_KEY": "sekrit-value-123456"}):
        text = "request failed with body containing sekrit-value-123456 in it"
        out = redact.redact(text)
    assert "sekrit-value-123456" not in out
    assert "***REDACTED***" in out


def test_redact_masks_query_param_key_patterns():
    text = "GET https://api.bestbuy.com/v1/products?apiKey=ABCDEF123456&format=json failed"
    out = redact.redact(text)
    assert "ABCDEF123456" not in out
    assert "apiKey=" in out  # the param NAME stays, only the value is masked


def test_redact_masks_generic_token_and_secret_params():
    assert "supersecrettoken" not in redact.redact("url?token=supersecrettoken&x=1")
    assert "shh12345" not in redact.redact("url?secret=shh12345")


def test_redact_ignores_code_shapes_not_secrets():
    """Regression guard (Session 52): the query-param pattern used to flag ordinary source code
    as a leaked secret — JSX `key={...}` props, `sorted(key=lambda ...)`/`key=len` sort kwargs,
    and `api_key=os.environ[...]` env lookups. None of these carry a literal secret value."""
    for text in (
        "return items.map(i => <Row key={i.id} />)",
        "rows.sort(key=lambda r: r.score)",
        "sorted(values, key=len)",
        'anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])',
    ):
        assert redact.redact(text) == text, f"should be unchanged: {text!r}"


def test_redact_ignores_same_name_kwarg_passthrough():
    """Regression guard (Session 55): scout/signals/ebay.py's `sold_comps(upc, token=token)` —
    a plain Python kwarg pass-through, not a secret. A real secret VALUE never happens to equal
    its own parameter name's literal text, so excluding this shape can't hide an actual leak."""
    for text in (
        "comps = sold_comps(upc, token=token)",
        "return fetch(url, key=key)",
        "call(secret=secret)",
        "build(api_key=api_key)",
    ):
        assert redact.redact(text) == text, f"should be unchanged: {text!r}"


def test_redact_masks_discord_webhook_urls():
    text = "post failed: https://discord.com/api/webhooks/1234567890123/AbCdEf-123_XyZ end"
    out = redact.redact(text)
    assert "AbCdEf-123_XyZ" not in out
    assert "discord.com/api/webhooks" not in out


def test_redact_ignores_short_env_values_to_avoid_over_masking():
    """A var named *_KEY with a trivially short/common value (e.g. a feature flag "1") must
    not turn every '1' in unrelated text into a mask — only real secret-length values."""
    with patch.dict(os.environ, {"SOME_KEY": "1"}):
        out = redact.redact("there are 1 candidates found")
    assert out == "there are 1 candidates found"


def test_redact_handles_multiple_distinct_secrets_in_one_string():
    with patch.dict(os.environ, {"FIRST_API_KEY": "firstsecretvalue", "SECOND_TOKEN": "secondsecretvalue"}):
        text = "firstsecretvalue and secondsecretvalue both appeared"
        out = redact.redact(text)
    assert "firstsecretvalue" not in out
    assert "secondsecretvalue" not in out


def test_redact_masks_jwt_shaped_strings():
    """THIS_WEEK.md Prompt W2 — a JWT (Supabase anon/service_role keys are JWTs) must be
    masked even when it ISN'T the current value of a *KEY*/*TOKEN*/*WEBHOOK* env var (e.g. an
    old rotated key committed accidentally) — scripts/pre-commit.py's secrets scan relies on
    this pattern matching independent of process environment."""
    fake_jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZha2UifQ."
                "AbCdEf1234567890_-signature")
    out = redact.redact(f"found a leaked key: {fake_jwt} in the diff")
    assert fake_jwt not in out
    assert "***REDACTED***" in out


def test_redact_does_not_mangle_non_jwt_dotted_text():
    text = "see learning-hub/data/ai-brain.json for the criteria.minRoi value"
    assert redact.redact(text) == text


def test_redact_leaves_ordinary_text_unchanged():
    text = "No KEEPA_KEY set. A paid Keepa key is required (see .env)."
    # This message mentions the ENV VAR NAME "KEEPA_KEY", not its value — must stay readable.
    out = redact.redact(text)
    assert out == text


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
