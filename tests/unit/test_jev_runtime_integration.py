# -*- coding: utf-8 -*-
"""P1 Task 1.3 — runtime orchestrator integration contracts (offline fakes).

No network, no live provider calls, no production data-dir writes: every test
uses tmp_path settings and injected fake dependencies.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from kr_quant.research import jev_runtime as rt
from kr_quant.research import season_jev_shadow
from kr_quant.research.jev_research_gate import research_gate_path

GEN = "gen-1"
PROVIDER = "typesafe_direct"
MODEL = "jev-latest"
EVALUATOR = "season-jev-shadow-v1"

_HEADS = (
    "materialNow",
    "needsCurrentYearCheck",
    "needsNews",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
    "needsDeepAI",
)


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(root=tmp_path, data_dir=tmp_path / "data")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_season_config(tmp_path: Path, payload: object) -> None:
    _write_json(tmp_path / "config" / "season_jev.json", payload)


def _threshold_cfg(*, news: float | None = None) -> dict:
    thresholds = {head: None for head in _HEADS}
    thresholds["needsNews"] = news
    return {
        "schema_version": 1,
        "buckets": [
            {
                "provider": PROVIDER,
                "requested_model": MODEL,
                "evaluator_version": EVALUATOR,
                "thresholds": thresholds,
            }
        ],
    }


def _write_thresholds(tmp_path: Path, *, news: float | None = None) -> dict:
    cfg = _threshold_cfg(news=news)
    _write_json(tmp_path / "config" / "jev_thresholds.json", cfg)
    return cfg


def _answers() -> dict:
    return {head: {"probability": 0.5} for head in _HEADS}


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


def _shadow_payload(results: list, *, generation_id: str = GEN) -> dict:
    return {
        "schema_version": 1,
        "evaluator_version": EVALUATOR,
        "generation_id": generation_id,
        "provider": PROVIDER,
        "model": MODEL,
        "requested_model": MODEL,
        "status": "COMPLETE",
        "results": results,
    }


def _bundle(*, generation_id: str = GEN, lookback: int = 5) -> dict:
    return {
        "generation_id": generation_id,
        "identity": {"lookback": lookback, "day": "2026-09-23"},
        "payload": {"rows": []},
    }


def _write_shadow_artifact(settings: SimpleNamespace, payload: dict) -> Path:
    path = season_jev_shadow.shadow_path(settings, payload["generation_id"], PROVIDER)
    _write_json(path, payload)
    return path


def _fake_evaluator(counter: dict, *, results: list | None = None, write_artifact: bool = False):
    def evaluator(settings, bundle):
        counter["calls"] += 1
        payload = _shadow_payload(results if results is not None else [_record("c1")])
        if write_artifact:
            _write_shadow_artifact(settings, payload)
        return payload

    return evaluator


def _eligibility_fake(*, mode_ok: bool = True, eligible_heads=("needsNews",), reason=None):
    def resolver(
        *,
        mode,
        threshold_cfg,
        approvals_dir,
        provider,
        requested_model,
        evaluator_version,
    ):
        return {
            "mode_ok": mode_ok,
            "reason": reason,
            "eligible_heads": list(eligible_heads),
            "ineligible_heads": {},
        }

    return resolver


def _fake_executor(recorder: dict):
    def executor(*, settings, gate_envelope, mode, eligibility, adapters, now):
        recorder["calls"] += 1
        recorder["mode"] = mode
        recorder["eligibility"] = eligibility
        recorder["gate"] = gate_envelope
        recorder["adapters"] = adapters
        return {
            "schema_version": 1,
            "artifact_type": "season_jev_runtime_overlay",
            "mode": mode,
            "generation_id": gate_envelope["generation_id"],
            "provider": gate_envelope["provider"],
            "requested_model": gate_envelope["requested_model"],
            "evaluator_version": gate_envelope["evaluator_version"],
            "threshold_config_hash": gate_envelope["threshold_config_hash"],
            "candidates": [],
            "side_effects_executed": True,
        }

    return executor


def _fake_verifier(recorder: dict):
    def verifier(*, settings, overlay, now):
        recorder["calls"] += 1
        out = dict(overlay)
        out["verified"] = True
        return out

    return verifier


def _wait_for(predicate, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_disabled_mode_zero_calls_and_writes(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"enabled": False})
    settings = _settings(tmp_path)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow, write_artifact=True),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )

    assert result["status"] == "SKIPPED"
    assert result["reason"] == "MODE_DISABLED"
    assert shadow["calls"] == 0
    assert executor["calls"] == 0
    assert verifier["calls"] == 0
    assert not (tmp_path / "data").exists()


def test_bundle_not_eligible_skips_without_side_effects(tmp_path: Path) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}

    for bundle in (_bundle(lookback=3), {"identity": {"lookback": 5}}):
        result = rt.run_runtime_pass(
            settings, bundle=bundle, shadow_evaluator=_fake_evaluator(shadow)
        )
        assert result["status"] == "SKIPPED"
        assert result["reason"] == "BUNDLE_NOT_ELIGIBLE"

    assert shadow["calls"] == 0
    assert not (tmp_path / "data").exists()


def test_shadow_mode_writes_gate_only_and_preserves_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    results = [
        _record("c1"),
        _record("c2", status="SKIPPED", skip_reason="API_CAP_DAILY", answers={}),
        _record("c3", status="ERROR", error="RUNNER:RuntimeError", answers={}),
        _record("c4", state_hash=""),
        _record("c5", status="REUSED"),
    ]
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow, results=results),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )

    assert result["status"] == "OK"
    assert result["counts"]["gate_candidates"] == 2
    assert result["counts"]["preserved"] == 3
    assert result["counts"]["shadow_calls"] == 1
    assert result["counts"]["gate_writes"] == 1
    assert executor["calls"] == 0
    assert verifier["calls"] == 0
    assert result["overlay"] is None
    assert result["paths"]["overlay"] is None

    envelope = json.loads(Path(result["paths"]["gate"]).read_text(encoding="utf-8"))
    assert [row["candidate_id"] for row in envelope["results"]] == ["c1", "c5"]
    assert envelope["side_effects_executed"] is False


def test_shadow_mode_reuses_existing_shadow_artifact_without_evaluation(
    tmp_path: Path,
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    _write_shadow_artifact(settings, _shadow_payload([_record("c1")]))
    shadow = {"calls": 0}

    result = rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator(shadow)
    )

    assert result["status"] == "OK"
    assert shadow["calls"] == 0
    assert result["resumed"] is True
    assert result["counts"]["gate_writes"] == 1
    assert Path(result["paths"]["gate"]).exists()


def test_shadow_mode_reuses_existing_gate_without_rewrite(tmp_path: Path) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}

    first = rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator(shadow)
    )
    assert first["status"] == "OK"
    gate_path = Path(first["paths"]["gate"])
    first_bytes = gate_path.read_bytes()

    second = rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator(shadow)
    )

    assert second["status"] == "OK"
    assert second["counts"]["gate_writes"] == 0
    assert second["resumed"] is True
    assert gate_path.read_bytes() == first_bytes


def test_canary_chain_reaches_executor_verifier_and_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}
    monkeypatch.setattr(
        rt, "resolve_mode_eligibility", _eligibility_fake(eligible_heads=("needsNews",)), raising=False
    )

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )

    assert result["status"] == "OK"
    assert executor["calls"] == 1
    assert verifier["calls"] == 1
    assert executor["mode"] == "canary"
    assert executor["eligibility"]["eligible_heads"] == ["needsNews"]
    overlay_path = Path(result["paths"]["overlay"])
    assert overlay_path.exists()
    persisted = json.loads(overlay_path.read_text(encoding="utf-8"))
    assert persisted["verified"] is True
    assert result["overlay"]["verified"] is True


def test_production_chain_passes_eligible_true_requirements(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "production", "enabled": True})
    _write_thresholds(tmp_path, news=0.4)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}
    monkeypatch.setattr(
        rt, "resolve_mode_eligibility", _eligibility_fake(eligible_heads=("needsNews",)), raising=False
    )

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )

    assert result["status"] == "OK"
    assert executor["mode"] == "production"
    gate = executor["gate"]
    assert gate["mode"] == "SHADOW_ONLY"
    requirements = gate["results"][0]["gate"]["research_requirements"]
    assert requirements["news"] is True
    assert all(
        requirements[key] is not True
        for key in ("current_year_check", "dart", "deep_ai", "invalidation_check")
    )
    assert executor["eligibility"]["eligible_heads"] == ["needsNews"]


def test_resume_gate_exists_overlay_missing_reaches_executor(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}

    first = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow, write_artifact=True),
    )
    assert first["status"] == "OK"

    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)
    shadow2 = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}

    second = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow2),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )

    assert second["status"] == "OK"
    assert shadow2["calls"] == 0
    assert second["counts"]["gate_writes"] == 0
    assert executor["calls"] == 1
    assert verifier["calls"] == 1
    assert second["resumed"] is True


def test_overlay_reuse_exact_identity_skips_executor(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}

    first = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow, write_artifact=True),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )
    assert first["status"] == "OK"
    assert executor["calls"] == 1

    second_executor = {"calls": 0}
    second_verifier = {"calls": 0}
    second = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=_fake_executor(second_executor),
        verifier=_fake_verifier(second_verifier),
    )

    assert second["status"] == "OK"
    assert second_executor["calls"] == 0
    assert second_verifier["calls"] == 0
    assert second["resumed"] is True
    assert second["overlay"]["verified"] is True


def test_overlay_identity_mismatch_is_not_reused(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}

    first = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator(shadow, write_artifact=True),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )
    assert first["status"] == "OK"
    overlay_path = Path(first["paths"]["overlay"])
    tampered = json.loads(overlay_path.read_text(encoding="utf-8"))
    tampered["threshold_config_hash"] = "0" * 64
    _write_json(overlay_path, tampered)

    second_executor = {"calls": 0}
    second = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=_fake_executor(second_executor),
        verifier=_fake_verifier({"calls": 0}),
    )

    assert second["status"] == "OK"
    assert second_executor["calls"] == 1


def test_verifier_unavailable_skips_without_executor_call(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)
    executor = {"calls": 0}

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=_fake_executor(executor),
    )

    assert result["status"] == "SKIPPED"
    assert result["reason"] == "VERIFIER_UNAVAILABLE"
    assert executor["calls"] == 0


def test_eligibility_incomplete_skips_before_executor(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        rt,
        "resolve_mode_eligibility",
        _eligibility_fake(mode_ok=False, reason="CANARY_ELIGIBILITY_INCOMPLETE"),
        raising=False,
    )
    executor = {"calls": 0}

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=_fake_executor(executor),
        verifier=_fake_verifier({"calls": 0}),
    )

    assert result["status"] == "SKIPPED"
    assert result["reason"] == "CANARY_ELIGIBILITY_INCOMPLETE"
    assert executor["calls"] == 0


def test_unreadable_threshold_config_errors_without_gate_artifact(
    tmp_path: Path,
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)

    result = rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator({"calls": 0})
    )

    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "THRESHOLD_CONFIG_UNREADABLE"
    assert not research_gate_path(settings, GEN, PROVIDER).exists()


def test_orchestrator_step_exception_is_contained(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)

    def boom(**kwargs):
        raise RuntimeError("executor exploded")

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=boom,
        verifier=_fake_verifier({"calls": 0}),
    )

    assert result["status"] == "ERROR"
    assert result["error"]["code"] == "ORCHESTRATOR_ERROR"
    assert "RuntimeError" in result["error"]["message"]


def test_request_runtime_evaluation_single_flight(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    calls = {"count": 0}
    gate_writes = {"count": 0}
    payload = _shadow_payload([_record("c1")])
    release = threading.Event()

    def fake_evaluate_generation(settings_, bundle):
        calls["count"] += 1
        release.wait(timeout=5)
        _write_shadow_artifact(settings_, payload)
        return payload

    real_write = rt.write_research_gate_artifact

    def counting_write(path, gate_payload):
        gate_writes["count"] += 1
        return real_write(path, gate_payload)

    monkeypatch.setattr(season_jev_shadow, "evaluate_generation", fake_evaluate_generation)
    monkeypatch.setattr(rt, "write_research_gate_artifact", counting_write)

    rt.request_runtime_evaluation(settings, _bundle())
    assert _wait_for(lambda: GEN in rt._PENDING_GENERATIONS)
    assert _wait_for(lambda: calls["count"] == 1)

    rt.request_runtime_evaluation(settings, _bundle())  # single-flight: swallowed

    release.set()
    assert _wait_for(lambda: GEN not in rt._PENDING_GENERATIONS)

    assert calls["count"] == 1
    assert gate_writes["count"] == 1
    assert research_gate_path(settings, GEN, PROVIDER).exists()


def test_request_runtime_evaluation_never_raises(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("pass exploded")

    monkeypatch.setattr(rt, "run_runtime_pass", boom)

    rt.request_runtime_evaluation(settings, _bundle())  # must not raise

    assert _wait_for(lambda: GEN not in rt._PENDING_GENERATIONS)
