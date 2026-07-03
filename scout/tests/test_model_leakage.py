"""
Regression tests for Code Review 2026-07-02, Finding B4: the legacy SQLite-based retrain loop
(model.py + pipeline.maybe_retrain()) must never let the scout's own rule_score leak into a
feature it then trains on — the same self-confirmation the project bans everywhere else — and
must stay disabled by default until unified with the leakage-safe labels.py path.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import model as model_mod  # noqa: E402
import pipeline  # noqa: E402


def test_features_list_excludes_rule_score():
    assert "rule_score" not in model_mod.FEATURES


def test_features_from_never_includes_rule_score_value():
    """Even though features_from() still accepts a rule_score argument (call-site
    compatibility), the returned vector must not contain it anywhere."""
    vector_low = model_mod.features_from({"price": 10.0}, rule_score=1.0, margin=0.2)
    vector_high = model_mod.features_from({"price": 10.0}, rule_score=999999.0, margin=0.2)
    assert vector_low == vector_high, "rule_score must have zero effect on the feature vector"
    assert len(vector_low) == len(model_mod.FEATURES)


def test_maybe_retrain_disabled_by_default():
    with patch.object(config, "LEGACY_RETRAIN_ENABLED", False):
        result = pipeline.maybe_retrain()
    assert result["trained"] is False
    assert "disabled by default" in result["reason"]


def test_maybe_retrain_never_touches_storage_or_model_when_disabled():
    with patch.object(config, "LEGACY_RETRAIN_ENABLED", False), \
         patch.object(pipeline.storage, "training_rows") as mock_rows, \
         patch.object(pipeline.model_mod, "train") as mock_train:
        pipeline.maybe_retrain()
    mock_rows.assert_not_called()
    mock_train.assert_not_called()


def test_maybe_retrain_proceeds_when_explicitly_enabled():
    rows = [{"price": 10.0, "label": 1}] * 25
    with patch.object(config, "LEGACY_RETRAIN_ENABLED", True), \
         patch.object(pipeline.storage, "training_rows", return_value=rows), \
         patch.object(pipeline.model_mod, "train", return_value={"trained": True}) as mock_train:
        result = pipeline.maybe_retrain()
    mock_train.assert_called_once()
    assert result == {"trained": True}


def test_config_legacy_retrain_env_var_gating():
    with patch.dict(os.environ, {"SCOUT_LEGACY_RETRAIN": "1"}):
        assert os.getenv("SCOUT_LEGACY_RETRAIN", "0") in ("1", "true", "True")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SCOUT_LEGACY_RETRAIN", None)
        assert os.getenv("SCOUT_LEGACY_RETRAIN", "0") not in ("1", "true", "True")


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
