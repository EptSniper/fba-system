"""
Tests for tests/ast_guards.py itself (Code Review 2026-07-02, Finding S9) — the shared helper
that broadened this project's "no write path to X" guards beyond a bare open()-only scan.
Exercised against raw source snippets so each bypass form is proven in isolation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ast_guards import (  # noqa: E402
    assert_only_write_target,
    find_module_calls,
    find_write_like_calls,
    open_call_targets_containing,
)


def test_catches_bare_open():
    hits = find_write_like_calls("open('ai-brain.json', 'w')\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_catches_os_open():
    hits = find_write_like_calls("import os\nos.open('ai-brain.json', os.O_WRONLY)\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_catches_io_and_codecs_open():
    hits = find_write_like_calls("import io\nio.open('ai-brain.json', 'w')\n")
    assert hits and hits[0][1] == "ai-brain.json"
    hits = find_write_like_calls("import codecs\ncodecs.open('ai-brain.json', 'w')\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_catches_pathlib_write_text():
    hits = find_write_like_calls("from pathlib import Path\nPath('ai-brain.json').write_text('x')\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_catches_pathlib_write_bytes():
    hits = find_write_like_calls("from pathlib import Path\nPath('ai-brain.json').write_bytes(b'x')\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_catches_pathlib_dot_open():
    hits = find_write_like_calls("from pathlib import Path\nPath('ai-brain.json').open('w')\n")
    assert hits and hits[0][1] == "ai-brain.json"


def test_does_not_flag_ordinary_file_handle_write():
    """Regression: an ordinary f.write(content) on an already-open, already-validated handle
    must NOT be treated as a new write destination — its argument is content, not a path. This
    exact case produced a false positive in tuning_report.py/propose_updates.py during S9."""
    src = (
        "REPORT_PATH = 'x'\n"
        "with open(REPORT_PATH, 'a') as f:\n"
        "    f.write('some content')\n"
    )
    hits = find_write_like_calls(src)
    assert len(hits) == 1  # only the open() call, not the f.write() call
    assert hits[0][1] == "REPORT_PATH"


def test_open_call_targets_containing_only_matches_string_literals():
    src = "PATH = 'ai-brain.json'\nopen(PATH, 'w')\n"
    # A Name reference (not a literal) can't be substring-matched — correctly returns nothing,
    # proving this helper only flags literal path strings, not indirect Name references.
    assert open_call_targets_containing(src, "ai-brain.json") == []


def test_assert_only_write_target_passes_for_matching_name():
    src = "REPORT_PATH = 'x'\nopen(REPORT_PATH, 'a')\n"
    assert_only_write_target(src, "REPORT_PATH")  # must not raise


def test_assert_only_write_target_fails_for_mismatched_target():
    src = "open('ai-brain.json', 'w')\n"
    try:
        assert_only_write_target(src, "REPORT_PATH")
        assert False, "expected an AssertionError"
    except AssertionError as e:
        assert "ai-brain.json" in str(e)


def test_find_module_calls_catches_attribute_style():
    hits = find_module_calls("import db\ndb.get_lead('x')\n", "db", {"db"})
    assert hits == {"get_lead"}


def test_find_module_calls_catches_from_import_bypass():
    hits = find_module_calls("from db import get_lead\nget_lead('x')\n", "db", {"db"})
    assert hits == {"get_lead"}


def test_find_module_calls_catches_aliased_import_bypass():
    hits = find_module_calls("import db as d\nd.get_lead('x')\n", "db", {"db"})
    assert hits == {"get_lead"}
