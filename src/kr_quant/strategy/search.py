from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from kr_quant.strategy.engine import BacktestResult, run_backtest
from kr_quant.strategy.registry import StrategyDefinition


def chronological_splits(data: pd.DataFrame, train_ratio: float = 0.6, validation_ratio: float = 0.2) -> dict[str, pd.DataFrame]:
    ordered = data.sort_values("date").reset_index(drop=True)
    size = len(ordered)
    train_end = max(15, int(size * train_ratio))
    validation_end = max(train_end + 8, int(size * (train_ratio + validation_ratio)))
    validation_end = min(validation_end, max(size - 8, train_end + 1))
    return {
        "TRAIN": ordered.iloc[:train_end].reset_index(drop=True),
        "VALIDATION": ordered.iloc[train_end:validation_end].reset_index(drop=True),
        "OOS": ordered.iloc[validation_end:].reset_index(drop=True),
    }


def parameter_combinations(spec: StrategyDefinition) -> list[dict[str, object]]:
    keys = sorted(spec.grid)
    out: list[dict[str, object]] = []
    for values in itertools.product(*(spec.grid[key] for key in keys)):
        params = dict(zip(keys, values, strict=True))
        if spec.valid_params(params):
            out.append(params)
    return out or [dict(spec.defaults)]


def _score(result: BacktestResult, minimum_trades: int) -> float:
    metrics = result.metrics
    trades = int(metrics.get("trade_count") or 0)
    adequacy = min(trades / max(minimum_trades, 1), 1.0)
    return (
        float(metrics.get("sharpe") or 0) * 0.55
        + float(metrics.get("total_return") or 0) * 0.25
        - abs(float(metrics.get("max_drawdown") or 0)) * 0.20
    ) * adequacy


def parameter_stability(scores: list[float]) -> float:
    if not scores:
        return 0.0
    arr = np.array(sorted(scores, reverse=True)[: min(5, len(scores))], dtype=float)
    center = float(np.mean(arr))
    dispersion = float(np.std(arr))
    if abs(center) < 1e-9:
        return 0.0
    coefficient = dispersion / max(abs(center), 0.05)
    return float(np.clip(100 * (1 - coefficient), 0, 100))


@dataclass
class SearchResult:
    parameters: dict[str, object]
    train_score: float
    oos: dict[str, Any]
    stability: float
    n_combos: int


def search_strategy(
    data: pd.DataFrame,
    spec: StrategyDefinition,
    *,
    slippage_bps: float = 5,
    minimum_trades: int = 8,
) -> SearchResult:
    splits = chronological_splits(data)
    train = splits["TRAIN"]
    oos = splits["OOS"]
    ranked: list[tuple[float, dict[str, object], BacktestResult]] = []
    for params in parameter_combinations(spec):
        try:
            result = run_backtest(train, spec.generate_signals(train, params), slippage_bps=slippage_bps)
        except Exception:  # noqa: BLE001
            continue
        ranked.append((_score(result, minimum_trades), params, result))
    if not ranked:
        return SearchResult(dict(spec.defaults), 0.0, {}, 0.0, 0)
    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best_params, _train = ranked[0]
    oos_bt = run_backtest(oos, spec.generate_signals(oos, best_params), slippage_bps=slippage_bps) if len(oos) >= 8 else None
    oos_metrics = dict(oos_bt.metrics) if oos_bt else {}
    return SearchResult(
        best_params,
        float(best_score),
        oos_metrics,
        parameter_stability([s for s, _, _ in ranked]),
        len(ranked),
    )


def walk_forward(
    data: pd.DataFrame,
    spec: StrategyDefinition,
    *,
    train_days: int = 40,
    test_days: int = 15,
    step_days: int = 15,
    slippage_bps: float = 5,
) -> list[dict[str, Any]]:
    ordered = data.sort_values("date").reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    start = 0
    window = 1
    while start + train_days + test_days <= len(ordered):
        train = ordered.iloc[start : start + train_days].reset_index(drop=True)
        test = ordered.iloc[start + train_days : start + train_days + test_days].reset_index(drop=True)
        picked = search_strategy(train, spec, slippage_bps=slippage_bps, minimum_trades=3)
        oos = run_backtest(test, spec.generate_signals(test, picked.parameters), slippage_bps=slippage_bps)
        rows.append(
            {
                "window": window,
                "oos_return": oos.metrics.get("total_return"),
                "oos_sharpe": oos.metrics.get("sharpe"),
                "trade_count": oos.metrics.get("trade_count"),
                "params": picked.parameters,
            }
        )
        start += max(1, step_days)
        window += 1
        if window > 6:
            break
    return rows


def walk_forward_score(windows: list[dict[str, Any]]) -> float:
    if not windows:
        return 0.0
    rets = [float(w.get("oos_return") or 0) for w in windows]
    positive = sum(1 for v in rets if v > 0) / len(rets)
    variability = float(np.std(rets)) if len(rets) > 1 else 0.0
    return float(np.clip(positive * 100 - min(variability * 100, 50), 0, 100))


def stability_label(*, sharpe: float, trades: int, wf_score: float, min_trades: int) -> str:
    if trades < min_trades or wf_score < 35:
        return "LOW"
    if sharpe >= 0.8 and wf_score >= 60:
        return "HIGH"
    return "MEDIUM"
