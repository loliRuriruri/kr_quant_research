# -*- coding: utf-8 -*-
"""Official corporate-action events and split-adjusted prices.

Raw OHLC stays untouched. Adjustment factors are applied only when an event is
explicitly confirmed. Unexplained price jumps are never treated as splits.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from kr_quant.universe.identifiers import canonical_ticker

EVENT_COLUMNS = [
    "ticker",
    "event_type",
    "ex_date",
    "event_date",
    "ratio",
    "cash_amount",
    "source",
    "confirmed",
    "notes",
]
# Paid rights and reductions require subscription/cash terms. A share ratio
# alone is not evidence for a pure split adjustment.
RATIO_TYPES = frozenset({"SPLIT", "MERGE", "BONUS"})
DIVIDEND_TYPES = frozenset({"DIVIDEND"})
EVENT_TYPES = RATIO_TYPES | DIVIDEND_TYPES | {"MERGER", "RIGHTS", "REDUCTION"}


def empty_actions() -> pd.DataFrame:
    return pd.DataFrame(columns=EVENT_COLUMNS)


def load_corporate_actions(path) -> pd.DataFrame:
    """Load confirmed official events. Missing file is an empty feed, not a guess."""
    from pathlib import Path

    file = Path(path) if path is not None else None
    if file is None or not file.exists():
        return empty_actions()
    try:
        frame = pd.read_parquet(file)
    except Exception:  # noqa: BLE001
        return empty_actions()
    return normalize_actions(frame)


def load_actions_from_settings(settings) -> pd.DataFrame:
    live = settings.staged_dir / "live" / "corporate_actions.parquet"
    demo = settings.staged_dir / "demo" / "corporate_actions.parquet"
    path = live if live.exists() else demo
    return load_corporate_actions(path)


def normalize_actions(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return empty_actions()
    work = frame.copy()
    for column in EVENT_COLUMNS:
        if column not in work.columns:
            work[column] = None
    work["ticker"] = work["ticker"].map(canonical_ticker)
    work = work[work["ticker"].astype(str) != ""]
    work["event_type"] = work["event_type"].astype(str).str.upper().str.strip()
    work = work[work["event_type"].isin(EVENT_TYPES)]
    work["ex_date"] = pd.to_datetime(work["ex_date"], errors="coerce").dt.date
    work = work.dropna(subset=["ex_date"])
    work["ratio"] = pd.to_numeric(work["ratio"], errors="coerce")
    work["cash_amount"] = pd.to_numeric(work["cash_amount"], errors="coerce")
    work["confirmed"] = work["confirmed"].map(lambda value: value is True or str(value).strip().lower() in {"1", "true", "yes"})
    work = work[work["confirmed"]]
    work["source"] = work["source"].fillna("").astype(str)
    work = work[work["source"].str.len() > 0]
    ratio_ok = work["event_type"].isin(RATIO_TYPES) & work["ratio"].notna() & (work["ratio"] > 0)
    cash_ok = work["event_type"].isin(DIVIDEND_TYPES) & work["cash_amount"].notna() & (work["cash_amount"] > 0)
    work = work[ratio_ok | cash_ok].copy()
    return work[EVENT_COLUMNS].drop_duplicates(["ticker", "event_type", "ex_date"]).reset_index(drop=True)


def apply_official_adjustments(prices: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    """Add adj_factor / adj OHLC / price_return / total_return. Raw columns stay."""
    if prices is None or prices.empty:
        return prices
    out = prices.copy()
    date_column = "trade_date" if "trade_date" in out.columns else "date"
    out["_ca_date"] = pd.to_datetime(out[date_column], errors="coerce").dt.date
    out['_ca_order'] = range(len(out))
    out = out.sort_values(['ticker', '_ca_date'] if 'ticker' in out else ['_ca_date'])
    out["adj_factor"] = 1.0
    events = normalize_actions(actions)
    if not events.empty and out['_ca_date'].notna().any():
        events = events[events['ex_date'] <= out['_ca_date'].max()]
    if not events.empty and "ticker" in out.columns:
        out["ticker"] = out["ticker"].map(lambda value: canonical_ticker(value) or str(value))
        factors = []
        for ticker, group in out.groupby("ticker", sort=False):
            ticker_events = events[events["ticker"] == ticker]
            factor = pd.Series(1.0, index=group.index)
            if not ticker_events.empty:
                dates = group["_ca_date"]
                for rec in ticker_events.sort_values("ex_date", ascending=False).itertuples(index=False):
                    if rec.event_type in RATIO_TYPES and rec.ratio and rec.ratio > 0:
                        factor.loc[dates < rec.ex_date] = factor.loc[dates < rec.ex_date] * (1.0 / float(rec.ratio))
            factors.append(factor)
        out["adj_factor"] = pd.concat(factors).reindex(out.index)
    for column in ("open", "high", "low", "close"):
        if column in out.columns:
            raw = pd.to_numeric(out[column], errors="coerce")
            out[f"adj_{column}"] = raw * out["adj_factor"]
    close = pd.to_numeric(out.get("close"), errors="coerce") if "close" in out.columns else None
    adj_close = pd.to_numeric(out.get("adj_close"), errors="coerce") if "adj_close" in out.columns else None
    if adj_close is not None:
        prev = adj_close.groupby(out["ticker"] if "ticker" in out.columns else out.index, sort=False).shift()
        out["price_return"] = (adj_close / prev - 1).where(prev > 0)
    else:
        out["price_return"] = None
    out["dividend_return"] = 0.0
    if not events.empty and close is not None:
        cash_events = events[events["event_type"].isin(DIVIDEND_TYPES)]
        if not cash_events.empty:
            prev_close = close.groupby(out["ticker"], sort=False).shift()
            for rec in cash_events.itertuples(index=False):
                mask = (out["ticker"] == rec.ticker) & (out["_ca_date"] == rec.ex_date)
                out.loc[mask, "dividend_return"] = float(rec.cash_amount) / prev_close.loc[mask].where(prev_close.loc[mask] > 0)
    out["total_return"] = pd.to_numeric(out["price_return"], errors="coerce").fillna(0) + pd.to_numeric(
        out["dividend_return"], errors="coerce"
    ).fillna(0)
    return out.sort_values('_ca_order').drop(columns=["_ca_date", '_ca_order'])


def explain_breaks_with_actions(issues: pd.DataFrame, actions: pd.DataFrame | None) -> pd.DataFrame:
    """Label raw discontinuities that fall on an official ex-date. Do not invent events."""
    if issues is None or issues.empty:
        return issues
    events = normalize_actions(actions)
    out = issues.copy()
    out["official_event_type"] = None
    out["official_ex_date"] = None
    out["official_source"] = None
    out["explained_by_official_action"] = False
    if events.empty:
        return out
    events = events.copy()
    events["ex_date"] = events["ex_date"].map(lambda value: str(value)[:10])
    for idx, row in out.iterrows():
        ticker = canonical_ticker(row.get("ticker"))
        dates = {str(row.get("trade_date") or "")[:10], str(row.get("previous_trade_date") or "")[:10]}
        dates.discard("")
        hit = events[(events["ticker"] == ticker) & (events["ex_date"].isin(dates))]
        if hit.empty:
            continue
        rec = hit.iloc[0]
        out.at[idx, "official_event_type"] = rec["event_type"]
        out.at[idx, "official_ex_date"] = rec["ex_date"]
        out.at[idx, "official_source"] = rec["source"]
        out.at[idx, "explained_by_official_action"] = True
        if rec["event_type"] in RATIO_TYPES:
            out.at[idx, "issue_code"] = "OFFICIAL_CORPORATE_ACTION"
            out.at[idx, "severity"] = "WARNING"
            out.at[idx, "details"] = (
                f"공식 {rec['event_type']} ex-date {rec['ex_date']} (ratio={rec['ratio']}, source={rec['source']}). "
                "원시 구간은 분리하고 수정주가 시계열만 연결합니다."
            )
    return out


def series_contract(*, official: bool) -> dict[str, Any]:
    if official:
        return {
            "price_basis": "official_adjusted_price",
            "return_series": "adj_close_price_return",
            "total_return_includes_dividends": True,
            "raw_ohlc_preserved": True,
            "unexplained_breaks_isolated": True,
        }
    return {
        "price_basis": "listed_shares_market_cap_proxy",
        "return_series": "raw_close_on_clean_segment",
        "total_return_includes_dividends": False,
        "raw_ohlc_preserved": True,
        "unexplained_breaks_isolated": True,
    }


def audit_adjustment_impact(prices: pd.DataFrame, actions: pd.DataFrame | None) -> dict[str, Any]:
    """Compare isolated raw history vs official-adjusted history. No silent join."""
    from kr_quant.quality.price_integrity import latest_clean_price_segments

    raw_clean, issues, _ = latest_clean_price_segments(prices)
    adjusted = apply_official_adjustments(prices, actions)
    explained = explain_breaks_with_actions(issues, actions)
    adj_close = pd.to_numeric(adjusted.get("adj_close"), errors="coerce") if "adj_close" in adjusted.columns else pd.Series(dtype=float)
    raw_close = pd.to_numeric(prices.get("close"), errors="coerce") if prices is not None and "close" in prices.columns else pd.Series(dtype=float)

    def _span_return(series: pd.Series) -> float | None:
        valid = series.dropna()
        valid = valid[valid > 0]
        if len(valid) < 2:
            return None
        return float(valid.iloc[-1] / valid.iloc[0] - 1)

    matched = int(explained["explained_by_official_action"].sum()) if not explained.empty and "explained_by_official_action" in explained.columns else 0
    unexplained = int((~explained["explained_by_official_action"]).sum()) if not explained.empty and "explained_by_official_action" in explained.columns else int(len(issues))
    return {
        "raw_rows": 0 if prices is None else int(len(prices)),
        "isolated_raw_rows": 0 if raw_clean is None else int(len(raw_clean)),
        "adjusted_rows": int(len(adjusted)) if adjusted is not None else 0,
        "raw_span_return": _span_return(raw_close),
        "isolated_raw_span_return": _span_return(pd.to_numeric(raw_clean["close"], errors="coerce") if raw_clean is not None and "close" in raw_clean.columns else pd.Series(dtype=float)),
        "adjusted_span_return": _span_return(adj_close),
        "official_events_matched": matched,
        "unexplained_breaks": unexplained,
        "corporate_action_confirmation": matched > 0,
        "note": "공식 이벤트가 없으면 수정주가로 단절을 잇지 않습니다.",
    }
