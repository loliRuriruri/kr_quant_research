# -*- coding: utf-8 -*-
"""P1 Task 1.3 — runtime orchestrator integration contracts (offline fakes).

No network, no live provider calls, no production data-dir writes: every test
uses tmp_path settings and injected fake dependencies.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from kr_quant.research import jev_runtime as rt
from kr_quant.research import season_jev_shadow
from kr_quant.research.jev_research_gate import research_gate_path
from kr_quant.web import season_snapshot as snapshots

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


def _input_hash(
    candidate_id: str,
    state_hash: str,
    requirement_type: str,
    state: object = None,
) -> str:
    payload = {
        "candidate_id": candidate_id,
        "state_hash": state_hash,
        "requirement_type": requirement_type,
        "state": state,
    }
    blob = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _executions_from_gate(gate_envelope: dict) -> list[dict]:
    executions = []
    for row in gate_envelope.get("results") or []:
        gate = row.get("gate") or {}
        for requirement_type, decision in (gate.get("research_requirements") or {}).items():
            if decision is not True:
                continue
            executions.append(
                {
                    "schema_version": 1,
                    "generation_id": gate_envelope["generation_id"],
                    "provider": gate_envelope["provider"],
                    "requested_model": gate_envelope["requested_model"],
                    "evaluator_version": gate_envelope["evaluator_version"],
                    "candidate_id": row["candidate_id"],
                    "state_hash": gate["state_hash"],
                    "requirement_type": requirement_type,
                    "input_hash": _input_hash(row["candidate_id"], gate["state_hash"], requirement_type),
                    "status": "VERIFIED",
                }
            )
    return executions


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
            "executions": _executions_from_gate(gate_envelope),
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


# ---------------------------------------------------------------------------
# Task 1.3 corrective — execution reuse identity (9-tuple + VERIFIED)
# ---------------------------------------------------------------------------


def _canary_run_once(tmp_path: Path, monkeypatch, *, news: float | None = 0.4):
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path, news=news)
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
    return settings, first


def _second_canary_run(settings) -> dict:
    executor = {"calls": 0}
    verifier = {"calls": 0}
    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=_fake_executor(executor),
        verifier=_fake_verifier(verifier),
    )
    result["_executor_calls"] = executor["calls"]
    result["_verifier_calls"] = verifier["calls"]
    return result


def _tamper_overlay(first: dict, mutate) -> None:
    overlay_path = Path(first["paths"]["overlay"])
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    mutate(overlay)
    _write_json(overlay_path, overlay)


def test_overlay_reuse_requires_exact_verified_execution_identity(
    tmp_path: Path, monkeypatch
) -> None:
    settings, first = _canary_run_once(tmp_path, monkeypatch)
    overlay = json.loads(Path(first["paths"]["overlay"]).read_text(encoding="utf-8"))
    assert overlay["executions"]
    assert all(execution["status"] == "VERIFIED" for execution in overlay["executions"])

    second = _second_canary_run(settings)

    assert second["status"] == "OK"
    assert second["_executor_calls"] == 0
    assert second["_verifier_calls"] == 0
    assert second["resumed"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_id", "other-candidate"),
        ("state_hash", "b" * 64),
        ("requirement_type", "dart"),
        ("input_hash", "c" * 64),
    ],
)
def test_overlay_reuse_blocked_by_execution_identity_mismatch(
    tmp_path: Path, monkeypatch, field: str, value: str
) -> None:
    settings, first = _canary_run_once(tmp_path, monkeypatch)
    _tamper_overlay(
        first, lambda overlay: overlay["executions"][0].update({field: value})
    )

    second = _second_canary_run(settings)

    assert second["status"] == "OK"
    assert second["_executor_calls"] == 1
    assert second["_verifier_calls"] == 1


def test_overlay_reuse_blocked_by_non_verified_status(
    tmp_path: Path, monkeypatch
) -> None:
    settings, first = _canary_run_once(tmp_path, monkeypatch)
    _tamper_overlay(
        first, lambda overlay: overlay["executions"][0].update({"status": "FAILED"})
    )

    second = _second_canary_run(settings)

    assert second["_executor_calls"] == 1


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_overlay_reuse_blocked_by_extra_or_missing_execution(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    settings, first = _canary_run_once(tmp_path, monkeypatch)

    def mutate(overlay: dict) -> None:
        if mutation == "extra":
            extra = dict(overlay["executions"][0])
            extra["candidate_id"] = "extra-candidate"
            extra["input_hash"] = "d" * 64
            overlay["executions"].append(extra)
        else:
            overlay["executions"] = overlay["executions"][:-1]

    _tamper_overlay(first, mutate)

    second = _second_canary_run(settings)

    assert second["_executor_calls"] == 1


# ---------------------------------------------------------------------------
# Task 1.3 corrective — gate resume candidate identity
# ---------------------------------------------------------------------------


def _shadow_run_once(tmp_path: Path, results: list):
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    _write_shadow_artifact(settings, _shadow_payload(results))
    first = rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator({"calls": 0})
    )
    assert first["status"] == "OK"
    assert first["counts"]["gate_writes"] == 1
    return settings, first


def _rewrite_shadow(settings, results: list) -> None:
    _write_shadow_artifact(settings, _shadow_payload(results))


def _second_shadow_run(settings) -> dict:
    return rt.run_runtime_pass(
        settings, bundle=_bundle(), shadow_evaluator=_fake_evaluator({"calls": 0})
    )


def test_gate_reuse_requires_exact_candidate_identity_set(tmp_path: Path) -> None:
    settings, first = _shadow_run_once(
        tmp_path, [_record("c1"), _record("c5", status="REUSED")]
    )

    second = _second_shadow_run(settings)

    assert second["status"] == "OK"
    assert second["counts"]["gate_writes"] == 0
    assert second["resumed"] is True


@pytest.mark.parametrize("mutation", ["candidate_id", "state_hash", "extra", "missing"])
def test_gate_reuse_blocked_by_candidate_set_mismatch(
    tmp_path: Path, mutation: str
) -> None:
    settings, first = _shadow_run_once(tmp_path, [_record("c1")])

    if mutation == "candidate_id":
        _rewrite_shadow(settings, [_record("c2")])
    elif mutation == "state_hash":
        _rewrite_shadow(settings, [_record("c1", state_hash="b" * 64)])
    elif mutation == "extra":
        _rewrite_shadow(settings, [_record("c1"), _record("c9")])
    else:
        _rewrite_shadow(settings, [])

    second = _second_shadow_run(settings)

    assert second["counts"]["gate_writes"] == 1


# ---------------------------------------------------------------------------
# Task 1.3 corrective — async wrapper bundle guard
# ---------------------------------------------------------------------------


def test_request_runtime_evaluation_rejects_ineligible_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    settings = _settings(tmp_path)
    calls = {"count": 0}

    def counting_pass(*args, **kwargs):
        calls["count"] += 1

    monkeypatch.setattr(rt, "run_runtime_pass", counting_pass)

    bad_bundles = [
        _bundle(lookback=3),
        {"generation_id": GEN},
        {"identity": {"lookback": 5}},
        {"generation_id": GEN, "identity": {"lookback": "5"}},
        {"generation_id": GEN, "identity": None},
    ]
    for bad in bad_bundles:
        assert rt.request_runtime_evaluation(settings, bad) is None

    assert calls["count"] == 0
    assert not rt._PENDING_GENERATIONS
    assert not (tmp_path / "data").exists()


# ---------------------------------------------------------------------------
# Task 1.3 corrective — locked future executor interface seam
# ---------------------------------------------------------------------------


def test_locked_future_executor_interface_can_be_wired(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "canary", "enabled": True})
    _write_thresholds(tmp_path, news=0.4)
    settings = _settings(tmp_path)
    monkeypatch.setattr(rt, "resolve_mode_eligibility", _eligibility_fake(), raising=False)
    recorded = {}

    def build_execution_plan(*, gate_envelope, mode, research_cfg, eligibility):
        recorded["plan"] = {
            "gate_envelope": gate_envelope,
            "mode": mode,
            "research_cfg": research_cfg,
            "eligibility": eligibility,
        }
        return {"schema_version": 1, "actions": []}

    def run_execution_pass(*, settings, gate_envelope, plan, adapters, now=None):
        recorded["pass"] = {
            "settings": settings,
            "gate_envelope": gate_envelope,
            "plan": plan,
            "adapters": adapters,
            "now": now,
        }
        return {
            "schema_version": 1,
            "artifact_type": "season_jev_runtime_overlay",
            "generation_id": gate_envelope["generation_id"],
            "provider": gate_envelope["provider"],
            "requested_model": gate_envelope["requested_model"],
            "evaluator_version": gate_envelope["evaluator_version"],
            "threshold_config_hash": gate_envelope["threshold_config_hash"],
            "executions": _executions_from_gate(gate_envelope),
        }

    def adapter(*, settings, gate_envelope, mode, eligibility, adapters, now):
        plan = build_execution_plan(
            gate_envelope=gate_envelope,
            mode=mode,
            research_cfg={"mode": mode},
            eligibility=eligibility,
        )
        return run_execution_pass(
            settings=settings,
            gate_envelope=gate_envelope,
            plan=plan,
            adapters=adapters,
            now=now,
        )

    result = rt.run_runtime_pass(
        settings,
        bundle=_bundle(),
        shadow_evaluator=_fake_evaluator({"calls": 0}),
        executor=adapter,
        verifier=_fake_verifier({"calls": 0}),
    )

    assert result["status"] == "OK"
    assert recorded["plan"]["mode"] == "canary"
    assert recorded["pass"]["plan"] == {"schema_version": 1, "actions": []}
    assert Path(result["paths"]["overlay"]).exists()


# ---------------------------------------------------------------------------
# Task 1.3 final corrective — gate resume invariants
# ---------------------------------------------------------------------------


def _tamper_gate(first: dict, mutate) -> None:
    gate_path = Path(first["paths"]["gate"])
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    mutate(gate)
    _write_json(gate_path, gate)


def test_gate_reuse_requires_shadow_only_side_effect_free_invariants(
    tmp_path: Path,
) -> None:
    settings, first = _shadow_run_once(tmp_path, [_record("c1")])
    gate = json.loads(Path(first["paths"]["gate"]).read_text(encoding="utf-8"))
    assert gate["mode"] == "SHADOW_ONLY"
    assert gate["side_effects_executed"] is False

    second = _second_shadow_run(settings)

    assert second["status"] == "OK"
    assert second["counts"]["gate_writes"] == 0
    assert second["resumed"] is True


def test_gate_reuse_blocked_by_tampered_side_effects(tmp_path: Path) -> None:
    settings, first = _shadow_run_once(tmp_path, [_record("c1")])
    _tamper_gate(first, lambda gate: gate.update({"side_effects_executed": True}))

    second = _second_shadow_run(settings)

    assert second["counts"]["gate_writes"] == 1
    replacement = json.loads(Path(second["paths"]["gate"]).read_text(encoding="utf-8"))
    assert replacement["side_effects_executed"] is False
    assert replacement["mode"] == "SHADOW_ONLY"


def test_gate_reuse_blocked_by_invalid_mode(tmp_path: Path) -> None:
    settings, first = _shadow_run_once(tmp_path, [_record("c1")])
    _tamper_gate(first, lambda gate: gate.update({"mode": "ERROR"}))

    second = _second_shadow_run(settings)

    assert second["counts"]["gate_writes"] == 1
    replacement = json.loads(Path(second["paths"]["gate"]).read_text(encoding="utf-8"))
    assert replacement["mode"] == "SHADOW_ONLY"
    assert replacement["side_effects_executed"] is False


# ---------------------------------------------------------------------------
# P1 Task 1.5 — season snapshot hook integration
# ---------------------------------------------------------------------------


def test_hook_disabled_mode_zero_downstream_work(tmp_path: Path, monkeypatch) -> None:
    _write_season_config(tmp_path, {"enabled": False})
    settings = _settings(tmp_path)
    shadow = {"calls": 0}
    monkeypatch.setattr(
        season_jev_shadow,
        "evaluate_generation",
        lambda *a, **k: shadow.__setitem__("calls", shadow["calls"] + 1),
    )

    snapshots._schedule_shadow(settings, _bundle(), 5)

    assert _wait_for(lambda: GEN not in rt._PENDING_GENERATIONS)
    assert shadow["calls"] == 0
    assert not (tmp_path / "data").exists()


def test_hook_shadow_mode_reaches_shadow_and_gate_only(
    tmp_path: Path, monkeypatch
) -> None:
    _write_season_config(tmp_path, {"mode": "shadow", "enabled": True})
    _write_thresholds(tmp_path)
    settings = _settings(tmp_path)
    shadow = {"calls": 0}
    executor = {"calls": 0}
    verifier = {"calls": 0}
    real_pass = rt.run_runtime_pass

    def wrapped(settings_, *, bundle):
        return real_pass(
            settings_,
            bundle=bundle,
            shadow_evaluator=_fake_evaluator(shadow),
            executor=_fake_executor(executor),
            verifier=_fake_verifier(verifier),
        )

    monkeypatch.setattr(rt, "run_runtime_pass", wrapped)
    monkeypatch.setattr(
        season_jev_shadow, "request_shadow_evaluation", lambda *a, **k: None
    )

    snapshots._schedule_shadow(settings, _bundle(), 5)

    assert _wait_for(lambda: GEN not in rt._PENDING_GENERATIONS)
    assert shadow["calls"] == 1
    assert research_gate_path(settings, GEN, PROVIDER).exists()
    assert executor["calls"] == 0
    assert verifier["calls"] == 0
    assert not (tmp_path / "data" / "research_snapshots" / "season_jev_runtime").exists()


def test_hook_duplicate_schedule_is_single_flight(tmp_path: Path, monkeypatch) -> None:
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

    snapshots._schedule_shadow(settings, _bundle(), 5)
    assert _wait_for(lambda: GEN in rt._PENDING_GENERATIONS, timeout=1.0)
    assert _wait_for(lambda: calls["count"] == 1)

    snapshots._schedule_shadow(settings, _bundle(), 5)  # duplicate: single-flight

    release.set()
    assert _wait_for(lambda: GEN not in rt._PENDING_GENERATIONS)

    assert calls["count"] == 1
    assert gate_writes["count"] == 1
    assert research_gate_path(settings, GEN, PROVIDER).exists()
