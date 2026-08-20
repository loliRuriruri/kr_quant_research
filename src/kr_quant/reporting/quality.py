from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.models import RunContext, ScoredName


def build_quality_report(
    ctx: RunContext,
    names: list[ScoredName],
    records: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    df = pd.DataFrame(records) if records else pd.DataFrame()
    eligible = [n for n in names if n.universe_eligible]
    excluded = [n for n in names if not n.universe_eligible]
    reason_counts: dict[str, int] = {}
    for n in excluded:
        for r in n.hard_reasons or n.exclusion_reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    missing_metrics: dict[str, int] = {}
    for n in eligible:
        for k, m in n.metrics.items():
            if m.state in {"DATA_MISSING", "INSUFFICIENT_HISTORY", "SCOPE_MISMATCH"}:
                missing_metrics[k] = missing_metrics.get(k, 0) + 1
    report = {
        "run_id": ctx.run_id,
        "as_of_date": ctx.as_of_date.isoformat(),
        "status": ctx.status,
        "model_version": ctx.model_version,
        "config_hash": ctx.config_hash,
        "source_bundle_hash": ctx.source_bundle_hash,
        "result_hash": ctx.result_hash,
        "warnings": ctx.warnings,
        "counts": {
            "scored": len(names),
            "universe_eligible": len(eligible),
            "excluded": len(excluded),
            "top100_eligible": int(sum(1 for n in names if n.top100_eligible)),
            "top20_eligible": int(sum(1 for n in names if n.top20_eligible)),
        },
        "exclusion_reason_counts": reason_counts,
        "missing_metric_counts": missing_metrics,
        "coverage": {
            "median": float(df["weighted_metric_coverage"].median()) if not df.empty else None,
            "mean": float(df["weighted_metric_coverage"].mean()) if not df.empty else None,
        },
        "data_confidence": {
            "median": float(df["data_confidence"].median()) if not df.empty else None,
            "below_70": int((df["data_confidence"] < 70).sum()) if not df.empty else 0,
        },
        **(extra or {}),
    }
    return report


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
