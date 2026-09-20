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


# ===========================================================================
# J3 Task 3 — evaluate_research_gate_generation (Design 24/25/26/31/32)
# ===========================================================================


def _shadow_payload(*, results, generation_id="gen-A", provider=None, requested_model=None, evaluator_version=None):
    return {
        "schema_version": 1,
        "evaluator_version": evaluator_version if evaluator_version is not None else DIRECT[2],
        "generation_id": generation_id,
        "provider": provider if provider is not None else DIRECT[0],
        "requested_model": requested_model if requested_model is not None else DIRECT[1],
        "results": results,
    }


def _cand(cid: str, state: str, *, answers=None, resolved_model="jev-1.13.0", extra=None, review_choice=None):
    ans = answers if answers is not None else _complete_answers(0.5)
    if review_choice is not None:
        ans = dict(ans)
        ans["reviewClass"] = {
            "type": "choice",
            "choice": review_choice,
            "probabilities": {review_choice: 1.0},
            "confidence": 0.8,
        }
    rec = {
        "candidate_id": cid,
        "state_hash": state,
        "answers": ans,
        "resolved_model": resolved_model,
        "candidate_type": "ticker",
        "ticker": "005930",
    }
    if extra:
        rec.update(extra)
    return rec


def test_design_24_two_candidates_one_envelope():
    payload = _shadow_payload(
        results=[
            _cand("cand-B", "state-B"),
            _cand("cand-A", "state-A"),
        ]
    )
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    env = gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)
    assert env["artifact_type"] == gate.GATE_ARTIFACT_TYPE
    assert env["mode"] == gate.MODE_SHADOW_ONLY
    assert env["side_effects_executed"] is False
    assert len(env["results"]) == 2
    ids = [r["candidate_id"] for r in env["results"]]
    assert ids == ["cand-A", "cand-B"]
    assert all("gate" in r and "state_hash" not in r for r in env["results"])
    assert "state_hash" not in env


def test_design_25_duplicate_candidate_id_rejects():
    payload = _shadow_payload(
        results=[
            _cand("cand-A", "state-1"),
            _cand("cand-A", "state-2"),
        ]
    )
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)


def test_design_26_distinct_state_hashes_valid():
    payload = _shadow_payload(
        results=[
            _cand("cand-A", "state-A"),
            _cand("cand-B", "state-B"),
        ]
    )
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    env = gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)
    by_id = {r["candidate_id"]: r["gate"] for r in env["results"]}
    assert by_id["cand-A"]["state_hash"] == "state-A"
    assert by_id["cand-B"]["state_hash"] == "state-B"
    assert "state_hash" not in env


def test_design_31_candidate_error_isolates_sibling():
    bad_answers = _complete_answers(0.5)
    del bad_answers["needsNews"]
    payload = _shadow_payload(
        results=[
            _cand("cand-A", "state-A"),
            _cand("cand-B", "state-B", answers=bad_answers),
        ]
    )
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    env = gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)
    by_id = {r["candidate_id"]: r["gate"] for r in env["results"]}
    assert by_id["cand-A"]["mode"] == gate.MODE_SHADOW_ONLY
    assert by_id["cand-B"]["mode"] == gate.MODE_ERROR
    assert by_id["cand-B"]["error"]["code"] == "MISSING_HEAD"
    assert env["mode"] == gate.MODE_SHADOW_ONLY


def test_design_32_envelope_corruption_raises():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    good = [_cand("cand-A", "state-A")]
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(results=good, generation_id=""),
            threshold_cfg=cfg,
        )
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(results=good, provider="unknown"),
            threshold_cfg=cfg,
        )
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(results=good, requested_model=""),
            threshold_cfg=cfg,
        )
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(results=good, evaluator_version=""),
            threshold_cfg=cfg,
        )
    bad_payload = _shadow_payload(results=good)
    bad_payload["results"] = "nope"
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(bad_payload, threshold_cfg=cfg)
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(results=good),
            threshold_cfg={"buckets": []},
        )


def test_design_21_30_order_and_determinism():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    results_a = [
        _cand("cand-C", "sC"),
        _cand("cand-A", "sA"),
        _cand("cand-B", "sB"),
    ]
    results_b = [
        _cand("cand-B", "sB"),
        _cand("cand-C", "sC"),
        _cand("cand-A", "sA"),
    ]
    env1 = gate.evaluate_research_gate_generation(_shadow_payload(results=results_a), threshold_cfg=cfg)
    env2 = gate.evaluate_research_gate_generation(_shadow_payload(results=results_b), threshold_cfg=cfg)
    assert [r["candidate_id"] for r in env1["results"]] == ["cand-A", "cand-B", "cand-C"]
    assert env1 == env2
    assert "timestamp" not in env1


def test_upstream_reviewclass_under_answers_only():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    payload = _shadow_payload(
        results=[_cand("cand-A", "state-A", review_choice="monitor")]
    )
    assert "reviewClass" not in payload["results"][0]
    env = gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)
    gate_obj = env["results"][0]["gate"]
    assert gate_obj["diagnostics"]["review_class"] == "monitor"
    assert gate_obj["diagnostics"]["resolved_model"] == "jev-1.13.0"
    # decision invariance when only review choice changes
    payload2 = _shadow_payload(
        results=[_cand("cand-A", "state-A", review_choice="escalate")]
    )
    env2 = gate.evaluate_research_gate_generation(payload2, threshold_cfg=cfg)
    g2 = env2["results"][0]["gate"]
    assert g2["heads"] == gate_obj["heads"]
    assert g2["diagnostics"]["review_class"] == "escalate"


def test_top_level_identity_overrides_candidate_copies():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    payload = _shadow_payload(
        results=[
            _cand(
                "cand-A",
                "state-A",
                extra={
                    "provider": "openrouter",
                    "requested_model": "typesafe/jev-1.13",
                    "evaluator_version": "other",
                },
            )
        ]
    )
    env = gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)
    g = env["results"][0]["gate"]
    assert g["provider"] == DIRECT[0]
    assert g["requested_model"] == DIRECT[1]
    assert g["evaluator_version"] == DIRECT[2]


def test_quant_metadata_ignored():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    a = _cand(
        "cand-A",
        "state-A",
        extra={
            "quant_reference": {"x": 1},
            "grade": "A",
            "pre_entry_rank": 1,
            "seasonality_score": 9,
            "score_breakdown": {"a": 1},
        },
    )
    b = _cand(
        "cand-A",
        "state-A",
        extra={
            "quant_reference": {"x": 99},
            "grade": "Z",
            "pre_entry_rank": 999,
            "seasonality_score": -1,
            "score_breakdown": {"a": 0},
        },
    )
    env1 = gate.evaluate_research_gate_generation(_shadow_payload(results=[a]), threshold_cfg=cfg)
    env2 = gate.evaluate_research_gate_generation(_shadow_payload(results=[b]), threshold_cfg=cfg)
    assert env1["results"][0]["gate"]["heads"] == env2["results"][0]["gate"]["heads"]


def test_empty_results_valid_envelope():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    env = gate.evaluate_research_gate_generation(_shadow_payload(results=[]), threshold_cfg=cfg)
    assert env["mode"] == gate.MODE_SHADOW_ONLY
    assert env["results"] == []
    assert HEX64.match(env["threshold_config_hash"])


def test_malformed_result_element_raises():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    payload = _shadow_payload(results=["bad"])
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(payload, threshold_cfg=cfg)


def test_malformed_candidate_id_list_isolates():
    """Unhashable list candidate_id must become INVALID_IDENTITY, not TypeError."""
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    rec = _cand("cand-A", "state-A")
    rec["candidate_id"] = []
    env = gate.evaluate_research_gate_generation(
        _shadow_payload(results=[rec]),
        threshold_cfg=cfg,
    )
    assert len(env["results"]) == 1
    g = env["results"][0]["gate"]
    assert g["mode"] == gate.MODE_ERROR
    assert g["error"]["code"] == "INVALID_IDENTITY"


def test_malformed_candidate_id_dict_isolates():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    rec = _cand("cand-A", "state-A")
    rec["candidate_id"] = {}
    env = gate.evaluate_research_gate_generation(
        _shadow_payload(results=[rec]),
        threshold_cfg=cfg,
    )
    assert len(env["results"]) == 1
    g = env["results"][0]["gate"]
    assert g["mode"] == gate.MODE_ERROR
    assert g["error"]["code"] == "INVALID_IDENTITY"


def test_malformed_candidate_id_preserves_valid_sibling():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    good = _cand("cand-A", "state-A")
    bad = _cand("cand-B", "state-B")
    bad["candidate_id"] = []
    env = gate.evaluate_research_gate_generation(
        _shadow_payload(results=[bad, good]),
        threshold_cfg=cfg,
    )
    by_outer = {r["candidate_id"] if isinstance(r["candidate_id"], str) else "MALFORMED": r["gate"] for r in env["results"]}
    # Find by gate identity fields / modes
    modes = sorted(r["gate"]["mode"] for r in env["results"])
    assert modes == [gate.MODE_ERROR, gate.MODE_SHADOW_ONLY]
    shadow = next(r for r in env["results"] if r["gate"]["mode"] == gate.MODE_SHADOW_ONLY)
    err = next(r for r in env["results"] if r["gate"]["mode"] == gate.MODE_ERROR)
    assert shadow["candidate_id"] == "cand-A"
    assert shadow["gate"]["mode"] == gate.MODE_SHADOW_ONLY
    assert err["gate"]["error"]["code"] == "INVALID_IDENTITY"


def test_duplicate_valid_string_candidate_id_still_rejects():
    cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    with pytest.raises(ResearchGateError):
        gate.evaluate_research_gate_generation(
            _shadow_payload(
                results=[
                    _cand("cand-A", "state-1"),
                    _cand("cand-A", "state-2"),
                ]
            ),
            threshold_cfg=cfg,
        )


# ===========================================================================
# J3 Task 4 — Persistence and Reuse (Design 20/21/27/28/29/30/35)
# ===========================================================================

import types
from kr_quant.atomic_io import write_json_atomic as _real_write_json_atomic


def _settings(tmp_path: Path):
    return types.SimpleNamespace(data_dir=tmp_path)


def _direct_cfg(thresholds=None):
    thr = thresholds if thresholds is not None else _null_thresholds()
    return _cfg(_bucket(*DIRECT, thr))


def _build_env(cfg, results=None, generation_id="gen-A"):
    if results is None:
        results = [_cand("cand-A", "state-A")]
    return gate.evaluate_research_gate_generation(
        _shadow_payload(results=results, generation_id=generation_id),
        threshold_cfg=cfg,
    )


def _persist(tmp_path, env, generation_id=None, provider=None):
    settings = _settings(tmp_path)
    gid = generation_id or env["generation_id"]
    prov = provider or env["provider"]
    path = gate.research_gate_path(settings, gid, prov)
    gate.write_research_gate_artifact(path, env)
    return path


def test_research_gate_paths(tmp_path):
    settings = _settings(tmp_path)
    d = gate.research_gate_dir(settings)
    assert d == tmp_path / "research_snapshots" / "season_jev_research_gate"
    p = gate.research_gate_path(settings, "gen-A", "typesafe_direct")
    assert p == d / "gen-A__typesafe_direct__gate.json"
    assert not d.exists()
    unsafe = gate.research_gate_path(settings, "gen-B", "foo/bar:baz")
    assert unsafe.name == "gen-B__foo_bar_baz__gate.json"


def test_write_uses_atomic_compact(tmp_path, monkeypatch):
    calls = []

    def spy(path, payload, *, encoding="utf-8", compact=False):
        calls.append({"path": Path(path), "compact": compact})
        return _real_write_json_atomic(path, payload, encoding=encoding, compact=compact)

    monkeypatch.setattr(gate, "write_json_atomic", spy)
    cfg = _direct_cfg()
    env = _build_env(cfg)
    path = _persist(tmp_path, env)
    assert path.exists()
    assert len(calls) == 1
    assert calls[0]["compact"] is True
    assert calls[0]["path"] == path


def test_design_24_secondary_persisted_two_candidate_envelope(tmp_path):
    cfg = _direct_cfg()
    env = _build_env(
        cfg,
        results=[_cand("cand-B", "state-B"), _cand("cand-A", "state-A")],
    )
    path = _persist(tmp_path, env)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(loaded["results"]) == 2
    assert [r["candidate_id"] for r in loaded["results"]] == ["cand-A", "cand-B"]
    assert all("gate" in r for r in loaded["results"])
    assert "state_hash" not in loaded
    art_dir = gate.research_gate_dir(_settings(tmp_path))
    files = list(art_dir.glob("*.json"))
    assert len(files) == 1


def test_design_21_deterministic_envelope_and_bytes(tmp_path):
    cfg = _direct_cfg()
    results = [_cand("cand-C", "sC"), _cand("cand-A", "sA"), _cand("cand-B", "sB")]
    env1 = _build_env(cfg, results=results)
    env2 = _build_env(cfg, results=list(reversed(results)))
    assert env1 == env2
    assert "timestamp" not in env1
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    gate.write_research_gate_artifact(p1, env1)
    gate.write_research_gate_artifact(p2, env2)
    assert p1.read_bytes() == p2.read_bytes()


def test_design_30_persisted_order_abc(tmp_path):
    cfg = _direct_cfg()
    env = _build_env(
        cfg,
        results=[_cand("cand-C", "sC"), _cand("cand-A", "sA"), _cand("cand-B", "sB")],
    )
    path = _persist(tmp_path, env)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert [r["candidate_id"] for r in loaded["results"]] == ["cand-A", "cand-B", "cand-C"]


def test_reuse_positive_exact_eight_field_match(tmp_path):
    cfg = _direct_cfg()
    env = _build_env(cfg, results=[_cand("cand-A", "state-A")])
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    g = env["results"][0]["gate"]
    key = gate._reuse_key(
        schema_version=env["schema_version"],
        generation_id=env["generation_id"],
        provider=env["provider"],
        requested_model=env["requested_model"],
        evaluator_version=env["evaluator_version"],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=env["threshold_config_hash"],
    )
    assert key in index
    assert index[key] == g
    assert len(key) == 8


def test_design_20_matching_threshold_change_invalidates(tmp_path):
    thr_a = _null_thresholds()
    thr_b = _null_thresholds()
    thr_b["needsNews"] = 0.5
    cfg_a = _direct_cfg(thr_a)
    cfg_b = _direct_cfg(thr_b)
    h_a = threshold_config_hash(cfg_a, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_b = threshold_config_hash(cfg_b, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert h_a != h_b
    env = _build_env(cfg_a, results=[_cand("cand-A", "state-A")])
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    key_b = gate._reuse_key(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=h_b,
    )
    assert key_b not in index


def test_design_28_no_fallback_to_old_threshold_hash(tmp_path):
    thr1 = _null_thresholds()
    thr2 = dict(thr1)
    thr2["needsDart"] = 0.4
    cfg1 = _direct_cfg(thr1)
    cfg2 = _direct_cfg(thr2)
    h1 = threshold_config_hash(cfg1, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h2 = threshold_config_hash(cfg2, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert h1 != h2
    env = _build_env(cfg1)
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    key2 = gate._reuse_key(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=h2,
    )
    assert key2 not in index
    key1 = gate._reuse_key(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=h1,
    )
    assert key1 in index


def test_design_29_unrelated_provider_bucket_edit_preserves_reuse(tmp_path):
    thr = _null_thresholds()
    cfg_a = _cfg(_bucket(*DIRECT, thr), _bucket(*OPENROUTER, thr))
    thr_or = dict(thr)
    thr_or["needsNews"] = 0.9
    cfg_b = _cfg(_bucket(*DIRECT, thr), _bucket(*OPENROUTER, thr_or))
    h_a = threshold_config_hash(cfg_a, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    h_b = threshold_config_hash(cfg_b, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert h_a == h_b
    env = gate.evaluate_research_gate_generation(
        _shadow_payload(results=[_cand("cand-A", "state-A")]),
        threshold_cfg=cfg_a,
    )
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    key = gate._reuse_key(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=h_b,
    )
    assert key in index


def test_design_35_missing_to_matched_invalidates(tmp_path):
    missing_cfg = _cfg()
    matched_cfg = _cfg(_bucket(*DIRECT, _null_thresholds()))
    h_missing = threshold_config_hash(
        missing_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2]
    )
    h_matched = threshold_config_hash(
        matched_cfg, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2]
    )
    assert h_missing != h_matched
    env = _build_env(missing_cfg, results=[_cand("cand-A", "state-A")])
    assert env["threshold_config_hash"] == h_missing
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    key_matched = gate._reuse_key(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        candidate_id="cand-A",
        state_hash="state-A",
        threshold_config_hash=h_matched,
    )
    assert key_matched not in index


def test_design_27_state_hash_invalidates_only_that_candidate(tmp_path):
    cfg = _direct_cfg()
    env = _build_env(
        cfg,
        results=[_cand("cand-A", "state-A"), _cand("cand-B", "state-B")],
    )
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    common = dict(
        schema_version=1,
        generation_id=env["generation_id"],
        provider=DIRECT[0],
        requested_model=DIRECT[1],
        evaluator_version=DIRECT[2],
        threshold_config_hash=env["threshold_config_hash"],
    )
    key_a2 = gate._reuse_key(candidate_id="cand-A", state_hash="state-A2", **common)
    key_b = gate._reuse_key(candidate_id="cand-B", state_hash="state-B", **common)
    key_a = gate._reuse_key(candidate_id="cand-A", state_hash="state-A", **common)
    assert key_a2 not in index
    assert key_b in index
    assert key_a in index
    with pytest.raises(ResearchGateError) as ei:
        gate._assert_persisted_state_identity(index[key_a], state_hash="state-A2")
    assert "STATE_HASH_MISMATCH" in str(ei.value)
    gate._assert_persisted_state_identity(index[key_b], state_hash="state-B")


def test_unsupported_schema_raises(tmp_path):
    path = tmp_path / "bad_schema.json"
    path.write_text(
        json.dumps({"schema_version": 99, "artifact_type": gate.GATE_ARTIFACT_TYPE, "results": []}),
        encoding="utf-8",
    )
    with pytest.raises(ResearchGateError) as ei:
        gate.load_reuse_index(path)
    assert "UNSUPPORTED_SCHEMA" in str(ei.value)


def test_error_gates_not_indexed(tmp_path):
    cfg = _direct_cfg()
    bad_answers = _complete_answers(0.5)
    del bad_answers["needsNews"]
    env = _build_env(
        cfg,
        results=[
            _cand("cand-A", "state-A"),
            _cand("cand-B", "state-B", answers=bad_answers),
        ],
    )
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    assert len(index) == 1
    only_key = next(iter(index))
    assert only_key[5] == "cand-A"


def test_malformed_candidate_id_not_indexed(tmp_path):
    cfg = _direct_cfg()
    bad = _cand("cand-X", "state-X")
    bad["candidate_id"] = []
    good = _cand("cand-A", "state-A")
    env = _build_env(cfg, results=[bad, good])
    path = _persist(tmp_path, env)
    index = gate.load_reuse_index(path)
    assert len(index) == 1
    assert next(iter(index))[5] == "cand-A"


def test_malformed_artifacts_yield_no_reuse(tmp_path):
    assert gate.load_reuse_index(tmp_path / "nope.json") == {}
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    assert gate.load_reuse_index(bad_json) == {}
    bad_root = tmp_path / "root.json"
    bad_root.write_text(json.dumps([1, 2]), encoding="utf-8")
    assert gate.load_reuse_index(bad_root) == {}
    bad_type = tmp_path / "type.json"
    bad_type.write_text(
        json.dumps({
            "schema_version": 1,
            "artifact_type": "other",
            "generation_id": "g",
            "provider": "typesafe_direct",
            "requested_model": "jev-latest",
            "evaluator_version": "v",
            "threshold_config_hash": "a" * 64,
            "results": [],
        }),
        encoding="utf-8",
    )
    assert gate.load_reuse_index(bad_type) == {}


def test_load_reuse_index_missing_path_empty(tmp_path):
    assert gate.load_reuse_index(tmp_path / "missing__gate.json") == {}


# ===========================================================================
# J3 Task 4 correction — persisted artifact fail-closed hardening
# ===========================================================================


def _minimal_valid_artifact(**overrides):
    """Build a structurally valid persisted artifact; override fields as needed."""
    thr = "a" * 64
    gate_obj = {
        "schema_version": 1,
        "mode": gate.MODE_SHADOW_ONLY,
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "generation_id": "gen-A",
        "candidate_id": "cand-A",
        "state_hash": "state-A",
        "threshold_config_hash": thr,
        "heads": {},
        "side_effects_executed": False,
    }
    art = {
        "schema_version": 1,
        "artifact_type": gate.GATE_ARTIFACT_TYPE,
        "mode": gate.MODE_SHADOW_ONLY,
        "generation_id": "gen-A",
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "threshold_config_hash": thr,
        "results": [{"candidate_id": "cand-A", "gate": gate_obj}],
        "side_effects_executed": False,
    }
    art.update(overrides)
    return art


def _write_art(tmp_path, art, name="art.json"):
    path = tmp_path / name
    path.write_text(json.dumps(art), encoding="utf-8")
    return path


def test_persisted_schema_bool_true_unsupported(tmp_path):
    art = _minimal_valid_artifact(schema_version=True)
    with pytest.raises(ResearchGateError) as ei:
        gate.load_reuse_index(_write_art(tmp_path, art))
    assert "UNSUPPORTED_SCHEMA" in str(ei.value)


def test_persisted_schema_bool_false_unsupported(tmp_path):
    art = _minimal_valid_artifact(schema_version=False)
    with pytest.raises(ResearchGateError) as ei:
        gate.load_reuse_index(_write_art(tmp_path, art))
    assert "UNSUPPORTED_SCHEMA" in str(ei.value)


def test_persisted_schema_string_one_unsupported(tmp_path):
    art = _minimal_valid_artifact(schema_version="1")
    with pytest.raises(ResearchGateError) as ei:
        gate.load_reuse_index(_write_art(tmp_path, art))
    assert "UNSUPPORTED_SCHEMA" in str(ei.value)


def test_persisted_schema_float_one_unsupported(tmp_path):
    art = _minimal_valid_artifact(schema_version=1.0)
    with pytest.raises(ResearchGateError) as ei:
        gate.load_reuse_index(_write_art(tmp_path, art))
    assert "UNSUPPORTED_SCHEMA" in str(ei.value)


def test_persisted_whitespace_generation_id_empty_index(tmp_path):
    art = _minimal_valid_artifact(generation_id="   ")
    art["results"][0]["gate"]["generation_id"] = "   "
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_whitespace_candidate_id_not_indexed(tmp_path):
    thr = "b" * 64
    good_gate = {
        "schema_version": 1,
        "mode": gate.MODE_SHADOW_ONLY,
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "generation_id": "gen-A",
        "candidate_id": "cand-A",
        "state_hash": "state-A",
        "threshold_config_hash": thr,
        "side_effects_executed": False,
    }
    bad_gate = dict(good_gate)
    bad_gate["candidate_id"] = "   "
    art = {
        "schema_version": 1,
        "artifact_type": gate.GATE_ARTIFACT_TYPE,
        "mode": gate.MODE_SHADOW_ONLY,
        "generation_id": "gen-A",
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "threshold_config_hash": thr,
        "results": [
            {"candidate_id": "   ", "gate": bad_gate},
            {"candidate_id": "cand-A", "gate": good_gate},
        ],
        "side_effects_executed": False,
    }
    index = gate.load_reuse_index(_write_art(tmp_path, art))
    assert len(index) == 1
    assert next(iter(index))[5] == "cand-A"


def test_persisted_whitespace_state_hash_not_reused(tmp_path):
    art = _minimal_valid_artifact()
    art["results"][0]["gate"]["state_hash"] = "   "
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_short_threshold_hash_empty(tmp_path):
    art = _minimal_valid_artifact(threshold_config_hash="x")
    art["results"][0]["gate"]["threshold_config_hash"] = "x"
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_uppercase_threshold_hash_empty(tmp_path):
    h = "A" * 64
    art = _minimal_valid_artifact(threshold_config_hash=h)
    art["results"][0]["gate"]["threshold_config_hash"] = h
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_duplicate_candidate_id_empty(tmp_path):
    thr = "c" * 64
    g1 = {
        "schema_version": 1,
        "mode": gate.MODE_SHADOW_ONLY,
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "generation_id": "gen-A",
        "candidate_id": "cand-A",
        "state_hash": "state-1",
        "threshold_config_hash": thr,
        "side_effects_executed": False,
    }
    g2 = dict(g1)
    g2["state_hash"] = "state-2"
    art = {
        "schema_version": 1,
        "artifact_type": gate.GATE_ARTIFACT_TYPE,
        "mode": gate.MODE_SHADOW_ONLY,
        "generation_id": "gen-A",
        "provider": DIRECT[0],
        "requested_model": DIRECT[1],
        "evaluator_version": DIRECT[2],
        "threshold_config_hash": thr,
        "results": [
            {"candidate_id": "cand-A", "gate": g1},
            {"candidate_id": "cand-A", "gate": g2},
        ],
        "side_effects_executed": False,
    }
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_unsupported_provider_empty(tmp_path):
    art = _minimal_valid_artifact(provider="other")
    art["results"][0]["gate"]["provider"] = "other"
    assert gate.load_reuse_index(_write_art(tmp_path, art)) == {}


def test_persisted_valid_positive_control_still_indexed(tmp_path):
    art = _minimal_valid_artifact()
    index = gate.load_reuse_index(_write_art(tmp_path, art))
    assert len(index) == 1
    key = next(iter(index))
    assert key[5] == "cand-A"
    assert key[7] == "a" * 64
