# -*- coding: utf-8 -*-
"""JEV runtime mode resolution, shadow gate pass, orchestrator, and status (P1 Tasks 1.1–1.4).

Pure, fail-closed resolution of the runtime lifecycle mode from the raw
``config/season_jev.json`` payload, the lower-level shadow gate pass that wires
the existing J3 research gate, the synchronous runtime orchestrator with its
fire-and-forget wrapper, and a read-only runtime status snapshot.

Scope lock: no provider execution beyond the existing shadow public interface,
no research executor, no evidence verifier, no config writes. The future P3
executor (``build_execution_plan`` → ``run_execution_pass``) is fail-closed
until its own authorized task lands; the canary/production executor is an
explicit injectable Task-1.3 seam, and the overlay resume identity is the
locked 9-tuple + ``VERIFIED`` execution status contract.

Spec: docs/superpowers/specs/2026-09-23-jev-production-routing-design.md §4.3–§4.6, §12
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Mapping

from kr_quant.atomic_io import write_json_atomic
from kr_quant.research.jev_research_gate import (
    GATE_ARTIFACT_TYPE,
    MODE_SHADOW_ONLY,
    ResearchGateError,
    evaluate_research_gate_generation,
    research_gate_dir,
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

EXECUTION_IDENTITY_FIELDS = (
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


def execution_reuse_key(execution: Any) -> tuple | None:
    """Locked execution reuse key: the exact 9-tuple, or None when incomplete.

    Fields: schema_version, generation_id, provider, requested_model,
    evaluator_version, candidate_id, state_hash, requirement_type, input_hash.
    """
    if not isinstance(execution, Mapping):
        return None
    values: list[Any] = []
    for field in EXECUTION_IDENTITY_FIELDS:
        value = execution.get(field)
        if field == "schema_version":
            if isinstance(value, bool) or not isinstance(value, int):
                return None
        elif not isinstance(value, str) or not value.strip():
            return None
        values.append(value)
    return tuple(values)


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _execution_input_hash(
    candidate_id: str,
    state_hash: str,
    requirement_type: str,
    state: Any,
) -> str:
    """SHA-256 of canonical JSON {candidate_id, state_hash, requirement_type, state}."""
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "candidate_id": candidate_id,
                "state_hash": state_hash,
                "requirement_type": requirement_type,
                "state": state,
            }
        )
    ).hexdigest()


def _expected_execution_keys(
    gate_envelope: Mapping[str, Any],
    shadow_payload: Mapping[str, Any],
) -> set[tuple]:
    """Expected execution identities for the gate's true requirements."""
    states: dict[str, Any] = {}
    for record in shadow_payload.get("results") or []:
        if isinstance(record, Mapping):
            candidate_id = record.get("candidate_id")
            if isinstance(candidate_id, str) and candidate_id:
                states[candidate_id] = record.get("state")

    keys: set[tuple] = set()
    generation_id = gate_envelope.get("generation_id")
    provider = gate_envelope.get("provider")
    requested_model = gate_envelope.get("requested_model")
    evaluator_version = gate_envelope.get("evaluator_version")
    for row in gate_envelope.get("results") or []:
        if not isinstance(row, Mapping):
            continue
        gate = row.get("gate")
        if not isinstance(gate, Mapping) or gate.get("mode") != "SHADOW_ONLY":
            continue
        candidate_id = row.get("candidate_id")
        state_hash = gate.get("state_hash")
        if not isinstance(candidate_id, str) or not candidate_id:
            continue
        if not isinstance(state_hash, str) or not state_hash:
            continue
        requirements = gate.get("research_requirements")
        if not isinstance(requirements, Mapping):
            continue
        for requirement_type, decision in requirements.items():
            if decision is not True:
                continue
            keys.add(
                (
                    RUNTIME_SCHEMA_VERSION,
                    generation_id,
                    provider,
                    requested_model,
                    evaluator_version,
                    candidate_id,
                    state_hash,
                    requirement_type,
                    _execution_input_hash(
                        candidate_id,
                        state_hash,
                        str(requirement_type),
                        states.get(candidate_id),
                    ),
                )
            )
    return keys


def _candidate_identity_set(records: Any) -> set[tuple]:
    out: set[tuple] = set()
    for record in records or []:
        if not isinstance(record, Mapping):
            continue
        candidate_id = record.get("candidate_id")
        state_hash = record.get("state_hash")
        if isinstance(candidate_id, str) and isinstance(state_hash, str):
            out.add((candidate_id, state_hash))
    return out


def _gate_candidate_identity_set(gate_envelope: Any) -> set[tuple] | None:
    if not isinstance(gate_envelope, Mapping):
        return None
    results = gate_envelope.get("results")
    if not isinstance(results, list):
        return None
    out: set[tuple] = set()
    for row in results:
        if not isinstance(row, Mapping):
            return None
        gate = row.get("gate")
        candidate_id = row.get("candidate_id")
        state_hash = gate.get("state_hash") if isinstance(gate, Mapping) else None
        if not isinstance(candidate_id, str) or not candidate_id:
            return None
        if not isinstance(state_hash, str) or not state_hash:
            return None
        out.add((candidate_id, state_hash))
    return out


def _overlay_reusable(
    overlay: Any,
    *,
    generation_id: str,
    payload: Mapping[str, Any],
    current_hash: str,
    expected_keys: set[tuple],
) -> bool:
    """Overlay reuse requires generation identity AND exact VERIFIED executions.

    Every persisted execution must carry the locked 9-tuple identity, must be
    ``VERIFIED``, and must match the gate's current expected execution key set
    exactly (no extras, no missing).
    """
    if not isinstance(overlay, Mapping) or overlay.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        return False
    if not _identity_matches(overlay, generation_id, payload, current_hash):
        return False
    executions = overlay.get("executions")
    if not isinstance(executions, list):
        return False
    verified: set[tuple] = set()
    for execution in executions:
        key = execution_reuse_key(execution)
        if key is None:
            return False
        if execution.get("status") != "VERIFIED":
            return False
        if key not in expected_keys:
            return False
        verified.add(key)
    return verified == set(expected_keys)


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
    candidate_set: set[tuple],
) -> bool:
    if not isinstance(cached, Mapping) or cached.get("artifact_type") != GATE_ARTIFACT_TYPE:
        return False
    if cached.get("mode") != MODE_SHADOW_ONLY:
        return False
    if cached.get("side_effects_executed") is not False:
        return False
    if not _identity_matches(cached, generation_id, payload, current_hash):
        return False
    cached_set = _gate_candidate_identity_set(cached)
    return cached_set is not None and cached_set == candidate_set


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
        candidate_set = _candidate_identity_set(parts["gate_candidates"])

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
            if _gate_identity_matches(
                cached_gate, generation_id, payload, current_hash, candidate_set
            ):
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

        expected_keys = _expected_execution_keys(gate, payload)

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
            if _overlay_reusable(
                cached_overlay,
                generation_id=generation_id,
                payload=payload,
                current_hash=current_hash,
                expected_keys=expected_keys,
            ):
                overlay = dict(cached_overlay)
                base["resumed"] = True
        if overlay is None:
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

    Bundle guard (pre-thread): the bundle must be a mapping with a non-empty
    ``generation_id`` and ``identity.lookback == 5``; otherwise it returns
    ``None`` without registering the pending set, spawning a thread, calling
    ``run_runtime_pass``, or writing anything.
    """
    try:
        if not isinstance(bundle, Mapping):
            return
        generation_id = str(bundle.get("generation_id") or "")
        if not generation_id:
            return
        identity = bundle.get("identity")
        if not isinstance(identity, Mapping) or identity.get("lookback") != 5:
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


# ---------------------------------------------------------------------------
# Task 1.4 — read-only runtime status snapshot
# ---------------------------------------------------------------------------

_EMPTY_SHADOW_STATUS: dict[str, Any] = {
    "present": False,
    "error": None,
    "generation_id": None,
    "provider": None,
    "requested_model": None,
    "evaluator_version": None,
    "status": None,
    "path": None,
    "counts": {"GENERATED": 0, "REUSED": 0, "SKIPPED": 0, "ERROR": 0, "unknown": 0},
    "total": 0,
}

_EMPTY_GATE_STATUS: dict[str, Any] = {
    "present": False,
    "readable": None,
    "error": None,
    "generation_id": None,
    "provider": None,
    "requested_model": None,
    "evaluator_version": None,
    "threshold_config_hash": None,
    "mode": None,
    "side_effects_executed": None,
    "candidate_count": 0,
    "calibrated_heads": [],
    "uncalibrated_heads": [],
    "calibrated_head_count": 0,
    "uncalibrated_head_count": 0,
    "path": None,
}


def _empty_shadow_status() -> dict[str, Any]:
    return {**_EMPTY_SHADOW_STATUS, "counts": dict(_EMPTY_SHADOW_STATUS["counts"])}


def _empty_gate_status() -> dict[str, Any]:
    return {
        **_EMPTY_GATE_STATUS,
        "calibrated_heads": [],
        "uncalibrated_heads": [],
    }


def _shadow_status(settings) -> dict[str, Any]:
    """Read-only summary of the latest usable shadow artifact."""
    from kr_quant.research import season_jev_shadow

    status = _empty_shadow_status()
    try:
        folder = season_jev_shadow.shadow_dir(settings)
        if not folder.is_dir():
            return status
        best = None
        for path in sorted(folder.glob("*.json")):
            if path.name.startswith("_") or path.name.startswith("."):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, Mapping):
                continue
            generation_id = payload.get("generation_id")
            if not isinstance(generation_id, str) or not generation_id:
                continue
            finished_at = payload.get("finished_at")
            key = (
                str(finished_at) if isinstance(finished_at, str) else "",
                generation_id,
                path.name,
            )
            if best is None or key > best[0]:
                best = (key, payload, path)
    except OSError as exc:
        return {**status, "error": type(exc).__name__}
    if best is None:
        return status

    _, payload, path = best
    counts = {"GENERATED": 0, "REUSED": 0, "SKIPPED": 0, "ERROR": 0, "unknown": 0}
    results = payload.get("results")
    total = 0
    if isinstance(results, list):
        total = len(results)
        for record in results:
            record_status = record.get("status") if isinstance(record, Mapping) else None
            if (
                isinstance(record_status, str)
                and record_status in counts
                and record_status != "unknown"
            ):
                counts[record_status] += 1
            else:
                counts["unknown"] += 1
    return {
        "present": True,
        "error": None,
        "generation_id": payload.get("generation_id"),
        "provider": payload.get("provider"),
        "requested_model": payload.get("requested_model"),
        "evaluator_version": payload.get("evaluator_version"),
        "status": payload.get("status"),
        "path": str(path),
        "counts": counts,
        "total": total,
    }


def _gate_status(settings, shadow_status: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only summary of the gate artifact matching the latest shadow."""
    status = _empty_gate_status()
    try:
        path = None
        generation_id = shadow_status.get("generation_id")
        provider = shadow_status.get("provider")
        if (
            shadow_status.get("present") is True
            and isinstance(generation_id, str)
            and generation_id
            and isinstance(provider, str)
            and provider
        ):
            candidate = research_gate_path(settings, generation_id, provider)
            if candidate.is_file():
                path = candidate
        if path is None:
            folder = research_gate_dir(settings)
            if folder.is_dir():
                candidates = sorted(
                    p
                    for p in folder.glob("*__gate.json")
                    if p.is_file() and not p.name.startswith(("_", "."))
                )
                if candidates:
                    path = candidates[-1]
    except OSError as exc:
        return {**status, "error": type(exc).__name__}
    if path is None:
        return status

    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gate = None
    if not isinstance(gate, Mapping):
        return {**status, "present": True, "readable": False, "path": str(path)}

    calibrated: set[str] = set()
    uncalibrated: set[str] = set()
    results = gate.get("results")
    candidate_count = len(results) if isinstance(results, list) else 0
    if isinstance(results, list):
        for row in results:
            if not isinstance(row, Mapping):
                continue
            gate_obj = row.get("gate")
            if not isinstance(gate_obj, Mapping) or gate_obj.get("mode") != MODE_SHADOW_ONLY:
                continue
            heads = gate_obj.get("calibrated_heads")
            if isinstance(heads, list):
                for head in heads:
                    if isinstance(head, str) and head:
                        calibrated.add(head)
            heads = gate_obj.get("uncalibrated_heads")
            if isinstance(heads, list):
                for head in heads:
                    if isinstance(head, str) and head:
                        uncalibrated.add(head)
    return {
        "present": True,
        "readable": True,
        "error": None,
        "generation_id": gate.get("generation_id"),
        "provider": gate.get("provider"),
        "requested_model": gate.get("requested_model"),
        "evaluator_version": gate.get("evaluator_version"),
        "threshold_config_hash": gate.get("threshold_config_hash"),
        "mode": gate.get("mode"),
        "side_effects_executed": gate.get("side_effects_executed"),
        "candidate_count": candidate_count,
        "calibrated_heads": sorted(calibrated),
        "uncalibrated_heads": sorted(uncalibrated),
        "calibrated_head_count": len(calibrated),
        "uncalibrated_head_count": len(uncalibrated),
        "path": str(path),
    }


def _threshold_status(settings, identity, threshold_cfg) -> dict[str, Any]:
    cfg = threshold_cfg
    if cfg is None:
        from kr_quant.research.jev_calibration import CalibrationError, load_thresholds

        path = Path(settings.root) / "config" / "jev_thresholds.json"
        if not path.is_file():
            return {"status": "MISSING", "error": None, "current_threshold_config_hash": None}
        try:
            cfg = load_thresholds(path)
        except (OSError, ValueError, TypeError, CalibrationError) as exc:
            return {
                "status": "UNREADABLE",
                "error": type(exc).__name__,
                "current_threshold_config_hash": None,
            }

    current_hash = None
    if identity is not None:
        try:
            current_hash = threshold_config_hash(
                cfg,
                provider=identity[0],
                requested_model=identity[1],
                evaluator_version=identity[2],
            )
        except ResearchGateError as exc:
            return {
                "status": "LOADED",
                "error": _gate_error_code(str(exc)),
                "current_threshold_config_hash": None,
            }
    return {"status": "LOADED", "error": None, "current_threshold_config_hash": current_hash}


def runtime_status(
    settings,
    *,
    threshold_cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only snapshot of the current JEV runtime state.

    Never activates, schedules, evaluates, or writes anything: it only reads
    the raw runtime config, existing shadow/gate artifacts, and (optionally)
    the calibration threshold config. Missing directories and malformed
    artifacts fail closed into zero/absent status fields.
    """
    raw = load_raw_runtime_config(settings)
    resolution = resolve_runtime_mode(raw)
    shadow = _shadow_status(settings)
    gate = _gate_status(settings, shadow)

    identity = None
    for source in (gate, shadow):
        provider = source.get("provider")
        requested_model = source.get("requested_model")
        evaluator_version = source.get("evaluator_version")
        if (
            isinstance(provider, str)
            and provider
            and isinstance(requested_model, str)
            and requested_model
            and isinstance(evaluator_version, str)
            and evaluator_version
        ):
            identity = (provider, requested_model, evaluator_version)
            break

    raw_provider = raw.get("provider")
    raw_model = raw.get("model")
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "mode": resolution["mode"],
        "mode_reason": resolution["reason"],
        "mode_errors": list(resolution["errors"]),
        "provider": (raw_provider if isinstance(raw_provider, str) else None)
        or "typesafe_direct",
        "requested_model": (raw_model if isinstance(raw_model, str) else None)
        or "jev-latest",
        "shadow": shadow,
        "gate": gate,
        "thresholds": _threshold_status(settings, identity, threshold_cfg),
    }
