# -*- coding: utf-8 -*-
"""One committed output generation for ranking artifacts.

Individual parquet/csv/json writes are already atomic, but a reader can still
see yesterday's quality report next to today's ranking file. This module keeps
a generation directory and swaps a single current_manifest.json pointer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.atomic_io import write_csv_atomic, write_json_atomic, write_parquet_atomic
from kr_quant.hashing import sha256_file
from kr_quant.settings import Settings

MANIFEST_NAME = "current_manifest.json"
STATE_NAME = "generation_state.json"
GENERATION_FILES = (
    "latest_all_stocks.parquet",
    "latest_top20.csv",
    "latest_top100.csv",
    "data_quality_report.json",
    "universe_evidence.json",
    "latest_universe_snapshot.parquet",
    "price_integrity_issues.parquet",
)


def manifest_path(settings: Settings) -> Path:
    return settings.output_dir / MANIFEST_NAME


def state_path(settings: Settings) -> Path:
    return settings.output_dir / STATE_NAME


def generation_dir(settings: Settings, run_id: str) -> Path:
    return settings.output_dir / "generations" / str(run_id)


def load_manifest(settings: Settings) -> dict[str, Any] | None:
    path = manifest_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_updating(settings: Settings) -> bool:
    path = state_path(settings)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(payload, dict) and payload.get("updating"))


def mark_updating(settings: Settings, run_id: str, *, updating: bool) -> None:
    write_json_atomic(
        state_path(settings),
        {
            "updating": updating,
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def current_output_path(settings: Settings, filename: str) -> Path:
    """Return the committed generation file, or the legacy latest path."""
    manifest = load_manifest(settings)
    if manifest:
        directory = Path(str(manifest.get("generation_dir") or ""))
        candidate = directory / filename
        if directory.exists() and candidate.exists():
            return candidate
    return settings.output_dir / filename


def begin_generation(settings: Settings, run_id: str) -> Path:
    folder = generation_dir(settings, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    mark_updating(settings, run_id, updating=True)
    return folder


def _file_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "sha256": sha256_file(path) if path.exists() else None,
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    suffix = path.suffix.lower()
    if suffix == ".parquet" and path.exists():
        frame = pd.read_parquet(path)
        info["rows"] = int(len(frame))
        if "as_of_date" in frame.columns:
            values = pd.to_datetime(frame["as_of_date"], errors="coerce").dropna()
            if not values.empty:
                info["as_of_date"] = values.max().date().isoformat()
    elif suffix == ".csv" and path.exists():
        frame = pd.read_csv(path, dtype=str)
        info["rows"] = int(len(frame))
    elif suffix == ".json" and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("as_of_date"):
            info["as_of_date"] = str(payload.get("as_of_date"))[:10]
            info["run_id"] = payload.get("run_id")
    return info


def validate_generation(folder: Path, *, as_of: str, run_id: str) -> dict[str, Any]:
    files: dict[str, Any] = {}
    missing: list[str] = []
    mismatched: list[str] = []
    for name in GENERATION_FILES:
        path = folder / name
        if not path.exists():
            missing.append(name)
            continue
        info = _file_info(path)
        files[name] = info
        observed = info.get("as_of_date")
        if observed and observed != as_of:
            mismatched.append(f"{name}:{observed}")
        if name == "data_quality_report.json" and info.get("run_id") and info.get("run_id") != run_id:
            mismatched.append(f"quality_run_id:{info.get('run_id')}")
    if missing:
        raise IOError(f"generation incomplete missing={missing}")
    if mismatched:
        raise IOError(f"generation as_of/run_id mismatch {mismatched}")
    quality_as_of = (files.get("data_quality_report.json") or {}).get("as_of_date")
    stocks_as_of = (files.get("latest_all_stocks.parquet") or {}).get("as_of_date")
    if quality_as_of and stocks_as_of and quality_as_of != stocks_as_of:
        raise IOError(f"mixed generation quality={quality_as_of} stocks={stocks_as_of}")
    return files


def commit_generation(
    settings: Settings,
    *,
    run_id: str,
    as_of: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    folder = generation_dir(settings, run_id)
    files = validate_generation(folder, as_of=as_of, run_id=run_id)
    manifest = {
        "run_id": run_id,
        "as_of_date": as_of,
        "generation_dir": str(folder),
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        **(extra or {}),
    }
    write_json_atomic(manifest_path(settings), manifest)
    mark_updating(settings, run_id, updating=False)
    return manifest


def publish_aliases(settings: Settings, run_id: str) -> None:
    """Copy the committed generation to legacy latest_* names after the pointer swap."""
    folder = generation_dir(settings, run_id)
    dest = settings.output_dir
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {
        "latest_all_stocks.parquet": write_parquet_atomic,
        "latest_universe_snapshot.parquet": write_parquet_atomic,
        "price_integrity_issues.parquet": write_parquet_atomic,
        "latest_top20.csv": None,
        "latest_top100.csv": None,
        "data_quality_report.json": None,
        "universe_evidence.json": None,
    }
    for name, writer in mapping.items():
        source = folder / name
        if not source.exists():
            continue
        target = dest / name
        if writer is write_parquet_atomic:
            writer(pd.read_parquet(source), target)
        elif name.endswith(".csv"):
            write_csv_atomic(pd.read_csv(source, dtype=str), target)
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
            write_json_atomic(target, payload)


def publish_run_generation(
    settings: Settings,
    *,
    run_id: str,
    as_of: str,
    all_stocks: pd.DataFrame,
    top100: pd.DataFrame,
    top20: pd.DataFrame,
    quality: dict[str, Any],
    universe_evidence: dict[str, Any],
    universe_snapshot: pd.DataFrame,
    price_integrity_issues: pd.DataFrame,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    folder = begin_generation(settings, run_id)
    write_parquet_atomic(all_stocks, folder / "latest_all_stocks.parquet")
    write_csv_atomic(top100, folder / "latest_top100.csv")
    write_csv_atomic(top20, folder / "latest_top20.csv")
    write_json_atomic(folder / "data_quality_report.json", quality)
    write_json_atomic(folder / "universe_evidence.json", universe_evidence)
    write_parquet_atomic(universe_snapshot, folder / "latest_universe_snapshot.parquet")
    write_parquet_atomic(price_integrity_issues, folder / "price_integrity_issues.parquet")
    manifest = commit_generation(settings, run_id=run_id, as_of=as_of, extra=extra)
    publish_aliases(settings, run_id)
    return manifest
