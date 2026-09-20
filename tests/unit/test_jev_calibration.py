import hashlib
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


# --- Task 2 ---

def test_sample_id_formula():
    sid = cal.make_sample_id(
        "typesafe_direct",
        "jev-latest",
        "season-jev-shadow-v1",
        "abc",
    )
    raw = b"typesafe_direct\njev-latest\nseason-jev-shadow-v1\nabc"
    assert sid == hashlib.sha256(raw).hexdigest()


def test_ticker_grouped_same_ticker_different_generation_and_state():
    a = cal.assign_split(ticker="005930", state_hash="h1")
    b = cal.assign_split(ticker="005930", state_hash="h2")

    assert a == b
    assert a in {
        cal.SPLIT_CALIBRATION,
        cal.SPLIT_HOLDOUT,
    }


def test_missing_ticker_uses_state_hash_deterministic():
    a = cal.assign_split(ticker="", state_hash="deadbeef")
    b = cal.assign_split(ticker=None, state_hash="deadbeef")

    assert a == b
    assert cal.assign_split(
        ticker=None,
        state_hash="deadbeef",
    ) == a


def test_split_ticker_conflict_fail_closed():
    rows = [
        {
            "sample_id": "s1",
            "ticker": "005930",
            "state_hash": "h1",
            "split": cal.SPLIT_CALIBRATION,
            "annotation_version": 1,
        },
        {
            "sample_id": "s2",
            "ticker": "005930",
            "state_hash": "h2",
            "split": cal.SPLIT_HOLDOUT,
            "annotation_version": 1,
        },
    ]

    with pytest.raises(
        cal.CalibrationError,
        match="SPLIT_TICKER_CONFLICT",
    ):
        cal.ensure_split_consistency(rows)


def test_split_state_hash_conflict_fail_closed():
    rows = [
        {
            "sample_id": "s1",
            "ticker": "",
            "state_hash": "same-hash",
            "split": cal.SPLIT_CALIBRATION,
            "annotation_version": 1,
        },
        {
            "sample_id": "s2",
            "ticker": "",
            "state_hash": "same-hash",
            "split": cal.SPLIT_HOLDOUT,
            "annotation_version": 1,
        },
    ]

    with pytest.raises(
        cal.CalibrationError,
        match="SPLIT_STATE_HASH_CONFLICT",
    ):
        cal.ensure_split_consistency(rows)


def test_split_sample_conflict_fail_closed():
    rows = [
        {
            "sample_id": "same-sample",
            "ticker": "",
            "state_hash": "h1",
            "split": cal.SPLIT_CALIBRATION,
            "annotation_version": 1,
        },
        {
            "sample_id": "same-sample",
            "ticker": "",
            "state_hash": "h1",
            "split": cal.SPLIT_HOLDOUT,
            "annotation_version": 2,
        },
    ]

    with pytest.raises(
        cal.CalibrationError,
        match="SPLIT_SAMPLE_CONFLICT",
    ):
        cal.ensure_split_consistency(rows)


def test_revision_conflict_same_version_different_content():
    rows = [
        {
            "sample_id": "s",
            "annotation_version": 2,
            "labeled_at": "2026-01-01T00:00:00Z",
            "human_labels": {"needsDart": True},
        },
        {
            "sample_id": "s",
            "annotation_version": 2,
            "labeled_at": "2026-01-02T00:00:00Z",
            "human_labels": {"needsDart": False},
        },
    ]

    with pytest.raises(
        cal.RevisionConflict,
        match="REVISION_CONFLICT",
    ):
        cal.select_active_rows(rows)


def test_revision_duplicate_same_content_dedupes():
    row = {
        "sample_id": "s",
        "annotation_version": 1,
        "labeled_at": "2026-01-01T00:00:00Z",
        "human_labels": {"needsDart": True},
    }

    active = cal.select_active_rows([row, dict(row)])

    assert len(active) == 1


def test_revision_higher_integer_version_wins():
    rows = [
        {
            "sample_id": "s",
            "annotation_version": 1,
            "human_labels": {"needsDart": False},
        },
        {
            "sample_id": "s",
            "annotation_version": 2,
            "human_labels": {"needsDart": True},
        },
    ]

    active = cal.select_active_rows(rows)

    assert len(active) == 1
    assert active[0]["annotation_version"] == 2
    assert active[0]["human_labels"]["needsDart"] is True


def test_dataset_hash_row_order_invariant():
    rows = [
        {
            "sample_id": "b",
            "annotation_version": 1,
            "x": 1,
        },
        {
            "sample_id": "a",
            "annotation_version": 1,
            "x": 2,
        },
    ]

    left = cal.dataset_hash_v1(rows)
    right = cal.dataset_hash_v1(list(reversed(rows)))

    assert left == right
    assert len(left) == 64


@pytest.mark.parametrize(
    "bad",
    ["v1", "1", 0, -1, 1.5, True, None],
)
def test_annotation_version_invalid_fail_closed(bad):
    with pytest.raises(cal.CalibrationError):
        cal.select_active_rows([
            {
                "sample_id": "s",
                "annotation_version": bad,
                "human_labels": {},
            }
        ])


@pytest.mark.parametrize(
    "bad",
    [
        {"quantReference": {}},
        {"quant_reference": {}},
        {"pre_entry_rank": 1},
        {"nested": {"grade": "A"}},
        {"score_breakdown": {}},
        {"seasonality_score": 1.0},
    ],
)
def test_forbidden_quant_fields_rejected(bad):
    with pytest.raises(ValueError):
        cal.assert_calibration_state_clean(bad)


# --- Task 3 ---

def _samples():
    def row(sid, split, lab, p):
        return {
            "sample_id": sid,
            "split": split,
            "human_labels": {
                "needsNews": lab,
            },
            "jev_answers": {
                "needsNews": {
                    "probability": p,
                }
            },
        }

    return [
        row("c1", cal.SPLIT_CALIBRATION, True, 0.80),
        row("c2", cal.SPLIT_CALIBRATION, True, 0.40),
        row("c3", cal.SPLIT_CALIBRATION, False, 0.70),
        row("c4", cal.SPLIT_CALIBRATION, "unknown", 0.90),
        row("h1", cal.SPLIT_HOLDOUT, True, 0.10),
    ]


def test_confusion_and_rates_with_fpr_one():
    m = cal.evaluate_head_at_threshold(
        _samples(),
        head="needsNews",
        threshold=0.5,
    )

    assert (
        m["TP"],
        m["FP"],
        m["TN"],
        m["FN"],
    ) == (1, 1, 0, 1)

    assert m["precision"] == 0.5
    assert m["recall"] == 0.5
    assert m["FPR"] == 1.0
    assert m["FNR"] == 0.5
    assert m["unknown_count"] == 1


def test_fpr_none_when_no_human_negatives():
    rows = [
        {
            "sample_id": "a",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {
                "needsNews": True,
            },
            "jev_answers": {
                "needsNews": {
                    "probability": 0.9,
                }
            },
        },
        {
            "sample_id": "b",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {
                "needsNews": True,
            },
            "jev_answers": {
                "needsNews": {
                    "probability": 0.1,
                }
            },
        },
    ]

    m = cal.evaluate_head_at_threshold(
        rows,
        head="needsNews",
        threshold=0.5,
    )

    assert m["FP"] == 0
    assert m["TN"] == 0
    assert m["FPR"] is None


def test_invalid_probability_excluded_and_counted():
    rows = _samples() + [{
        "sample_id": "c5",
        "split": cal.SPLIT_CALIBRATION,
        "human_labels": {
            "needsNews": True,
        },
        "jev_answers": {
            "needsNews": {
                "probability": 1.5,
            }
        },
    }]

    m = cal.evaluate_head_at_threshold(
        rows,
        head="needsNews",
        threshold=0.5,
    )

    assert m["invalid_probability_count"] == 1


def test_sweep_uses_observed_boundaries_and_calibration_only():
    table = cal.sweep_head_thresholds(
        _samples(),
        head="needsNews",
    )

    thresholds = [
        row["threshold"]
        for row in table
    ]

    assert thresholds == sorted({
        0.0,
        1.0,
        0.80,
        0.40,
        0.70,
    })

    assert 0.90 not in thresholds
    assert 0.10 not in thresholds

    assert all(
        "holdout_metrics" not in row
        for row in table
    )

    assert cal.predict_positive(
        0.5,
        0.5,
    ) is True

    assert cal.predict_positive(
        0.49,
        0.5,
    ) is False


def test_fn_sensitive_heads_listed_no_auto_winner_api():
    assert cal.FN_SENSITIVE_HEADS == frozenset({
        "needsDart",
        "historicalConflict",
        "invalidationCheckNeeded",
    })

    assert not hasattr(
        cal,
        "auto_select_production_threshold",
    )


def test_rates_from_counts_none_on_zero_denominator():
    assert cal.rates_from_counts({"TP": 0, "FP": 0, "TN": 1, "FN": 1})["precision"] is None
    assert cal.rates_from_counts({"TP": 0, "FP": 1, "TN": 1, "FN": 0})["recall"] is None
    assert cal.rates_from_counts({"TP": 1, "FP": 0, "TN": 0, "FN": 0})["FPR"] is None
    assert cal.rates_from_counts({"TP": 0, "FP": 1, "TN": 1, "FN": 0})["FNR"] is None


def test_invalid_probability_boundaries_excluded_from_sweep():
    rows = [
        {
            "sample_id": "ok",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": True},
            "jev_answers": {"needsNews": {"probability": 0.25}},
        },
        {
            "sample_id": "nan",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": False},
            "jev_answers": {"needsNews": {"probability": float("nan")}},
        },
        {
            "sample_id": "inf",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": False},
            "jev_answers": {"needsNews": {"probability": float("inf")}},
        },
        {
            "sample_id": "neg",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": False},
            "jev_answers": {"needsNews": {"probability": -0.1}},
        },
        {
            "sample_id": "hi",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": False},
            "jev_answers": {"needsNews": {"probability": 1.1}},
        },
        {
            "sample_id": "boolp",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsNews": False},
            "jev_answers": {"needsNews": {"probability": True}},
        },
    ]
    table = cal.sweep_head_thresholds(rows, head="needsNews")
    thresholds = [r["threshold"] for r in table]
    assert thresholds == sorted({0.0, 1.0, 0.25})
