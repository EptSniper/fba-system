"""
Regression tests for Code Review 2026-07-02, Finding B7: upload_to_supabase.py must default
to the LOCAL embedding provider and refuse Gemini/OpenAI without an explicit --force-provider
flag, since the live corpus was embedded locally and mixing providers silently corrupts
retrieval with no error at write time.

Run via subprocess (`python -c "import upload_to_supabase"`) rather than a normal import: the
module runs its provider-gating checks (sys.exit on a bad config) at MODULE level, guarded from
the actual upload work by `if __name__ == "__main__":` — importing it is safe (no real network
calls), but only in a fresh process, since the checks run once at import time.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAG_DIR = os.path.dirname(HERE)

# Inherit the FULL parent environment (Windows Python needs several system vars just to start
# — replacing the whole environment with a minimal dict crashes the interpreter itself before
# it ever reaches the code under test) and only override the specific vars this test cares
# about. Explicitly clear any real EMBED_PROVIDER/*_API_KEY this dev machine might have so a
# real .env value can never leak into what's supposed to be a controlled test.
BASE_ENV = dict(os.environ)
for _var in ("EMBED_PROVIDER", "GEMINI_API_KEY", "OPENAI_API_KEY"):
    BASE_ENV.pop(_var, None)
BASE_ENV["SUPABASE_URL"] = "https://fake.supabase.co"
BASE_ENV["SUPABASE_SERVICE_KEY"] = "fake-key"


def _run(extra_env=None, args=None):
    env = dict(BASE_ENV)
    env.update(extra_env or {})
    # Extra args must come AFTER "-c <code>" to land in sys.argv[1:] for the executed code —
    # placed before, they'd be parsed as interpreter flags instead.
    result = subprocess.run(
        [sys.executable, "-c", "import upload_to_supabase"] + (args or []),
        cwd=RAG_DIR, capture_output=True, text=True, timeout=30, env=env,
    )
    return result


def test_default_provider_is_local_not_gemini():
    # No EMBED_PROVIDER set -> defaults to local -> never hits the gemini/openai refusal path.
    # (May still exit non-zero if fastembed isn't installed in this environment — that's a
    # separate, honest, expected failure mode, not the thing under test here.)
    result = _run()
    assert "Refusing to run" not in result.stdout + result.stderr


def test_gemini_without_force_flag_is_refused():
    result = _run(extra_env={"EMBED_PROVIDER": "gemini"})
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Refusing to run" in combined
    assert "--force-provider" in combined


def test_openai_without_force_flag_is_refused():
    result = _run(extra_env={"EMBED_PROVIDER": "openai"})
    assert result.returncode != 0
    assert "Refusing to run" in result.stdout + result.stderr


def test_gemini_with_force_flag_passes_the_provider_gate():
    """With --force-provider, the refusal check is skipped — the NEXT gate (a real
    GEMINI_API_KEY) is what stops it, proving the provider gate itself was passed."""
    result = _run(extra_env={"EMBED_PROVIDER": "gemini"}, args=["--force-provider"])
    combined = result.stdout + result.stderr
    assert "Refusing to run" not in combined
    assert "GEMINI_API_KEY" in combined  # the next honest gate, not the provider refusal


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
