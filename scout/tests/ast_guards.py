"""
Shared AST-based static-analysis helpers for this project's "no write path to X" / "only calls
allowlisted functions" guard tests (Code Review 2026-07-02, Finding S9).

The ORIGINAL per-file guards only matched a bare `open(...)` call (`ast.Call` with
`node.func` an `ast.Name` whose `.id == "open"`), and only matched module-attribute calls shaped
`db.<name>` (an `ast.Attribute` on a plain `ast.Name`). Both miss real bypass forms:
  - `os.open(...)` / `io.open(...)` / `codecs.open(...)` — attribute-style opens, not a bare
    Name, so the old `node.func.id == "open"` check never even looked at them.
  - `pathlib.Path(x).write_text(...)` / `.write_bytes(...)` / `.open(...)` — method calls where
    the DESTINATION path was set on the `Path(x)` constructor call, not the write call itself
    (there is no `open(...)` call at all here for the old guard to find).
  - `from db import get_lead` then a bare `get_lead(...)` call — bypasses a `db.<name>`
    attribute-access scan entirely since there's no `db.` prefix left in the source.
  - `import db as d` then `d.<name>(...)` — the alias isn't literally "db", so a scan hardcoded
    to `node.value.id == "db"` misses it.

Deliberately NOT flagged: an ordinary `f.write(content)` / `f.writelines(...)` call on an
already-open file HANDLE — its argument is the content being written, not a destination, so
checking it against an allowed path is a category error (this was tried and produced false
positives on totally legitimate `with open(REPORT_PATH) as f: f.write(...)` code — the path was
already validated at the `open()` call).

This module is NOT a test file itself (no `test_` prefix) so pytest won't collect it.
"""
import ast
import inspect

_OPEN_NAMES = {"open"}
_PATH_SHORTCUT_NAMES = {"write_text", "write_bytes"}


def _parse(module_or_source):
    """Accepts either a live module (uses inspect.getsource) or a raw source string directly —
    the latter lets tests exercise these helpers against a fake snippet without needing a real
    file backing it (inspect.getsource fails on dynamically-exec'd modules)."""
    if isinstance(module_or_source, str):
        return ast.parse(module_or_source)
    return ast.parse(inspect.getsource(module_or_source))


def _call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _literal_or_name(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def find_write_like_calls(module):
    """Every call in `module`'s source that ESTABLISHES a file-write destination: bare
    open(...), <alias>.open(...) (os/io/codecs), Path(...).open(...), and
    Path(...).write_text()/.write_bytes() shortcut calls. Resolves the actual destination
    argument correctly for each shape (the shortcut calls' own argument is the DATA being
    written, not the path — the path lives on the Path(...) constructor call instead).
    Returns a list of (call_node, target_literal_or_name_or_None)."""
    tree = _parse(module)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in _OPEN_NAMES:
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
                # Path(...).open(...) — the destination is the Path() constructor's own arg.
                receiver = node.func.value
                target = _literal_or_name(receiver.args[0]) if receiver.args else None
            else:
                # bare open(path, ...) OR os.open(path, ...) / io.open(path, ...) / etc. — the
                # path is this call's own first positional arg either way.
                target = _literal_or_name(node.args[0]) if node.args else None
            hits.append((node, target))
        elif name in _PATH_SHORTCUT_NAMES and isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if isinstance(receiver, ast.Call):
                target = _literal_or_name(receiver.args[0]) if receiver.args else None
            else:
                target = _literal_or_name(receiver)
            hits.append((node, target))
    return hits


def open_call_targets_containing(module, needle):
    """Every write-like call whose resolved destination is a string literal containing
    `needle`. (Name-only targets, e.g. a plain `REPORT_PATH` reference, can't be substring-
    matched — this only flags literal path strings.)"""
    return [t for _node, t in find_write_like_calls(module) if isinstance(t, str) and needle in t]


def assert_only_write_target(module, allowed_name_const):
    """Every write-like call's resolved destination must be a plain Name reference equal to
    `allowed_name_const` (e.g. "REPORT_PATH") — catches any call whose destination isn't that
    one constant, including the os/io/codecs/pathlib forms the original bare-open-only scan
    missed entirely."""
    hits = find_write_like_calls(module)
    assert hits, "expected at least one write-like call (writing the report)"
    for node, target in hits:
        assert target == allowed_name_const, (
            f"write-like call at line {node.lineno} targets {target!r}, not {allowed_name_const!r}")


def find_module_calls(module, source_module_name, attribute_alias_candidates):
    """Every function name from `source_module_name` that `module`'s source actually calls,
    however it was imported: `import <source_module_name> as X -> X.<name>(...)` (covers any
    alias in attribute_alias_candidates, not just the literal module name), OR
    `from <source_module_name> import <name>[, <name> as alias]` -> a bare `<name-or-alias>(...)`
    call. Returns the set of matched (as seen at the call site) names."""
    tree = _parse(module)

    # Names bound via `from source_module_name import ...` (aliases included).
    from_imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == source_module_name:
            for alias in node.names:
                from_imported.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == source_module_name:
                    attribute_alias_candidates = set(attribute_alias_candidates) | {alias.asname or alias.name}

    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in attribute_alias_candidates):
            found.add(node.attr)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in from_imported):
            found.add(node.func.id)
    return found
