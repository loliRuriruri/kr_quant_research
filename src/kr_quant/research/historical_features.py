"""As-of feature version selection and seasonal scoring, without current I/O.

This accepts already calculated historical financial features, not raw DART
statements. Original availability/source truth must be independently audited.
"""
from __future__ import annotations

import copy
import math

from kr_quant.research.pit_readiness import _aware
from kr_quant.research.pre_entry_replay import payload_hash
from kr_quant.strategy.discovery_engine import pattern_from_month_stat
from kr_quant.strategy.event_explainer import explain_and_score_pattern

KINDS = ("financial_features", "flow", "event")
FIELDS = {"financial_features": ("quant_score", "return_3m", "volume_ratio"),
          "flow": ("foreign_net", "institution_net")}


def select_as_of_features(records: list[dict], *, ticker: str, decision_at: str) -> dict:
    """Choose newest effective version known by decision time, with expiry.

    Record: ticker, kind, available_at, effective_at, valid_until (all aware),
    source, data, sha256=payload_hash(data). A newer expired record cannot cause
    fallback to an older still-valid record. Ambiguous same-version rows fail.
    Future public records are ignored before inspecting their payload.
    """
    decision = _aware(decision_at)
    if decision is None:
        raise ValueError("decision_at requires timezone")
    groups = {kind: [] for kind in KINDS}
    issues = []
    for record in copy.deepcopy(records):
        if record.get("ticker") != ticker or record.get("kind") not in KINDS:
            continue
        available = _aware(record.get("available_at"))
        effective = _aware(record.get("effective_at"))
        if available is None or effective is None:
            issues.append("INVALID_INPUT_TIMESTAMP")
            continue
        if available > decision or effective > decision:
            continue
        groups[record["kind"]].append((effective, available, record))
    chosen = {}
    for kind, values in groups.items():
        if not values:
            issues.append(f"MISSING_{kind.upper()}")
            continue
        values.sort(key=lambda item: (item[0], item[1]), reverse=True)
        effective, available, row = values[0]
        if len(values) > 1 and values[1][:2] == values[0][:2]:
            issues.append(f"AMBIGUOUS_{kind.upper()}")
            continue
        until = _aware(row.get("valid_until"))
        if until is None or until < decision or until < effective or until < available:
            issues.append(f"EXPIRED_OR_INVALID_{kind.upper()}")
            continue
        try:
            data = row["data"]
            if not isinstance(data, dict) or payload_hash(data) != row.get("sha256"):
                raise ValueError("HASH")
            if not isinstance(row.get("source"), str) or not row["source"].strip():
                raise ValueError("SOURCE")
            for name in FIELDS.get(kind, ()):
                v = data.get(name)
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ValueError("FEATURE")
            if kind == "financial_features" and (not 0 <= data["quant_score"] <= 100 or data["volume_ratio"] < 0):
                raise ValueError("RANGE")
            chosen[kind] = row
        except (KeyError, TypeError, ValueError):
            issues.append(f"INVALID_{kind.upper()}")
    return {"status": "BLOCKED" if issues else "SELECTED_UNVERIFIED", "verified": False,
            "selected": chosen if not issues else {}, "issues": issues}


def score_historical_pattern(*, records: list[dict], ticker: str, company: str,
                             market: str, month_stat: dict, decision_at: str,
                             lookback_years: int = 5) -> dict:
    """Score one historical monthly pattern; no peak/ranking/returns certification."""
    selection = select_as_of_features(records, ticker=ticker, decision_at=decision_at)
    result = {"kind": "HISTORICAL_PATTERN_SCORE", "verified": False,
              "status": "BLOCKED", "issues": selection["issues"], "row": None}
    if selection["issues"]:
        return result
    selected = selection["selected"]
    try:
        pattern = pattern_from_month_stat(ticker, company, market, month_stat,
                                         lookback_years=lookback_years, as_of_date=decision_at)
        if pattern is None or pattern.sample_count < 2 or pattern.win_rate < .5:
            result.update(status="EXCLUDED", issues=["PATTERN_NOT_ELIGIBLE"])
            return result
        # Only declared numerical fields reach the scorer; no arbitrary overrides.
        features = {key: selected[kind]["data"][key] for kind, names in FIELDS.items() for key in names}
        context = dict(selected["event"]["data"], source=selected["event"]["source"])
        row = explain_and_score_pattern(pattern, features, event_context=context)
        result.update(status="SCORED_UNVERIFIED", row=row,
                      lineage={kind: {k: rec[k] for k in ("source", "available_at", "effective_at", "valid_until", "sha256")}
                               for kind, rec in selected.items()})
    except (KeyError, TypeError, ValueError, OverflowError):
        result["issues"] = ["INVALID_PATTERN_OR_EVENT"]
    return result
