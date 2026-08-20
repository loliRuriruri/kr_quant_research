from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from kr_quant.strategy.metrics import performance_metrics


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float | int | None]


def _simulate(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    commission_bps: float,
    slippage_bps: float,
) -> BacktestResult:
    frame = data.sort_values("date").reset_index(drop=True).copy()
    signal_frame = signals.reset_index(drop=True).reindex(frame.index).fillna(False)
    if frame.empty:
        return BacktestResult(pd.DataFrame(), pd.DataFrame(), {"total_return": 0.0, "trade_count": 0})
    fee = (float(commission_bps) + float(slippage_bps)) / 10_000
    cash = 1.0
    shares = 0.0
    pending: str | None = None
    entry_value: float | None = None
    entry_index: int | None = None
    trade_rows: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []
    turnover = 0.0
    exposed_days = 0
    first_open = float(frame.iloc[0]["open"] or frame.iloc[0]["close"] or 0)

    for index, row in frame.iterrows():
        open_price = float(row["open"] or row["close"] or 0)
        close_price = float(row["close"] or 0)
        if pending == "BUY" and shares == 0 and open_price > 0:
            execution_price = open_price * (1 + fee)
            shares = cash / execution_price
            entry_value = execution_price
            entry_index = index
            turnover += cash
            cash = 0.0
        elif pending == "SELL" and shares > 0 and open_price > 0:
            execution_price = open_price * (1 - fee)
            proceeds = shares * execution_price
            turnover += proceeds
            trade_rows.append(
                {
                    "entry_date": frame.iloc[entry_index]["date"] if entry_index is not None else None,
                    "exit_date": row["date"],
                    "return": execution_price / entry_value - 1 if entry_value else 0.0,
                    "holding_days": index - entry_index if entry_index is not None else 0,
                }
            )
            cash = proceeds
            shares = 0.0
            entry_value = None
            entry_index = None
        pending = None

        if index == len(frame) - 1 and shares > 0 and close_price > 0:
            execution_price = close_price * (1 - fee)
            proceeds = shares * execution_price
            turnover += proceeds
            trade_rows.append(
                {
                    "entry_date": frame.iloc[entry_index]["date"] if entry_index is not None else None,
                    "exit_date": row["date"],
                    "return": execution_price / entry_value - 1 if entry_value else 0.0,
                    "holding_days": index - entry_index if entry_index is not None else 0,
                }
            )
            cash = proceeds
            shares = 0.0

        equity = cash + shares * close_price
        if shares > 0:
            exposed_days += 1
        benchmark = close_price / first_open if first_open > 0 else 1.0
        equity_rows.append({"date": row["date"], "equity": equity, "benchmark": benchmark})

        entry_signal = bool(signal_frame.iloc[index].get("entry", False))
        exit_signal = bool(signal_frame.iloc[index].get("exit", False))
        if shares == 0 and entry_signal:
            pending = "BUY"
        elif shares > 0 and exit_signal:
            pending = "SELL"

    curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    metrics = performance_metrics(
        curve,
        trade_returns=trades["return"].tolist() if not trades.empty else [],
        holding_days=trades["holding_days"].tolist() if not trades.empty else [],
        turnover=turnover,
        exposure=exposed_days / len(frame) if len(frame) else 0.0,
    )
    return BacktestResult(curve, trades, metrics)


def run_backtest(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    commission_bps: float = 0,
    slippage_bps: float = 5,
) -> BacktestResult:
    """Long-only. Signal on day t executes at day t+1 open."""
    return _simulate(data, signals, commission_bps=commission_bps, slippage_bps=slippage_bps)


def oos_return(curve: pd.DataFrame, oos_ratio: float = 0.2) -> float | None:
    if curve is None or curve.empty or len(curve) < 10:
        return None
    cut = max(1, int(len(curve) * (1 - oos_ratio)))
    tail = curve.iloc[cut - 1 :]
    eq = pd.to_numeric(tail["equity"], errors="coerce").dropna()
    if len(eq) < 2 or float(eq.iloc[0]) <= 0:
        return None
    return float(eq.iloc[-1] / eq.iloc[0] - 1)
