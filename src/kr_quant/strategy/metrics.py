from __future__ import annotations

import math

import numpy as np
import pandas as pd


def performance_metrics(
    equity_curve: pd.DataFrame,
    *,
    trade_returns: list[float],
    holding_days: list[int],
    turnover: float,
    exposure: float,
) -> dict[str, float | int | None]:
    if equity_curve is None or equity_curve.empty:
        return {"total_return": 0.0, "trade_count": 0, "sharpe": 0.0}
    equity = pd.to_numeric(equity_curve["equity"], errors="coerce").dropna()
    benchmark = pd.to_numeric(equity_curve["benchmark"], errors="coerce").dropna()
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0
    benchmark_return = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1) if len(benchmark) > 1 else 0.0
    std = float(returns.std(ddof=0)) if not returns.empty else 0.0
    mean = float(returns.mean()) if not returns.empty else 0.0
    sharpe = mean / std * math.sqrt(252) if std > 0 else 0.0
    peak = equity.cummax()
    mdd = float((equity / peak - 1).min()) if len(equity) else 0.0
    wins = [v for v in trade_returns if v > 0]
    losses = [v for v in trade_returns if v < 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else 0.0
    if "benchmark_total" in equity_curve.columns:
        hold_total = pd.to_numeric(equity_curve["benchmark_total"], errors="coerce").dropna()
        benchmark_total_return = (
            float(hold_total.iloc[-1] / hold_total.iloc[0] - 1) if len(hold_total) > 1 and float(hold_total.iloc[0] or 0) > 0 else 0.0
        )
    else:
        benchmark_total_return = benchmark_return
    n_bars = int(len(equity))
    aligned = True
    if "date" in equity_curve.columns:
        aligned = int(equity_curve["date"].nunique()) == n_bars
    return {
        "total_return": round(total_return, 4),
        "benchmark_return": round(benchmark_return, 4),
        "benchmark_price_return": round(benchmark_return, 4),
        "benchmark_total_return": round(benchmark_total_return, 4),
        "excess_return": round(total_return - benchmark_return, 4),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown": round(mdd, 4),
        "win_rate": round(win_rate, 3),
        "trade_count": len(trade_returns),
        "avg_holding_days": round(float(np.mean(holding_days)), 1) if holding_days else 0.0,
        "turnover": round(float(turnover), 3),
        "exposure": round(float(exposure), 3),
        "benchmark_kind": "same_security_aligned_buy_and_hold",
        "benchmark_aligned": aligned,
        "benchmark_aligned_bars": n_bars,
    }
