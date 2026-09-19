"""JEV calibration threshold contract (Task 1).

Fail-closed lookup for boolean-head thresholds. Production routing is NOT
enabled here: every successful lookup still returns SHADOW_ONLY.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

BOOLEAN_HEADS: tuple[str, ...] = (
    "materialNow",
    "needsCurrentYearCheck",
    "needsNews",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
    "needsDeepAI",
)

STATUS_UNCALIBRATED = "UNCALIBRATED"
STATUS_SHADOW_ONLY = "SHADOW_ONLY"


class CalibrationError(ValueError):
    """Invalid threshold configuration or value."""


def load_thresholds(path: Path | str) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise CalibrationError("thresholds root must be an object")
    buckets = data.get("buckets")
    if not isinstance(buckets, list):
        raise CalibrationError("buckets must be a list")
    return data


def _uncalibrated() -> dict[str, Any]:
    return {
        "status": STATUS_SHADOW_ONLY,
        "reason": STATUS_UNCALIBRATED,
        "threshold": None,
    }


def _validate_numeric(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"threshold must be a finite number in [0, 1], got {value!r}")
    f = float(value)
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        raise CalibrationError(f"threshold must be a finite number in [0, 1], got {value!r}")
    return f


def lookup_threshold(
    cfg: Mapping[str, Any],
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
    head: str,
) -> dict[str, Any]:
    if head not in BOOLEAN_HEADS:
        return _uncalibrated()

    buckets = cfg.get("buckets")
    if not isinstance(buckets, list):
        return _uncalibrated()

    match: Mapping[str, Any] | None = None
    for bucket in buckets:
        if not isinstance(bucket, Mapping):
            continue
        if (
            bucket.get("provider") == provider
            and bucket.get("requested_model") == requested_model
            and bucket.get("evaluator_version") == evaluator_version
        ):
            match = bucket
            break

    if match is None:
        return _uncalibrated()

    thresholds = match.get("thresholds")
    if not isinstance(thresholds, Mapping) or head not in thresholds:
        return _uncalibrated()

    value = thresholds[head]
    if value is None:
        return _uncalibrated()

    numeric = _validate_numeric(value)
    # Task 1: numeric values are still shadow-only (no production routing).
    return {
        "status": STATUS_SHADOW_ONLY,
        "reason": None,
        "threshold": numeric,
    }


def threshold_status_from_path(
    path: Path | str,
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
    head: str,
) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return _uncalibrated()
    try:
        cfg = load_thresholds(p)
    except (OSError, json.JSONDecodeError, CalibrationError):
        return _uncalibrated()
    return lookup_threshold(
        cfg,
        provider=provider,
        requested_model=requested_model,
        evaluator_version=evaluator_version,
        head=head,
    )
