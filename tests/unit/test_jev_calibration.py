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


# --- Task 4 ---

def _manifest(**over):
    base = {
        "dataset_id": "d1",
        "dataset_hash": "a" * 64,
        "bucket": {
            "provider": "typesafe_direct",
            "requested_model": "jev-latest",
            "evaluator_version": "season-jev-shadow-v1",
        },
        "head": "needsDart",
        "selected_threshold": 0.73,
        "selection_basis": "calibration_only",
        "calibration_metrics_hash": "b" * 64,
        "holdout_revealed": False,
    }
    base.update(over)
    return base


def test_calibration_report_omits_holdout_metrics():
    samples = [
        {
            "sample_id": "c1",
            "split": cal.SPLIT_CALIBRATION,
            "ticker": "005930",
            "human_labels": {"needsDart": True},
            "jev_answers": {"needsDart": {"probability": 0.8}},
            "annotation_version": 1,
        },
        {
            "sample_id": "h1",
            "split": cal.SPLIT_HOLDOUT,
            "ticker": "000660",
            "human_labels": {"needsDart": False},
            "jev_answers": {"needsDart": {"probability": 0.2}},
            "annotation_version": 1,
        },
    ]
    report = cal.build_calibration_report(
        dataset_id="d1",
        dataset_hash="a" * 64,
        bucket={
            "provider": "typesafe_direct",
            "requested_model": "jev-latest",
            "evaluator_version": "season-jev-shadow-v1",
        },
        samples=samples,
    )
    assert report["state"] == cal.STATE_CALIBRATION_OPEN
    assert "holdout_metrics" not in report
    assert "needsDart" in report["heads"]
    assert report["dataset_hash_method_version"] == cal.HASH_METHOD_VERSION
    assert report["split_method_version"] == cal.SPLIT_METHOD_VERSION
    assert report["sweep_method_version"] == cal.SWEEP_METHOD_VERSION
    assert report["prediction_rule"] == "probability >= threshold"


def test_holdout_before_lock_unavailable():
    with pytest.raises(
        cal.CalibrationError,
        match="CALIBRATION_OPEN|SELECTION_LOCKED|holdout",
    ):
        cal.evaluate_holdout_locked(
            samples=[],
            selection={
                "state": cal.STATE_CALIBRATION_OPEN,
                "head": "needsDart",
                "selected_threshold": 0.7,
                "holdout_revealed": False,
            },
        )


def test_lock_selection_rejects_bad_invariants():
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(selection_basis="holdout"))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(head="reviewClass"))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(selected_threshold=1.5))
    with pytest.raises(cal.CalibrationError):
        cal.lock_selection(_manifest(holdout_revealed=True))


def test_lock_selection_hash_excludes_own_field():
    locked = cal.lock_selection(_manifest())
    assert locked["state"] == cal.STATE_SELECTION_LOCKED
    assert locked["selection_basis"] == "calibration_only"
    assert locked["holdout_revealed"] is False
    recomputed = cal.selection_manifest_hash(locked)
    assert locked["selection_manifest_hash"] == recomputed
    mutated = dict(locked)
    mutated["selection_manifest_hash"] = "0" * 64
    assert cal.selection_manifest_hash(mutated) == recomputed


def test_holdout_eval_derives_threshold_only_from_selection():
    samples = [
        {
            "sample_id": "h1",
            "split": cal.SPLIT_HOLDOUT,
            "human_labels": {"needsDart": True},
            "jev_answers": {"needsDart": {"probability": 0.9}},
        },
        {
            "sample_id": "h2",
            "split": cal.SPLIT_HOLDOUT,
            "human_labels": {"needsDart": False},
            "jev_answers": {"needsDart": {"probability": 0.1}},
        },
    ]
    selection = cal.lock_selection(_manifest(selected_threshold=0.73))
    report = cal.evaluate_holdout_locked(samples=samples, selection=selection)
    assert report["selected_threshold"] == 0.73
    assert report["head"] == "needsDart"
    assert "alternative_threshold" not in report
    assert "best_threshold" not in report
    assert "winner" not in report
    assert "recommended_threshold" not in report
    assert "production_threshold" not in report
    assert report["state"] == cal.STATE_HOLDOUT_REVEALED
    reviewed = cal.attach_review_status(report, cal.REVIEW_REJECT)
    assert reviewed["review_status"] == cal.REVIEW_REJECT


def test_threshold_change_after_reveal_marks_non_pristine():
    selection = {
        "holdout_revealed": True,
        "selected_threshold": 0.5,
        "pristine_holdout": True,
    }
    out = cal.mark_holdout_non_pristine(selection)
    assert out["pristine_holdout"] is False


def _label_rows(n_true, n_false, n_unknown=0, split=None):
    split = split or cal.SPLIT_CALIBRATION
    rows = []
    for i in range(n_true):
        rows.append({
            "sample_id": f"t{i}",
            "split": split,
            "human_labels": {"needsDart": True},
            "jev_answers": {"needsDart": {"probability": 0.8}},
        })
    for i in range(n_false):
        rows.append({
            "sample_id": f"f{i}",
            "split": split,
            "human_labels": {"needsDart": False},
            "jev_answers": {"needsDart": {"probability": 0.2}},
        })
    for i in range(n_unknown):
        rows.append({
            "sample_id": f"u{i}",
            "split": split,
            "human_labels": {"needsDart": "unknown"},
            "jev_answers": {"needsDart": {"probability": 0.5}},
        })
    return rows


def test_support_status_gates_50_100_and_unknown_excluded():
    s49 = cal.support_status(
        _label_rows(25, 24, 10),
        head="needsDart",
        split=cal.SPLIT_CALIBRATION,
    )
    assert s49["valid_count"] == 49
    assert s49["unknown_count"] == 10
    assert s49["analysis_eligible"] is False
    assert s49["production_review_eligible"] is False

    s50 = cal.support_status(
        _label_rows(25, 25, 5),
        head="needsDart",
        split=cal.SPLIT_CALIBRATION,
    )
    assert s50["valid_count"] == 50
    assert s50["analysis_eligible"] is True
    assert s50["production_review_eligible"] is False

    s100 = cal.support_status(
        _label_rows(50, 50, 3),
        head="needsDart",
        split=cal.SPLIT_CALIBRATION,
    )
    assert s100["valid_count"] == 100
    assert s100["production_review_eligible"] is True


def test_support_status_insufficient_class_support():
    rows = _label_rows(5, 45)
    st = cal.support_status(rows, head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert st["valid_count"] == 50
    assert st["insufficient_class_support"] is True


def test_attach_review_status_allows_only_known_values():
    report = {
        "selected_threshold": 0.73,
        "state": cal.STATE_HOLDOUT_REVEALED,
    }
    ok = cal.attach_review_status(report, cal.REVIEW_ACCEPT)
    assert ok["review_status"] == cal.REVIEW_ACCEPT
    for bad in ("AUTO_ACCEPT", "WINNER", "best", ""):
        with pytest.raises(cal.CalibrationError):
            cal.attach_review_status(report, bad)


def test_holdout_eval_ignores_calibration_rows():
    samples = [
        {
            "sample_id": "c_bad",
            "split": cal.SPLIT_CALIBRATION,
            "human_labels": {"needsDart": True},
            "jev_answers": {"needsDart": {"probability": 0.01}},
        },
        {
            "sample_id": "h1",
            "split": cal.SPLIT_HOLDOUT,
            "human_labels": {"needsDart": True},
            "jev_answers": {"needsDart": {"probability": 0.9}},
        },
        {
            "sample_id": "h2",
            "split": cal.SPLIT_HOLDOUT,
            "human_labels": {"needsDart": False},
            "jev_answers": {"needsDart": {"probability": 0.1}},
        },
    ]
    selection = cal.lock_selection(_manifest(selected_threshold=0.5))
    report = cal.evaluate_holdout_locked(samples=samples, selection=selection)
    assert (report["TP"], report["FP"], report["TN"], report["FN"]) == (1, 0, 1, 0)


def test_support_status_split_isolation():
    rows = (
        _label_rows(25, 25, split=cal.SPLIT_CALIBRATION)
        + _label_rows(10, 10, split=cal.SPLIT_HOLDOUT)
    )
    st = cal.support_status(rows, head="needsDart", split=cal.SPLIT_CALIBRATION)
    assert st["valid_count"] == 50


def test_selection_manifest_hash_key_order_invariant():
    a = {"z": 1, "a": {"y": 2, "x": 3}, "m": True}
    b = {"m": True, "a": {"x": 3, "y": 2}, "z": 1}
    assert cal.selection_manifest_hash(a) == cal.selection_manifest_hash(b)
