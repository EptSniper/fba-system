"""
test_harvest.py — the idle-token harvester (DATA_ENGINE_PLAN.md V0 #4).

The harvester is DISABLED on the Pro trickle, so these tests exercise it with a fake Keepa client
and the brain flag forced on/off, covering: the honest disabled no-op, budget math
(harvestTokenShare * observed daily generation), the refusal when the refill rate is unreadable,
the priority-queue order + dedupe, resumability (a same-day state file carries spend forward and
skips finished tiers), and that harvesting archives raw responses via the keepa_client boundary.
"""
import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import harvest  # noqa: E402
import datalake  # noqa: E402
import keepa_client  # noqa: E402


class FakeKeepa:
    """Minimal stand-in for a keepa.Keepa client: a monotonic tokens_consumed counter and a
    readable refill rate, plus product_finder/query that cost tokens."""
    def __init__(self, refill_per_min=20, finder_asins=None):
        self.tokens_consumed = 0
        self.tokens_per_minute = refill_per_min
        self._finder_asins = finder_asins if finder_asins is not None else ["A1", "A2", "A3"]

    def product_finder(self, params, domain=None, wait=False):
        self.tokens_consumed += 1  # PF costs ~1 token
        return list(self._finder_asins)

    def query(self, asins, **kwargs):
        self.tokens_consumed += len(asins)  # ~1 token/ASIN
        return [{"asin": a, "title": f"t{a}", "stats": {}} for a in asins]

    def seller_query(self, seller_id, domain=None):
        return {seller_id: {"asinList": []}}


def _force_brain(monkey_share=0.4, enabled=True):
    """Patch harvest._brain_learning to a controlled learning block."""
    return mock.patch.object(harvest, "_brain_learning",
                             return_value={"harvesterEnabled": enabled, "harvestTokenShare": monkey_share})


class HarvestConfigTest(unittest.TestCase):
    def test_disabled_by_default_reads_brain(self):
        with _force_brain(enabled=False):
            self.assertFalse(harvest.enabled())
            r = harvest.run_harvest(api=FakeKeepa())
            self.assertEqual(r["status"], "disabled")
            self.assertIn("blocked-on-upgrade", r["reason"])
            self.assertEqual(r["spent"], 0)

    def test_token_share_clamped(self):
        with mock.patch.object(harvest, "_brain_learning", return_value={"harvestTokenShare": 5}):
            self.assertEqual(harvest.harvest_token_share(), 1.0)
        with mock.patch.object(harvest, "_brain_learning", return_value={"harvestTokenShare": -1}):
            self.assertEqual(harvest.harvest_token_share(), 0.0)
        with mock.patch.object(harvest, "_brain_learning", return_value={}):
            self.assertEqual(harvest.harvest_token_share(), harvest.DEFAULT_HARVEST_TOKEN_SHARE)

    def test_observed_daily_generation(self):
        api = FakeKeepa(refill_per_min=20)
        self.assertEqual(harvest.observed_daily_generation(api), 20 * 1440)
        # unknown rate -> None (refuse to guess)
        self.assertIsNone(harvest.observed_daily_generation(object()))


class HarvestRunTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("DATALAKE_ENABLED", "DATA_LAKE_DIR")}
        self.tmp = tempfile.mkdtemp(prefix="fba-harvest-test-")
        os.environ["DATALAKE_ENABLED"] = "1"
        os.environ["DATA_LAKE_DIR"] = self.tmp
        datalake.reset_stats()
        # The `keepa` package isn't installed on this machine (it's optional); the fake api makes
        # _require_keepa() the only blocker, so flip the installed-flag like the other keepa tests.
        self._keepa_patch = mock.patch.object(keepa_client, "_KEEPA", True)
        self._keepa_patch.start()

    def tearDown(self):
        self._keepa_patch.stop()
        datalake.reset_stats()
        shutil.rmtree(self.tmp, ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_budget_from_share_and_generation(self):
        api = FakeKeepa(refill_per_min=20)
        with _force_brain(monkey_share=0.4, enabled=True):
            # only an active-leads tier (explicit ASINs), no finder expansion, tiny budget
            r = harvest.run_harvest(api=api, active_lead_asins=lambda: ["L1", "L2"])
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["budget"], int(0.4 * 20 * 1440))
        self.assertGreaterEqual(r["enriched"], 2)  # the two lead ASINs got enriched

    def test_refuses_without_refill_rate(self):
        api = FakeKeepa()
        del api.tokens_per_minute  # unreadable rate
        with _force_brain(enabled=True):
            r = harvest.run_harvest(api=api, active_lead_asins=lambda: ["L1"])
        self.assertEqual(r["status"], "refused")

    def test_priority_queue_order_and_dedupe(self):
        api = FakeKeepa()
        with mock.patch.object(harvest.discovery_hints, "hinted_brand_seeds", return_value=["Nike", "Lego"]):
            q = harvest.build_priority_queue(api, limit=100, active_lead_asins=lambda: ["L1", "L1", "L2"])
        kinds = [item["kind"] for item in q]
        # tier 1 leads first, then hint brands; strictly increasing tier numbers
        self.assertEqual(kinds[0], "leads")
        self.assertIn("hint_brands", kinds)
        tiers = [item["tier"] for item in q]
        self.assertEqual(tiers, sorted(tiers))
        leads = [item for item in q if item["kind"] == "leads"][0]
        self.assertEqual(leads["asins"], ["L1", "L2"])  # deduped, order preserved

    def test_resumable_state_carries_spend_and_skips_done_tiers(self):
        api = FakeKeepa(refill_per_min=20)
        with _force_brain(enabled=True):
            harvest.run_harvest(api=api, active_lead_asins=lambda: ["L1", "L2"])
        # a state file exists for today with spend + the leads tier marked done
        with open(harvest._state_path(), encoding="utf-8") as f:
            st = json.load(f)
        self.assertGreater(st["spent"], 0)
        self.assertIn("leads", st["done_tiers"])

        # a second same-day run must NOT re-enrich the finished leads tier
        api2 = FakeKeepa(refill_per_min=20)
        with _force_brain(enabled=True):
            r2 = harvest.run_harvest(api=api2, active_lead_asins=lambda: ["L1", "L2"])
        self.assertNotIn("leads", r2["tiers_run"])

    def test_harvest_archives_raw_responses(self):
        api = FakeKeepa(refill_per_min=20)
        with _force_brain(enabled=True):
            harvest.run_harvest(api=api, active_lead_asins=lambda: ["L1", "L2"])
        # the enrich boundary archived one keepa/product row per ASIN -> parquet on disk
        rows = 0
        keepa_dir = os.path.join(self.tmp, "keepa")
        if os.path.isdir(keepa_dir):
            import pyarrow.parquet as pq
            for dp, _d, files in os.walk(keepa_dir):
                for f in files:
                    if f.endswith(".parquet"):
                        rows += pq.read_metadata(os.path.join(dp, f)).num_rows
        self.assertGreaterEqual(rows, 2)


if __name__ == "__main__":
    unittest.main()
