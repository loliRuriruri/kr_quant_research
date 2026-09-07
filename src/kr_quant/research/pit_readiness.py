"""Read-only source inventory and fail-closed contracts for historical replay.

Inventory is NOT certification of historical availability. No production ranking,
collector, cache or portfolio is modified or called by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import pandas as pd
import pyarrow.parquet as pq

from kr_quant.hashing import sha256_file


SOURCES = {
    "prices": ("data/staged/live/prices.parquet", ("ticker", "trade_date")),
    "master": ("data/staged/live/master.parquet", ("ticker",)),
    "listing_history": ("data/staged/live/listing_history.parquet", ("ticker", "event_type", "event_date")),
    "financial_facts": ("data/staged/live/financial_facts.parquet", ("ticker", "canonical_account", "fs_div", "period_start", "period_end", "rcept_no")),
    "scores": ("data/output/daily_history.parquet", ("run_id", "ticker")),
    "universe": ("data/output/latest_universe_snapshot.parquet", ("ticker", "as_of_date")),
    "status": ("data/raw/status/krx_status.csv", ("ticker", "as_of_date")),
}
DATE_COLUMNS = ("trade_date", "event_date", "list_date", "period_end", "rcept_dt",
                "available_date", "as_of_date", "created_at", "captured_at", "cutoff_ts", "decision_date")


def _aware(value):
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            return None
        return stamp.tz_convert("UTC")
    except (ValueError, TypeError, OverflowError):
        return None


def validate_replay_inputs(records: list[dict], *, decision_at: str,
                           required_inputs: tuple[str, ...]) -> dict:
    """Structural preflight only; caller must independently verify provenance.

    Each record identifies one immutable input partition. available_at is the
    original public availability, NOT the date a backfill was downloaded.
    effective_end is the latest observation used by that partition. Hash syntax
    is checked here; bytes/provenance and universe completeness are not certified.
    A passing contract must never be presented as verified investment performance.
    """
    decision = _aware(decision_at)
    if (decision is None or not required_inputs
            or any(not isinstance(name, str) or not name.strip() for name in required_inputs)
            or len(set(required_inputs)) != len(required_inputs)):
        raise ValueError("aware decision_at and unique nonempty required_inputs are required")
    issues, seen, found = [], set(), set()
    for index, row in enumerate(records):
        kind, key = row.get("input"), row.get("partition_id")
        if not isinstance(kind, str) or not isinstance(key, str) or not key.strip():
            issues.append({"index": index, "code": "IDENTITY_MISSING"})
            continue
        identity = (kind, key)
        if identity in seen:
            issues.append({"index": index, "code": "DUPLICATE_PARTITION"})
        seen.add(identity)
        found.add(kind)
        for name in ("available_at", "effective_end"):
            stamp = _aware(row.get(name))
            if stamp is None:
                issues.append({"index": index, "code": f"{name.upper()}_INVALID"})
            elif stamp > decision:
                issues.append({"index": index, "code": f"{name.upper()}_FUTURE"})
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
            issues.append({"index": index, "code": "HASH_INVALID"})
        if not isinstance(row.get("provenance_ref"), str) or not row["provenance_ref"].strip():
            issues.append({"index": index, "code": "PROVENANCE_MISSING"})
    issues.extend({"input": name, "code": "INPUT_MISSING"} for name in required_inputs if name not in found)
    return {"status": "BLOCKED" if issues else "CONTRACT_VALID",
            "verified": False, "issues": issues}


def profile_source(root: Path, relative: str, keys: tuple[str, ...]) -> dict:
    path = root / relative
    result = {"path": relative, "historical_availability": "UNVERIFIED"}
    if not path.is_file():
        return {**result, "status": "MISSING"}
    before = sha256_file(path)
    try:
        if path.suffix == ".parquet":
            parquet = pq.ParquetFile(path)
            schema = parquet.schema_arrow
            names = schema.names
            columns = sorted(set(keys + DATE_COLUMNS + ("revision_id", "is_correction", "is_withdrawn")) & set(names))
            frame = parquet.read(columns=columns).to_pandas()
            result.update(rows=parquet.metadata.num_rows, columns={f.name: str(f.type) for f in schema})
        else:
            frame = pd.read_csv(path, dtype=str)
            result.update(rows=len(frame), columns={c: str(t) for c, t in frame.dtypes.items()})
        result["date_ranges"] = {}
        for column in DATE_COLUMNS:
            if column in frame:
                values = pd.to_datetime(frame[column], errors="coerce", utc=True)
                result["date_ranges"][column] = {
                    "min": None if not values.notna().any() else values.min().isoformat(),
                    "max": None if not values.notna().any() else values.max().isoformat(),
                    "null_or_invalid": int(values.isna().sum()),
                    "distinct_days": int(values.dt.date.nunique()),
                }
        result["candidate_key"] = list(keys)
        result["missing_key_columns"] = [k for k in keys if k not in frame]
        if keys and not result["missing_key_columns"]:
            result["duplicate_key_rows"] = int(frame.duplicated(list(keys), keep=False).sum())
            result["null_key_rows"] = int(frame[list(keys)].isna().any(axis=1).sum())
        if "ticker" in frame:
            result["tickers"] = int(frame.ticker.nunique())
        if "available_date" in frame and "period_end" in frame:
            available = pd.to_datetime(frame.available_date, errors="coerce", utc=True)
            period = pd.to_datetime(frame.period_end, errors="coerce", utc=True)
            result["available_equals_period_end"] = int((available.notna() & (available == period)).sum())
        if "rcept_no" in frame:
            result["receipt_missing"] = int((frame.rcept_no.isna() | frame.rcept_no.astype(str).str.strip().eq("")).sum())
        for column in ("revision_id", "is_correction", "is_withdrawn", "event_type"):
            if column in frame:
                result[column + "_counts"] = {str(k): int(v) for k, v in frame[column].value_counts(dropna=False).items()}
        result["status"] = "PROFILED"
    except (ValueError, OSError, KeyError) as exc:
        result.update(status="READ_ERROR", error_type=type(exc).__name__)
    after = sha256_file(path)
    result.update(sha256=before, source_unchanged=before == after)
    if before != after:
        result["status"] = "SOURCE_CHANGED"
    return result


def audit_local_sources(root: Path) -> dict:
    """Known production inputs, not an exhaustive disk search or PIT backtest."""
    return {
        "schema": 1, "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "NOT_READY", "verified": False,
        "scope": "Actual seasonal pre-entry historical replay; known local production sources",
        "sources": {name: profile_source(root, path, keys) for name, (path, keys) in SOURCES.items()},
        "unconnected_requirements": [
            "Historical universe/status including delisted securities and original availability",
            "As-of financial revisions and historical Quant/flow inputs without latest-value fallback",
            "As-of event knowledge/model version (event confidence affects seasonal score)",
            "Official sessions, corporate-action adjustment evidence, execution and cost assumptions",
            "Production selector with injected time and future-data invariance tests",
        ],
        "limitations": ["Column presence and hashes do not prove original availability or truth.",
                        "Candidate-key duplicate counts are diagnostics, not automatic deletion rules.",
                        "UTC parsing in profiles is for date summaries only, not proof of timezone precision.",
                        "Input contract is a separate preflight; production replay is not connected yet."],
    }
