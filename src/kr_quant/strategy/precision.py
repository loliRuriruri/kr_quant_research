# -*- coding: utf-8 -*-
"""Backtest precision overlays. Parameter selection stays on the default cost model."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import pandas as pd

from kr_quant.strategy.engine import BacktestResult, ExecutionModel

DEFAULT_COST = {
    "low": {"commission_bps": 0.5, "slippage_bps": 2.0, "impact_bps_at_max_participation": 10.0},
    "conservative": {"commission_bps": 3.0, "slippage_bps": 15.0, "impact_bps_at_max_participation": 40.0},
}
DEFAULT_CAPACITY = {"small_krw": 2_000_000.0, "large_krw": 50_000_000.0}
MIN_TRADES_FOR_SHARPE = 8
THIN_TRADE_COUNT = 2


def _block(cfg: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    current: dict[str, Any] = dict(cfg or {})
    for key in keys:
        current = dict(current.get(key) or {})
    return current


def cost_models(base: ExecutionModel, cfg: dict[str, Any] | None = None) -> dict[str, ExecutionModel]:
    cost = _block(cfg, "sensitivity", "cost")
    low = {**DEFAULT_COST["low"], **dict(cost.get("low") or {})}
    conservative = {**DEFAULT_COST["conservative"], **dict(cost.get("conservative") or {})}
    return {
        "low": replace(
            base,
            commission_bps=float(low.get("commission_bps") or 0),
            slippage_bps=float(low.get("slippage_bps") or 0),
            impact_bps_at_max_participation=float(low.get("impact_bps_at_max_participation") or 0),
        ),
        "default": base,
        "conservative": replace(
            base,
            commission_bps=float(conservative.get("commission_bps") or 0),
            slippage_bps=float(conservative.get("slippage_bps") or 0),
            impact_bps_at_max_participation=float(conservative.get("impact_bps_at_max_participation") or 0),
        ),
    }


def capacity_models(base: ExecutionModel, cfg: dict[str, Any] | None = None) -> dict[str, ExecutionModel]:
    cap = _block(cfg, "sensitivity", "capacity")
    default_notional = float(base.position_notional_krw or 10_000_000)
    small = float(cap.get("small_krw") or DEFAULT_CAPACITY["small_krw"])
    large = float(cap.get("large_krw") or DEFAULT_CAPACITY["large_krw"])
    return {
        "small": replace(base, position_notional_krw=small),
        "default": replace(base, position_notional_krw=default_notional or 10_000_000),
        "large": replace(base, position_notional_krw=large),
    }


def compact_metrics(result: BacktestResult) -> dict[str, Any]:
    metrics = dict(result.metrics or {})
    return {
        "total_return": metrics.get("total_return"),
        "sharpe": metrics.get("sharpe"),
        "trade_count": metrics.get("trade_count"),
        "max_drawdown": metrics.get("max_drawdown"),
        "max_participation_rate_observed": metrics.get("max_participation_rate_observed"),
        "blocked_order_reasons": metrics.get("blocked_order_reasons") or {},
        "estimated_cost_ratio": metrics.get("estimated_cost_ratio"),
    }


def sample_reliability(
    *,
    trade_count: int,
    oos_trade_count: int | None = None,
    min_trades: int = MIN_TRADES_FOR_SHARPE,
    thin_trades: int = THIN_TRADE_COUNT,
) -> dict[str, Any]:
    n = int(trade_count or 0)
    oos_n = None if oos_trade_count is None else int(oos_trade_count or 0)
    thin = n < min_trades
    very_thin = n <= thin_trades
    warning = None
    if very_thin:
        warning = f"왕복 매매 {n}회라 샤프·연환산 수익률을 대표 지표로 쓰지 않습니다. 거래 로그로만 재현하세요."
    elif thin:
        warning = f"왕복 매매 {n}회로 표본이 부족합니다. 샤프는 참고값이며 성과 순위로 쓰지 마세요."
    oos_warning = None
    if oos_n is not None and oos_n <= thin_trades:
        oos_warning = f"최종검증 매매 {oos_n}회라 최종검증 샤프를 대표 지표로 쓰지 않습니다."
    elif oos_n is not None and oos_n < min_trades:
        oos_warning = f"최종검증 매매 {oos_n}회로 표본이 부족합니다. 최종검증 샤프를 대표 성과로 쓰지 마세요."
    return {
        "trade_count": n,
        "oos_trade_count": oos_n,
        "min_trades_for_sharpe": min_trades,
        "representative_sharpe": not thin,
        "representative_oos_sharpe": None if oos_n is None else oos_n >= min_trades,
        "representative_annualized": (not thin) and n >= min_trades,
        "warning": warning,
        "oos_warning": oos_warning,
    }


def public_trades(trades: pd.DataFrame | None, *, limit: int = 24) -> list[dict[str, Any]]:
    if trades is None or getattr(trades, "empty", True):
        return []
    rows: list[dict[str, Any]] = []
    for rec in trades.tail(limit).to_dict("records"):
        item: dict[str, Any] = {}
        for key, value in rec.items():
            if hasattr(value, "isoformat"):
                item[key] = str(value)[:10]
            elif isinstance(value, float):
                item[key] = None if pd.isna(value) else round(float(value), 6)
            elif value is None or (isinstance(value, str) and value == "nan"):
                item[key] = None
            else:
                item[key] = value
        rows.append(item)
    return rows


def _day(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def ticker_listing_window(history: pd.DataFrame | None, ticker: str, start: Any, end: Any) -> dict[str, Any]:
    start_day = _day(start)
    end_day = _day(end)
    code = str(ticker or "").zfill(6)
    payload: dict[str, Any] = {
        "ticker": code,
        "window_from": None if start_day is None else start_day.isoformat(),
        "window_to": None if end_day is None else end_day.isoformat(),
        "listed_throughout": None,
        "list_date": None,
        "delist_date": None,
        "source": "listing_history",
        "limitation": "종목 상장 기간 확인입니다. 당시 시장 전체 유니버스를 재선정한 PIT 포트폴리오가 아닙니다.",
    }
    if history is None or getattr(history, "empty", True) or not code:
        payload["source"] = "unavailable"
        payload["limitation"] = "상장 이력 파일이 없어 이 종목이 검증 구간 내내 상장돼 있었는지 확인하지 못합니다."
        return payload
    work = history.copy()
    if "ticker" not in work.columns:
        payload["source"] = "unavailable"
        return payload
    work["ticker"] = work["ticker"].astype(str).str.zfill(6)
    rows = work[work["ticker"] == code]
    if rows.empty:
        payload["listed_throughout"] = None
        payload["limitation"] = "이 종목의 상장·상장폐지 이력이 없습니다. 현재 시세가 있다고 해서 과거 전 기간 상장을 가정하지 않습니다."
        return payload
    events = rows.copy()
    if "event_type" not in events.columns or "event_date" not in events.columns:
        payload["source"] = "unavailable"
        return payload
    events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce").dt.date
    listed = events[events["event_type"] == "LIST"]["event_date"].dropna()
    delisted = events[events["event_type"] == "DELIST"]["event_date"].dropna()
    list_date = min(listed) if len(listed) else None
    delist_date = min(delisted) if len(delisted) else None
    payload["list_date"] = None if list_date is None else list_date.isoformat()
    payload["delist_date"] = None if delist_date is None else delist_date.isoformat()
    throughout = True
    if start_day and list_date and list_date > start_day:
        throughout = False
    if end_day and delist_date and delist_date <= end_day:
        throughout = False
    payload["listed_throughout"] = throughout
    if not throughout:
        payload["limitation"] = (
            "검증 구간에 상장 전 또는 상장폐지 후 날짜가 포함될 수 있습니다. "
            "현재 TOP20 소급 결과를 당시 시장 전체 성과로 말하지 마세요."
        )
    return payload
