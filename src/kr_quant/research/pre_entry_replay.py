"""Replay ranking of prepared historical inputs, never a full-strategy OOS claim.

The caller supplies historical candidates, eligibility and quotes. This module
does not load today's caches, generate event knowledge, or certify availability.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import pandas as pd

from kr_quant.research.pit_readiness import validate_replay_inputs, _aware
from kr_quant.strategy.pre_entry_ranking import rank_pre_entry_from_inputs

REQUIRED = ("candidates", "eligibility", "quotes")


def payload_hash(payload: dict) -> str:
    """Exact JSON payload checksum, rejecting non-finite values."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def replay_prepared_ranking(partitions: list[dict], *, decision_at: str,
                            market_date: str) -> dict:
    """Three checked envelopes, each with metadata + payload.

    Payload: decision_at, market_date, rows; candidates also require model_id.
    metadata uses the PIT contract (sha256 is payload_hash, original input
    available_at, effective_end, input, partition_id, provenance_ref).
    Previous-day-or-earlier prices only; intraday release precision is not known.
    All inputs must be complete supplied snapshots, not partial ticker patches.
    """
    decision = _aware(decision_at)
    if decision is None:
        raise ValueError("decision_at requires timezone")
    reference = pd.Timestamp(market_date)
    if pd.isna(reference) or reference.tzinfo is not None or reference != reference.normalize():
        raise ValueError("market_date requires a calendar date")
    if reference.date() >= decision.tz_convert("Asia/Seoul").date():
        raise ValueError("Historical replay requires an earlier market_date")
    # Snapshot inputs before validating so callers' containers remain unchanged.
    partitions = copy.deepcopy(partitions)
    contract = validate_replay_inputs([p["metadata"] for p in partitions],
                                     decision_at=decision_at, required_inputs=REQUIRED)
    issues = list(contract["issues"])
    by_kind = {}
    for partition in partitions:
        meta, payload = partition["metadata"], partition["payload"]
        kind = meta.get("input")
        if kind not in REQUIRED or kind in by_kind:
            issues.append({"input": kind, "code": "UNEXPECTED_OR_MULTIPLE_SNAPSHOT"})
        by_kind[kind] = payload
        if meta.get("sha256") != payload_hash(payload):
            issues.append({"input": kind, "code": "PAYLOAD_HASH_MISMATCH"})
        if (_aware(payload.get("decision_at")) != decision
                or payload.get("market_date") != reference.date().isoformat()):
            issues.append({"input": kind, "code": "CONTEXT_MISMATCH"})
    result = {"kind": "PREPARED_INPUT_RANK_REPLAY", "verified": False,
              "decision_at": decision_at, "market_date": market_date,
              "status": "BLOCKED", "rows": [], "issues": issues}
    if issues:
        return result
    try:
        if not str(by_kind["candidates"].get("model_id") or "").strip():
            raise ValueError("MODEL_ID_MISSING")
        indices = {}
        for kind in REQUIRED:
            rows = by_kind[kind]["rows"]
            if not isinstance(rows, list):
                raise ValueError("ROWS_INVALID")
            indexed = {}
            for row in rows:
                ticker = row.get("ticker")
                if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isalnum():
                    raise ValueError("TICKER_INVALID")
                key = (ticker, row.get("pattern_id")) if kind == "candidates" else ticker
                if key in indexed:
                    raise ValueError("DUPLICATE_ROW")
                indexed[key] = row
                if kind == "eligibility" and type(row.get("eligible")) is not bool:
                    raise ValueError("ELIGIBILITY_UNKNOWN")
                if kind == "quotes":
                    if row.get("as_of") != market_date:
                        raise ValueError("QUOTE_DATE_MISMATCH")
                    _finite(row.get("last_close"))
                if kind == "candidates":
                    if not isinstance(row.get("pattern_id"), str) or not row["pattern_id"]:
                        raise ValueError("PATTERN_ID_MISSING")
                    _finite(row.get("seasonality_score"))
                    peak = row.get("remaining_peak") or {}
                    if type(peak.get("available")) is not bool:
                        raise ValueError("PEAK_STATUS_UNKNOWN")
                    if peak["available"]:
                        _finite(peak.get("remaining_p50"))
                        if peak.get("price_as_of") != market_date:
                            raise ValueError("PEAK_DATE_MISMATCH")
            indices[kind] = indexed
        candidates = by_kind["candidates"]["rows"]
        for row in candidates:
            if row["ticker"] not in indices["eligibility"] or row["ticker"] not in indices["quotes"]:
                raise ValueError("CANDIDATE_INPUT_MISSING")
        clean = {ticker for ticker, row in indices["eligibility"].items() if row["eligible"]}
        result["rows"] = rank_pre_entry_from_inputs(candidates, clean_set=clean, quotes=indices["quotes"])
        result.update(status="RANKED_UNVERIFIED", model_id=by_kind["candidates"]["model_id"],
                      input_count=len(candidates), excluded_count=len(candidates)-len(result["rows"]))
    except (ValueError, TypeError, KeyError) as exc:
        result["issues"].append({"code": str(exc)})
    return result


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("FINITE_NUMBER_REQUIRED")
