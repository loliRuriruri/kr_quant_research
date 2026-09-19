import json
from pathlib import Path

import pytest

from kr_quant.research import jev_calibration as cal


def _seed(tmp_path: Path) -> Path:
    path = tmp_path / "jev_thresholds.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "buckets": [
            {
                "provider": "typesafe_direct",
                "requested_model": "jev-latest",
                "evaluator_version": "season-jev-shadow-v1",
                "thresholds": {h: None for h in [
                    "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
                    "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
                ]},
            },
            {
                "provider": "openrouter",
                "requested_model": "typesafe/jev-1.13",
                "evaluator_version": "season-jev-shadow-v1",
                "thresholds": {h: None for h in [
                    "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
                    "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
                ]},
            },
        ],
    }), encoding="utf-8")
    return path


def test_boolean_heads_match_spec():
    assert cal.BOOLEAN_HEADS == (
        "materialNow", "needsCurrentYearCheck", "needsNews", "needsDart",
        "historicalConflict", "invalidationCheckNeeded", "needsDeepAI",
    )
    assert "reviewClass" not in cal.BOOLEAN_HEADS


def test_null_threshold_is_shadow_only(tmp_path):
    cfg = cal.load_thresholds(_seed(tmp_path))
    got = cal.lookup_threshold(
        cfg, provider="typesafe_direct", requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1", head="needsDart",
    )
    assert got["status"] == cal.STATUS_SHADOW_ONLY
    assert got["reason"] == cal.STATUS_UNCALIBRATED
    assert got["threshold"] is None


def test_threshold_status_from_missing_path(tmp_path):
    got = cal.threshold_status_from_path(
        tmp_path / "nope.json",
        provider="typesafe_direct", requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1", head="needsNews",
    )
    assert got["status"] == cal.STATUS_SHADOW_ONLY
    assert got["reason"] == cal.STATUS_UNCALIBRATED
    assert got["threshold"] is None


def test_missing_bucket_head_and_mismatches(tmp_path):
    cfg = cal.load_thresholds(_seed(tmp_path))
    cases = [
        dict(provider="openrouter", requested_model="jev-latest",
             evaluator_version="season-jev-shadow-v1", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="typesafe/jev-1.13",
             evaluator_version="season-jev-shadow-v1", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="jev-latest",
             evaluator_version="other-eval", head="needsDart"),
        dict(provider="typesafe_direct", requested_model="jev-latest",
             evaluator_version="season-jev-shadow-v1", head="reviewClass"),
    ]
    for kwargs in cases:
        got = cal.lookup_threshold(cfg, **kwargs)
        assert got["status"] == cal.STATUS_SHADOW_ONLY
        assert got["reason"] == cal.STATUS_UNCALIBRATED
        assert got["threshold"] is None


def test_numeric_threshold_still_shadow_only_no_production_routing(tmp_path):
    path = _seed(tmp_path)
    cfg = cal.load_thresholds(path)
    cfg["buckets"][0]["thresholds"]["needsDart"] = 0.73
    got = cal.lookup_threshold(
        cfg, provider="typesafe_direct", requested_model="jev-latest",
        evaluator_version="season-jev-shadow-v1", head="needsDart",
    )
    assert got["status"] == cal.STATUS_SHADOW_ONLY
    assert got["reason"] is None
    assert got["threshold"] == 0.73


@pytest.mark.parametrize("bad", [-0.1, 1.1, True, float("nan"), float("inf"), "0.5"])
def test_invalid_numeric_threshold_fail_closed(tmp_path, bad):
    path = _seed(tmp_path)
    cfg = cal.load_thresholds(path)
    cfg["buckets"][0]["thresholds"]["needsDart"] = bad
    with pytest.raises(cal.CalibrationError):
        cal.lookup_threshold(
            cfg, provider="typesafe_direct", requested_model="jev-latest",
            evaluator_version="season-jev-shadow-v1", head="needsDart",
        )
