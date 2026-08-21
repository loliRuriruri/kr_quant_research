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


def _clip_100(val: float | None) -> float:
    if val is None or math.isnan(val) or math.isinf(val):
        return 50.0
    return max(0.0, min(100.0, float(val)))


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
            "score": 50.0,
            "state": "NEUTRAL",
            "state_ko": "중립 (시세 없음)",
            "components": {},
            "used_in_quant": False,
            "disclaimer": "자체 한국 시장 감성 지표입니다.",
        }

    px = prices.copy()
    date_col = "date" if "date" in px.columns else "trade_date"
    px[date_col] = pd.to_datetime(px[date_col])
    px = px.sort_values(["ticker", date_col])

    # 1. Market Momentum: Market average close vs 120D moving average
    daily_mkt = px.groupby(date_col)["close"].mean()
    mkt_mom_score = 50.0
    if len(daily_mkt) >= 120:
        ma120 = daily_mkt.tail(120).mean()
        cur_mkt = daily_mkt.iloc[-1]
        ratio = (cur_mkt / ma120) if ma120 > 0 else 1.0
        # ratio 0.90 -> 0, 1.00 -> 50, 1.10 -> 100
        mkt_mom_score = _clip_100(50.0 + (ratio - 1.0) * 500.0)
    elif len(daily_mkt) >= 20:
        ma20 = daily_mkt.tail(20).mean()
        cur_mkt = daily_mkt.iloc[-1]
        ratio = (cur_mkt / ma20) if ma20 > 0 else 1.0
        mkt_mom_score = _clip_100(50.0 + (ratio - 1.0) * 500.0)

    # 2. Breadth: 5-day advance / decline ratio across all stocks
    piv = px.pivot_table(index=date_col, columns="ticker", values="close")
    ret_5d = piv.pct_change(5, fill_method=None).iloc[-1].dropna() if len(piv) >= 6 else pd.Series(dtype=float)
    breadth_score = 50.0
    if not ret_5d.empty:
        adv_count = (ret_5d > 0).sum()
        dec_count = (ret_5d < 0).sum()
        total_valid = adv_count + dec_count
        if total_valid > 0:
            breadth_score = _clip_100((adv_count / total_valid) * 100.0)

    # 3. High / Low: 120-day 5-day rolling new highs vs new lows
    high_low_score = 50.0
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
    vol_score = 50.0
    if len(returns) >= 20:
        vol20 = float(returns.tail(20).std() * (252 ** 0.5))
        # Annualized vol 10% -> 80, 20% -> 50, 30% -> 20
        vol_score = _clip_100(100.0 - vol20 * 250.0)

    # 5. Trading Value Participation: 5-day value of advancing vs declining
    trading_val_score = 50.0
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
    flow_score = 50.0
    if foreign_net_5d is not None:
        # 1000억 순매수 -> 80, -1000억 -> 20
        # normalized in billions KRW
        billions = foreign_net_5d / 1e9 if foreign_net_5d > 1e6 else foreign_net_5d
        flow_score = _clip_100(50.0 + (billions / 20.0))

    components = {
        "momentum": {
            "label": "시장 모멘텀 (120D 이평)",
            "score": round(mkt_mom_score, 1),
            "weight": w["momentum"],
        },
        "breadth": {
            "label": "상승/하락 확산도 (5D)",
            "score": round(breadth_score, 1),
            "weight": w["breadth"],
        },
        "high_low": {
            "label": "신고가/신저가 비율",
            "score": round(high_low_score, 1),
            "weight": w["high_low"],
        },
        "volatility": {
            "label": "실현 변동성 안정도",
            "score": round(vol_score, 1),
            "weight": w["volatility"],
        },
        "trading_value": {
            "label": "상승종목 거래대금 비중",
            "score": round(trading_val_score, 1),
            "weight": w["trading_value"],
        },
        "foreign_flow": {
            "label": "외국인 5D 누적 수급",
            "score": round(flow_score, 1),
            "weight": w["foreign_flow"],
        },
    }

    total_weight = sum(w.values())
    weighted_score = sum(components[k]["score"] * components[k]["weight"] for k in components) / total_weight
    final_score = round(weighted_score, 1)

    if final_score >= 80.0:
        state = "EXTREME_GREED"
    elif final_score >= 60.0:
        state = "GREED"
    elif final_score >= 40.0:
        state = "NEUTRAL"
    elif final_score >= 20.0:
        state = "FEAR"
    else:
        state = "EXTREME_FEAR"

    return {
        "score": final_score,
        "state": state,
        "state_ko": SENTIMENT_STATE_KO[state],
        "components": components,
        "used_in_quant": False,
        "disclaimer": "자체 한국 시장 공포·탐욕 지표입니다. 매수/매도 신호가 아닙니다.",
    }
