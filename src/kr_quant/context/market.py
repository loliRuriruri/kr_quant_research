from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

COMPONENT_KO = {
    "trend": "60일 추세 참여도",
    "breadth": "20일 상승 종목 비율",
    "liquidity": "거래대금 강도",
    "volatility": "변동성 안정",
    "rates": "미국 장단기 금리차",
    "fx": "원화 안정",
    "momentum": "60일 상승 종목 비율",
}

COMPONENT_SOURCE = {
    "trend": "KRX",
    "breadth": "KRX",
    "liquidity": "KRX",
    "volatility": "KRX",
    "rates": "FRED T10Y2Y",
    "fx": "FRED DEXKOUS",
    "momentum": "KRX",
}


def _iso(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError):
        text = str(value)[:10]
        return text if len(text) >= 10 else None


def _lag_days(as_of: str | None, reference: str | None) -> int | None:
    if not as_of or not reference:
        return None
    try:
        return (date.fromisoformat(str(reference)[:10]) - date.fromisoformat(str(as_of)[:10])).days
    except ValueError:
        return None


def _clip(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def component_score(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        if raw.get("available") is False:
            return None
        value = raw.get("score")
        if value is None:
            return None
        return float(value)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _component(
    *,
    score: float | None,
    as_of: str | None,
    source: str,
    formula: str,
    observation: str,
    opinion: str,
    falsification: str,
    sample_count: int | None = None,
    sample_unit: str = "종목",
    lookback_days: int | None = None,
    observed_value: Any = None,
    observed_unit: str | None = None,
    change_1d: float | None = None,
    change_1m: float | None = None,
    lag_days: int | None = None,
    stale: bool = False,
    available: bool | None = None,
    missing_reason: str | None = None,
    related: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    present = (score is not None) if available is None else bool(available)
    return {
        "score": None if score is None else round(float(score), 2),
        "available": present,
        "as_of": as_of,
        "source": source,
        "source_kind": "official",
        "sample_count": sample_count,
        "sample_unit": sample_unit,
        "lookback_days": lookback_days,
        "observed_value": observed_value,
        "observed_unit": observed_unit,
        "change_1d": None if change_1d is None else round(float(change_1d), 2),
        "change_1m": None if change_1m is None else round(float(change_1m), 2),
        "lag_days": lag_days,
        "stale": bool(stale),
        "formula": formula,
        "observation": observation,
        "opinion": opinion,
        "falsification": falsification,
        "missing_reason": missing_reason,
        "related": related or [],
        "used_in_quant": False,
    }


def _missing(name: str, reason: str, *, source: str | None = None) -> dict[str, Any]:
    return _component(
        score=None,
        as_of=None,
        source=source or COMPONENT_SOURCE.get(name, "KRX"),
        formula="",
        observation="",
        opinion="관측이 없어 해석하지 않습니다.",
        falsification="해당 원천이 채워지면 국면 점수에 다시 포함합니다.",
        available=False,
        missing_reason=reason,
        sample_count=None,
    )


def _pct(signals: list[float]) -> float | None:
    if not signals:
        return None
    return round(sum(signals) / len(signals) * 100, 2)


def _close_upto(group: pd.DataFrame, *, drop_last: int = 0) -> pd.Series:
    close = group if isinstance(group, pd.Series) else pd.to_numeric(group["close"], errors="coerce").dropna()
    if drop_last:
        if len(close) <= drop_last:
            return pd.Series(dtype=float)
        close = close.iloc[:-drop_last]
    return close


def _participation(groups: dict[Any, pd.DataFrame], *, lookback: int, mode: str, drop_last: int = 0) -> tuple[float | None, int]:
    signals: list[float] = []
    for group in groups.values():
        close = _close_upto(group, drop_last=drop_last)
        if mode == "ma":
            if len(close) >= lookback:
                signals.append(float(close.iloc[-1] > close.tail(lookback).mean()))
        elif mode == "change":
            if len(close) >= lookback and float(close.iloc[-lookback]) > 0:
                signals.append(float(close.iloc[-1] > close.iloc[-lookback]))
    return _pct(signals), len(signals)


def market_regime(components: dict[str, Any], config: dict) -> dict[str, Any]:
    weights = dict((config.get("market_regime") or {}).get("weights") or {})
    if not weights:
        raise ValueError("시장 국면 가중치가 없습니다.")
    available: list[tuple[str, float, float]] = []
    missing: list[str] = []
    details: dict[str, Any] = {}
    configured_sum = float(sum(float(weight) for weight in weights.values()))
    for name, weight in weights.items():
        raw = components.get(name)
        score = component_score(raw)
        detail = dict(raw) if isinstance(raw, dict) else {"score": score, "available": score is not None, "source": COMPONENT_SOURCE.get(name)}
        detail["configured_weight"] = float(weight)
        details[name] = detail
        if score is None:
            missing.append(name)
            detail["available"] = False
            detail["contribution"] = 0.0
            detail["effective_weight"] = 0.0
            continue
        available.append((name, score, float(weight)))
    if not available:
        raise ValueError("관측된 시장 구성요소가 없습니다.")
    used_weight = float(sum(item[2] for item in available))
    regime_score = round(sum(score * weight for _, score, weight in available) / used_weight, 2)
    contributions: list[dict[str, Any]] = []
    for name, score, weight in available:
        contribution = round(score * weight / used_weight, 2)
        details[name]["contribution"] = contribution
        details[name]["effective_weight"] = round(weight / used_weight * 100.0, 2)
        contributions.append(
            {
                "id": name,
                "label": COMPONENT_KO.get(name, name),
                "score": round(score, 2),
                "configured_weight": weight,
                "effective_weight": details[name]["effective_weight"],
                "contribution": contribution,
            }
        )
    check_sum = round(sum(item["contribution"] for item in contributions), 2)
    confidence = round(used_weight / configured_sum, 4) if configured_sum else 0.0
    if regime_score >= float((config.get("market_regime") or {}).get("risk_on_min") or 70):
        regime = "RISK_ON"
        label = "위험선호"
    elif regime_score >= float((config.get("market_regime") or {}).get("neutral_min") or 40):
        regime = "NEUTRAL"
        label = "중립"
    else:
        regime = "RISK_OFF"
        label = "위험회피"
    missing_labels = [COMPONENT_KO.get(name, name) for name in missing]
    falsification = (
        "관측 구성요소의 기여 합이 위험회피 기준 아래로 내려가거나, 미연결 금리가 역전된 채로 채워지면 해석을 바꿉니다."
    )
    opinion = f"내부 국면 해석은 {label}입니다. 아래 숫자는 관측 점수이며 매수·매도 신호가 아닙니다."
    out: dict[str, Any] = {
        "regime_score": regime_score,
        "regime": regime,
        "label": label,
        "used_in_quant": False,
        "weight_policy": "missing_excluded_and_redistributed",
        "configured_weight_sum": configured_sum,
        "available_weight_sum": used_weight,
        "missing": missing,
        "confidence": confidence,
        "confidence_label": (
            f"미관측 {', '.join(missing_labels)} 가중치 {round(configured_sum - used_weight, 1)}를 제외하고 "
            f"{round(used_weight, 1)}/{round(configured_sum, 1)}만 사용"
            if missing
            else "설정 가중치 전체를 사용"
        ),
        "formula": "관측 점수 × 설정 가중치의 합 ÷ 관측된 가중치 합. 빠진 지표는 0점이 아니라 분모에서 제외합니다.",
        "score_check": {
            "contributions_sum": check_sum,
            "regime_score": regime_score,
            "reproducible": abs(check_sum - regime_score) <= 0.05,
        },
        "contributions": contributions,
        "details": details,
        "opinion": opinion,
        "falsification": falsification,
    }
    for name in weights:
        out[name] = component_score(components.get(name))
    return out


def derive_market_components(prices: pd.DataFrame) -> dict[str, Any]:
    if prices is None or prices.empty:
        raise ValueError("가격 데이터가 없습니다.")
    ordered = prices.copy()
    date_col = "date" if "date" in ordered.columns else "trade_date"
    ordered[date_col] = pd.to_datetime(ordered[date_col])
    ordered = ordered.sort_values(["ticker", date_col])
    as_of = _iso(ordered[date_col].max())
    # Clean each series once for the nine participation calculations.
    groups = {ticker: pd.to_numeric(group['close'], errors='coerce').dropna()
              for ticker, group in ordered.groupby('ticker')}
    n_tickers = len(groups)

    trend, trend_n = _participation(groups, lookback=60, mode="ma")
    trend_prev, _ = _participation(groups, lookback=60, mode="ma", drop_last=1)
    trend_m, _ = _participation(groups, lookback=60, mode="ma", drop_last=21)
    breadth, breadth_n = _participation(groups, lookback=20, mode="change")
    breadth_prev, _ = _participation(groups, lookback=20, mode="change", drop_last=1)
    breadth_m, _ = _participation(groups, lookback=20, mode="change", drop_last=21)
    momentum, mom_n = _participation(groups, lookback=60, mode="change")
    mom_prev, _ = _participation(groups, lookback=60, mode="change", drop_last=1)
    mom_m, _ = _participation(groups, lookback=60, mode="change", drop_last=21)

    value_col = "trading_value" if "trading_value" in ordered.columns else None
    liquidity = None
    liq_obs = None
    liq_change_1d = None
    liq_change_1m = None
    if value_col:
        daily_value = ordered.groupby(date_col)[value_col].sum(min_count=1).dropna()
        if len(daily_value) >= 20 and float(daily_value.tail(20).mean()) > 0:
            mean20 = float(daily_value.tail(20).mean())
            last = float(daily_value.iloc[-1])
            ratio = last / mean20
            liquidity = _clip(ratio * 50.0)
            liq_obs = last
            if len(daily_value) >= 21:
                prev_ratio = float(daily_value.iloc[-2]) / float(daily_value.iloc[-21:-1].mean())
                liq_change_1d = _clip(prev_ratio * 50.0)
                if liq_change_1d is not None and liquidity is not None:
                    liq_change_1d = liquidity - liq_change_1d
            if len(daily_value) >= 41:
                older = float(daily_value.iloc[-22]) / float(daily_value.iloc[-41:-21].mean())
                liq_change_1m = _clip(older * 50.0)
                if liq_change_1m is not None and liquidity is not None:
                    liq_change_1m = liquidity - liq_change_1m

    returns = ordered.pivot_table(index=date_col, columns="ticker", values="close").pct_change(fill_method=None)
    market_returns = returns.mean(axis=1).dropna()
    volatility = None
    vol_obs = None
    vol_change_1d = None
    vol_change_1m = None
    if len(market_returns) >= 20:
        window = market_returns.tail(60) if len(market_returns) >= 60 else market_returns.tail(20)
        annualized = float(window.std() * (252**0.5))
        volatility = _clip(100.0 - annualized * 200.0)
        vol_obs = annualized
        if len(market_returns) >= 21:
            prev_win = market_returns.iloc[:-1].tail(60 if len(market_returns) >= 61 else 20)
            prev_vol = _clip(100.0 - float(prev_win.std() * (252**0.5)) * 200.0)
            if prev_vol is not None and volatility is not None:
                vol_change_1d = volatility - prev_vol
        if len(market_returns) >= 41:
            old_win = market_returns.iloc[:-21].tail(60 if len(market_returns) >= 81 else 20)
            old_vol = _clip(100.0 - float(old_win.std() * (252**0.5)) * 200.0)
            if old_vol is not None and volatility is not None:
                vol_change_1m = volatility - old_vol

    def _delta(now: float | None, then: float | None) -> float | None:
        if now is None or then is None:
            return None
        return round(now - then, 2)

    return {
        "trend": _component(
            score=trend,
            as_of=as_of,
            source="KRX",
            sample_count=trend_n or n_tickers,
            lookback_days=60,
            observed_value=trend,
            observed_unit="%",
            change_1d=_delta(trend, trend_prev),
            change_1m=_delta(trend, trend_m),
            formula="종가가 60일 평균보다 높은 종목 비율 × 100",
            observation=f"{trend_n}종목 중 60일 이평 위 비율 {trend}",
            opinion="중기 추세 확산이 넓은지 좁은지에 대한 해석입니다.",
            falsification="60일 이평 위 종목이 40% 아래로 내려가면 추세 기여는 부담으로 바뀝니다.",
            missing_reason=None if trend is not None else "60일 이력이 있는 종목이 없습니다.",
        )
        if trend is not None
        else _missing("trend", "60일 이력이 있는 종목이 없습니다."),
        "breadth": _component(
            score=breadth,
            as_of=as_of,
            source="KRX",
            sample_count=breadth_n or n_tickers,
            lookback_days=20,
            observed_value=breadth,
            observed_unit="%",
            change_1d=_delta(breadth, breadth_prev),
            change_1m=_delta(breadth, breadth_m),
            formula="종가가 20거래일 전보다 높은 종목 비율 × 100",
            observation=f"{breadth_n}종목의 20일 상승 비율 {breadth}",
            opinion="단기 상승 종목이 넓은지 좁은지에 대한 해석입니다.",
            falsification="20일 상승 종목이 40% 아래로 내려가면 확산 기여는 부담으로 바뀝니다.",
        )
        if breadth is not None
        else _missing("breadth", "20일 이력이 있는 종목이 없습니다."),
        "liquidity": _component(
            score=liquidity,
            as_of=as_of,
            source="KRX",
            sample_count=n_tickers,
            lookback_days=20,
            observed_value=liq_obs,
            observed_unit="KRW",
            change_1d=liq_change_1d,
            change_1m=liq_change_1m,
            formula="당일 거래대금 ÷ 20일 평균 × 50, 0~100 절단",
            observation=f"거래대금 20일 평균 대비 점수 {liquidity}",
            opinion="유동성이 평균보다 강한지 약한지에 대한 해석입니다.",
            falsification="거래대금이 20일 평균의 절반 아래로 가면 유동성 기여는 부담으로 바뀝니다.",
        )
        if liquidity is not None
        else _missing("liquidity", "거래대금 시계열이 부족합니다."),
        "volatility": _component(
            score=volatility,
            as_of=as_of,
            source="KRX",
            sample_count=n_tickers,
            lookback_days=60 if len(market_returns) >= 60 else 20,
            observed_value=None if vol_obs is None else round(vol_obs, 4),
            observed_unit="연환산",
            change_1d=vol_change_1d,
            change_1m=vol_change_1m,
            formula="100 − 시장 평균수익률 연환산 표준편차 × 200, 0~100 절단",
            observation=f"KRX 일봉 실현변동성 점수 {volatility}",
            opinion="한국 주식 실현변동성이 낮은지를 안정으로 해석합니다. VIX와 같은 시장이 아닙니다.",
            falsification="연환산 변동성이 30%를 넘으면 변동성 기여는 부담으로 바뀝니다.",
        )
        if volatility is not None
        else _missing("volatility", "수익률 표본이 부족합니다."),
        "rates": _missing("rates", "FRED 장단기 금리차가 아직 연결되지 않았습니다."),
        "fx": _missing("fx", "FRED 원/달러가 아직 연결되지 않았습니다."),
        "momentum": _component(
            score=momentum,
            as_of=as_of,
            source="KRX",
            sample_count=mom_n or n_tickers,
            lookback_days=60,
            observed_value=momentum,
            observed_unit="%",
            change_1d=_delta(momentum, mom_prev),
            change_1m=_delta(momentum, mom_m),
            formula="종가가 60거래일 전보다 높은 종목 비율 × 100",
            observation=f"{mom_n}종목의 60일 상승 비율 {momentum}",
            opinion="중기 모멘텀 종목 밀도에 대한 해석입니다.",
            falsification="60일 상승 종목이 40% 아래로 내려가면 모멘텀 기여는 부담으로 바뀝니다.",
        )
        if momentum is not None
        else _missing("momentum", "60일 이력이 있는 종목이 없습니다."),
        "_meta": {"as_of": as_of, "ticker_count": n_tickers, "source": "KRX"},
    }


def _history_change(history: list[dict[str, Any]] | None, *, bars_ago: int) -> float | None:
    rows = [item for item in (history or []) if isinstance(item, dict) and item.get("value") is not None]
    if len(rows) <= bars_ago:
        return None
    last = float(rows[-1]["value"])
    prev = float(rows[-1 - bars_ago]["value"])
    return last - prev


def attach_macro(
    components: dict[str, Any],
    fred_series: list[dict[str, Any]] | None,
    *,
    krx_as_of: str | None = None,
) -> dict[str, Any]:
    """Map FRED series into 0-100 display scores. Does not affect Quant."""
    by_id = {str(row.get("id")): row for row in (fred_series or []) if isinstance(row, dict)}
    curve = by_id.get("T10Y2Y") or {}
    if curve.get("value") is not None:
        as_of = _iso(curve.get("date"))
        lag = _lag_days(as_of, krx_as_of)
        score = _clip(50.0 + float(curve["value"]) * 20.0)
        related = []
        for sid, label, unit in (("DGS2", "미국 2년 금리", "%"), ("DGS10", "미국 10년 금리", "%")):
            item = by_id.get(sid) or {}
            if item.get("value") is None:
                continue
            related.append(
                {
                    "id": sid,
                    "label": label,
                    "source": "FRED",
                    "as_of": _iso(item.get("date")),
                    "value": item.get("value"),
                    "unit": unit,
                    "note": "국면 점수 가중치에는 넣지 않고 장단기 스프레드의 구성만 보여 줍니다.",
                }
            )
        components["rates"] = _component(
            score=score,
            as_of=as_of,
            source="FRED T10Y2Y",
            sample_count=1,
            sample_unit="지표",
            lookback_days=1,
            observed_value=curve.get("value"),
            observed_unit="%p",
            change_1d=curve.get("delta"),
            change_1m=_history_change(curve.get("history"), bars_ago=21),
            lag_days=lag,
            stale=bool(lag is not None and lag > 5),
            formula="50 + 미국 10Y-2Y 스프레드(%p)×20, 0~100 절단",
            observation=f"미국 10Y-2Y {curve.get('value')}%p ({as_of})",
            opinion="스프레드가 플러스면 금리 기여를 상대적으로 우호로 해석합니다.",
            falsification="스프레드가 -0.5%p 이하로 역전되면 금리 기여는 부담 구간으로 내려갑니다.",
            related=related,
        )
    fx = by_id.get("DEXKOUS") or {}
    last = fx.get("value")
    prev = fx.get("prev_value")
    if last is not None and prev not in (None, 0):
        as_of = _iso(fx.get("date"))
        lag = _lag_days(as_of, krx_as_of)
        change = (float(last) / float(prev)) - 1.0
        score = _clip(50.0 - change * 500.0)
        components["fx"] = _component(
            score=score,
            as_of=as_of,
            source="FRED DEXKOUS",
            sample_count=1,
            sample_unit="지표",
            lookback_days=1,
            observed_value=last,
            observed_unit="USD/KRW",
            change_1d=fx.get("delta"),
            change_1m=_history_change(fx.get("history"), bars_ago=21),
            lag_days=lag,
            stale=bool(lag is not None and lag > 5),
            formula="50 − 원/달러 전일 대비 변화율×500, 0~100 절단",
            observation=f"원/달러 {last} ({as_of})",
            opinion="원화 급락은 외국인 환차손 부담으로 해석합니다.",
            falsification="원/달러가 전일 대비 1% 이상 상승하면 환율 기여는 부담으로 내려갑니다.",
        )
    vix = by_id.get("VIXCLS") or {}
    vol = components.get("volatility")
    if isinstance(vol, dict) and vix.get("value") is not None:
        related = list(vol.get("related") or [])
        related.append(
            {
                "id": "VIXCLS",
                "label": "VIX",
                "source": "FRED",
                "as_of": _iso(vix.get("date")),
                "value": vix.get("value"),
                "unit": "",
                "note": "미국 VIX는 한국 실현변동성과 시장·시차가 다릅니다. 국면 점수에 넣지 않습니다.",
            }
        )
        vol["related"] = related
        components["volatility"] = vol
    components["_macro"] = {
        "source": "FRED",
        "used_in_quant": False,
        "series": [
            {
                "id": row.get("id"),
                "label": row.get("label"),
                "as_of": _iso(row.get("date")),
                "value": row.get("value"),
                "unit": row.get("unit"),
                "delta": row.get("delta"),
            }
            for row in (fred_series or [])
            if isinstance(row, dict) and row.get("id") in {"DGS2", "DGS10", "T10Y2Y", "DEXKOUS", "VIXCLS"}
        ],
    }
    return components
