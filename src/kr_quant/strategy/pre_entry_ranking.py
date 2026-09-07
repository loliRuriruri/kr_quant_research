"""Deterministic pre-entry ordering with explicitly supplied inputs; no I/O."""
from typing import Any
import numpy as np

PRE_ENTRY_STAGE_WEIGHT: dict[str, int] = {
    "TODAY_ENTRY": 100,
    "PRE_ENTRY_15": 80,
    "PRE_ENTRY_30": 60,
    "ACCUMULATE_60": 40,
    "RALLY_ACTIVE": 30,
    "EXIT_PEAK": 10,
}


def rank_pre_entry_from_inputs(rows: list[dict[str, Any]], *, clean_set: set[str],
                               quotes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {key for key, weight in PRE_ENTRY_STAGE_WEIGHT.items() if weight >= 40}
    candidates = [dict(row) for row in rows if row.get("entry_stage") in allowed]
    valid_rows: list[dict[str, Any]] = []
    for row in candidates:
        ticker = str(row.get("ticker") or "").zfill(6)
        if ticker not in clean_set:
            continue
        remaining = row.get("remaining_peak") or {}
        if not bool(remaining.get("available")):
            continue
        quote = quotes.get(ticker, {})
        close = quote.get("last_close")
        if close is None or not np.isfinite(close) or close < 1000.0:
            continue
        if remaining.get("price_as_of") and str(remaining["price_as_of"]) != str(quote.get("as_of")):
            continue
        row["last_close"] = close
        row["chg_pct"] = quote.get("chg_pct")
        row["price_as_of"] = quote.get("as_of")
        valid_rows.append(row)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        remaining = row.get("remaining_peak") or {}
        remaining_p50 = remaining.get("remaining_p50")
        return (
            -PRE_ENTRY_STAGE_WEIGHT.get(str(row.get("entry_stage") or ""), 0),
            -float(row.get("seasonality_score") or 0),
            -float(remaining_p50 if remaining_p50 is not None else -99),
            str(row.get("ticker") or ""),
            str(row.get("pattern_id") or ""),
        )

    valid_rows.sort(key=sort_key)
    for index, row in enumerate(valid_rows, start=1):
        row["pre_entry_rank"] = index
    return valid_rows
