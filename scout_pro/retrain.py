"""
retrain.py — gated continuous learning.

Combines schedule-based and trigger-based retraining. Each call trains a versioned
CHALLENGER and promotes it only if it beats the champion (registry handles the
gate). Drift is reported as the trigger signal. Never uncontrolled online learning.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import database as db
import monitoring
import registry

log = logging.getLogger("scout_pro.retrain")


def run(force: bool = False) -> Dict[str, Any]:
    db.init_db()
    drift = monitoring.feature_drift()
    report: Dict[str, Any] = {"drift": drift, "forced": force,
                              "triggered_by_drift": bool(drift.get("drift_detected"))}
    # Gated retrain: challenger is trained every run; promotion is still gated by PR-AUC.
    report["classifier"] = registry.train_and_gate("classifier")
    report["auxiliary"] = registry.train_auxiliary()
    log.info("retrain report: %s", report)
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run(force=True), indent=2, default=str))
