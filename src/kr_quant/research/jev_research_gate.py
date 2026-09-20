# -*- coding: utf-8 -*-
"""J3 Research Gate Shadow — Task 1 threshold identity foundation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from kr_quant.research.jev_calibration import CalibrationError, load_thresholds

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


def _validate_cfg_structure(cfg: Mapping[str, Any]) -> list[Any]:
    if not isinstance(cfg, Mapping):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: thresholds root must be an object")
    buckets = cfg.get("buckets")
    if not isinstance(buckets, list):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: buckets must be a list")
    return buckets


def _find_exact_buckets(
    buckets: list[Any],
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    for bucket in buckets:
        if not isinstance(bucket, Mapping):
            continue
        if (
            bucket.get("provider") == provider
            and bucket.get("requested_model") == requested_model
            and bucket.get("evaluator_version") == evaluator_version
        ):
            matches.append(bucket)
    return matches


def _validate_threshold_mapping(thresholds: Mapping[str, Any]) -> None:
    for _head, value in thresholds.items():
        if value is None:
            continue
        _validate_numeric_threshold(value)


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
    _validate_threshold_mapping(thresholds)

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
    buckets = data.get("buckets")
    if not isinstance(buckets, list):
        raise ResearchGateError("THRESHOLD_CONFIG_UNREADABLE: buckets must be a list")
    return dict(data)
