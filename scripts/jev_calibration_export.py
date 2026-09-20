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
    p.add_argument("--provider", required=True)
    p.add_argument("--requested-model", required=True)
    p.add_argument("--evaluator-version", required=True)

    p = sub.add_parser("blind-template", help="Build blind human-label template JSONL")
    p.add_argument("--internal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("ingest-labels", help="Join blind labels onto internal rows")
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--internal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("calibration-report", help="Build calibration-open report JSON")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--provider", required=True)
    p.add_argument("--requested-model", required=True)
    p.add_argument("--evaluator-version", required=True)

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
        rows = cal.export_candidates_from_shadow(
            payload,
            provider=args.provider,
            requested_model=args.requested_model,
            evaluator_version=args.evaluator_version,
        )
        cal.write_jsonl_atomic(Path(args.out), rows)
    elif args.command == "blind-template":
        internal = cal.read_jsonl(Path(args.internal))
        template = cal.build_blind_label_template(internal)
        cal.write_jsonl_atomic(Path(args.out), template)
    elif args.command == "ingest-labels":
        labels = cal.read_jsonl(Path(args.labels))
        internal = cal.read_jsonl(Path(args.internal))
        joined = cal.ingest_blind_labels(template_rows=labels, internal_rows=internal)
        cal.write_jsonl_atomic(Path(args.out), joined)
    elif args.command == "calibration-report":
        samples = cal.read_jsonl(Path(args.dataset))
        dataset_hash = cal.dataset_hash_v1(samples)
        report = cal.build_calibration_report(
            dataset_id=args.dataset_id,
            dataset_hash=dataset_hash,
            bucket={
                "provider": args.provider,
                "requested_model": args.requested_model,
                "evaluator_version": args.evaluator_version,
            },
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
