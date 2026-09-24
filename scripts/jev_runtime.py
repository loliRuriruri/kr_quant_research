#!/usr/bin/env python3
"""Operator CLI: run one synchronous JEV runtime pass for the current 5y bundle.

This is an explicit operator/evidence entrypoint only. The production automatic
hook remains ``season_snapshot._schedule_shadow`` ->
``request_runtime_evaluation``; this CLI intentionally calls the synchronous
``jev_runtime.run_runtime_pass`` instead.

Exit codes:
- 0: runtime pass completed with status OK or SKIPPED (locked runtime contract)
- 1: no current bundle / generation mismatch / runtime ERROR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_RESULT_KEYS = (
    "mode",
    "generation_id",
    "status",
    "shadow",
    "gate",
    "counts",
    "reason",
    "error",
    "paths",
    "resumed",
)


def _load_settings():
    from kr_quant.settings import load_settings

    return load_settings(ROOT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev_runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    runtime_pass = sub.add_parser(
        "runtime-pass",
        help="Run one synchronous JEV runtime pass for the current 5-year Season bundle.",
    )
    runtime_pass.add_argument(
        "--generation",
        default=None,
        help="Require this exact current bundle generation id (no historical loads).",
    )
    return parser


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "runtime-pass":
        return 2

    from kr_quant.web import season_snapshot

    settings = _load_settings()
    bundle = season_snapshot.read_bundle(settings, 5)
    if bundle is None:
        _print(
            {
                "status": "NO_CURRENT_BUNDLE",
                "mode": None,
                "generation_id": None,
                "reason": "no current persisted 5-year bundle",
            }
        )
        return 1

    generation_id = bundle.get("generation_id")
    if args.generation is not None and args.generation != generation_id:
        _print(
            {
                "status": "GENERATION_MISMATCH",
                "mode": None,
                "generation_id": generation_id,
                "requested_generation": args.generation,
            }
        )
        return 1

    from kr_quant.research.jev_runtime import run_runtime_pass

    result = run_runtime_pass(settings, bundle=bundle)
    payload = {key: result.get(key) for key in _RESULT_KEYS}
    _print(payload)
    return 0 if result.get("status") in {"OK", "SKIPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
