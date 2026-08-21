"""DART Event Forward Return Backtest Engine.

Overlay research only. Never writes quant_score.
Calculates forward returns, excess returns, win rates, and sample statistics
for classified corporate filing events across multiple trading horizons.
"""

from __future__ import annotations

import math
from datetime import datetime, date
from typing import Any, Sequence

import numpy as np
import pandas as pd

from kr_quant.events.classify import EVENT_KO

DEFAULT_HORIZONS: tuple[int, ...] = (1, 5, 20, 60)


def _format_date(val: Any) -> str:
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    text = str(val or "").replace(".", "-").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def calculate_event_forward_returns(
    events: Sequence[dict[str, Any]],
    prices: pd.DataFrame,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> list[dict[str, Any]]:
    """Calculates forward returns for a list of classified events against a price history dataframe."""
    if not events or prices is None or prices.empty:
        return []

    px = prices.copy()
    date_col = "date" if "date" in px.columns else "trade_date"
    px["date_str"] = px[date_col].apply(_format_date)
    px["ticker_str"] = px["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    px["close_num"] = pd.to_numeric(px["close"], errors="coerce")

    # Pivot prices table for fast lookup: index = date_str, columns = ticker_str
    table = px.pivot_table(index="date_str", columns="ticker_str", values="close_num")
    table = table.sort_index()
    all_dates = list(table.index)
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    # Market average returns for benchmark comparison
    market_mean_series = table.mean(axis=1)

    annotated_events: list[dict[str, Any]] = []

    for ev in events:
        ticker = "".join(ch for ch in str(ev.get("ticker") or "") if ch.isdigit()).zfill(6)
        rep_date = _format_date(ev.get("report_date") or ev.get("rcept_dt") or "")
        event_type = ev.get("event_type") or "OTHER"

        row = dict(ev)
        row["ticker"] = ticker
        row["report_date"] = rep_date
        row["event_type"] = event_type
        row["event_ko"] = EVENT_KO.get(event_type, event_type)
        row["used_in_quant"] = False

        if ticker not in table.columns or not rep_date:
            annotated_events.append(row)
            continue

        cur_idx = None
        if rep_date in date_to_idx:
            cur_idx = date_to_idx[rep_date]
        else:
            for i, d in enumerate(all_dates):
                if d >= rep_date:
                    cur_idx = i
                    break

        if cur_idx is None:
            annotated_events.append(row)
            continue

        start_px = table.iloc[cur_idx].get(ticker)
        if start_px is None or start_px <= 0 or math.isnan(start_px):
            annotated_events.append(row)
            continue

        start_mkt = market_mean_series.iloc[cur_idx]

        for h in horizons:
            fwd_key = f"ret_{h}d"
            excess_key = f"excess_{h}d"
            target_idx = cur_idx + h
            if target_idx < len(all_dates):
                end_px = table.iloc[target_idx].get(ticker)
                if end_px is not None and end_px > 0 and not math.isnan(end_px):
                    fwd_ret = (end_px / start_px) - 1.0
                    row[fwd_key] = round(fwd_ret, 4)

                    end_mkt = market_mean_series.iloc[target_idx]
                    if start_mkt and end_mkt and start_mkt > 0 and end_mkt > 0:
                        mkt_ret = (end_mkt / start_mkt) - 1.0
                        row[excess_key] = round(fwd_ret - mkt_ret, 4)
                    else:
                        row[excess_key] = None
                else:
                    row[fwd_key] = None
                    row[excess_key] = None
            else:
                row[fwd_key] = None
                row[excess_key] = None

        annotated_events.append(row)

    return annotated_events


def summarize_event_backtest(
    annotated_events: Sequence[dict[str, Any]],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    """Aggregates forward returns by event_type into win-rate, excess-return, and distribution statistics."""
    if not annotated_events:
        return {
            "used_in_quant": False,
            "total_events": 0,
            "by_type": {},
            "summary_table": [],
            "horizons": list(horizons),
        }

    groups: dict[str, list[dict[str, Any]]] = {}
    for ev in annotated_events:
        etype = ev.get("event_type") or "OTHER"
        groups.setdefault(etype, []).append(ev)

    by_type: dict[str, Any] = {}
    summary_table: list[dict[str, Any]] = []

    for etype, ev_list in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        type_stats: dict[str, Any] = {
            "event_type": etype,
            "event_ko": EVENT_KO.get(etype, etype),
            "sample_size": len(ev_list),
            "horizons": {},
        }

        row_summary: dict[str, Any] = {
            "event_type": etype,
            "event_ko": EVENT_KO.get(etype, etype),
            "count": len(ev_list),
        }

        for h in horizons:
            fwd_vals = [
                ev[f"ret_{h}d"]
                for ev in ev_list
                if ev.get(f"ret_{h}d") is not None
            ]
            excess_vals = [
                ev[f"excess_{h}d"]
                for ev in ev_list
                if ev.get(f"excess_{h}d") is not None
            ]

            if fwd_vals:
                n = len(fwd_vals)
                mean_ret = float(np.mean(fwd_vals))
                median_ret = float(np.median(fwd_vals))
                win_count = sum(1 for v in fwd_vals if v > 0)
                win_rate = round(win_count / n * 100.0, 1)
                max_ret = float(np.max(fwd_vals))
                min_ret = float(np.min(fwd_vals))

                excess_mean = float(np.mean(excess_vals)) if excess_vals else 0.0
                excess_win_count = sum(1 for v in excess_vals if v > 0) if excess_vals else 0
                excess_win_rate = round(excess_win_count / len(excess_vals) * 100.0, 1) if excess_vals else 0.0

                h_stat = {
                    "valid_samples": n,
                    "mean_return": round(mean_ret * 100.0, 2),
                    "median_return": round(median_ret * 100.0, 2),
                    "win_rate": win_rate,
                    "mean_excess_return": round(excess_mean * 100.0, 2),
                    "excess_win_rate": excess_win_rate,
                    "max_return": round(max_ret * 100.0, 2),
                    "min_return": round(min_ret * 100.0, 2),
                }
                type_stats["horizons"][f"{h}d"] = h_stat

                row_summary[f"win_rate_{h}d"] = win_rate
                row_summary[f"mean_ret_{h}d"] = round(mean_ret * 100.0, 2)
                row_summary[f"excess_{h}d"] = round(excess_mean * 100.0, 2)
            else:
                type_stats["horizons"][f"{h}d"] = None
                row_summary[f"win_rate_{h}d"] = None
                row_summary[f"mean_ret_{h}d"] = None
                row_summary[f"excess_{h}d"] = None

        by_type[etype] = type_stats
        summary_table.append(row_summary)

    return {
        "used_in_quant": False,
        "total_events": len(annotated_events),
        "by_type": by_type,
        "summary_table": summary_table,
        "horizons": list(horizons),
        "disclaimer": "공시 이벤트 사후 수익률은 연구 오버레이입니다. 과거 통계가 미래 수익을 보장하지 않습니다.",
    }


def backtest_events(
    events: Sequence[dict[str, Any]],
    prices: pd.DataFrame,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    """End-to-end event backtest pipeline: calculates forward returns and summarizes statistics."""
    annotated = calculate_event_forward_returns(events, prices, horizons=horizons)
    summary = summarize_event_backtest(annotated, horizons=horizons)
    summary["events"] = annotated
    return summary
