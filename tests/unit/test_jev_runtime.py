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
