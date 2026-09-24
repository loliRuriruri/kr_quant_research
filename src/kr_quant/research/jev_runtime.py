# -*- coding: utf-8 -*-
"""JEV runtime mode resolution, shadow gate pass, and orchestrator (P1 Tasks 1.1–1.3).

Pure, fail-closed resolution of the runtime lifecycle mode from the raw
``config/season_jev.json`` payload, the lower-level shadow gate pass that wires
the existing J3 research gate, and the synchronous runtime orchestrator with
its fire-and-forget wrapper.

Scope lock: no provider execution beyond the existing shadow public interface,
no research executor, no evidence verifier, no config writes. P2–P4
functionality stays lazy/injectable until its own authorized tasks land.

Spec: docs/superpowers/specs/2026-09-23-jev-production-routing-design.md §4.3–§4.6
"""
from __future__ import annotations

import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Mapping

from kr_quant.atomic_io import write_json_atomic
from kr_quant.research.jev_research_gate import (
    GATE_ARTIFACT_TYPE,
    ResearchGateError,
    evaluate_research_gate_generation,
    research_gate_path,
    threshold_config_hash,
    write_research_gate_artifact,
)

logger = logging.getLogger("kr_quant.jev_runtime")

RUNTIME_SCHEMA_VERSION = 1
RUNTIME_ARTIFACT_TYPE = "season_jev_runtime_overlay"

MODE_DISABLED = "disabled"
MODE_SHADOW = "shadow"
MODE_CANARY = "canary"
MODE_PRODUCTION = "production"
MODES = (MODE_DISABLED, MODE_SHADOW, MODE_CANARY, MODE_PRODUCTION)

SHADOW_GATE_ELIGIBLE_STATUSES = frozenset({"GENERATED", "REUSED"})
SHADOW_BUDGET_SKIP_REASONS = frozenset(
    {"API_CAP_GENERATION", "API_CAP_DAILY", "API_BUDGET_UNAVAILABLE"}
)
SHADOW_JOIN_KEY_FIELDS = (
    "generation_id",
    "provider",
    "requested_model",
    "evaluator_version",
    "candidate_id",
    "state_hash",
)

# Internal marker used by load_raw_runtime_config to carry a load failure into
# resolve_runtime_mode without raising. Never persisted.
_CONFIG_LOAD_ERROR_KEY = "__config_load_error__"


def _disabled(reason: str | None = None, errors: list[str] | None = None) -> dict[str, Any]:
    return {"mode": MODE_DISABLED, "reason": reason, "errors": list(errors or [])}


def load_raw_runtime_config(settings) -> dict[str, Any]:
    """Read ``config/season_jev.json`` without raising.

    Returns the parsed object on success; on any read/parse failure returns a
    marker mapping that ``resolve_runtime_mode`` turns into a fail-closed
    ``disabled`` result with the error recorded. The file is never written.
    """
    path = Path(settings.root) / "config" / "season_jev.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {_CONFIG_LOAD_ERROR_KEY: f"CONFIG_UNREADABLE:{type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return {_CONFIG_LOAD_ERROR_KEY: f"CONFIG_UNREADABLE:{type(exc).__name__}"}
    if not isinstance(data, dict):
        return {_CONFIG_LOAD_ERROR_KEY: "CONFIG_UNREADABLE:not_an_object"}
    return data


def resolve_runtime_mode(raw_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the runtime mode exactly per spec §4.3.

    Returns ``{"mode": str, "reason": str | None, "errors": list[str]}``.

    Hard rules:
    - Any conflict or invalid value resolves to ``disabled`` (fail closed).
    - Legacy configuration (no ``mode`` key) can only ever resolve to
      ``shadow`` or ``disabled`` — never ``canary`` / ``production``.
    - Pure: the input mapping is never mutated; nothing is written.
    """
    if not isinstance(raw_cfg, Mapping):
        return _disabled("CONFIG_MODE_INVALID", ["config must be a mapping"])

    load_error = raw_cfg.get(_CONFIG_LOAD_ERROR_KEY)
    if load_error:
        return _disabled(None, [str(load_error)])

    mode_present = "mode" in raw_cfg
    enabled_present = "enabled" in raw_cfg

    if mode_present:
        mode = raw_cfg.get("mode")
        if not isinstance(mode, str) or mode not in MODES:
            return _disabled("CONFIG_MODE_INVALID", [f"invalid mode: {mode!r}"])
        if enabled_present:
            enabled = raw_cfg.get("enabled")
            if not isinstance(enabled, bool):
                return _disabled("CONFIG_MODE_INVALID", ["enabled must be a boolean"])
            if enabled != (mode != MODE_DISABLED):
                return _disabled(
                    "CONFIG_MODE_CONFLICT",
                    [f"mode={mode!r} conflicts with enabled={enabled!r}"],
                )
        return {"mode": mode, "reason": None, "errors": []}

    # Legacy configuration (no mode key): shadow/disabled only.
    if enabled_present and raw_cfg.get("enabled") is True:
        return {"mode": MODE_SHADOW, "reason": "LEGACY_ENABLED_TRUE", "errors": []}
    return _disabled()


def _gate_error_code(message: str) -> str:
    """Deterministic code from a J3 ResearchGateError message (no secrets)."""
    head = str(message).split(":", 1)[0].strip()
    if head and " " not in head and head.replace("_", "").isalnum() and head.isupper():
        return head
    return "GATE_ERROR"


def run_shadow_gate_pass(
    settings,
    *,
    shadow_payload: Mapping[str, Any],
    threshold_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate the J3 research gate for one gate-eligible shadow payload and
    persist the generation envelope atomically.

    Returns ``{"status": "SKIPPED", "reason": "MODE_DISABLED"}`` when the
    resolved runtime mode is ``disabled`` (no gate evaluation, no write),
    ``{"status": "OK", "gate": <envelope>, "path": <str>}`` on success, or
    ``{"status": "ERROR", "error": {"code": ..., "message": ...}}`` when J3
    rejects the envelope/threshold config (nothing is persisted).

    Expected J3 validation failures never escape. Inputs are never mutated.
    J3 remains the sole authority for gate contents, identity and hashes.
    """
    resolution = resolve_runtime_mode(load_raw_runtime_config(settings))
    if resolution["mode"] == MODE_DISABLED:
        return {"status": "SKIPPED", "reason": "MODE_DISABLED"}

    try:
        gate = evaluate_research_gate_generation(shadow_payload, threshold_cfg=threshold_cfg)
    except ResearchGateError as exc:
        return {
            "status": "ERROR",
            "error": {"code": _gate_error_code(str(exc)), "message": str(exc)},
        }

    path = research_gate_path(settings, gate["generation_id"], gate["provider"])
    write_research_gate_artifact(path, gate)
    return {"status": "OK", "gate": gate, "path": str(path)}


# ---------------------------------------------------------------------------
# Task 1.3 — runtime orchestrator entrypoint
# ---------------------------------------------------------------------------

_PENDING_GENERATIONS: set[str] = set()
_PENDING_LOCK = threading.Lock()


def _has_state_hash(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    value = record.get("state_hash")
    return isinstance(value, str) and bool(value.strip())


def partition_shadow_records(shadow_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Split shadow records into gate candidates and preserved provenance.

    Only ``GENERATED`` / ``REUSED`` records with a non-empty ``state_hash`` may
    enter ``gate_candidates``. ``SKIPPED`` / ``ERROR`` records and records with
    a missing/empty ``state_hash`` go to ``preserved`` unchanged (original
    ``status`` / ``skip_reason`` / ``error`` / ``answers`` / identity fields).
    Source records are never mutated.
    """
    if not isinstance(shadow_payload, Mapping):
        raise ValueError("shadow_payload must be a mapping")
    results = shadow_payload.get("results")
    if not isinstance(results, list):
        raise ValueError("shadow_payload.results must be a list")

    gate_candidates: list[Any] = []
    preserved: list[Any] = []
    for record in results:
        if (
            isinstance(record, Mapping)
            and record.get("status") in SHADOW_GATE_ELIGIBLE_STATUSES
            and _has_state_hash(record)
        ):
            gate_candidates.append(record)
        else:
            preserved.append(record)
    return {"gate_candidates": gate_candidates, "preserved": preserved}


def map_shadow_record_status(record: Any) -> dict[str, Any]:
    """Deterministic runtime status mapping for one shadow record.

    Upstream shadow provenance wins: a budget-skipped record with ``answers={}``
    stays ``SKIPPED_BUDGET`` and is never converted into ``MISSING_ANSWERS`` /
    ``MISSING_HEAD`` / a generic gate error.
    """
    if not isinstance(record, Mapping):
        return {"runtime_status": "FAILED", "reason": "SHADOW_ERROR"}
    if not _has_state_hash(record):
        return {"runtime_status": "FAILED", "reason": "STATE_HASH_MISSING"}
    status = record.get("status")
    if status in SHADOW_GATE_ELIGIBLE_STATUSES:
        return {"runtime_status": "GATE_CANDIDATE", "reason": None}
    if status == "SKIPPED":
        reason = record.get("skip_reason")
        if reason in SHADOW_BUDGET_SKIP_REASONS:
            return {"runtime_status": "SKIPPED_BUDGET", "reason": reason}
        return {"runtime_status": "SKIPPED_UNCALIBRATED", "reason": reason}
    if status == "ERROR":
        return {"runtime_status": "FAILED", "reason": record.get("error") or "SHADOW_ERROR"}
    return {"runtime_status": "FAILED", "reason": "SHADOW_ERROR"}


def _safe_component(value: Any) -> str:
    """Sanitize one path component (same convention as J3's provider sanitizer)."""
    text = str(value)
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in text)
    if not safe or set(safe) <= {"."}:
        raise ValueError("unsafe path component")
    return safe


def _runtime_overlay_dir(settings) -> Path:
    return Path(settings.data_dir) / "research_snapshots" / "season_jev_runtime"


def runtime_overlay_path(settings, generation_id: str, provider: str) -> Path:
    return (
        _runtime_overlay_dir(settings)
        / f"{_safe_component(generation_id)}__{_safe_component(provider)}__runtime.json"
    )


def write_runtime_overlay(path: Path, payload: Mapping[str, Any]) -> None:
    write_json_atomic(Path(path), dict(payload), encoding="utf-8", compact=True)


def _lazy_callable(module_name: str, attribute: str):
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    candidate = getattr(module, attribute, None)
    return candidate if callable(candidate) else None


def _valid_shadow_payload(payload: Any, generation_id: str) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("generation_id") != generation_id:
        return False
    for field in ("provider", "requested_model", "evaluator_version"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return isinstance(payload.get("results"), list)


def _identity_matches(
    cached: Any,
    generation_id: str,
    payload: Mapping[str, Any],
    current_hash: str,
) -> bool:
    if not isinstance(cached, Mapping):
        return False
    if cached.get("generation_id") != generation_id:
        return False
    for field in ("provider", "requested_model", "evaluator_version"):
        if cached.get(field) != payload.get(field):
            return False
    return cached.get("threshold_config_hash") == current_hash


def _gate_identity_matches(
    cached: Any,
    generation_id: str,
    payload: Mapping[str, Any],
    current_hash: str,
) -> bool:
    if not isinstance(cached, Mapping) or cached.get("artifact_type") != GATE_ARTIFACT_TYPE:
        return False
    return _identity_matches(cached, generation_id, payload, current_hash)


def _overlay_identity_matches(
    cached: Any,
    generation_id: str,
    payload: Mapping[str, Any],
    current_hash: str,
) -> bool:
    if not isinstance(cached, Mapping) or cached.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        return False
    return _identity_matches(cached, generation_id, payload, current_hash)


def run_runtime_pass(
    settings,
    *,
    bundle: Mapping[str, Any],
    threshold_cfg: Mapping[str, Any] | None = None,
    shadow_evaluator=None,
    adapters=None,
    executor=None,
    verifier=None,
    now=None,
) -> dict[str, Any]:
    """Synchronous runtime orchestration core.

    Mode chain (spec §4.5):

    - ``disabled`` → ``SKIPPED`` / ``MODE_DISABLED``; zero calls and writes.
    - ``shadow``   → shadow → gate → STOP (no executor/verifier/overlay).
    - ``canary`` / ``production`` → shadow → gate → eligibility → executor →
      verifier → overlay, with P2–P4 dependencies lazy/injectable.

    Resume semantics (spec §4.6): existing shadow artifact resumes the shadow
    step, an identity-matching gate artifact resumes the gate step, and an
    identity-matching overlay resumes the executor/verifier step. Exceptions
    from any step are contained into an ``ERROR`` result.
    """
    resolution = resolve_runtime_mode(load_raw_runtime_config(settings))
    mode = resolution["mode"]
    generation_id = (
        str(bundle.get("generation_id") or "") if isinstance(bundle, Mapping) else ""
    )
    counts = {
        "gate_candidates": 0,
        "preserved": 0,
        "shadow_calls": 0,
        "gate_writes": 0,
        "executor_calls": 0,
        "verifier_calls": 0,
    }
    base: dict[str, Any] = {
        "mode": mode,
        "generation_id": generation_id or None,
        "reason": None,
        "error": None,
        "shadow": None,
        "gate": None,
        "overlay": None,
        "paths": {"shadow": None, "gate": None, "overlay": None},
        "resumed": False,
        "counts": counts,
    }

    if mode == MODE_DISABLED:
        return {**base, "status": "SKIPPED", "reason": "MODE_DISABLED"}

    try:
        if not isinstance(bundle, Mapping) or not generation_id:
            return {**base, "status": "SKIPPED", "reason": "BUNDLE_NOT_ELIGIBLE"}
        bundle_identity = bundle.get("identity")
        if not isinstance(bundle_identity, Mapping) or bundle_identity.get("lookback") != 5:
            return {**base, "status": "SKIPPED", "reason": "BUNDLE_NOT_ELIGIBLE"}

        from kr_quant.research import season_jev_shadow

        try:
            shadow_cfg = season_jev_shadow.load_config(settings)
            provider = season_jev_shadow.provider_name(shadow_cfg)
        except ValueError as exc:
            return {
                **base,
                "status": "ERROR",
                "error": {"code": "UNSUPPORTED_PROVIDER", "message": str(exc)[:200]},
            }

        shadow_file = season_jev_shadow.shadow_path(settings, generation_id, provider)
        base["paths"]["shadow"] = str(shadow_file)
        payload = None
        if season_jev_shadow.has_shadow(settings, generation_id, shadow_cfg):
            try:
                cached_shadow = json.loads(shadow_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached_shadow = None
            if isinstance(cached_shadow, Mapping):
                payload = cached_shadow
                base["resumed"] = True
        if payload is None:
            evaluator = (
                shadow_evaluator
                if shadow_evaluator is not None
                else season_jev_shadow.evaluate_generation
            )
            counts["shadow_calls"] = 1
            payload = evaluator(settings, bundle)
            if payload is None:
                return {**base, "status": "SKIPPED", "reason": "SHADOW_NOT_AVAILABLE"}
        if not _valid_shadow_payload(payload, generation_id):
            return {
                **base,
                "status": "ERROR",
                "error": {
                    "code": "INVALID_SHADOW_PAYLOAD",
                    "message": "shadow payload identity/results invalid",
                },
            }
        base["shadow"] = {"status": payload.get("status"), "resumed": base["resumed"]}

        parts = partition_shadow_records(payload)
        counts["gate_candidates"] = len(parts["gate_candidates"])
        counts["preserved"] = len(parts["preserved"])

        cfg = threshold_cfg
        if cfg is None:
            from kr_quant.research.jev_calibration import CalibrationError, load_thresholds

            try:
                cfg = load_thresholds(Path(settings.root) / "config" / "jev_thresholds.json")
            except (OSError, ValueError, TypeError, CalibrationError) as exc:
                return {
                    **base,
                    "status": "ERROR",
                    "error": {
                        "code": "THRESHOLD_CONFIG_UNREADABLE",
                        "message": type(exc).__name__,
                    },
                }

        try:
            current_hash = threshold_config_hash(
                cfg,
                provider=payload["provider"],
                requested_model=payload["requested_model"],
                evaluator_version=payload["evaluator_version"],
            )
        except ResearchGateError as exc:
            return {
                **base,
                "status": "ERROR",
                "error": {"code": _gate_error_code(str(exc)), "message": str(exc)[:200]},
            }

        gate_file = research_gate_path(settings, generation_id, payload["provider"])
        base["paths"]["gate"] = str(gate_file)
        gate = None
        if gate_file.exists():
            try:
                cached_gate = json.loads(gate_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached_gate = None
            if _gate_identity_matches(cached_gate, generation_id, payload, current_hash):
                gate = dict(cached_gate)
                base["resumed"] = True
        if gate is None:
            gate_payload = {
                "generation_id": generation_id,
                "provider": payload["provider"],
                "requested_model": payload["requested_model"],
                "evaluator_version": payload["evaluator_version"],
                "results": parts["gate_candidates"],
            }
            gate_result = run_shadow_gate_pass(
                settings, shadow_payload=gate_payload, threshold_cfg=cfg
            )
            if gate_result.get("status") == "ERROR":
                return {**base, "status": "ERROR", "error": gate_result["error"]}
            if gate_result.get("status") != "OK":
                return {
                    **base,
                    "status": "SKIPPED",
                    "reason": gate_result.get("reason") or "GATE_SKIPPED",
                }
            gate = gate_result["gate"]
            counts["gate_writes"] = 1
        base["gate"] = gate

        if mode == MODE_SHADOW:
            return {**base, "status": "OK"}

        # canary / production seams (P2–P4 modules stay lazy/injectable)
        eligibility_resolver = globals().get("resolve_mode_eligibility")
        if eligibility_resolver is None:
            return {**base, "status": "SKIPPED", "reason": "ELIGIBILITY_UNAVAILABLE"}
        eligibility = eligibility_resolver(
            mode=mode,
            threshold_cfg=cfg,
            approvals_dir=Path(settings.data_dir) / "research" / "jev_calibration" / "approvals",
            provider=payload["provider"],
            requested_model=payload["requested_model"],
            evaluator_version=payload["evaluator_version"],
        )
        if not isinstance(eligibility, Mapping) or not eligibility.get("mode_ok"):
            reason = eligibility.get("reason") if isinstance(eligibility, Mapping) else None
            return {
                **base,
                "status": "SKIPPED",
                "reason": reason
                or (
                    "CANARY_ELIGIBILITY_INCOMPLETE"
                    if mode == MODE_CANARY
                    else "PRODUCTION_ELIGIBILITY_INCOMPLETE"
                ),
            }

        overlay_file = runtime_overlay_path(settings, generation_id, payload["provider"])
        base["paths"]["overlay"] = str(overlay_file)
        overlay = None
        if overlay_file.exists():
            try:
                cached_overlay = json.loads(overlay_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached_overlay = None
            if _overlay_identity_matches(cached_overlay, generation_id, payload, current_hash):
                overlay = dict(cached_overlay)
                base["resumed"] = True
        if overlay is None:
            if executor is None:
                executor = _lazy_callable(
                    "kr_quant.research.jev_research_executor", "run_execution_pass"
                )
            if executor is None:
                return {**base, "status": "SKIPPED", "reason": "EXECUTOR_UNAVAILABLE"}
            if verifier is None:
                return {**base, "status": "SKIPPED", "reason": "VERIFIER_UNAVAILABLE"}
            counts["executor_calls"] = 1
            overlay = executor(
                settings=settings,
                gate_envelope=gate,
                mode=mode,
                eligibility=eligibility,
                adapters=adapters,
                now=now,
            )
            if not isinstance(overlay, Mapping):
                return {
                    **base,
                    "status": "ERROR",
                    "error": {"code": "INVALID_OVERLAY", "message": "executor must return a mapping"},
                }
            counts["verifier_calls"] = 1
            overlay = verifier(settings=settings, overlay=overlay, now=now)
            if not isinstance(overlay, Mapping):
                return {
                    **base,
                    "status": "ERROR",
                    "error": {"code": "INVALID_OVERLAY", "message": "verifier must return a mapping"},
                }
            persisted = dict(overlay)
            for key, value in (
                ("schema_version", RUNTIME_SCHEMA_VERSION),
                ("artifact_type", RUNTIME_ARTIFACT_TYPE),
                ("generation_id", generation_id),
                ("provider", payload["provider"]),
                ("requested_model", payload["requested_model"]),
                ("evaluator_version", payload["evaluator_version"]),
                ("threshold_config_hash", current_hash),
            ):
                persisted.setdefault(key, value)
            write_runtime_overlay(overlay_file, persisted)
            overlay = persisted
        base["overlay"] = overlay
        return {**base, "status": "OK"}
    except Exception as exc:  # contained: runtime failures never propagate
        return {
            **base,
            "status": "ERROR",
            "error": {
                "code": "ORCHESTRATOR_ERROR",
                "message": f"{type(exc).__name__}: {str(exc)[:200]}",
            },
        }


def request_runtime_evaluation(settings, bundle: Mapping[str, Any]) -> None:
    """Fire-and-forget wrapper around :func:`run_runtime_pass`.

    Returns immediately, uses one daemon worker thread, provides in-process
    single-flight per generation, and never raises to the caller.
    """
    try:
        if not isinstance(bundle, Mapping):
            return
        generation_id = str(bundle.get("generation_id") or "")
        if not generation_id:
            return
        with _PENDING_LOCK:
            if generation_id in _PENDING_GENERATIONS:
                return
            _PENDING_GENERATIONS.add(generation_id)

        def work() -> None:
            try:
                run_runtime_pass(settings, bundle=bundle)
            except Exception:
                logger.exception("JEV runtime pass failed; season snapshot unchanged")
            finally:
                with _PENDING_LOCK:
                    _PENDING_GENERATIONS.discard(generation_id)

        threading.Thread(
            target=work, name=f"jev-runtime-{generation_id[:8]}", daemon=True
        ).start()
    except Exception:
        logger.exception("JEV runtime request failed; ignored")
