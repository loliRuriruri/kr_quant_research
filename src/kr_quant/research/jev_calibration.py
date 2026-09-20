"""JEV calibration threshold contract (Task 1).

Fail-closed lookup for boolean-head thresholds. Production routing is NOT
enabled here: every successful lookup still returns SHADOW_ONLY.
"""
from __future__ import annotations

import hashlib
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

SPLIT_CALIBRATION = "calibration"
SPLIT_HOLDOUT = "holdout"

SPLIT_METHOD_VERSION = "ticker-grouped-v1"
HASH_METHOD_VERSION = "canonical-jsonl-v1"

_FORBIDDEN_STATE_KEYS = frozenset({
    "quantReference",
    "quant_reference",
    "pre_entry_rank",
    "grade",
    "seasonality_score",
    "score_breakdown",
})


class CalibrationError(ValueError):
    """Invalid threshold configuration or value."""


class RevisionConflict(CalibrationError):
    """Same annotation_version with conflicting canonical content."""


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


def make_sample_id(
    provider: str,
    requested_model: str,
    evaluator_version: str,
    state_hash: str,
) -> str:
    raw = f"{provider}\n{requested_model}\n{evaluator_version}\n{state_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def assign_split(
    *,
    ticker: str | None,
    state_hash: str,
) -> str:
    if ticker is not None and ticker.strip() != "":
        group_identity = ticker.strip()
    else:
        group_identity = state_hash
    group_hash = hashlib.sha256(group_identity.encode("utf-8")).hexdigest()
    bucket = int(group_hash[0:8], 16) % 100
    if bucket < 70:
        return SPLIT_CALIBRATION
    return SPLIT_HOLDOUT


def assert_calibration_state_clean(state: object) -> None:
    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in _FORBIDDEN_STATE_KEYS:
                    raise ValueError(f"forbidden calibration state key: {key}")
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(state)


def _canonical_json(obj: object) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _require_annotation_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalibrationError(
            f"annotation_version must be int >= 1, got {value!r}"
        )
    if value < 1:
        raise CalibrationError(
            f"annotation_version must be int >= 1, got {value!r}"
        )
    return value


def validate_sample(sample: dict) -> None:
    if not isinstance(sample, dict):
        raise CalibrationError("sample must be a dict")
    sample_id = sample.get("sample_id")
    if not isinstance(sample_id, str) or sample_id.strip() == "":
        raise CalibrationError("sample_id must be a non-empty string")
    state_hash = sample.get("state_hash")
    if not isinstance(state_hash, str) or state_hash.strip() == "":
        raise CalibrationError("state_hash must be a non-empty string")
    _require_annotation_version(sample.get("annotation_version"))
    split = sample.get("split")
    if split not in {SPLIT_CALIBRATION, SPLIT_HOLDOUT}:
        raise CalibrationError(f"invalid split: {split!r}")
    if "state" in sample:
        assert_calibration_state_clean(sample["state"])


def select_active_rows(rows: list[dict]) -> list[dict]:
    by_sample: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CalibrationError("row must be a dict")
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or sample_id.strip() == "":
            raise CalibrationError("sample_id must be a non-empty string")
        _require_annotation_version(row.get("annotation_version"))
        by_sample.setdefault(sample_id, []).append(row)

    active: list[dict] = []
    for sample_id in sorted(by_sample.keys()):
        group = by_sample[sample_id]
        max_ver = max(int(r["annotation_version"]) for r in group)
        candidates = [r for r in group if int(r["annotation_version"]) == max_ver]
        canon = {_canonical_json(r) for r in candidates}
        if len(canon) > 1:
            raise RevisionConflict(
                f"REVISION_CONFLICT for sample_id={sample_id!r} "
                f"annotation_version={max_ver}"
            )
        active.append(candidates[0])
    return active


def dataset_hash_v1(rows: list[dict]) -> str:
    active = select_active_rows(rows)
    active_sorted = sorted(active, key=lambda r: str(r.get("sample_id", "")))
    parts: list[bytes] = []
    for row in active_sorted:
        line = _canonical_json(row) + "\n"
        parts.append(line.encode("utf-8"))
    return hashlib.sha256(b"".join(parts)).hexdigest()


def ensure_split_consistency(rows: list[dict]) -> None:
    by_ticker: dict[str, set[str]] = {}
    by_state: dict[str, set[str]] = {}
    by_sample: dict[str, set[str]] = {}

    for row in rows:
        if not isinstance(row, dict):
            raise CalibrationError("row must be a dict")
        split = row.get("split")
        if split not in {SPLIT_CALIBRATION, SPLIT_HOLDOUT}:
            raise CalibrationError(f"invalid split: {split!r}")

        sample_id = row.get("sample_id")
        if isinstance(sample_id, str) and sample_id.strip() != "":
            by_sample.setdefault(sample_id, set()).add(split)

        ticker = row.get("ticker")
        if isinstance(ticker, str) and ticker.strip() != "":
            by_ticker.setdefault(ticker.strip(), set()).add(split)

        state_hash = row.get("state_hash")
        if isinstance(state_hash, str) and state_hash.strip() != "":
            by_state.setdefault(state_hash, set()).add(split)

    for sample_id, splits in by_sample.items():
        if len(splits) > 1:
            raise CalibrationError(
                f"SPLIT_SAMPLE_CONFLICT sample_id={sample_id!r} "
                f"splits={sorted(splits)}"
            )
    for ticker, splits in by_ticker.items():
        if len(splits) > 1:
            raise CalibrationError(
                f"SPLIT_TICKER_CONFLICT ticker={ticker!r} splits={sorted(splits)}"
            )
    for state_hash, splits in by_state.items():
        if len(splits) > 1:
            raise CalibrationError(
                f"SPLIT_STATE_HASH_CONFLICT state_hash={state_hash!r} "
                f"splits={sorted(splits)}"
            )


FN_SENSITIVE_HEADS = frozenset({
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
})

SWEEP_METHOD_VERSION = "observed-boundaries-v1"


def confusion_counts(
    *,
    y_true: list[bool],
    y_pred: list[bool],
) -> dict:
    if len(y_true) != len(y_pred):
        raise CalibrationError("y_true and y_pred length mismatch")
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred):
        if t and p:
            tp += 1
        elif (not t) and p:
            fp += 1
        elif (not t) and (not p):
            tn += 1
        else:
            fn += 1
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn}


def rates_from_counts(counts: dict) -> dict:
    tp = int(counts.get("TP", 0))
    fp = int(counts.get("FP", 0))
    tn = int(counts.get("TN", 0))
    fn = int(counts.get("FN", 0))
    precision = (tp / (tp + fp)) if (tp + fp) else None
    recall = (tp / (tp + fn)) if (tp + fn) else None
    fpr = (fp / (fp + tn)) if (fp + tn) else None
    fnr = (fn / (fn + tp)) if (fn + tp) else None
    return {
        "precision": precision,
        "recall": recall,
        "FPR": fpr,
        "FNR": fnr,
    }


def predict_positive(
    probability: float,
    threshold: float,
) -> bool:
    return float(probability) >= float(threshold)


def _is_valid_probability(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    f = float(value)
    return math.isfinite(f) and 0.0 <= f <= 1.0


def _extract_probability(sample: dict, head: str) -> object:
    answers = sample.get("jev_answers")
    if not isinstance(answers, Mapping):
        return None
    node = answers.get(head)
    if not isinstance(node, Mapping):
        return None
    return node.get("probability")


def _extract_label(sample: dict, head: str) -> object:
    labels = sample.get("human_labels")
    if not isinstance(labels, Mapping):
        return None
    return labels.get(head)


def evaluate_head_at_threshold(
    samples: list[dict],
    *,
    head: str,
    threshold: float,
) -> dict:
    y_true: list[bool] = []
    y_pred: list[bool] = []
    unknown_count = 0
    invalid_probability_count = 0

    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("split") != SPLIT_CALIBRATION:
            continue
        label = _extract_label(sample, head)
        if label == "unknown":
            unknown_count += 1
            continue
        if label is not True and label is not False:
            continue
        prob = _extract_probability(sample, head)
        if not _is_valid_probability(prob):
            invalid_probability_count += 1
            continue
        y_true.append(bool(label))
        y_pred.append(predict_positive(float(prob), threshold))

    counts = confusion_counts(y_true=y_true, y_pred=y_pred)
    rates = rates_from_counts(counts)
    return {
        **counts,
        **rates,
        "unknown_count": unknown_count,
        "invalid_probability_count": invalid_probability_count,
        "threshold": float(threshold),
        "head": head,
    }


def sweep_head_thresholds(
    samples: list[dict],
    *,
    head: str,
) -> list[dict]:
    observed: set[float] = set()
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("split") != SPLIT_CALIBRATION:
            continue
        label = _extract_label(sample, head)
        if label is not True and label is not False:
            continue
        prob = _extract_probability(sample, head)
        if not _is_valid_probability(prob):
            continue
        observed.add(float(prob))
    candidates = sorted(observed | {0.0, 1.0})
    return [
        evaluate_head_at_threshold(samples, head=head, threshold=t)
        for t in candidates
    ]
