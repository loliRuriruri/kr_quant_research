"""JEV calibration tooling.

Fail-closed threshold lookup, dataset identity, metrics/sweep, and
selection/holdout review helpers. Production routing stays shadow-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def _evaluate_split_at_threshold(
    samples: list[dict],
    *,
    head: str,
    threshold: float,
    split: str,
) -> dict:
    y_true: list[bool] = []
    y_pred: list[bool] = []
    unknown_count = 0
    invalid_probability_count = 0

    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("split") != split:
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
        "support_positive": sum(1 for t in y_true if t),
        "support_negative": sum(1 for t in y_true if not t),
    }


def evaluate_head_at_threshold(
    samples: list[dict],
    *,
    head: str,
    threshold: float,
) -> dict:
    # Task 3 public contract: calibration split only.
    return _evaluate_split_at_threshold(
        samples,
        head=head,
        threshold=threshold,
        split=SPLIT_CALIBRATION,
    )


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


STATE_CALIBRATION_OPEN = "CALIBRATION_OPEN"
STATE_SELECTION_LOCKED = "SELECTION_LOCKED"
STATE_HOLDOUT_REVEALED = "HOLDOUT_REVEALED"

REVIEW_ACCEPT = "ACCEPT"
REVIEW_REJECT = "REJECT"
REVIEW_COLLECT_MORE_LABELS = "COLLECT_MORE_LABELS"

_ALLOWED_REVIEW = frozenset({
    REVIEW_ACCEPT,
    REVIEW_REJECT,
    REVIEW_COLLECT_MORE_LABELS,
})


def support_status(
    samples: list[dict],
    *,
    head: str,
    split: str,
) -> dict:
    positive_count = 0
    negative_count = 0
    unknown_count = 0
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("split") != split:
            continue
        label = _extract_label(sample, head)
        if label is True:
            positive_count += 1
        elif label is False:
            negative_count += 1
        elif label == "unknown":
            unknown_count += 1
    valid_count = positive_count + negative_count
    analysis_eligible = valid_count >= 50
    production_review_eligible = valid_count >= 100
    insufficient_class_support = bool(
        analysis_eligible and (positive_count < 10 or negative_count < 10)
    )
    return {
        "valid_count": valid_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "unknown_count": unknown_count,
        "support_positive": positive_count,
        "support_negative": negative_count,
        "analysis_eligible": analysis_eligible,
        "production_review_eligible": production_review_eligible,
        "insufficient_class_support": insufficient_class_support,
        "head": head,
        "split": split,
    }


def build_calibration_report(
    *,
    dataset_id: str,
    dataset_hash: str,
    bucket: dict,
    samples: list[dict],
) -> dict:
    heads: dict[str, Any] = {}
    for head in BOOLEAN_HEADS:
        support = support_status(
            samples, head=head, split=SPLIT_CALIBRATION
        )
        sweep = sweep_head_thresholds(samples, head=head)
        heads[head] = {
            "support": support,
            "sweep": sweep,
            "shortlist": _pareto_shortlist(sweep, head=head),
            "fn_sensitive": head in FN_SENSITIVE_HEADS,
        }
    return {
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "dataset_hash_method_version": HASH_METHOD_VERSION,
        "split_method_version": SPLIT_METHOD_VERSION,
        "sweep_method_version": SWEEP_METHOD_VERSION,
        "prediction_rule": "probability >= threshold",
        "bucket": dict(bucket),
        "state": STATE_CALIBRATION_OPEN,
        "created_at": _utc_now_iso(),
        "resolved_model_distribution": _resolved_model_distribution(samples),
        "heads": heads,
    }


def selection_manifest_hash(manifest: dict) -> str:
    if not isinstance(manifest, dict):
        raise CalibrationError("manifest must be a dict")
    payload = {
        k: v for k, v in manifest.items() if k != "selection_manifest_hash"
    }
    raw = _canonical_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def lock_selection(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise CalibrationError("manifest must be a dict")
    if manifest.get("selection_basis") != "calibration_only":
        raise CalibrationError("selection_basis must be calibration_only")
    head = manifest.get("head")
    if head not in BOOLEAN_HEADS:
        raise CalibrationError(f"invalid selection head: {head!r}")
    if head == "reviewClass":
        raise CalibrationError("reviewClass cannot be locked")
    threshold = manifest.get("selected_threshold")
    if not _is_valid_probability(threshold):
        raise CalibrationError(f"invalid selected_threshold: {threshold!r}")
    if manifest.get("holdout_revealed") is True:
        raise CalibrationError("cannot lock with holdout_revealed=True")
    if manifest.get("state") == STATE_HOLDOUT_REVEALED:
        raise CalibrationError("cannot re-lock HOLDOUT_REVEALED as pristine")

    locked = dict(manifest)
    locked["selected_threshold"] = float(threshold)
    locked["state"] = STATE_SELECTION_LOCKED
    locked["holdout_revealed"] = False
    locked["selection_basis"] = "calibration_only"
    existing_at = manifest.get("selected_at")
    if isinstance(existing_at, str) and existing_at.strip() != "":
        locked["selected_at"] = existing_at
    else:
        locked["selected_at"] = _utc_now_iso()
    locked["selection_manifest_hash"] = selection_manifest_hash(locked)
    return locked


def evaluate_holdout_locked(
    *,
    samples: list[dict],
    selection: dict,
) -> dict:
    if not isinstance(selection, dict):
        raise CalibrationError("selection must be a dict")
    if selection.get("state") != STATE_SELECTION_LOCKED:
        raise CalibrationError(
            "holdout requires SELECTION_LOCKED (got "
            f"{selection.get('state')!r}; CALIBRATION_OPEN forbidden)"
        )
    head = selection.get("head")
    if head not in BOOLEAN_HEADS:
        raise CalibrationError(f"invalid selection head: {head!r}")
    threshold = selection.get("selected_threshold")
    if not _is_valid_probability(threshold):
        raise CalibrationError(f"invalid selected_threshold: {threshold!r}")
    locked_at = selection.get("selected_at")
    if not isinstance(locked_at, str) or locked_at.strip() == "":
        raise CalibrationError(
            "selection_locked_at requires non-empty selected_at"
        )

    metrics = _evaluate_split_at_threshold(
        samples,
        head=str(head),
        threshold=float(threshold),
        split=SPLIT_HOLDOUT,
    )
    return {
        "state": STATE_HOLDOUT_REVEALED,
        "head": head,
        "selected_threshold": float(threshold),
        "selection_manifest_hash": selection.get("selection_manifest_hash"),
        "selection_basis": "calibration_only",
        "selection_locked_at": locked_at,
        "holdout_revealed_at": _utc_now_iso(),
        "TP": metrics["TP"],
        "FP": metrics["FP"],
        "TN": metrics["TN"],
        "FN": metrics["FN"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "FPR": metrics["FPR"],
        "FNR": metrics["FNR"],
        "support_positive": metrics["support_positive"],
        "support_negative": metrics["support_negative"],
        "unknown_count": metrics["unknown_count"],
        "invalid_probability_count": metrics["invalid_probability_count"],
        "holdout_revealed": True,
    }


def attach_review_status(report: dict, review_status: str) -> dict:
    if review_status not in _ALLOWED_REVIEW:
        raise CalibrationError(f"invalid review_status: {review_status!r}")
    out = dict(report)
    out["review_status"] = review_status
    return out


def mark_holdout_non_pristine(selection: dict) -> dict:
    out = dict(selection)
    out["pristine_holdout"] = False
    return out


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def calibration_metrics_hash(report: dict) -> str:
    if not isinstance(report, dict):
        raise CalibrationError("report must be a dict")
    payload = {
        k: v
        for k, v in report.items()
        if k not in {"created_at", "calibration_metrics_hash"}
    }
    raw = _canonical_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _metric_complete(row: Mapping[str, Any]) -> bool:
    return all(
        row.get(k) is not None
        for k in ("recall", "precision", "FPR", "FNR")
    )


def _dominates(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if not (_metric_complete(a) and _metric_complete(b)):
        return False
    ge = (
        a["recall"] >= b["recall"]
        and a["precision"] >= b["precision"]
        and a["FPR"] <= b["FPR"]
        and a["FNR"] <= b["FNR"]
    )
    if not ge:
        return False
    return (
        a["recall"] > b["recall"]
        or a["precision"] > b["precision"]
        or a["FPR"] < b["FPR"]
        or a["FNR"] < b["FNR"]
    )


def _pareto_shortlist(sweep: list[dict], *, head: str) -> list[dict]:
    rationale = (
        "fn_sensitive_pareto" if head in FN_SENSITIVE_HEADS else "pareto"
    )
    shortlist: list[dict] = []
    for cand in sweep:
        dominated = False
        for other in sweep:
            if other is cand:
                continue
            if _dominates(other, cand):
                dominated = True
                break
        if not dominated:
            row = dict(cand)
            row["rationale"] = rationale
            shortlist.append(row)
    shortlist.sort(key=lambda r: float(r.get("threshold", 0.0)))
    return shortlist


def _resolved_model_distribution(samples: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("split") != SPLIT_CALIBRATION:
            continue
        model = sample.get("resolved_model")
        if isinstance(model, str) and model.strip() != "":
            counts[model] = counts.get(model, 0) + 1
    return {k: counts[k] for k in sorted(counts.keys())}
