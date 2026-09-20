# -*- coding: utf-8 -*-
"""J3 Research Gate Shadow — Task 1 threshold identity foundation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from kr_quant.atomic_io import write_json_atomic

from kr_quant.research.jev_calibration import (
    BOOLEAN_HEADS,
    STATUS_SHADOW_ONLY,
    STATUS_UNCALIBRATED,
    CalibrationError,
    load_thresholds,
    lookup_threshold,
)

GATE_SCHEMA_VERSION = 1
GATE_ARTIFACT_TYPE = "season_jev_research_gate"

MODE_SHADOW_ONLY = "SHADOW_ONLY"
MODE_ERROR = "ERROR"

BUCKET_MATCHED = "MATCHED"
BUCKET_MISSING = "MISSING"


class ResearchGateError(ValueError):
    """Envelope-level / operation-level J3 failure."""


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_numeric_threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchGateError(f"INVALID_THRESHOLD: threshold must be a finite number in [0, 1], got {value!r}")
    f = float(value)
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        raise ResearchGateError(f"INVALID_THRESHOLD: threshold must be a finite number in [0, 1], got {value!r}")
    return f


def _require_non_empty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ResearchGateError(f"THRESHOLD_CONFIG_UNREADABLE: {field} must be a non-empty string")
    return value


def _validate_threshold_mapping(thresholds: Mapping[str, Any]) -> None:
    for _head, value in thresholds.items():
        if value is None:
            continue
        _validate_numeric_threshold(value)


def _validate_bucket_mapping(bucket: Any, *, index: int) -> Mapping[str, Any]:
    if not isinstance(bucket, Mapping):
        raise ResearchGateError(
            f"THRESHOLD_CONFIG_UNREADABLE: buckets[{index}] must be an object"
        )
    _require_non_empty_str(bucket.get("provider"), f"buckets[{index}].provider")
    _require_non_empty_str(bucket.get("requested_model"), f"buckets[{index}].requested_model")
    _require_non_empty_str(bucket.get("evaluator_version"), f"buckets[{index}].evaluator_version")
    thresholds = bucket.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise ResearchGateError(
            f"THRESHOLD_CONFIG_UNREADABLE: buckets[{index}].thresholds must be an object"
        )
    _validate_threshold_mapping(thresholds)
    return bucket


def _validate_cfg_structure(cfg: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Validate entire threshold config before MATCHED/MISSING selection."""
    if not isinstance(cfg, Mapping):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: thresholds root must be an object")
    schema_version = cfg.get("schema_version")
    if schema_version is None:
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: schema_version is required")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: schema_version must be integer 1")
    if schema_version != 1:
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: schema_version must be 1")
    buckets = cfg.get("buckets")
    if not isinstance(buckets, list):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: buckets must be a list")
    validated: list[Mapping[str, Any]] = []
    for i, bucket in enumerate(buckets):
        validated.append(_validate_bucket_mapping(bucket, index=i))
    return validated


def _find_exact_buckets(
    buckets: list[Mapping[str, Any]],
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    for bucket in buckets:
        if (
            bucket.get("provider") == provider
            and bucket.get("requested_model") == requested_model
            and bucket.get("evaluator_version") == evaluator_version
        ):
            matches.append(bucket)
    return matches


def threshold_config_hash(
    cfg: Mapping[str, Any],
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
) -> str:
    """Return 64-char lowercase SHA-256 of the effective-bucket canonical payload."""
    if not isinstance(cfg, Mapping):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: thresholds root must be an object")
    if not isinstance(provider, str) or not provider:
        raise ResearchGateError("INVALID_IDENTITY: provider must be a non-empty string")
    if not isinstance(requested_model, str) or not requested_model:
        raise ResearchGateError("INVALID_IDENTITY: requested_model must be a non-empty string")
    if not isinstance(evaluator_version, str) or not evaluator_version:
        raise ResearchGateError("INVALID_IDENTITY: evaluator_version must be a non-empty string")

    buckets = _validate_cfg_structure(cfg)
    matches = _find_exact_buckets(
        buckets,
        provider=provider,
        requested_model=requested_model,
        evaluator_version=evaluator_version,
    )
    if len(matches) > 1:
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: duplicate exact matching bucket")
    if len(matches) == 0:
        payload: dict[str, Any] = {
            "schema_version": GATE_SCHEMA_VERSION,
            "provider": provider,
            "requested_model": requested_model,
            "evaluator_version": evaluator_version,
            "bucket_status": BUCKET_MISSING,
            "thresholds": None,
        }
        return _sha256_hex(_canonical_json_bytes(payload))

    bucket = matches[0]
    thresholds = bucket.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: matching bucket thresholds must be an object")

    # Preserve exact raw mapping (absent stays absent; null stays null). Do not copy/reorder keys.
    payload = {
        "schema_version": GATE_SCHEMA_VERSION,
        "provider": provider,
        "requested_model": requested_model,
        "evaluator_version": evaluator_version,
        "bucket_status": BUCKET_MATCHED,
        "thresholds": thresholds,
    }
    return _sha256_hex(_canonical_json_bytes(payload))


def _load_threshold_cfg(path: Path) -> dict[str, Any]:
    """Load threshold config via J2 load_thresholds; fail closed as THRESHOLD_CONFIG_UNREADABLE."""
    try:
        data = load_thresholds(path)
    except (OSError, json.JSONDecodeError, CalibrationError) as exc:
        raise ResearchGateError(f"THRESHOLD_CONFIG_UNREADABLE: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — convert unexpected load failures
        # Only rewrap if it looks like a load/parse problem; otherwise let it propagate? Plan says equivalent.
        raise ResearchGateError(f"THRESHOLD_CONFIG_UNREADABLE: {exc}") from exc

    if not isinstance(data, Mapping):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: thresholds root must be an object")
    try:
        _validate_cfg_structure(data)
    except ResearchGateError:
        raise
    return dict(data)


SUPPORTED_PROVIDERS = frozenset({"typesafe_direct", "openrouter"})

_REQUIREMENT_MAP = {
    "needsCurrentYearCheck": "current_year_check",
    "needsNews": "news",
    "needsDart": "dart",
    "needsDeepAI": "deep_ai",
    "invalidationCheckNeeded": "invalidation_check",
}


def _error_gate(
    code: str,
    message: str,
    *,
    provider: Any = None,
    requested_model: Any = None,
    evaluator_version: Any = None,
    generation_id: Any = None,
    candidate_id: Any = None,
    state_hash: Any = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": GATE_SCHEMA_VERSION,
        "mode": MODE_ERROR,
        "error": {"code": code, "message": message},
        "side_effects_executed": False,
    }
    for key, value in (
        ("provider", provider),
        ("requested_model", requested_model),
        ("evaluator_version", evaluator_version),
        ("generation_id", generation_id),
        ("candidate_id", candidate_id),
        ("state_hash", state_hash),
    ):
        if isinstance(value, str) and value.strip():
            out[key] = value
    return out


def _require_identity_str(value: Any, field: str) -> str | dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return _error_gate("INVALID_IDENTITY", f"{field} must be a non-empty string")
    return value


def _validate_probability(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        return None
    return f


def evaluate_research_gate(
    *,
    answers: Mapping[str, Any],
    threshold_cfg: Mapping[str, Any],
    provider: str,
    requested_model: str,
    evaluator_version: str,
    generation_id: str,
    candidate_id: str,
    state_hash: str,
    review_class: Any = None,
    resolved_model: Any = None,
) -> dict[str, Any]:
    """Pure single-candidate Research Gate Shadow decision (Task 2)."""
    # 1) identity
    for field, value in (
        ("provider", provider),
        ("requested_model", requested_model),
        ("evaluator_version", evaluator_version),
        ("generation_id", generation_id),
        ("candidate_id", candidate_id),
        ("state_hash", state_hash),
    ):
        checked = _require_identity_str(value, field)
        if isinstance(checked, dict):
            return checked

    # 2) supported provider
    if provider not in SUPPORTED_PROVIDERS:
        return _error_gate(
            "UNSUPPORTED_PROVIDER",
            f"unsupported provider: {provider!r}",
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            generation_id=generation_id,
            candidate_id=candidate_id,
            state_hash=state_hash,
        )

    # 3) answers mapping
    if not isinstance(answers, Mapping):
        return _error_gate(
            "MISSING_ANSWERS",
            "answers must be a mapping",
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            generation_id=generation_id,
            candidate_id=candidate_id,
            state_hash=state_hash,
        )

    # 4–5) BOOLEAN_HEADS + probabilities
    probs: dict[str, float] = {}
    for head in BOOLEAN_HEADS:
        if head not in answers:
            return _error_gate(
                "MISSING_HEAD",
                f"missing required BOOLEAN_HEAD: {head}",
                provider=provider,
                requested_model=requested_model,
                evaluator_version=evaluator_version,
                generation_id=generation_id,
                candidate_id=candidate_id,
                state_hash=state_hash,
            )
        node = answers[head]
        if not isinstance(node, Mapping) or "probability" not in node:
            return _error_gate(
                "INVALID_PROBABILITY",
                f"invalid probability node for head {head}",
                provider=provider,
                requested_model=requested_model,
                evaluator_version=evaluator_version,
                generation_id=generation_id,
                candidate_id=candidate_id,
                state_hash=state_hash,
            )
        validated = _validate_probability(node.get("probability"))
        if validated is None:
            return _error_gate(
                "INVALID_PROBABILITY",
                f"invalid probability for head {head}: {node.get('probability')!r}",
                provider=provider,
                requested_model=requested_model,
                evaluator_version=evaluator_version,
                generation_id=generation_id,
                candidate_id=candidate_id,
                state_hash=state_hash,
            )
        probs[head] = validated

    # 6) threshold config hash
    try:
        cfg_hash = threshold_config_hash(
            threshold_cfg,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
        )
    except ResearchGateError as exc:
        msg = str(exc)
        code = "THRESHOLD_CONFIG_UNREADABLE"
        if "INVALID_THRESHOLD" in msg:
            code = "INVALID_THRESHOLD"
        elif "INVALID_IDENTITY" in msg:
            code = "INVALID_IDENTITY"
        elif "THRESHOLD_CONFIG_UNREADABLE" in msg:
            code = "THRESHOLD_CONFIG_UNREADABLE"
        return _error_gate(
            code,
            msg,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            generation_id=generation_id,
            candidate_id=candidate_id,
            state_hash=state_hash,
        )

    # 7–8) per-head lookup + build output
    heads: dict[str, Any] = {}
    calibrated_heads: list[str] = []
    uncalibrated_heads: list[str] = []
    research_requirements: dict[str, Any] = {
        "current_year_check": None,
        "news": None,
        "dart": None,
        "deep_ai": None,
        "invalidation_check": None,
    }

    for head in BOOLEAN_HEADS:
        try:
            looked = lookup_threshold(
                threshold_cfg,
                provider=provider,
                requested_model=requested_model,
                evaluator_version=evaluator_version,
                head=head,
            )
        except CalibrationError as exc:
            return _error_gate(
                "INVALID_THRESHOLD",
                str(exc),
                provider=provider,
                requested_model=requested_model,
                evaluator_version=evaluator_version,
                generation_id=generation_id,
                candidate_id=candidate_id,
                state_hash=state_hash,
            )

        threshold = looked.get("threshold")
        probability = probs[head]
        if threshold is None:
            decision = None
            reason = STATUS_UNCALIBRATED
            uncalibrated_heads.append(head)
        else:
            decision = bool(probability >= threshold)
            reason = None
            calibrated_heads.append(head)

        heads[head] = {
            "probability": probability,
            "threshold": threshold,
            "decision": decision,
            "reason": reason,
        }
        req_key = _REQUIREMENT_MAP.get(head)
        if req_key is not None:
            research_requirements[req_key] = decision

    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "mode": MODE_SHADOW_ONLY,
        "provider": provider,
        "requested_model": requested_model,
        "evaluator_version": evaluator_version,
        "generation_id": generation_id,
        "candidate_id": candidate_id,
        "state_hash": state_hash,
        "threshold_config_hash": cfg_hash,
        "heads": heads,
        "research_requirements": research_requirements,
        "material_now": heads["materialNow"]["decision"],
        "historical_conflict": heads["historicalConflict"]["decision"],
        "calibrated_heads": calibrated_heads,
        "uncalibrated_heads": uncalibrated_heads,
        "all_heads_calibrated": len(calibrated_heads) == len(BOOLEAN_HEADS),
        "diagnostics": {
            "review_class": review_class,
            "resolved_model": resolved_model,
        },
        "side_effects_executed": False,
    }



def _extract_review_class(answers: Any) -> Any:
    if not isinstance(answers, Mapping):
        return None
    review_node = answers.get("reviewClass")
    if isinstance(review_node, Mapping) and isinstance(review_node.get("choice"), str):
        return review_node.get("choice")
    return None


def evaluate_research_gate_generation(
    shadow_payload: Mapping[str, Any],
    *,
    threshold_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Orchestrate one upstream shadow generation into an in-memory gate envelope."""
    if not isinstance(shadow_payload, Mapping):
        raise ResearchGateError("invalid shadow_payload: must be a mapping")

    generation_id = shadow_payload.get("generation_id")
    provider = shadow_payload.get("provider")
    requested_model = shadow_payload.get("requested_model")
    evaluator_version = shadow_payload.get("evaluator_version")
    results = shadow_payload.get("results")

    for field, value in (
        ("generation_id", generation_id),
        ("provider", provider),
        ("requested_model", requested_model),
        ("evaluator_version", evaluator_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ResearchGateError(f"invalid generation identity: {field}")

    if provider not in SUPPORTED_PROVIDERS:
        raise ResearchGateError(f"unsupported provider: {provider!r}")

    if not isinstance(results, list):
        raise ResearchGateError("invalid generation results: must be a list")

    # Generation-scope threshold prevalidation + envelope hash
    try:
        envelope_hash = threshold_config_hash(
            threshold_cfg,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
        )
    except ResearchGateError:
        raise

    # Validate result elements. Uniqueness applies only to valid non-empty
    # string candidate_ids (hashable set). Malformed IDs must reach
    # evaluate_research_gate so Task-2 can return INVALID_IDENTITY without
    # an incidental TypeError from set membership.
    seen_valid: set[str] = set()
    validated_records: list[Mapping[str, Any]] = []
    for idx, record in enumerate(results):
        if not isinstance(record, Mapping):
            raise ResearchGateError(f"invalid generation results[{idx}]: must be a mapping")
        cid = record.get("candidate_id")
        if isinstance(cid, str) and cid:
            if cid in seen_valid:
                raise ResearchGateError(f"duplicate candidate_id: {cid!r}")
            seen_valid.add(cid)
        validated_records.append(record)

    out_results: list[dict[str, Any]] = []
    for record in validated_records:
        candidate_id = record.get("candidate_id")
        state_hash = record.get("state_hash")
        answers = record.get("answers")
        resolved_model = record.get("resolved_model")
        review_class = _extract_review_class(answers)

        gate_obj = evaluate_research_gate(
            answers=answers,  # type: ignore[arg-type]
            threshold_cfg=threshold_cfg,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            generation_id=generation_id,
            candidate_id=candidate_id,  # type: ignore[arg-type]
            state_hash=state_hash,  # type: ignore[arg-type]
            review_class=review_class,
            resolved_model=resolved_model,
        )

        if gate_obj.get("mode") == MODE_SHADOW_ONLY:
            candidate_hash = gate_obj.get("threshold_config_hash")
            if candidate_hash != envelope_hash:
                raise ResearchGateError(
                    "inconsistent threshold_config_hash between envelope and candidate gate"
                )

        out_results.append(
            {
                "candidate_id": candidate_id,
                "gate": gate_obj,
            }
        )

    out_results.sort(key=lambda row: str(row.get("candidate_id")))

    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "artifact_type": GATE_ARTIFACT_TYPE,
        "mode": MODE_SHADOW_ONLY,
        "generation_id": generation_id,
        "provider": provider,
        "requested_model": requested_model,
        "evaluator_version": evaluator_version,
        "threshold_config_hash": envelope_hash,
        "results": out_results,
        "side_effects_executed": False,
    }



def _provider_safe(provider: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in provider)


def research_gate_dir(settings) -> Path:
    return Path(settings.data_dir) / "research_snapshots" / "season_jev_research_gate"


def research_gate_path(settings, generation_id: str, provider: str) -> Path:
    safe = _provider_safe(provider)
    return research_gate_dir(settings) / f"{generation_id}__{safe}__gate.json"


def write_research_gate_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    write_json_atomic(Path(path), dict(payload), encoding="utf-8", compact=True)


def _reuse_key(
    *,
    schema_version: int,
    generation_id: str,
    provider: str,
    requested_model: str,
    evaluator_version: str,
    candidate_id: str,
    state_hash: str,
    threshold_config_hash: str,
) -> tuple:
    return (
        schema_version,
        generation_id,
        provider,
        requested_model,
        evaluator_version,
        candidate_id,
        state_hash,
        threshold_config_hash,
    )


def _assert_persisted_state_identity(
    persisted_gate: Mapping[str, Any],
    *,
    state_hash: str,
) -> None:
    """Strict claim check: stored state_hash must match requested state_hash."""
    stored = persisted_gate.get("state_hash") if isinstance(persisted_gate, Mapping) else None
    if stored != state_hash:
        raise ResearchGateError(
            f"STATE_HASH_MISMATCH: stored={stored!r} requested={state_hash!r}"
        )


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def load_reuse_index(path: Path) -> dict:
    """Load exact 8-field reuse index from one J3 generation artifact.

    Missing/unreadable/malformed (non-schema) artifacts yield {}.
    Unsupported schema_version raises ResearchGateError(UNSUPPORTED_SCHEMA).
    Only SHADOW_ONLY gates with consistent identity enter the index.
    """
    path = Path(path)
    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {}

    if not isinstance(data, Mapping):
        return {}

    schema_version = data.get("schema_version")
    if schema_version != GATE_SCHEMA_VERSION:
        raise ResearchGateError(
            f"UNSUPPORTED_SCHEMA: schema_version={schema_version!r}"
        )

    if data.get("artifact_type") != GATE_ARTIFACT_TYPE:
        return {}

    generation_id = data.get("generation_id")
    provider = data.get("provider")
    requested_model = data.get("requested_model")
    evaluator_version = data.get("evaluator_version")
    threshold_config_hash = data.get("threshold_config_hash")
    results = data.get("results")

    if not (
        _is_non_empty_str(generation_id)
        and _is_non_empty_str(provider)
        and _is_non_empty_str(requested_model)
        and _is_non_empty_str(evaluator_version)
        and _is_non_empty_str(threshold_config_hash)
        and isinstance(results, list)
    ):
        return {}

    index: dict = {}
    for item in results:
        if not isinstance(item, Mapping):
            return {}
        candidate_id = item.get("candidate_id")
        gate_obj = item.get("gate")
        if not isinstance(gate_obj, Mapping):
            return {}
        if not _is_non_empty_str(candidate_id):
            # malformed candidate identity — skip indexing this candidate only
            # but do not trust partial corruption of sibling structure beyond this
            continue
        if gate_obj.get("mode") != MODE_SHADOW_ONLY:
            continue

        # gate identity must agree with artifact
        if (
            gate_obj.get("schema_version") != schema_version
            or gate_obj.get("generation_id") != generation_id
            or gate_obj.get("provider") != provider
            or gate_obj.get("requested_model") != requested_model
            or gate_obj.get("evaluator_version") != evaluator_version
            or gate_obj.get("threshold_config_hash") != threshold_config_hash
            or gate_obj.get("candidate_id") != candidate_id
        ):
            return {}

        state_hash = gate_obj.get("state_hash")
        if not _is_non_empty_str(state_hash):
            return {}

        key = _reuse_key(
            schema_version=int(schema_version),
            generation_id=generation_id,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            candidate_id=candidate_id,
            state_hash=state_hash,
            threshold_config_hash=threshold_config_hash,
        )
        index[key] = dict(gate_obj)

    return index
