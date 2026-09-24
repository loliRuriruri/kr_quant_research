#!/usr/bin/env python3
"""Operator CLI: build and verify JEV threshold approval artifacts (offline).

Subcommands:
- build:  build a threshold approval record from a locked calibration selection
          and its bound holdout report, then write it atomically.
- verify: verify an approval artifact against the threshold config.

No network. No provider calls. No config writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kr_quant.atomic_io import write_json_atomic  # noqa: E402
from kr_quant.research import jev_runtime as rt  # noqa: E402


def _load_json_object(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _non_empty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_unit(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not (0.0 <= number <= 1.0):
        return None
    return number


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _refuse(reason: str) -> int:
    _print({"status": "REFUSED", "reason": reason})
    return 1


def _cmd_build(args: argparse.Namespace) -> int:
    from kr_quant.research.jev_calibration import (
        BOOLEAN_HEADS,
        selection_manifest_hash,
    )

    selection = _load_json_object(args.selection)
    if selection is None:
        return _refuse("SELECTION_UNREADABLE")
    holdout = _load_json_object(args.holdout)
    if holdout is None:
        return _refuse("HOLDOUT_UNREADABLE")

    if selection.get("state") != "SELECTION_LOCKED":
        return _refuse("SELECTION_NOT_LOCKED")
    if selection.get("selection_basis") != "calibration_only":
        return _refuse("SELECTION_BASIS_INVALID")
    head = _non_empty_str(selection.get("head"))
    if head is None or head not in BOOLEAN_HEADS:
        return _refuse("SELECTION_HEAD_INVALID")
    threshold = _finite_unit(selection.get("selected_threshold"))
    if threshold is None:
        return _refuse("SELECTION_THRESHOLD_INVALID")
    if selection.get("holdout_revealed") is not False:
        return _refuse("SELECTION_NOT_PRISTINE")
    dataset_id = _non_empty_str(selection.get("dataset_id"))
    dataset_hash = _non_empty_str(selection.get("dataset_hash"))
    if dataset_id is None or dataset_hash is None:
        return _refuse("SELECTION_DATASET_INVALID")
    bucket = selection.get("bucket")
    if not isinstance(bucket, dict):
        return _refuse("SELECTION_BUCKET_MISSING")
    provider = _non_empty_str(bucket.get("provider"))
    requested_model = _non_empty_str(bucket.get("requested_model"))
    evaluator_version = _non_empty_str(bucket.get("evaluator_version"))
    if provider is None or requested_model is None or evaluator_version is None:
        return _refuse("SELECTION_BUCKET_INVALID")
    locked_at = _non_empty_str(selection.get("selected_at"))
    if locked_at is None:
        return _refuse("SELECTION_TIMESTAMP_MISSING")
    stored_selection_hash = _non_empty_str(selection.get("selection_manifest_hash"))
    if stored_selection_hash is None:
        return _refuse("SELECTION_HASH_MISSING")
    if stored_selection_hash != selection_manifest_hash(selection):
        return _refuse("SELECTION_HASH_MISMATCH")

    if holdout.get("state") != "HOLDOUT_REVEALED":
        return _refuse("HOLDOUT_NOT_REVEALED")
    if holdout.get("holdout_revealed") is not True:
        return _refuse("HOLDOUT_NOT_REVEALED")
    if holdout.get("head") != head:
        return _refuse("HOLDOUT_HEAD_MISMATCH")
    holdout_threshold = _finite_unit(holdout.get("selected_threshold"))
    if holdout_threshold is None or holdout_threshold != threshold:
        return _refuse("HOLDOUT_THRESHOLD_MISMATCH")
    if holdout.get("selection_manifest_hash") != stored_selection_hash:
        return _refuse("HOLDOUT_SELECTION_MISMATCH")
    if holdout.get("selection_locked_at") != locked_at:
        return _refuse("HOLDOUT_LOCK_TIMESTAMP_MISMATCH")
    revealed_at = _non_empty_str(holdout.get("holdout_revealed_at"))
    if revealed_at is None:
        return _refuse("HOLDOUT_TIMESTAMP_MISSING")
    if holdout.get("review_status") != "ACCEPT":
        return _refuse("REVIEW_NOT_ACCEPTED")

    if selection.get("pristine_holdout") is False or holdout.get("pristine_holdout") is False:
        return _refuse("HOLDOUT_NOT_PRISTINE")

    locked_at_dt = _parse_utc_timestamp(locked_at)
    revealed_at_dt = _parse_utc_timestamp(revealed_at)
    if locked_at_dt is None or revealed_at_dt is None or revealed_at_dt <= locked_at_dt:
        return _refuse("HOLDOUT_CHRONOLOGY_INVALID")

    if "approval_hash" in holdout:
        return _refuse("HOLDOUT_SCHEMA_INVALID")

    holdout_payload = {
        key: value for key, value in holdout.items() if key != "holdout_report_hash"
    }
    computed_holdout_hash = rt.approval_record_hash(holdout_payload)
    stored_holdout_hash = holdout.get("holdout_report_hash")
    if stored_holdout_hash is not None and stored_holdout_hash != computed_holdout_hash:
        return _refuse("HOLDOUT_HASH_MISMATCH")

    positive = _non_negative_int(holdout.get("support_positive"))
    negative = _non_negative_int(holdout.get("support_negative"))
    if positive is None or negative is None:
        return _refuse("HOLDOUT_SUPPORT_INVALID")
    support = {
        "valid_count": positive + negative,
        "positive_count": positive,
        "negative_count": negative,
    }

    expected_name = f"{rt.bucket_hash(provider, requested_model, evaluator_version)}__{head}.json"
    out_path = Path(args.out)
    if out_path.name != expected_name:
        return _refuse("OUTPUT_PATH_MISMATCH")

    record = rt.build_approval_record(
        provider=provider,
        requested_model=requested_model,
        evaluator_version=evaluator_version,
        head=head,
        threshold=threshold,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        selection_manifest_hash=stored_selection_hash,
        selection_locked_at=locked_at,
        holdout_report_hash=computed_holdout_hash,
        holdout_revealed_at=revealed_at,
        holdout_pristine=True,
        review_status="ACCEPT",
        support=support,
        approved_by="human",
        approved_at=datetime.now(timezone.utc).isoformat(),
    )
    verdict = rt.verify_approval_record(
        record,
        provider=provider,
        requested_model=requested_model,
        evaluator_version=evaluator_version,
        head=head,
        threshold=threshold,
    )
    if not verdict.get("ok"):
        return _refuse("SELF_VERIFY_FAILED")

    write_json_atomic(out_path, record)
    _print(
        {
            "status": "OK",
            "out": str(out_path),
            "approval_hash": record["approval_hash"],
        }
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from kr_quant.research.jev_calibration import lookup_threshold

    def _fail() -> int:
        _print({"ok": False, "reason": "APPROVAL_MISMATCH"})
        return 1

    record = _load_json_object(args.approval)
    config = _load_json_object(args.config)
    if record is None or config is None:
        return _fail()
    provider = _non_empty_str(record.get("provider"))
    requested_model = _non_empty_str(record.get("requested_model"))
    evaluator_version = _non_empty_str(record.get("evaluator_version"))
    head = _non_empty_str(record.get("head"))
    if provider is None or requested_model is None or evaluator_version is None or head is None:
        return _fail()
    try:
        looked = lookup_threshold(
            config,
            provider=provider,
            requested_model=requested_model,
            evaluator_version=evaluator_version,
            head=head,
        )
    except Exception:
        return _fail()
    verdict = rt.verify_approval_record(
        record,
        provider=provider,
        requested_model=requested_model,
        evaluator_version=evaluator_version,
        head=head,
        threshold=looked.get("threshold"),
    )
    ok = bool(verdict.get("ok"))
    _print({"ok": ok, "reason": verdict.get("reason")})
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev_threshold_approval")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser(
        "build",
        help="Build a threshold approval artifact from a locked selection and its holdout report.",
    )
    build.add_argument("--selection", type=Path, required=True)
    build.add_argument("--holdout", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    verify = sub.add_parser(
        "verify",
        help="Verify an approval artifact against the threshold config.",
    )
    verify.add_argument("--approval", type=Path, required=True)
    verify.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        return _cmd_build(args)
    if args.command == "verify":
        return _cmd_verify(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
