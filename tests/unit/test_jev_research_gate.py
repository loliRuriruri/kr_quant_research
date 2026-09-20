# -*- coding: utf-8 -*-
"""J3 Task 1 — threshold identity foundation (primary 33/34/36/37/38/39)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from kr_quant.research.jev_research_gate import (
    BUCKET_MATCHED,
    BUCKET_MISSING,
    GATE_SCHEMA_VERSION,
    ResearchGateError,
    _load_threshold_cfg,
    threshold_config_hash,
)


HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _bucket(provider: str, model: str, evaluator: str, thresholds: dict) -> dict:
    return {
        "provider": provider,
        "requested_model": model,
        "evaluator_version": evaluator,
        "thresholds": thresholds,
    }


def _cfg(*buckets: dict) -> dict:
    return {"schema_version": 1, "buckets": list(buckets)}


DIRECT = ("typesafe_direct", "jev-latest", "season-jev-shadow-v1")
OPENROUTER = ("openrouter", "typesafe/jev-1.13", "season-jev-shadow-v1")


# ---------------------------------------------------------------------------
# Design 33 — missing exact bucket → deterministic hash
# ---------------------------------------------------------------------------


def test_design_33_missing_bucket_deterministic_hash():
    cfg = _cfg(
        _bucket(*OPENROUTER, {
            "materialNow": None,
            "needsNews": None,
            "needsDart": None,
            "needsDeepAI": None,
            "needsCurrentYearCheck": None,
            "historicalConflict": None,
            "invalidationCheckNeeded": None,
        })
    )
    h1 = threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h2 = threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert HEX64.match(h1)
    assert h1 == h2


# ---------------------------------------------------------------------------
# Design 34 — MISSING identity changes alter hash
# ---------------------------------------------------------------------------


def test_design_34_missing_hash_differs_by_identity():
    cfg = _cfg()  # valid empty buckets list — all MISSING
    base = dict(provider="p", requested_model="m", evaluator_version="e")
    h_base = threshold_config_hash(cfg, **base)
    assert HEX64.match(h_base)
    assert threshold_config_hash(cfg, provider="p2", requested_model="m", evaluator_version="e") != h_base
    assert threshold_config_hash(cfg, provider="p", requested_model="m2", evaluator_version="e") != h_base
    assert threshold_config_hash(cfg, provider="p", requested_model="m", evaluator_version="e2") != h_base


# ---------------------------------------------------------------------------
# Design 36 — all-null MATCHED != MISSING
# ---------------------------------------------------------------------------


def test_design_36_all_null_matched_differs_from_missing():
    all_null = {
        "materialNow": None,
        "needsCurrentYearCheck": None,
        "needsNews": None,
        "needsDart": None,
        "historicalConflict": None,
        "invalidationCheckNeeded": None,
        "needsDeepAI": None,
    }
    matched_cfg = _cfg(_bucket(*DIRECT, all_null))
    missing_cfg = _cfg(_bucket(*OPENROUTER, all_null))
    h_matched = threshold_config_hash(matched_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_missing = threshold_config_hash(missing_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert HEX64.match(h_matched)
    assert HEX64.match(h_missing)
    assert h_matched != h_missing


# ---------------------------------------------------------------------------
# Design 37 — absent head != explicit null head (MATCHED)
# ---------------------------------------------------------------------------


def test_design_37_absent_head_differs_from_explicit_null():
    absent = {"needsNews": 0.5, "needsDart": None}  # materialNow ABSENT
    explicit_null = {"needsNews": 0.5, "needsDart": None, "materialNow": None}
    cfg_absent = _cfg(_bucket(*DIRECT, absent))
    cfg_null = _cfg(_bucket(*DIRECT, explicit_null))
    h_absent = threshold_config_hash(cfg_absent, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_null = threshold_config_hash(cfg_null, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert HEX64.match(h_absent)
    assert HEX64.match(h_null)
    assert h_absent != h_null


# ---------------------------------------------------------------------------
# Design 38 — unrelated provider bucket edit does not change hash
# ---------------------------------------------------------------------------


def test_design_38_unrelated_provider_edit_unchanged():
    base_buckets = [
        _bucket(*DIRECT, {"needsNews": None, "needsDeepAI": 0.7}),
        _bucket(*OPENROUTER, {"needsNews": None}),
    ]
    edited = [
        _bucket(*DIRECT, {"needsNews": None, "needsDeepAI": 0.7}),
        _bucket(*OPENROUTER, {"needsNews": 0.9}),  # unrelated edit
    ]
    h1 = threshold_config_hash(_cfg(*base_buckets), provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h2 = threshold_config_hash(_cfg(*edited), provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert h1 == h2


# ---------------------------------------------------------------------------
# Design 39 — fail closed; no fabricated MISSING hash
# ---------------------------------------------------------------------------


def test_design_39a_malformed_in_memory_cfg_fails():
    with pytest.raises((ResearchGateError, TypeError, ValueError)):
        threshold_config_hash("not-a-mapping", provider="p", requested_model="m", evaluator_version="e")  # type: ignore[arg-type]


def test_design_39a_buckets_not_list_fails():
    with pytest.raises(ResearchGateError):
        threshold_config_hash({"schema_version": 1, "buckets": {}}, provider="p", requested_model="m", evaluator_version="e")


def test_design_39a_duplicate_exact_bucket_fails():
    cfg = _cfg(
        _bucket(*DIRECT, {"needsNews": None}),
        _bucket(*DIRECT, {"needsNews": 0.1}),
    )
    with pytest.raises(ResearchGateError):
        threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])


def test_design_39a_invalid_numeric_threshold_fails():
    cfg = _cfg(_bucket(*DIRECT, {"needsNews": 1.5}))
    with pytest.raises(ResearchGateError):
        threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])


def test_design_39a_bool_threshold_fails():
    cfg = _cfg(_bucket(*DIRECT, {"needsNews": True}))
    with pytest.raises(ResearchGateError):
        threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])


def test_design_39bcd_path_failures(tmp_path: Path):
    missing = tmp_path / "nope.json"
    with pytest.raises(ResearchGateError) as ei:
        _load_threshold_cfg(missing)
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(ResearchGateError) as ei2:
        _load_threshold_cfg(bad_json)
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei2.value)

    structural = tmp_path / "structural.json"
    structural.write_text(json.dumps({"schema_version": 1, "buckets": "nope"}), encoding="utf-8")
    with pytest.raises(ResearchGateError) as ei3:
        _load_threshold_cfg(structural)
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei3.value)


def test_design_39_no_fabricated_missing_via_empty_dict():
    # empty dict is malformed (no buckets list) — must fail, not hash as MISSING
    with pytest.raises(ResearchGateError):
        threshold_config_hash({}, provider="p", requested_model="m", evaluator_version="e")


# ---------------------------------------------------------------------------
# Constants smoke + secondary hash isolation (not primary 5–8 claim)
# ---------------------------------------------------------------------------


def test_constants_and_schema_version():
    assert GATE_SCHEMA_VERSION == 1
    assert BUCKET_MATCHED == "MATCHED"
    assert BUCKET_MISSING == "MISSING"


def test_secondary_exact_bucket_isolation_hash_facing():
    """SECONDARY only — primary ownership of 5/6/7/8 remains Task 2."""
    cfg = _cfg(
        _bucket(*DIRECT, {"needsNews": 0.5}),
        _bucket(*OPENROUTER, {"needsNews": 0.5}),
    )
    h_d = threshold_config_hash(cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_o = threshold_config_hash(cfg, provider=OPENROUTER[0], requested_model=OPENROUTER[1], evaluator_version=OPENROUTER[2])
    assert h_d != h_o


def test_secondary_missing_to_matched_changes_hash():
    """SECONDARY only — primary ownership of 35 remains Task 4."""
    missing_cfg = _cfg()
    matched_cfg = _cfg(_bucket(*DIRECT, {"needsNews": None}))
    h_m = threshold_config_hash(missing_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_k = threshold_config_hash(matched_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert h_m != h_k




# ---------------------------------------------------------------------------
# Design 39 fail-closed structural regressions (Task-1 correction)
# ---------------------------------------------------------------------------


def test_design_39_wrong_schema_version_fails():
    with pytest.raises(ResearchGateError) as ei:
        threshold_config_hash(
            {"schema_version": 999, "buckets": []},
            provider="p",
            requested_model="m",
            evaluator_version="e",
        )
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)


def test_design_39_missing_schema_version_fails():
    with pytest.raises(ResearchGateError) as ei:
        threshold_config_hash(
            {"buckets": []},
            provider="p",
            requested_model="m",
            evaluator_version="e",
        )
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)


def test_design_39_non_mapping_bucket_element_fails():
    with pytest.raises(ResearchGateError) as ei:
        threshold_config_hash(
            {"schema_version": 1, "buckets": ["bad-bucket"]},
            provider=DIRECT[0],
            requested_model=DIRECT[1],
            evaluator_version=DIRECT[2],
        )
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)


def test_design_39_incomplete_bucket_mapping_fails():
    with pytest.raises(ResearchGateError) as ei:
        threshold_config_hash(
            {
                "schema_version": 1,
                "buckets": [{"provider": "typesafe_direct"}],
            },
            provider=DIRECT[0],
            requested_model=DIRECT[1],
            evaluator_version=DIRECT[2],
        )
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)


def test_design_39_malformed_unrelated_bucket_fails_globally():
    cfg = {
        "schema_version": 1,
        "buckets": [
            _bucket(*DIRECT, {"needsNews": None, "needsDeepAI": 0.7}),
            "broken-unrelated-bucket",
        ],
    }
    with pytest.raises(ResearchGateError) as ei:
        threshold_config_hash(
            cfg,
            provider=DIRECT[0],
            requested_model=DIRECT[1],
            evaluator_version=DIRECT[2],
        )
    assert "THRESHOLD_CONFIG_UNREADABLE" in str(ei.value)


def test_design_39_valid_empty_buckets_still_missing_hash():
    h = threshold_config_hash(
        {"schema_version": 1, "buckets": []},
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
    )
    assert HEX64.match(h)



def test_load_valid_cfg_roundtrip(tmp_path: Path):
    path = tmp_path / "ok.json"
    cfg = _cfg(_bucket(*DIRECT, {"needsNews": None}))
    path.write_text(json.dumps(cfg), encoding="utf-8")
    loaded = _load_threshold_cfg(path)
    assert loaded["buckets"][0]["provider"] == DIRECT[0]
    h = threshold_config_hash(loaded, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert HEX64.match(h)


# ===========================================================================
# J3 Task 2 — evaluate_research_gate (Design 1–19 + locked error codes)
# ===========================================================================

from kr_quant.research import jev_research_gate as gate
from kr_quant.research.jev_calibration import BOOLEAN_HEADS, STATUS_UNCALIBRATED


def _complete_answers(prob: float = 0.5, **overrides: float) -> dict:
    out = {
        head: {"type": "boolean", "probability": float(overrides.get(head, prob)), "decision": True}
        for head in BOOLEAN_HEADS
    }
    return out


def _null_thresholds() -> dict:
    return {h: None for h in BOOLEAN_HEADS}


def _eval(**kwargs):
    base = dict(
        answers=_complete_answers(0.5),
        threshold_cfg=_cfg(_bucket(*DIRECT, _null_thresholds())),
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        generation_id="gen-A",
        candidate_id="cand-1",
        state_hash="state-aaa",
    )
    base.update(kwargs)
    return gate.evaluate_research_gate(**base)


def test_design_01_all_null_thresholds_uncalibrated():
    result = _eval()
    assert result["mode"] == gate.MODE_SHADOW_ONLY
    assert result["side_effects_executed"] is False
    assert result["calibrated_heads"] == []
    assert result["uncalibrated_heads"] == list(BOOLEAN_HEADS)
    assert result["all_heads_calibrated"] is False
    for head in BOOLEAN_HEADS:
        h = result["heads"][head]
        assert h["threshold"] is None
        assert h["decision"] is None
        assert h["reason"] == STATUS_UNCALIBRATED


def test_design_02_one_calibrated_head_true_and_false():
    thr = _null_thresholds()
    thr["needsNews"] = 0.6
    cfg = _cfg(_bucket(*DIRECT, thr))
    true_r = _eval(answers=_complete_answers(0.5, needsNews=0.7), threshold_cfg=cfg)
    assert true_r["heads"]["needsNews"]["decision"] is True
    assert true_r["heads"]["needsNews"]["reason"] is None
    assert true_r["heads"]["needsDart"]["decision"] is None
    false_r = _eval(answers=_complete_answers(0.5, needsNews=0.5), threshold_cfg=cfg)
    assert false_r["heads"]["needsNews"]["decision"] is False


def test_design_03_mixed_heads_aggregates():
    thr = _null_thresholds()
    thr["needsNews"] = 0.4
    thr["needsDeepAI"] = 0.8
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(answers=_complete_answers(0.5, needsNews=0.5, needsDeepAI=0.7), threshold_cfg=cfg)
    assert r["calibrated_heads"] == ["needsNews", "needsDeepAI"]
    assert "needsDart" in r["uncalibrated_heads"]
    assert r["all_heads_calibrated"] is False
    assert r["research_requirements"]["news"] is True
    assert r["research_requirements"]["deep_ai"] is False
    assert r["research_requirements"]["dart"] is None


def test_design_04_exact_boundary_ge_true():
    thr = _null_thresholds()
    thr["needsNews"] = 0.64
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(answers=_complete_answers(0.5, needsNews=0.64), threshold_cfg=cfg)
    assert r["heads"]["needsNews"]["decision"] is True


def test_design_05_provider_isolation():
    thr = _null_thresholds()
    thr["needsNews"] = 0.1
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(
        threshold_cfg=cfg,
        provider=OPENROUTER[0],
        requested_model=OPENROUTER[1],
        evaluator_version=OPENROUTER[2],
        answers=_complete_answers(0.9),
    )
    assert r["mode"] == gate.MODE_SHADOW_ONLY
    assert r["heads"]["needsNews"]["decision"] is None
    assert r["heads"]["needsNews"]["reason"] == STATUS_UNCALIBRATED


def test_design_06_requested_model_isolation():
    thr = _null_thresholds()
    thr["needsNews"] = 0.1
    cfg = _cfg(_bucket(DIRECT[0], "other-model", DIRECT[2], thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.9))
    assert r["heads"]["needsNews"]["decision"] is None
    assert r["heads"]["needsNews"]["reason"] == STATUS_UNCALIBRATED


def test_design_07_evaluator_isolation():
    thr = _null_thresholds()
    thr["needsNews"] = 0.1
    cfg = _cfg(_bucket(DIRECT[0], DIRECT[1], "other-eval", thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.9))
    assert r["heads"]["needsNews"]["decision"] is None
    assert r["heads"]["needsNews"]["reason"] == STATUS_UNCALIBRATED


def test_design_08_missing_bucket_shadow_uncalibrated_with_hash():
    cfg = _cfg(_bucket(*OPENROUTER, _null_thresholds()))
    r = _eval(threshold_cfg=cfg)
    assert r["mode"] == gate.MODE_SHADOW_ONLY
    assert HEX64.match(r["threshold_config_hash"])
    assert all(r["heads"][h]["decision"] is None for h in BOOLEAN_HEADS)
    assert all(r["heads"][h]["reason"] == STATUS_UNCALIBRATED for h in BOOLEAN_HEADS)


def test_design_09_invalid_probability_error():
    for bad in [True, "0.5", float("nan"), float("inf"), -0.1, 1.1]:
        answers = _complete_answers(0.5)
        answers["needsNews"] = {"type": "boolean", "probability": bad}
        r = _eval(answers=answers)
        assert r["mode"] == gate.MODE_ERROR
        assert r["error"]["code"] == "INVALID_PROBABILITY"
        assert r["side_effects_executed"] is False


def test_design_10_invalid_threshold_error():
    thr = _null_thresholds()
    thr["needsNews"] = 1.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg)
    assert r["mode"] == gate.MODE_ERROR
    assert r["error"]["code"] == "INVALID_THRESHOLD"


def test_design_11_no_half_fallback():
    r_hi = _eval(answers=_complete_answers(0.99))
    r_lo = _eval(answers=_complete_answers(0.01))
    assert r_hi["heads"]["needsNews"]["decision"] is None
    assert r_lo["heads"]["needsNews"]["decision"] is None


def test_design_12_no_provider_fallback():
    thr = _null_thresholds()
    thr["needsNews"] = 0.1
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(
        threshold_cfg=cfg,
        provider=OPENROUTER[0],
        requested_model=OPENROUTER[1],
        evaluator_version=OPENROUTER[2],
        answers=_complete_answers(0.99),
    )
    assert r["heads"]["needsNews"]["decision"] is None
    assert r["heads"]["needsNews"]["reason"] == STATUS_UNCALIBRATED


def test_design_13_review_class_non_routing():
    thr = _null_thresholds()
    thr["needsNews"] = 0.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    a = _eval(threshold_cfg=cfg, answers=_complete_answers(0.6), review_class="A")
    b = _eval(threshold_cfg=cfg, answers=_complete_answers(0.6), review_class="B")
    assert a["heads"] == b["heads"]
    assert a["research_requirements"] == b["research_requirements"]
    assert a["diagnostics"]["review_class"] == "A"
    assert b["diagnostics"]["review_class"] == "B"


def test_design_14_material_now_advisory_only():
    thr = _null_thresholds()
    thr["materialNow"] = 0.4
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.5, materialNow=0.9))
    assert r["material_now"] is True
    assert r["research_requirements"]["news"] is None
    assert r["research_requirements"]["dart"] is None


def test_design_15_historical_conflict_advisory_only():
    thr = _null_thresholds()
    thr["historicalConflict"] = 0.4
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.5, historicalConflict=0.9))
    assert r["historical_conflict"] is True
    assert r["research_requirements"]["news"] is None


def test_design_16_needs_news_flag_no_call():
    thr = _null_thresholds()
    thr["needsNews"] = 0.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.5, needsNews=0.9))
    assert r["research_requirements"]["news"] is True
    assert r["side_effects_executed"] is False


def test_design_17_needs_dart_flag_no_call():
    thr = _null_thresholds()
    thr["needsDart"] = 0.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.5, needsDart=0.9))
    assert r["research_requirements"]["dart"] is True
    assert r["side_effects_executed"] is False


def test_design_18_needs_deep_ai_flag_no_call():
    thr = _null_thresholds()
    thr["needsDeepAI"] = 0.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    r = _eval(threshold_cfg=cfg, answers=_complete_answers(0.5, needsDeepAI=0.9))
    assert r["research_requirements"]["deep_ai"] is True
    assert r["side_effects_executed"] is False


def test_design_19_quant_isolation_signature():
    import inspect
    sig = inspect.signature(gate.evaluate_research_gate)
    forbidden = {
        "state",
        "quantReference",
        "quant_reference",
        "pre_entry_rank",
        "grade",
        "seasonality_score",
        "score_breakdown",
        "settings",
        "client",
    }
    assert forbidden.isdisjoint(sig.parameters)


def test_error_missing_answers():
    r = _eval(answers=None)  # type: ignore[arg-type]
    assert r["mode"] == gate.MODE_ERROR
    assert r["error"]["code"] == "MISSING_ANSWERS"


def test_error_missing_head():
    answers = _complete_answers(0.5)
    del answers["needsNews"]
    r = _eval(answers=answers)
    assert r["mode"] == gate.MODE_ERROR
    assert r["error"]["code"] == "MISSING_HEAD"


def test_error_invalid_identity_empty_fields():
    for kw in ("provider", "requested_model", "evaluator_version", "generation_id", "candidate_id", "state_hash"):
        r = _eval(**{kw: "   "})
        assert r["mode"] == gate.MODE_ERROR
        assert r["error"]["code"] == "INVALID_IDENTITY"


def test_error_unsupported_provider():
    r = _eval(provider="unknown-provider")
    assert r["mode"] == gate.MODE_ERROR
    assert r["error"]["code"] == "UNSUPPORTED_PROVIDER"


def test_error_threshold_config_unreadable():
    r = _eval(threshold_cfg={"buckets": []})  # missing schema_version
    assert r["mode"] == gate.MODE_ERROR
    assert r["error"]["code"] == "THRESHOLD_CONFIG_UNREADABLE"


def test_resolved_model_diagnostic_only():
    thr = _null_thresholds()
    thr["needsNews"] = 0.5
    cfg = _cfg(_bucket(*DIRECT, thr))
    a = _eval(threshold_cfg=cfg, answers=_complete_answers(0.6), resolved_model="x")
    b = _eval(threshold_cfg=cfg, answers=_complete_answers(0.6), resolved_model="y")
    assert a["heads"] == b["heads"]
    assert a["diagnostics"]["resolved_model"] == "x"
    assert b["diagnostics"]["resolved_model"] == "y"
