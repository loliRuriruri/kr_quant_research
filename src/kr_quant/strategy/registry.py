from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

SignalFunction = Callable[[pd.DataFrame, dict[str, object]], pd.DataFrame]


def _numeric(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy().sort_values("date").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    if "open" in result.columns:
        result["open"] = result["open"].fillna(result["close"])
    return result


def _signal_frame(entry: pd.Series, exit_: pd.Series, extra: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    out = pd.DataFrame({"entry": entry.fillna(False).astype(bool), "exit": exit_.fillna(False).astype(bool)})
    if extra:
        for key, series in extra.items():
            out[key] = series
    return out


def _reason_on(mask: pd.Series, values: pd.Series, formatter) -> pd.Series:
    reason = pd.Series(pd.NA, index=mask.index, dtype="object")
    active = mask.fillna(False) & values.notna()
    if not bool(active.any()):
        return reason
    reason.loc[active] = [formatter(value) for value in values.loc[active]]
    return reason


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    relative = gain / loss.replace(0, pd.NA)
    return 100 - 100 / (1 + relative)


def rsi_signals(data: pd.DataFrame, params: dict[str, object]) -> pd.DataFrame:
    frame = _numeric(data)
    values = _rsi(frame["close"], int(params["period"]))
    oversold = float(params["oversold"])
    overbought = float(params["overbought"])
    entry = values < oversold
    exit_ = values > overbought
    return _signal_frame(
        entry,
        exit_,
        {
            "entry_reason": _reason_on(entry, values, lambda value: f"RSI {float(value):.1f} < 과매도 {oversold}"),
            "exit_reason": _reason_on(exit_, values, lambda value: f"RSI {float(value):.1f} > 과매수 {overbought}"),
        },
    )


def ma_cross_signals(data: pd.DataFrame, params: dict[str, object]) -> pd.DataFrame:
    frame = _numeric(data)
    fast_n = int(params["fast"])
    slow_n = int(params["slow"])
    fast = frame["close"].rolling(fast_n).mean()
    slow = frame["close"].rolling(slow_n).mean()
    entry = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    exit_ = fast < slow
    return _signal_frame(
        entry,
        exit_,
        {
            "entry_reason": _reason_on(entry, fast, lambda value: f"단기 {fast_n}일선이 장기 {slow_n}일선을 상향 돌파"),
            "exit_reason": _reason_on(exit_, fast, lambda value: f"단기 {fast_n}일선이 장기 {slow_n}일선 아래"),
        },
    )


def donchian_signals(data: pd.DataFrame, params: dict[str, object]) -> pd.DataFrame:
    frame = _numeric(data)
    entry_period = int(params["entry_period"])
    exit_period = int(params["exit_period"])
    high = frame["high"].shift(1).rolling(entry_period).max()
    low = frame["low"].shift(1).rolling(exit_period).min()
    entry = frame["close"] > high
    exit_ = frame["close"] < low
    return _signal_frame(
        entry,
        exit_,
        {
            "entry_reason": _reason_on(
                entry, frame["close"], lambda value: f"종가 {float(value):.0f}가 {entry_period}일 고점 돌파"
            ),
            "exit_reason": _reason_on(
                exit_, frame["close"], lambda value: f"종가 {float(value):.0f}가 {exit_period}일 저점 이탈"
            ),
        },
    )


def bollinger_signals(data: pd.DataFrame, params: dict[str, object]) -> pd.DataFrame:
    frame = _numeric(data)
    period = int(params["period"])
    width = float(params["stddev"])
    middle = frame["close"].rolling(period).mean()
    deviation = frame["close"].rolling(period).std(ddof=0)
    lower = middle - width * deviation
    entry = frame["close"] < lower
    exit_ = frame["close"] > middle
    return _signal_frame(
        entry,
        exit_,
        {
            "entry_reason": _reason_on(
                entry, frame["close"], lambda value: f"종가 {float(value):.0f}가 볼린저 하단({period}일, {width}σ) 이탈"
            ),
            "exit_reason": _reason_on(
                exit_, frame["close"], lambda value: f"종가 {float(value):.0f}가 볼린저 중심선 복귀"
            ),
        },
    )


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    family: str
    defaults: dict[str, object]
    grid: dict[str, list[object]]
    signal_function: SignalFunction

    def generate_signals(self, data: pd.DataFrame, params: dict[str, object] | None = None) -> pd.DataFrame:
        return self.signal_function(data, params or self.defaults)

    def valid_params(self, params: dict[str, object]) -> bool:
        if "fast" in params and "slow" in params and int(params["fast"]) >= int(params["slow"]):
            return False
        if "entry_period" in params and "exit_period" in params and int(params["exit_period"]) > int(params["entry_period"]):
            return False
        return True


def strategy_registry() -> dict[str, StrategyDefinition]:
    items = (
        StrategyDefinition(
            "rsi_reversion",
            "RSI 평균회귀",
            "MEAN_REVERSION",
            {"period": 14, "oversold": 30, "overbought": 70},
            {"period": [10, 14, 20], "oversold": [25, 30], "overbought": [70]},
            rsi_signals,
        ),
        StrategyDefinition(
            "bollinger_reversion",
            "볼린저 평균회귀",
            "MEAN_REVERSION",
            {"period": 20, "stddev": 2.0},
            {"period": [15, 20], "stddev": [1.5, 2.0]},
            bollinger_signals,
        ),
        StrategyDefinition(
            "ma_cross",
            "이동평균 교차",
            "TREND",
            {"fast": 10, "slow": 40},
            {"fast": [5, 10], "slow": [30, 40]},
            ma_cross_signals,
        ),
        StrategyDefinition(
            "donchian",
            "돈치안 돌파",
            "TREND",
            {"entry_period": 20, "exit_period": 10},
            {"entry_period": [15, 20], "exit_period": [8, 10]},
            donchian_signals,
        ),
    )
    return {item.strategy_id: item for item in items}


PARAM_KO = {
    "period": "기간",
    "oversold": "과매도",
    "overbought": "과매수",
    "stddev": "밴드폭",
    "fast": "단기이평",
    "slow": "장기이평",
    "entry_period": "진입 채널",
    "exit_period": "청산 채널",
}

FAMILY_KO = {
    "MEAN_REVERSION": "평균회귀",
    "TREND": "추세",
    "MOMENTUM": "모멘텀",
    "VOLUME": "거래량",
}

DAY_KEYS = {"period", "fast", "slow", "entry_period", "exit_period"}

SELECTION_KO = (
    "파라미터 후보는 학습 구간에서 계산하고 가운데 검증 구간 성과로 하나를 고릅니다. "
    "점수 = 샤프 55% + 수익률 25% − |최대낙폭| 20%이며, 매매가 목표보다 적으면 점수를 깎습니다. "
    "마지막 20% 최종검증과 walk-forward는 선택에 쓰지 않고 과적합 확인에만 사용합니다."
)


def format_params_ko(params: dict[str, object] | None) -> str:
    if not params:
        return ""
    parts: list[str] = []
    for key, value in params.items():
        label = PARAM_KO.get(key, key)
        if key in DAY_KEYS:
            parts.append(f"{label} {value}일")
        elif key == "stddev":
            parts.append(f"{label} {value}배")
        else:
            parts.append(f"{label} {value}")
    return " · ".join(parts)


def _how_it_works(row: dict[str, Any], params: dict[str, object]) -> str:
    sid = str(row.get("strategy_id") or "")
    name = str(row.get("name") or "")
    family = FAMILY_KO.get(str(row.get("family") or ""), "연구")
    if sid == "rsi_reversion" or name.startswith("RSI"):
        return (
            f"RSI가 과매도({params.get('oversold')})로 내려가면 사고, "
            f"과매수({params.get('overbought')})로 올라가면 파는 평균회귀입니다."
        )
    if sid == "bollinger_reversion" or "볼린저" in name:
        return (
            f"종가가 하단 밴드(기간 {params.get('period')}일, {params.get('stddev')}σ)를 벗어나면 사고, "
            "중심선으로 돌아오면 파는 평균회귀입니다."
        )
    if sid == "ma_cross" or "이동평균" in name:
        return (
            f"단기이평({params.get('fast')}일)이 장기이평({params.get('slow')}일)을 위로 돌파하면 "
            "추세를 따라 들어갑니다."
        )
    if sid == "donchian" or "돈치안" in name:
        return (
            f"최근 {params.get('entry_period')}일 고점을 돌파하면 들어가고, "
            f"{params.get('exit_period')}일 저점을 깨면 나옵니다."
        )
    return f"{name or '이 전략'}은 {family} 연구 후보입니다."


def strategy_comment(row: dict[str, Any]) -> str:
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    params_ko = format_params_ko(params)
    label = str(row.get("stability_label") or "")
    wf_hit = row.get("wf_hit")
    wf_n = int(row.get("wf_windows") or 0)
    trades = int(row.get("trade_count") or 0)
    oos = row.get("oos_sharpe")
    mdd = row.get("max_drawdown")
    bits = [_how_it_works(row, params)]
    if params_ko:
        bits.append(f"고른 설정: {params_ko}.")
    bits.append("선정은 학습 구간 점수만 쓰고, 이후 구간은 고를 때 보지 않습니다.")
    if oos is not None:
        try:
            bits.append(f"학습 밖 샤프 {float(oos):.2f}.")
        except (TypeError, ValueError):
            pass
    if wf_n:
        hit = "—" if wf_hit is None else f"{round(float(wf_hit) * 100)}%"
        bits.append(f"Walk-forward {wf_n}창 중 양수 {hit}.")
    bits.append(f"표본 매매 {trades}회.")
    if mdd is not None:
        try:
            bits.append(f"최대낙폭 {float(mdd) * 100:.1f}%.")
        except (TypeError, ValueError):
            pass
    if label == "LOW":
        bits.append("안정성 LOW라 연구 후보일 뿐 순위로 쓰지 마세요. 일봉이 짧거나 창마다 성과가 갈립니다.")
    elif label == "HIGH":
        bits.append("학습 밖 구간과 walk-forward가 같은 방향을 가리킵니다. 그래도 주문 신호가 아닙니다.")
    elif label == "MEDIUM":
        bits.append("중간 안정성입니다. 표본을 더 쌓기 전에는 순위로 쓰지 마세요.")
    return " ".join(b for b in bits if b)
