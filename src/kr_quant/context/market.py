from __future__ import annotations

from typing import Any

import pandas as pd


def market_regime(components: dict[str, float | None], config: dict) -> dict[str, Any]:
    weights = config["market_regime"]["weights"]
    score = 0.0
    total = 0.0
    for name, weight in weights.items():
        raw = components.get(name)
        if raw is None:
            continue
        value = max(0.0, min(float(raw), 100.0))
        score += value * float(weight)
        total += float(weight)
    if not total:
        raise ValueError("관측된 시장 구성요소가 없습니다.")
    score = round(score / total, 2)
    if score >= float(config["market_regime"]["risk_on_min"]):
        regime = "RISK_ON"
        label = "위험선호"
    elif score >= float(config["market_regime"]["neutral_min"]):
        regime = "NEUTRAL"
        label = "중립"
    else:
        regime = "RISK_OFF"
        label = "위험회피"
    return {
        "regime_score": score,
        "regime": regime,
        "label": label,
        "used_in_quant": False,
        **components,
    }


def _pct(signals: list[float]) -> float | None:
    if not signals:
        return None
    return round(sum(signals) / len(signals) * 100, 2)


def derive_market_components(prices: pd.DataFrame) -> dict[str, float | None]:
    if prices is None or prices.empty:
        raise ValueError("가격 데이터가 없습니다.")
    ordered = prices.copy()
    date_col = "date" if "date" in ordered.columns else "trade_date"
    ordered[date_col] = pd.to_datetime(ordered[date_col])
    ordered = ordered.sort_values(["ticker", date_col])
    groups = {ticker: group for ticker, group in ordered.groupby("ticker")}

    trend_signals: list[float] = []
    breadth_signals: list[float] = []
    momentum_signals: list[float] = []
    for group in groups.values():
        close = pd.to_numeric(group["close"], errors="coerce").dropna()
        if len(close) >= 60:
            trend_signals.append(float(close.iloc[-1] > close.tail(60).mean()))
            momentum_signals.append(float(close.iloc[-1] > close.iloc[-60]))
        if len(close) >= 20 and float(close.iloc[-20]) > 0:
            breadth_signals.append(float(close.iloc[-1] > close.iloc[-20]))

    value_col = "trading_value" if "trading_value" in ordered.columns else None
    liquidity = None
    if value_col:
        daily_value = ordered.groupby(date_col)[value_col].sum(min_count=1).dropna()
        if len(daily_value) >= 20 and float(daily_value.tail(20).mean()) > 0:
            ratio = float(daily_value.iloc[-1] / daily_value.tail(20).mean())
            liquidity = max(0.0, min(100.0, ratio * 50.0))

    returns = ordered.pivot_table(index=date_col, columns="ticker", values="close").pct_change(fill_method=None)
    market_returns = returns.mean(axis=1).dropna()
    volatility = None
    if len(market_returns) >= 20:
        annualized = float(market_returns.tail(60).std() * (252**0.5))
        volatility = max(0.0, min(100.0, 100.0 - annualized * 200.0))

    return {
        "trend": _pct(trend_signals),
        "breadth": _pct(breadth_signals),
        "liquidity": round(liquidity, 2) if liquidity is not None else None,
        "volatility": round(volatility, 2) if volatility is not None else None,
        "rates": None,
        "fx": None,
        "momentum": _pct(momentum_signals),
    }


def attach_macro(components: dict[str, float | None], fred_series: list[dict[str, Any]] | None) -> dict[str, float | None]:
    """Map FRED series into 0-100 display scores. Does not affect Quant."""
    by_id = {str(row.get("id")): row for row in (fred_series or []) if isinstance(row, dict)}
    curve = by_id.get("T10Y2Y") or {}
    if curve.get("value") is not None:
        # 0% spread -> 50, +1% -> 70, inverted -1% -> 30
        components["rates"] = max(0.0, min(100.0, 50.0 + float(curve["value"]) * 20.0))
    fx = by_id.get("DEXKOUS") or {}
    prev = fx.get("prev_value")
    last = fx.get("value")
    if last is not None and prev not in (None, 0):
        change = (float(last) / float(prev)) - 1.0
        components["fx"] = max(0.0, min(100.0, 50.0 - change * 500.0))
    return components


COMPONENT_KO = {
    "trend": "60일 추세 참여도",
    "breadth": "20일 상승 종목 비율",
    "liquidity": "거래대금 강도",
    "volatility": "변동성 안정",
    "rates": "미국 장단기 금리차",
    "fx": "원화 안정",
    "momentum": "60일 상승 종목 비율",
}
