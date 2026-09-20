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


def test_load_valid_cfg_roundtrip(tmp_path: Path):
    path = tmp_path / "ok.json"
    cfg = _cfg(_bucket(*DIRECT, {"needsNews": None}))
    path.write_text(json.dumps(cfg), encoding="utf-8")
    loaded = _load_threshold_cfg(path)
    assert loaded["buckets"][0]["provider"] == DIRECT[0]
    h = threshold_config_hash(loaded, provider=DIRECT[0], requested_model=DIRECT[1], evaluator_version=DIRECT[2])
    assert HEX64.match(h)
