#!/usr/bin/env python3
"""Thin argparse CLI for JEV calibration export/ingest/report workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kr_quant.atomic_io import write_json_atomic
from kr_quant.research import jev_calibration as cal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev_calibration_export")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("export-candidates", help="Export internal rows from shadow JSON")
    p.add_argument("--shadow", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("blind-template", help="Build blind human-label template JSONL")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("ingest-labels", help="Join blind labels onto internal rows")
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("calibration-report", help="Build calibration-open report JSON")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("lock-selection", help="Lock a calibration-only selection manifest")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("holdout-eval", help="Evaluate holdout for a locked selection")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "export-candidates":
        payload = json.loads(Path(args.shadow).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("shadow payload must be a JSON object")
        rows = cal.export_candidates_from_shadow(
            payload,
            provider=payload.get("provider"),
            requested_model=payload.get("requested_model"),
            evaluator_version=payload.get("evaluator_version"),
        )
        cal.write_jsonl_atomic(Path(args.out), rows)
    elif args.command == "blind-template":
        dataset = cal.read_jsonl(Path(args.dataset))
        template = cal.build_blind_label_template(dataset)
        cal.write_jsonl_atomic(Path(args.out), template)
    elif args.command == "ingest-labels":
        labels = cal.read_jsonl(Path(args.labels))
        dataset = cal.read_jsonl(Path(args.dataset))
        joined = cal.ingest_blind_labels(template_rows=labels, internal_rows=dataset)
        cal.write_jsonl_atomic(Path(args.out), joined)
    elif args.command == "calibration-report":
        dataset_path = Path(args.dataset)
        samples = cal.read_jsonl(dataset_path)
        dataset_hash = cal.dataset_hash_v1(samples)
        bucket = cal.dataset_bucket_identity(samples)
        report = cal.build_calibration_report(
            dataset_id=dataset_path.stem,
            dataset_hash=dataset_hash,
            bucket=bucket,
            samples=samples,
        )
        write_json_atomic(Path(args.out), report)
    elif args.command == "lock-selection":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        locked = cal.lock_selection(manifest)
        write_json_atomic(Path(args.out), locked)
    elif args.command == "holdout-eval":
        samples = cal.read_jsonl(Path(args.dataset))
        selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
        report = cal.evaluate_holdout_locked(samples=samples, selection=selection)
        write_json_atomic(Path(args.out), report)
    else:
        parser.error(f"unknown command {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
