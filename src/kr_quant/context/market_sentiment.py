"""Internal Korea Market Sentiment (Fear & Greed Index).

Self-contained 100-point market sentiment engine using KRX equity universe and foreigner flow.
Overlay only — used_in_quant=false.
Never alters Quant Score.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd

SENTIMENT_STATE_KO = {
    "EXTREME_FEAR": "극단적 공포",
    "FEAR": "공포",
    "NEUTRAL": "중립",
    "GREED": "탐욕",
    "EXTREME_GREED": "극단적 탐욕",
}

# Standard weights summing to 100
DEFAULT_WEIGHTS = {
    "momentum": 20.0,        # KOSPI vs 120D MA
    "breadth": 20.0,         # 5D advancing vs declining ratio
    "high_low": 15.0,        # 120D 5D new highs vs new lows
    "volatility": 15.0,      # 20D realized volatility inverse
    "trading_value": 15.0,   # 5D advancing trading value share
    "foreign_flow": 15.0,    # Foreigner 5D net buy intensity
}


def _clip_100(val: float | None) -> float | None:
    if val is None:
        return None
    try:
        number = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return max(0.0, min(100.0, number))


def compute_kr_market_sentiment(
    prices: pd.DataFrame,
    foreign_net_5d: float | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calculates internal Korea Fear & Greed Index (0~100) from universe price action and flow."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    if prices is None or prices.empty:
        return {
            "score": None,
            "state": "NEUTRAL",
            "state_ko": "중립 (시세 없음)",
            "components": {},
            "used_in_quant": False,
            "confidence": 0.0,
            "weight_policy": "missing_excluded_and_redistributed",
            "disclaimer": "자체 한국 시장 감성 지표입니다.",
        }

    px = prices.copy()
    date_col = "date" if "date" in px.columns else "trade_date"
    px[date_col] = pd.to_datetime(px[date_col])
    px = px.sort_values(["ticker", date_col])

    as_of = None
    try:
        as_of = pd.Timestamp(px[date_col].max()).date().isoformat()
    except (TypeError, ValueError):
        as_of = None
    n_tickers = int(px["ticker"].nunique()) if "ticker" in px.columns else 0

    # 1. Market Momentum: Market average close vs 120D moving average
    daily_mkt = px.groupby(date_col)["close"].mean()
    mkt_mom_score = None
    if len(daily_mkt) >= 120:
        ma120 = daily_mkt.tail(120).mean()
        cur_mkt = daily_mkt.iloc[-1]
        ratio = (cur_mkt / ma120) if ma120 > 0 else 1.0
        mkt_mom_score = _clip_100(50.0 + (ratio - 1.0) * 500.0)
    elif len(daily_mkt) >= 20:
        ma20 = daily_mkt.tail(20).mean()
        cur_mkt = daily_mkt.iloc[-1]
        ratio = (cur_mkt / ma20) if ma20 > 0 else 1.0
        mkt_mom_score = _clip_100(50.0 + (ratio - 1.0) * 500.0)

    # 2. Breadth: 5-day advance / decline ratio across all stocks
    piv = px.pivot_table(index=date_col, columns="ticker", values="close")
    ret_5d = piv.pct_change(5, fill_method=None).iloc[-1].dropna() if len(piv) >= 6 else pd.Series(dtype=float)
    breadth_score = None
    if not ret_5d.empty:
        adv_count = (ret_5d > 0).sum()
        dec_count = (ret_5d < 0).sum()
        total_valid = adv_count + dec_count
        if total_valid > 0:
            breadth_score = _clip_100((adv_count / total_valid) * 100.0)

    # 3. High / Low: 120-day 5-day rolling new highs vs new lows
    high_low_score = None
    if len(piv) >= 60:
        win = min(120, len(piv))
        rolling_max = piv.tail(win).max()
        rolling_min = piv.tail(win).min()
        latest = piv.iloc[-1]
        near_high = (latest >= rolling_max * 0.97).sum()
        near_low = (latest <= rolling_min * 1.03).sum()
        total_hl = near_high + near_low
        if total_hl > 0:
            high_low_score = _clip_100((near_high / total_hl) * 100.0)

    # 4. Volatility: 20-day realized market volatility inverse (lower vol = greedier / more stable)
    returns = piv.pct_change(fill_method=None).mean(axis=1).dropna()
    vol_score = None
    if len(returns) >= 20:
        vol20 = float(returns.tail(20).std() * (252 ** 0.5))
        # Annualized vol 10% -> 80, 20% -> 50, 30% -> 20
        vol_score = _clip_100(100.0 - vol20 * 250.0)

    # 5. Trading Value Participation: 5-day value of advancing vs declining
    trading_val_score = None
    val_col = "trading_value" if "trading_value" in px.columns else "amount"
    if val_col in px.columns and not ret_5d.empty:
        latest_val = px[px[date_col] == px[date_col].max()].set_index("ticker")[val_col].dropna()
        adv_tickers = ret_5d[ret_5d > 0].index
        dec_tickers = ret_5d[ret_5d < 0].index
        val_adv = latest_val.loc[latest_val.index.intersection(adv_tickers)].sum()
        val_dec = latest_val.loc[latest_val.index.intersection(dec_tickers)].sum()
        total_val = val_adv + val_dec
        if total_val > 0:
            trading_val_score = _clip_100((val_adv / total_val) * 100.0)

    # 6. Foreign Flow: 5-day cumulative foreigner net buy intensity
    flow_score = None
    if foreign_net_5d is not None:
        # 1000억 순매수 -> 80, -1000억 -> 20
        # normalized in billions KRW
        billions = foreign_net_5d / 1e9 if foreign_net_5d > 1e6 else foreign_net_5d
        flow_score = _clip_100(50.0 + (billions / 20.0))

    def _row(label: str, score: float | None, weight: float, *, missing: str | None = None) -> dict[str, Any]:
        available = score is not None
        return {
            "label": label,
            "score": None if score is None else round(float(score), 1),
            "weight": weight,
            "available": available,
            "as_of": as_of,
            "source": "KRX",
            "sample_count": n_tickers,
            "missing_reason": None if available else missing,
            "used_in_quant": False,
        }

    components = {
        "momentum": _row("시장 모멘텀 (120D 이평)", mkt_mom_score, w["momentum"], missing="이평 계산에 필요한 거래일이 부족합니다."),
        "breadth": _row("상승/하락 확산도 (5D)", breadth_score, w["breadth"], missing="5일 수익률을 만들 종목이 부족합니다."),
        "high_low": _row("신고가/신저가 비율", high_low_score, w["high_low"], missing="고저 비교에 필요한 이력이 부족합니다."),
        "volatility": _row("실현 변동성 안정도", vol_score, w["volatility"], missing="실현변동성 표본이 부족합니다."),
        "trading_value": _row("상승종목 거래대금 비중", trading_val_score, w["trading_value"], missing="거래대금 또는 상승·하락 구분이 없습니다."),
        "foreign_flow": _row("외국인 5D 누적 수급", flow_score, w["foreign_flow"], missing="외인 5일 순매수가 없어 포함하지 않습니다."),
    }

    usable = [(row["score"], row["weight"]) for row in components.values() if row["available"] and row["score"] is not None]
    used_weight = sum(weight for _, weight in usable)
    configured = sum(float(value) for value in w.values())
    if used_weight:
        final_score = round(sum(score * weight for score, weight in usable) / used_weight, 1)
        for row in components.values():
            if row["available"] and row["score"] is not None:
                row["contribution"] = round(row["score"] * row["weight"] / used_weight, 2)
            else:
                row["contribution"] = 0.0
    else:
        final_score = None
        for row in components.values():
            row["contribution"] = 0.0

    if final_score is None:
        state = "NEUTRAL"
        state_ko = "중립 (관측 부족)"
    elif final_score >= 80.0:
        state = "EXTREME_GREED"
        state_ko = SENTIMENT_STATE_KO[state]
    elif final_score >= 60.0:
        state = "GREED"
        state_ko = SENTIMENT_STATE_KO[state]
    elif final_score >= 40.0:
        state = "NEUTRAL"
        state_ko = SENTIMENT_STATE_KO[state]
    elif final_score >= 20.0:
        state = "FEAR"
        state_ko = SENTIMENT_STATE_KO[state]
    else:
        state = "EXTREME_FEAR"
        state_ko = SENTIMENT_STATE_KO[state]

    check_sum = round(sum(float(row.get("contribution") or 0) for row in components.values()), 1)
    return {
        "score": final_score,
        "state": state,
        "state_ko": state_ko,
        "components": components,
        "as_of": as_of,
        "sample_count": n_tickers,
        "used_in_quant": False,
        "weight_policy": "missing_excluded_and_redistributed",
        "confidence": round(used_weight / configured, 4) if configured else 0.0,
        "score_check": {
            "contributions_sum": check_sum,
            "score": final_score,
            "reproducible": final_score is None or abs(check_sum - final_score) <= 0.1,
        },
        "disclaimer": "자체 한국 시장 공포·탐욕 지표입니다. 매수/매도 신호가 아닙니다. 빠진 구성요소는 0점이 아니라 가중치에서 제외합니다.",
    }
