# -*- coding: utf-8 -*-
"""Task 1.1 — JEV runtime mode resolution contract (RED-first).

Spec: docs/superpowers/specs/2026-09-23-jev-production-routing-design.md §4.3
Plan: docs/superpowers/plans/2026-09-23-jev-production-activation-implementation.md Task 1.1

These tests are offline and pure: tmp_path config fixtures only, no network,
no production config writes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kr_quant.research import jev_runtime as rt
from kr_quant.research import season_jev_shadow
from kr_quant.research.jev_research_gate import research_gate_path


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(root=tmp_path, data_dir=tmp_path / "data")


def _write_config(tmp_path: Path, payload: object) -> Path:
    folder = tmp_path / "config"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "season_jev.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def test_constants_locked() -> None:
    assert rt.RUNTIME_SCHEMA_VERSION == 1
    assert rt.RUNTIME_ARTIFACT_TYPE == "season_jev_runtime_overlay"
    assert rt.MODE_DISABLED == "disabled"
    assert rt.MODE_SHADOW == "shadow"
    assert rt.MODE_CANARY == "canary"
    assert rt.MODE_PRODUCTION == "production"
    assert rt.MODES == ("disabled", "shadow", "canary", "production")


def test_mode_absent_enabled_false_is_disabled() -> None:
    result = rt.resolve_runtime_mode({"enabled": False})
    assert result == {"mode": "disabled", "reason": None, "errors": []}


def test_mode_absent_enabled_true_is_shadow_with_legacy_reason() -> None:
    result = rt.resolve_runtime_mode({"enabled": True})
    assert result == {"mode": "shadow", "reason": "LEGACY_ENABLED_TRUE", "errors": []}


def test_mode_absent_enabled_absent_is_disabled() -> None:
    result = rt.resolve_runtime_mode({})
    assert result == {"mode": "disabled", "reason": None, "errors": []}


@pytest.mark.parametrize("raw", [{}, {"enabled": True}, {"enabled": False}, {"enabled": "true"}])
def test_legacy_never_resolves_to_canary_or_production(raw: dict) -> None:
    result = rt.resolve_runtime_mode(raw)
    assert result["mode"] in {"disabled", "shadow"}


def test_legacy_non_bool_enabled_is_disabled() -> None:
    result = rt.resolve_runtime_mode({"enabled": "true"})
    assert result["mode"] == "disabled"


def test_mode_shadow_enabled_true_is_shadow() -> None:
    result = rt.resolve_runtime_mode({"mode": "shadow", "enabled": True})
    assert result == {"mode": "shadow", "reason": None, "errors": []}


def test_mode_disabled_enabled_false_is_disabled() -> None:
    result = rt.resolve_runtime_mode({"mode": "disabled", "enabled": False})
    assert result == {"mode": "disabled", "reason": None, "errors": []}


def test_mode_canary_enabled_true_is_canary() -> None:
    result = rt.resolve_runtime_mode({"mode": "canary", "enabled": True})
    assert result == {"mode": "canary", "reason": None, "errors": []}


def test_mode_production_enabled_true_is_production() -> None:
    result = rt.resolve_runtime_mode({"mode": "production", "enabled": True})
    assert result == {"mode": "production", "reason": None, "errors": []}


def test_mode_canary_enabled_false_is_conflict() -> None:
    result = rt.resolve_runtime_mode({"mode": "canary", "enabled": False})
    assert result["mode"] == "disabled"
    assert result["reason"] == "CONFIG_MODE_CONFLICT"
    assert result["errors"]


@pytest.mark.parametrize("enabled", ["true", 1, None, [], {}])
def test_mode_production_non_bool_enabled_is_invalid(enabled: object) -> None:
    result = rt.resolve_runtime_mode({"mode": "production", "enabled": enabled})
    assert result["mode"] == "disabled"
    assert result["reason"] == "CONFIG_MODE_INVALID"
    assert result["errors"]


@pytest.mark.parametrize("mode", ["bogus", "", "SHADOW", 123, None, ["shadow"]])
def test_invalid_mode_is_disabled_invalid(mode: object) -> None:
    result = rt.resolve_runtime_mode({"mode": mode, "enabled": True})
    assert result["mode"] == "disabled"
    assert result["reason"] == "CONFIG_MODE_INVALID"
    assert result["errors"]


@pytest.mark.parametrize("raw", [None, [], "shadow", 1])
def test_non_mapping_config_fails_closed(raw: object) -> None:
    result = rt.resolve_runtime_mode(raw)  # type: ignore[arg-type]
    assert result["mode"] == "disabled"
    assert result["reason"] == "CONFIG_MODE_INVALID"
    assert result["errors"]


def test_missing_config_file_records_error(tmp_path: Path) -> None:
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    assert isinstance(raw, dict)
    result = rt.resolve_runtime_mode(raw)
    assert result["mode"] == "disabled"
    assert result["errors"]
    assert "CONFIG_UNREADABLE" in " ".join(result["errors"])


def test_malformed_json_records_error(tmp_path: Path) -> None:
    folder = tmp_path / "config"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "season_jev.json").write_text("{not-json", encoding="utf-8")
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    result = rt.resolve_runtime_mode(raw)
    assert result["mode"] == "disabled"
    assert result["errors"]


def test_non_object_json_records_error(tmp_path: Path) -> None:
    _write_config(tmp_path, ["not", "an", "object"])
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    result = rt.resolve_runtime_mode(raw)
    assert result["mode"] == "disabled"
    assert result["errors"]


def test_invalid_utf8_bytes_record_error_and_preserve_file(tmp_path: Path) -> None:
    folder = tmp_path / "config"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "season_jev.json"
    payload = b"\xff\xfe\xfa"
    path.write_bytes(payload)
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    result = rt.resolve_runtime_mode(raw)
    assert result["mode"] == "disabled"
    assert result["errors"]
    assert "CONFIG_UNREADABLE" in " ".join(result["errors"])
    assert path.read_bytes() == payload


def test_valid_config_round_trip(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        {"mode": "shadow", "enabled": True, "provider": "typesafe_direct", "model": "jev-latest"},
    )
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    assert raw.get("mode") == "shadow"
    assert raw.get("enabled") is True
    result = rt.resolve_runtime_mode(raw)
    assert result == {"mode": "shadow", "reason": None, "errors": []}


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"enabled": True},
        {"enabled": False},
        {"mode": "shadow", "enabled": True},
        {"mode": "canary", "enabled": False},
        {"mode": "production", "enabled": "yes"},
        {"mode": "bogus"},
        {"mode": "shadow", "enabled": True, "nested": {"a": [1, {"b": 2}]}},
    ],
)
def test_resolution_is_pure_and_does_not_mutate_input(raw: dict) -> None:
    before = copy.deepcopy(raw)
    rt.resolve_runtime_mode(raw)
    assert raw == before


def test_resolution_writes_nothing(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    before = _snapshot(tmp_path)
    config_bytes = (tmp_path / "config" / "season_jev.json").read_bytes()
    raw = rt.load_raw_runtime_config(_settings(tmp_path))
    rt.resolve_runtime_mode(raw)
    assert _snapshot(tmp_path) == before
    assert (tmp_path / "config" / "season_jev.json").read_bytes() == config_bytes


# ---------------------------------------------------------------------------
# Task 1.2 — run_shadow_gate_pass
# ---------------------------------------------------------------------------

_HEADS = (
    "materialNow",
    "needsCurrentYearCheck",
    "needsNews",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
    "needsDeepAI",
)


def _answers(prob: float = 0.5) -> dict:
    return {head: {"probability": prob} for head in _HEADS}


def _threshold_cfg() -> dict:
    return {
        "schema_version": 1,
        "buckets": [
            {
                "provider": "typesafe_direct",
                "requested_model": "jev-latest",
                "evaluator_version": "season-jev-shadow-v1",
                "thresholds": {head: None for head in _HEADS},
            }
        ],
    }


def _shadow_payload(
    *,
    generation_id: str = "gen-1",
    provider: str = "typesafe_direct",
    results: object = None,
) -> dict:
    return {
        "generation_id": generation_id,
        "provider": provider,
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "results": results
        if results is not None
        else [
            {
                "candidate_id": "c1",
                "state_hash": "a" * 64,
                "answers": _answers(),
                "resolved_model": "jev-1.13.0",
            }
        ],
    }


def _active_settings(tmp_path: Path) -> SimpleNamespace:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    return _settings(tmp_path)


def _gate_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "research_snapshots" / "season_jev_research_gate"


def _assert_no_gate_artifacts(tmp_path: Path) -> None:
    folder = _gate_dir(tmp_path)
    assert not folder.exists() or not any(folder.iterdir())


def test_gate_pass_disabled_skips_without_artifact(tmp_path: Path) -> None:
    _write_config(tmp_path, {"enabled": False})
    settings = _settings(tmp_path)
    result = rt.run_shadow_gate_pass(
        settings, shadow_payload=_shadow_payload(), threshold_cfg=_threshold_cfg()
    )
    assert result == {"status": "SKIPPED", "reason": "MODE_DISABLED"}
    _assert_no_gate_artifacts(tmp_path)


def test_gate_pass_missing_config_skips_without_artifact(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = rt.run_shadow_gate_pass(
        settings, shadow_payload=_shadow_payload(), threshold_cfg=_threshold_cfg()
    )
    assert result == {"status": "SKIPPED", "reason": "MODE_DISABLED"}
    _assert_no_gate_artifacts(tmp_path)


def test_gate_pass_writes_exact_path_and_returns_persisted_gate(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    payload = _shadow_payload()
    cfg = _threshold_cfg()
    payload_before = copy.deepcopy(payload)
    cfg_before = copy.deepcopy(cfg)

    result = rt.run_shadow_gate_pass(settings, shadow_payload=payload, threshold_cfg=cfg)

    assert result["status"] == "OK"
    expected = research_gate_path(settings, "gen-1", "typesafe_direct")
    assert result["path"] == str(expected)
    persisted = json.loads(expected.read_text(encoding="utf-8"))
    assert persisted == result["gate"]
    assert result["gate"]["side_effects_executed"] is False
    assert result["gate"]["mode"] == "SHADOW_ONLY"
    assert result["gate"]["artifact_type"] == "season_jev_research_gate"
    assert payload == payload_before
    assert cfg == cfg_before


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {
            "generation_id": "",
            "provider": "typesafe_direct",
            "requested_model": "m",
            "evaluator_version": "v",
            "results": [],
        },
        {
            "generation_id": "g",
            "provider": "typesafe_direct",
            "requested_model": "m",
            "evaluator_version": "v",
            "results": "nope",
        },
        {
            "generation_id": "g",
            "provider": "typesafe_direct",
            "requested_model": "m",
            "evaluator_version": "v",
            "results": [{"candidate_id": "c1"}, {"candidate_id": "c1"}],
        },
    ],
)
def test_gate_pass_corrupt_envelope_errors_without_artifact(
    tmp_path: Path, payload: object
) -> None:
    settings = _active_settings(tmp_path)
    result = rt.run_shadow_gate_pass(
        settings, shadow_payload=payload, threshold_cfg=_threshold_cfg()
    )
    assert result["status"] == "ERROR"
    assert result["error"]["code"]
    assert result["error"]["message"]
    _assert_no_gate_artifacts(tmp_path)


def test_gate_pass_unsupported_provider_errors_without_artifact(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    result = rt.run_shadow_gate_pass(
        settings,
        shadow_payload=_shadow_payload(provider="vercel_gateway"),
        threshold_cfg=_threshold_cfg(),
    )
    assert result["status"] == "ERROR"
    assert result["error"]["code"]
    _assert_no_gate_artifacts(tmp_path)


@pytest.mark.parametrize(
    "cfg,code",
    [
        ({"schema_version": 2, "buckets": []}, "THRESHOLD_CONFIG_UNREADABLE"),
        (
            {
                "schema_version": 1,
                "buckets": [
                    {
                        "provider": "typesafe_direct",
                        "requested_model": "jev-latest",
                        "evaluator_version": "season-jev-shadow-v1",
                        "thresholds": {"needsNews": 2.0},
                    }
                ],
            },
            "INVALID_THRESHOLD",
        ),
    ],
)
def test_gate_pass_threshold_failure_errors_without_artifact(
    tmp_path: Path, cfg: dict, code: str
) -> None:
    settings = _active_settings(tmp_path)
    result = rt.run_shadow_gate_pass(
        settings, shadow_payload=_shadow_payload(), threshold_cfg=cfg
    )
    assert result["status"] == "ERROR"
    assert result["error"]["code"] == code
    _assert_no_gate_artifacts(tmp_path)


def test_gate_pass_repeated_identical_call_is_byte_identical(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    payload = _shadow_payload()
    cfg = _threshold_cfg()

    first = rt.run_shadow_gate_pass(settings, shadow_payload=payload, threshold_cfg=cfg)
    assert first["status"] == "OK"
    path = Path(first["path"])
    first_bytes = path.read_bytes()

    second = rt.run_shadow_gate_pass(settings, shadow_payload=payload, threshold_cfg=cfg)

    assert second["status"] == "OK"
    assert path.read_bytes() == first_bytes
    assert second["gate"] == first["gate"]


# ---------------------------------------------------------------------------
# Task 1.3 — partition_shadow_records / map_shadow_record_status
# ---------------------------------------------------------------------------


def _record(
    cid: str,
    *,
    status: str = "GENERATED",
    state_hash: object = "a" * 64,
    answers: object = None,
    skip_reason: object = None,
    error: object = None,
) -> dict:
    record = {
        "candidate_id": cid,
        "state_hash": state_hash,
        "ticker": "005930",
        "answers": _answers() if answers is None else answers,
        "status": status,
    }
    if skip_reason is not None:
        record["skip_reason"] = skip_reason
    if error is not None:
        record["error"] = error
    return record


def test_partition_generated_and_reused_are_gate_candidates() -> None:
    generated = _record("c1", status="GENERATED")
    reused = _record("c2", status="REUSED")
    parts = rt.partition_shadow_records(_shadow_payload(results=[generated, reused]))
    assert parts["gate_candidates"] == [generated, reused]
    assert parts["preserved"] == []


def test_partition_skipped_and_error_are_preserved_verbatim() -> None:
    skipped = _record("c1", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={})
    errored = _record("c2", status="ERROR", error="RUNNER:RuntimeError", answers={})
    parts = rt.partition_shadow_records(_shadow_payload(results=[skipped, errored]))
    assert parts["gate_candidates"] == []
    assert parts["preserved"] == [skipped, errored]
    assert parts["preserved"][0]["skip_reason"] == "API_CAP_DAILY"
    assert parts["preserved"][1]["error"] == "RUNNER:RuntimeError"


def test_partition_missing_state_hash_never_enters_gate_candidates() -> None:
    empty_hash = _record("c1", status="GENERATED", state_hash="")
    absent_hash = _record("c2", status="REUSED")
    absent_hash.pop("state_hash")
    parts = rt.partition_shadow_records(_shadow_payload(results=[empty_hash, absent_hash]))
    assert parts["gate_candidates"] == []
    assert parts["preserved"] == [empty_hash, absent_hash]


def test_partition_does_not_mutate_inputs() -> None:
    records = [
        _record("c1"),
        _record("c2", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={}),
    ]
    payload = _shadow_payload(results=records)
    before = copy.deepcopy(payload)
    rt.partition_shadow_records(payload)
    assert payload == before


@pytest.mark.parametrize("bad", [None, [], "x", {"results": "nope"}, {"results": None}])
def test_partition_rejects_malformed_payload(bad: object) -> None:
    with pytest.raises(ValueError):
        rt.partition_shadow_records(bad)  # type: ignore[arg-type]


def test_map_generated_and_reused_to_gate_candidate() -> None:
    assert rt.map_shadow_record_status(_record("c1")) == {
        "runtime_status": "GATE_CANDIDATE",
        "reason": None,
    }
    assert rt.map_shadow_record_status(_record("c1", status="REUSED")) == {
        "runtime_status": "GATE_CANDIDATE",
        "reason": None,
    }


@pytest.mark.parametrize(
    "reason", ["API_CAP_GENERATION", "API_CAP_DAILY", "API_BUDGET_UNAVAILABLE"]
)
def test_map_budget_skip_to_skipped_budget_with_original_reason(reason: str) -> None:
    record = _record("c1", status="SKIPPED", skip_reason=reason, answers={})
    assert rt.map_shadow_record_status(record) == {
        "runtime_status": "SKIPPED_BUDGET",
        "reason": reason,
    }


def test_map_budget_skip_with_empty_answers_never_becomes_gate_error() -> None:
    record = _record("c1", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={})
    mapped = rt.map_shadow_record_status(record)
    assert mapped["runtime_status"] == "SKIPPED_BUDGET"
    assert mapped["reason"] == "API_CAP_DAILY"
    assert "MISSING_ANSWERS" not in str(mapped)
    assert "MISSING_HEAD" not in str(mapped)


def test_map_other_skip_to_skipped_uncalibrated_with_reason() -> None:
    record = _record("c1", status="SKIPPED", skip_reason="SOMETHING_ELSE", answers={})
    assert rt.map_shadow_record_status(record) == {
        "runtime_status": "SKIPPED_UNCALIBRATED",
        "reason": "SOMETHING_ELSE",
    }


def test_map_error_to_failed_with_original_error() -> None:
    record = _record("c1", status="ERROR", error="PROCESS_TIMEOUT", answers={})
    assert rt.map_shadow_record_status(record) == {
        "runtime_status": "FAILED",
        "reason": "PROCESS_TIMEOUT",
    }


def test_map_error_without_reason_uses_bounded_code() -> None:
    record = _record("c1", status="ERROR", answers={})
    assert rt.map_shadow_record_status(record) == {
        "runtime_status": "FAILED",
        "reason": "SHADOW_ERROR",
    }


def test_map_missing_state_hash_to_failed_state_hash_missing() -> None:
    assert rt.map_shadow_record_status(_record("c1", state_hash="")) == {
        "runtime_status": "FAILED",
        "reason": "STATE_HASH_MISSING",
    }
    absent = _record("c1")
    absent.pop("state_hash")
    assert rt.map_shadow_record_status(absent) == {
        "runtime_status": "FAILED",
        "reason": "STATE_HASH_MISSING",
    }


def test_map_does_not_mutate_record() -> None:
    record = _record("c1", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={})
    before = copy.deepcopy(record)
    rt.map_shadow_record_status(record)
    assert record == before


# ---------------------------------------------------------------------------
# Task 1.3 corrective — locked execution identity (9-tuple)
# ---------------------------------------------------------------------------


def _execution(**overrides) -> dict:
    record = {
        "schema_version": 1,
        "generation_id": "gen-1",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "candidate_id": "c1",
        "state_hash": "a" * 64,
        "requirement_type": "news",
        "input_hash": "b" * 64,
        "status": "VERIFIED",
    }
    record.update(overrides)
    return record


def test_execution_identity_fields_locked() -> None:
    assert rt.EXECUTION_IDENTITY_FIELDS == (
        "schema_version",
        "generation_id",
        "provider",
        "requested_model",
        "evaluator_version",
        "candidate_id",
        "state_hash",
        "requirement_type",
        "input_hash",
    )


def test_execution_reuse_key_extracts_locked_nine_tuple() -> None:
    assert rt.execution_reuse_key(_execution()) == (
        1,
        "gen-1",
        "typesafe_direct",
        "jev-latest",
        "season-jev-shadow-v1",
        "c1",
        "a" * 64,
        "news",
        "b" * 64,
    )


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "generation_id",
        "provider",
        "requested_model",
        "evaluator_version",
        "candidate_id",
        "state_hash",
        "requirement_type",
        "input_hash",
    ],
)
def test_execution_reuse_key_requires_every_locked_field(field: str) -> None:
    record = _execution()
    record.pop(field)
    assert rt.execution_reuse_key(record) is None


@pytest.mark.parametrize("bad", [None, [], "x", 1])
def test_execution_reuse_key_rejects_non_mapping(bad: object) -> None:
    assert rt.execution_reuse_key(bad) is None


# ---------------------------------------------------------------------------
# Task 1.4 — runtime_status (read-only observability)
# ---------------------------------------------------------------------------


def _fs_snapshot(root: Path) -> dict:
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = path.read_bytes()
    return snapshot


def _mixed_threshold_cfg() -> dict:
    cfg = _threshold_cfg()
    cfg["buckets"][0]["thresholds"]["needsNews"] = 0.4
    return cfg


def _write_shadow_artifact(settings, payload: dict) -> Path:
    path = season_jev_shadow.shadow_path(
        settings, payload["generation_id"], payload["provider"]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_runtime_status_empty_environment_is_safe_and_read_only(tmp_path: Path) -> None:
    _write_config(tmp_path, {"enabled": False})
    settings = _settings(tmp_path)
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings)

    assert result["mode"] == "disabled"
    assert result["shadow"]["present"] is False
    assert result["shadow"]["counts"] == {
        "GENERATED": 0,
        "REUSED": 0,
        "SKIPPED": 0,
        "ERROR": 0,
        "unknown": 0,
    }
    assert result["shadow"]["total"] == 0
    assert result["gate"]["present"] is False
    assert result["gate"]["calibrated_head_count"] == 0
    assert result["gate"]["uncalibrated_head_count"] == 0
    assert result["thresholds"]["status"] == "MISSING"
    assert _fs_snapshot(tmp_path) == before
    assert not (tmp_path / "data").exists()


def test_runtime_status_shadow_counts(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)
    results = [
        _record("c1"),
        _record("c2"),
        _record("c3", status="REUSED"),
        _record("c4", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={}),
        _record("c5", status="ERROR", error="RUNNER:RuntimeError", answers={}),
        _record("c6", status="WEIRD"),
    ]
    _write_shadow_artifact(
        settings, {**_shadow_payload(results=results), "status": "COMPLETE"}
    )

    result = rt.runtime_status(settings)

    assert result["mode"] == "shadow"
    assert result["shadow"]["present"] is True
    assert result["shadow"]["generation_id"] == "gen-1"
    assert result["shadow"]["provider"] == "typesafe_direct"
    assert result["shadow"]["status"] == "COMPLETE"
    assert result["shadow"]["counts"] == {
        "GENERATED": 2,
        "REUSED": 1,
        "SKIPPED": 1,
        "ERROR": 1,
        "unknown": 1,
    }
    assert result["shadow"]["total"] == 6


def test_runtime_status_picks_latest_shadow_artifact(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)
    old = {
        **_shadow_payload(generation_id="gen-old", results=[_record("old")]),
        "finished_at": "2026-09-01T00:00:00+00:00",
    }
    new = {
        **_shadow_payload(generation_id="gen-new", results=[_record("new")]),
        "finished_at": "2026-09-02T00:00:00+00:00",
    }
    _write_shadow_artifact(settings, old)
    _write_shadow_artifact(settings, new)

    result = rt.runtime_status(settings)

    assert result["shadow"]["present"] is True
    assert result["shadow"]["generation_id"] == "gen-new"
    assert result["shadow"]["total"] == 1


def test_runtime_status_gate_calibrated_counts_and_hash(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    cfg = _mixed_threshold_cfg()
    gate_result = rt.run_shadow_gate_pass(
        settings, shadow_payload=_shadow_payload(), threshold_cfg=cfg
    )
    assert gate_result["status"] == "OK"

    result = rt.runtime_status(settings, threshold_cfg=cfg)

    gate = result["gate"]
    assert gate["present"] is True
    assert gate["readable"] is True
    assert gate["generation_id"] == "gen-1"
    assert gate["provider"] == "typesafe_direct"
    assert gate["requested_model"] == "jev-latest"
    assert gate["evaluator_version"] == "season-jev-shadow-v1"
    assert gate["threshold_config_hash"] == gate_result["gate"]["threshold_config_hash"]
    assert gate["mode"] == "SHADOW_ONLY"
    assert gate["side_effects_executed"] is False
    assert gate["calibrated_heads"] == ["needsNews"]
    assert gate["calibrated_head_count"] == 1
    assert gate["uncalibrated_head_count"] == 6
    assert result["thresholds"]["status"] == "LOADED"
    assert (
        result["thresholds"]["current_threshold_config_hash"]
        == gate["threshold_config_hash"]
    )


def test_runtime_status_shadow_without_gate_is_safe(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)
    _write_shadow_artifact(settings, _shadow_payload(results=[_record("c1")]))
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings)

    assert result["shadow"]["present"] is True
    assert result["gate"]["present"] is False
    assert result["gate"]["threshold_config_hash"] is None
    assert _fs_snapshot(tmp_path) == before
    assert not (
        tmp_path / "data" / "research_snapshots" / "season_jev_research_gate"
    ).exists()


def test_runtime_status_malformed_gate_is_safe_and_read_only(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    gate_path = research_gate_path(settings, "gen-1", "typesafe_direct")
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text("{not-json", encoding="utf-8")
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings, threshold_cfg=_mixed_threshold_cfg())

    assert result["gate"]["present"] is True
    assert result["gate"]["readable"] is False
    assert result["gate"]["threshold_config_hash"] is None
    assert _fs_snapshot(tmp_path) == before
    assert gate_path.read_text(encoding="utf-8") == "{not-json"


def test_runtime_status_malformed_shadow_is_skipped(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)
    folder = season_jev_shadow.shadow_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bad__typesafe_direct.json").write_text("{nope", encoding="utf-8")
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings)

    assert result["shadow"]["present"] is False
    assert _fs_snapshot(tmp_path) == before


def test_runtime_status_unreadable_thresholds_fail_safe(tmp_path: Path) -> None:
    _write_config(tmp_path, {"mode": "shadow", "enabled": True})
    (tmp_path / "config" / "jev_thresholds.json").write_text("{bad", encoding="utf-8")
    settings = _settings(tmp_path)
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings)

    assert result["thresholds"]["status"] == "UNREADABLE"
    assert result["thresholds"]["current_threshold_config_hash"] is None
    assert _fs_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "config,expected_mode,expected_reason",
    [
        ({"enabled": False}, "disabled", None),
        ({"enabled": True}, "shadow", "LEGACY_ENABLED_TRUE"),
        ({"mode": "shadow", "enabled": True}, "shadow", None),
    ],
)
def test_runtime_status_mode_and_reason(
    tmp_path: Path, config: dict, expected_mode: str, expected_reason: object
) -> None:
    _write_config(tmp_path, config)
    settings = _settings(tmp_path)

    result = rt.runtime_status(settings)

    assert result["mode"] == expected_mode
    assert result["mode_reason"] == expected_reason
    assert result["mode_errors"] == []


def test_runtime_status_read_only_over_full_fixture(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    cfg = _mixed_threshold_cfg()
    _write_shadow_artifact(settings, _shadow_payload(results=[_record("c1")]))
    rt.run_shadow_gate_pass(settings, shadow_payload=_shadow_payload(), threshold_cfg=cfg)
    before = _fs_snapshot(tmp_path)

    rt.runtime_status(settings, threshold_cfg=cfg)
    rt.runtime_status(settings)

    assert _fs_snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# Task 1.4 corrective — bind gate status to the latest shadow identity
# ---------------------------------------------------------------------------


def test_runtime_status_does_not_attach_stale_gate_to_newer_shadow(
    tmp_path: Path,
) -> None:
    settings = _active_settings(tmp_path)
    old_gate = rt.run_shadow_gate_pass(
        settings,
        shadow_payload=_shadow_payload(generation_id="gen-old"),
        threshold_cfg=_threshold_cfg(),
    )
    assert old_gate["status"] == "OK"
    _write_shadow_artifact(
        settings,
        {
            **_shadow_payload(generation_id="gen-new", results=[_record("c1")]),
            "finished_at": "2026-09-02T00:00:00+00:00",
        },
    )
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings)

    assert result["shadow"]["generation_id"] == "gen-new"
    assert result["gate"]["present"] is False
    assert result["gate"]["generation_id"] != "gen-old"
    assert _fs_snapshot(tmp_path) == before


def test_runtime_status_prefers_exact_matching_gate(tmp_path: Path) -> None:
    settings = _active_settings(tmp_path)
    cfg = _mixed_threshold_cfg()
    old_gate = rt.run_shadow_gate_pass(
        settings,
        shadow_payload=_shadow_payload(generation_id="gen-old"),
        threshold_cfg=cfg,
    )
    assert old_gate["status"] == "OK"
    _write_shadow_artifact(
        settings,
        {
            **_shadow_payload(generation_id="gen-new", results=[_record("c1")]),
            "finished_at": "2026-09-02T00:00:00+00:00",
        },
    )
    new_gate = rt.run_shadow_gate_pass(
        settings,
        shadow_payload=_shadow_payload(generation_id="gen-new"),
        threshold_cfg=cfg,
    )
    assert new_gate["status"] == "OK"
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings, threshold_cfg=cfg)

    assert result["shadow"]["generation_id"] == "gen-new"
    assert result["gate"]["generation_id"] == "gen-new"
    assert (
        result["gate"]["threshold_config_hash"]
        == new_gate["gate"]["threshold_config_hash"]
    )
    assert result["gate"]["calibrated_head_count"] == 1
    assert result["gate"]["uncalibrated_head_count"] == 6
    assert _fs_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation_id", "gen-old"),
        ("provider", "openrouter"),
        ("requested_model", "typesafe/jev-1.13"),
        ("evaluator_version", "season-jev-shadow-v2"),
    ],
)
def test_runtime_status_identity_mismatch_fails_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    settings = _active_settings(tmp_path)
    cfg = _mixed_threshold_cfg()
    gate_result = rt.run_shadow_gate_pass(
        settings,
        shadow_payload=_shadow_payload(generation_id="gen-new"),
        threshold_cfg=cfg,
    )
    assert gate_result["status"] == "OK"
    _write_shadow_artifact(
        settings,
        {
            **_shadow_payload(generation_id="gen-new", results=[_record("c1")]),
            "finished_at": "2026-09-02T00:00:00+00:00",
        },
    )
    gate_path = research_gate_path(settings, "gen-new", "typesafe_direct")
    tampered = dict(gate_result["gate"])
    tampered[field] = value
    gate_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    before = _fs_snapshot(tmp_path)

    result = rt.runtime_status(settings, threshold_cfg=cfg)

    gate = result["gate"]
    assert gate["present"] is True
    assert gate["readable"] is True
    assert gate["error"] == "IDENTITY_MISMATCH"
    assert gate["threshold_config_hash"] is None
    assert gate["calibrated_head_count"] == 0
    assert gate["uncalibrated_head_count"] == 0
    assert _fs_snapshot(tmp_path) == before
    assert gate_path.read_text(encoding="utf-8") == json.dumps(
        tampered, ensure_ascii=False
    )
