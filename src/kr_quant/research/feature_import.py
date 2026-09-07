"""Read-only import of explicitly versioned features and per-case gap ledger.

Legacy output dates are not relabelled as public availability. This importer
accepts the historical_features record contract and reports incompatible local
sources, rather than silently constructing historical values from current data.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from kr_quant.hashing import sha256_file
from kr_quant.research.historical_features import KINDS, select_as_of_features

REQUIRED_COLUMNS = {"ticker", "kind", "available_at", "effective_at", "valid_until", "source", "data", "sha256"}
LEGACY = {
    "financial_features": "data/output/daily_history.parquet",
    "flow": "data/cache/investor_flow.json",
    "event": "data/research_inputs/event_history.json",
}


def load_feature_archive(path: Path) -> tuple[list[dict], dict]:
    """Do not manufacture timezones, expiry, fields, checksums or event history."""
    info = {"path": str(path), "status": "MISSING", "rows": 0}
    if not path.is_file():
        return [], info
    before = sha256_file(path)
    try:
        if path.suffix.lower() == ".parquet":
            file = pq.ParquetFile(path)
            columns = set(file.schema_arrow.names)
            info["rows"] = file.metadata.num_rows
            missing = sorted(REQUIRED_COLUMNS - columns)
            if missing:
                info.update(status="INCOMPATIBLE_SCHEMA", missing_columns=missing)
                return [], info
            rows = file.read(columns=sorted(REQUIRED_COLUMNS)).to_pylist()
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = value if isinstance(value, list) else value.get("records", value.get("rows")) if isinstance(value, dict) else None
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                info.update(status="INCOMPATIBLE_SCHEMA")
                return [], info
            info["rows"] = len(rows)
            missing = sorted(set().union(*(REQUIRED_COLUMNS - set(row) for row in rows))) if rows else []
            if missing:
                info.update(status="INCOMPATIBLE_SCHEMA", missing_columns=missing)
                return [], info
        if any(row.get("kind") not in KINDS for row in rows):
            info.update(status="INVALID_KIND")
            return [], info
        if any(not isinstance(row.get("ticker"), str) or len(row["ticker"]) != 6
               or not row["ticker"].isascii() or not row["ticker"].isalnum()
               or not isinstance(row.get("data"), dict) for row in rows):
            info.update(status="INCOMPATIBLE_SCHEMA")
            return [], info
        info.update(status="LOADED_UNVERIFIED")
        return rows, info
    except (ValueError, OSError, TypeError) as exc:
        info.update(status="READ_ERROR", error_type=type(exc).__name__)
        return [], info
    finally:
        info["sha256"] = before
        info["source_unchanged"] = path.is_file() and sha256_file(path) == before
        if not info["source_unchanged"]:
            # Caller rejects rows from a changing source, including a return
            # already prepared in the try block.
            info["status"] = "SOURCE_CHANGED"


def import_feature_cases(root: Path, *, tickers: list[str], decisions: list[str],
                         archive: Path | None = None) -> dict:
    """One explicit ticker × decision case per ledger row, including failures.

    Without an explicit archive, inspect known local sources for compatibility.
    This is not historical-universe coverage: tickers are a user/test cohort.
    """
    if (not tickers or len(tickers) != len(set(tickers))
            or any(not isinstance(t, str) or len(t) != 6 or not t.isascii() or not t.isalnum() for t in tickers)):
        raise ValueError("Provide unique six-character ticker codes")
    if not decisions or len(decisions) != len(set(decisions)):
        raise ValueError("Provide unique decision timestamps")
    from kr_quant.research.pit_readiness import _aware
    if any(_aware(d) is None for d in decisions):
        raise ValueError("Decision timestamps require timezone")
    records, sources, fatal = [], [], False
    paths = [archive] if archive is not None else [root / p for p in LEGACY.values()]
    for path in paths:
        loaded, info = load_feature_archive(path)
        sources.append(info)
        if info["status"] == "LOADED_UNVERIFIED":
            records.extend(loaded)
        elif info["status"] in {"SOURCE_CHANGED", "READ_ERROR", "INVALID_KIND", "INCOMPATIBLE_SCHEMA"}:
            fatal = True
    grouped = {}
    for row in records:
        grouped.setdefault(row["ticker"], []).append(row)
    cases, reasons = [], Counter()
    for decision in decisions:
        for ticker in tickers:
            result = select_as_of_features(grouped.get(ticker, []), ticker=ticker, decision_at=decision)
            codes = list(result["issues"])
            if fatal:
                codes.append("SOURCE_IMPORT_BLOCKED")
            codes = sorted(set(codes))
            reasons.update(codes)
            selected = result["selected"] if not codes else {}
            cases.append({"ticker": ticker, "decision_at": decision,
                          "status": "BLOCKED" if codes else "SELECTED_UNVERIFIED",
                          "issues": codes, "selected": selected})
    blocked = sum(c["status"] == "BLOCKED" for c in cases)
    return {"schema": 1, "kind": "HISTORICAL_FEATURE_IMPORT", "verified": False,
            "status": "BLOCKED" if blocked == len(cases) else "PARTIAL" if blocked else "IMPORTED_UNVERIFIED",
            "case_count": len(cases), "blocked_count": blocked,
            "selected_count": len(cases) - blocked, "reason_counts": dict(sorted(reasons.items())),
            "sources": sources, "cases": cases,
            "scope": "Explicit ticker/decision cohort; not full historical universe or strategy OOS"}
