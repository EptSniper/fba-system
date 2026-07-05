"""
Regression test for a real, reproduced crash (Code Review 2026-07-02, nit): run_scout.py's
--dry-run path used to `print(summary)` a raw dict containing scoring.py's ✓/✗/→/★ reason
strings, which raises UnicodeEncodeError on a plain Windows console (cp1252 codepage) the
moment a dry-run cycle scores any real candidate. Reproduced directly on this environment:
    >>> print({"reason": "BSR 25,000 ✓"})   # cp1252 stdout -> UnicodeEncodeError

_print_summary() now serializes via json.dumps (ensure_ascii=True by default), matching the
already-safe pattern run_daily.py's own console print uses.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_scout  # noqa: E402

UNICODE_LADEN_SUMMARY = {
    "found": 12, "scored": 12, "above_threshold": 1, "new_picks": 1, "posted": 0,
    "picks": [{
        "asin": "B0TEST", "score": 91.2,
        "reason": "BSR 25,000 ✓ · ~200/mo ✓ · 6 offers ✓ · ROI 42% ✓ · $9/u ✓ · BuyBox 3P✓  →  91.2/100"
                  " (est.; confirm in SellerAmp)",
        "analyst_narrative": None,
    }],
}


def test_print_summary_does_not_raise_on_cp1252_stdout():
    """The exact reproduction: redirect stdout through a real cp1252-encoding TextIOWrapper
    (not utf-8) and confirm the unicode-laden summary prints without UnicodeEncodeError."""
    buf = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    real_stdout = sys.stdout
    try:
        sys.stdout = cp1252_stdout
        run_scout._print_summary(UNICODE_LADEN_SUMMARY)  # must not raise
        cp1252_stdout.flush()
    finally:
        sys.stdout = real_stdout
    printed = buf.getvalue().decode("cp1252")
    assert "BSR 25,000" in printed
    # The unicode checkmark must be ESCAPED (✓), not written raw — that's what makes it
    # cp1252-safe in the first place.
    assert "\\u2713" in printed
    parsed = json.loads(printed)
    assert parsed["picks"][0]["asin"] == "B0TEST"
    assert "✓" in parsed["picks"][0]["reason"]  # round-trips back to the real character


def test_bare_print_of_the_same_dict_would_have_crashed():
    """Sanity check that this reproduction is real, not a false confidence exercise: a bare
    print() of the same data through the same cp1252 stream DOES raise."""
    buf = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    real_stdout = sys.stdout
    try:
        sys.stdout = cp1252_stdout
        try:
            print(UNICODE_LADEN_SUMMARY)
            cp1252_stdout.flush()
            assert False, "expected UnicodeEncodeError from a raw print() on cp1252"
        except UnicodeEncodeError:
            pass
    finally:
        sys.stdout = real_stdout
