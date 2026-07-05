"""
scout/tests/conftest.py — test-suite guards.

The data lake (scout/datalake.py, DATA_ENGINE_PLAN.md V0) archives every external response to
disk in production. Under test we DON'T want the wired-in boundary archiving (keepa_client,
deals/sources, analyst) to touch the real C:\\fba-data-lake or write a manifest — so archiving
is disabled by default here and pointed at a throwaway temp dir as belt-and-suspenders.

datalake's OWN unit tests (test_datalake.py) re-enable it explicitly against their own temp dir,
so this default doesn't blunt their coverage.
"""
import os
import tempfile

# Set live so datalake.enabled() (which reads the env on every call) sees it before any test
# imports or exercises the archiving boundaries.
os.environ.setdefault("DATALAKE_ENABLED", "0")
os.environ.setdefault("DATA_LAKE_DIR", os.path.join(tempfile.gettempdir(), "fba-lake-test-noop"))
