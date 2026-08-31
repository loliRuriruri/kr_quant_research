from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import pandas as pd

from kr_quant.strategy.metrics import performance_metrics


@dataclass(frozen=True)
class ExecutionModel:
    commission_bps: float = 0.0
    slippage_bps: float = 5.0
    sell_tax_bps: float = 0.0
    sell_tax_schedule_bps: tuple[tuple[str, float], ...] = ()
    position_notional_krw: float = 0.0
    max_participation_rate: float = 0.0
    impact_bps_at_max_participation: float = 0.0
    price_limit_pct: float = 0.30
    lock_tolerance_pct: float = 0.005
    max_pending_days: int = 3
    block_zero_volume: bool = False

    def tax_bps(self, when: Any) -> float:
        try:
            day = pd.Timestamp(when).date()
        except (TypeError, ValueError):
            return float(self.sell_tax_bps)
        selected = float(self.sell_tax_bps)
        for effective, value in sorted(self.sell_tax_schedule_bps, key=lambda item: item[0]):
            try:
                if date.fromisoformat(str(effective)) <= day:
                    selected = float(value)
            except ValueError:
                continue
        return selected

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sell_tax_schedule_bps"] = [
            {"effective_from": effective, "bps": value} for effective, value in self.sell_tax_schedule_bps
        ]
        payload["execution"] = "signal close -> next tradable open"
        payload["price_limit_detection"] = "daily OHLC one-price lock proxy"
        return payload


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, Any]


def execution_model_from_mapping(
    value: ExecutionModel | dict[str, Any] | None,
    *,
    commission_bps: float,
    slippage_bps: float,
) -> ExecutionModel:
    if isinstance(value, ExecutionModel):
        return value
    raw = dict(value or {})
    schedule: list[tuple[str, float]] = []
    for item in raw.get("sell_tax_schedule_bps") or []:
        if isinstance(item, dict):
            effective = str(item.get("effective_from") or "")
            bps = item.get("bps")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            effective, bps = str(item[0]), item[1]
        else:
            continue
        try:
            date.fromisoformat(effective)
            schedule.append((effective, float(bps)))
        except (TypeError, ValueError):
            continue
    return ExecutionModel(
        commission_bps=float(raw.get("commission_bps", commission_bps) or 0),
        slippage_bps=float(raw.get("slippage_bps", slippage_bps) or 0),
        sell_tax_bps=float(raw.get("sell_tax_bps") or 0),
        sell_tax_schedule_bps=tuple(schedule),
        position_notional_krw=float(raw.get("position_notional_krw") or 0),
        max_participation_rate=float(raw.get("max_participation_rate") or 0),
        impact_bps_at_max_participation=float(raw.get("impact_bps_at_max_participation") or 0),
        price_limit_pct=float(raw.get("price_limit_pct") or 0.30),
        lock_tolerance_pct=float(raw.get("lock_tolerance_pct") or 0.005),
        max_pending_days=max(0, int(raw.get("max_pending_days") or 0)),
        block_zero_volume=bool(raw.get("block_zero_volume", False)),
    )


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if pd.notna(number) else default
    except (TypeError, ValueError):
        return default


def _fill_check(
    row: pd.Series,
    *,
    previous_close: float,
    side: str,
    model: ExecutionModel,
    notional_krw: float,
) -> tuple[bool, str | None, float, float]:
    open_price = _number(row.get("open") or row.get("close"))
    volume = _number(row.get("volume"))
    if open_price <= 0:
        return False, "INVALID_PRICE", 0.0, 0.0
    if model.block_zero_volume and volume <= 0:
        return False, "ZERO_VOLUME", 0.0, 0.0

    daily_value = open_price * max(volume, 0.0)
    participation = notional_krw / daily_value if daily_value > 0 and notional_krw > 0 else 0.0
    if model.max_participation_rate > 0 and participation > model.max_participation_rate:
        return False, "LIQUIDITY_LIMIT", participation, 0.0

    high = _number(row.get("high"), open_price)
    low = _number(row.get("low"), open_price)
    one_price = abs(high - low) <= max(open_price * 0.0001, 1e-9)
    gap = open_price / previous_close - 1 if previous_close > 0 else 0.0
    lock_level = model.price_limit_pct * (1 - model.lock_tolerance_pct)
    if one_price and side == "BUY" and gap >= lock_level:
        return False, "UPPER_LIMIT_LOCK", participation, 0.0
    if one_price and side == "SELL" and gap <= -lock_level:
        return False, "LOWER_LIMIT_LOCK", participation, 0.0

    impact = 0.0
    if model.max_participation_rate > 0 and model.impact_bps_at_max_participation > 0:
        impact = model.impact_bps_at_max_participation * min(
            max(participation / model.max_participation_rate, 0.0), 1.0
        )
    return True, None, participation, impact


def _simulate(data: pd.DataFrame, signals: pd.DataFrame, *, model: ExecutionModel) -> BacktestResult:
    frame = data.sort_values("date").reset_index(drop=True).copy()
    signal_frame = signals.reset_index(drop=True).reindex(frame.index).fillna(False)
    if frame.empty:
        return BacktestResult(pd.DataFrame(), pd.DataFrame(), {"total_return": 0.0, "trade_count": 0})
    cash = 1.0
    shares = 0.0
    pending: str | None = None
    pending_days = 0
    entry_value: float | None = None
    entry_market_price: float | None = None
    entry_index: int | None = None
    trade_rows: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []
    turnover = 0.0
    exposed_days = 0
    blocked: dict[str, int] = {}
    cancelled_orders = 0
    explicit_cost = 0.0
    max_participation = 0.0
    first_open = _number(frame.iloc[0].get("open") or frame.iloc[0].get("close"))

    for index, row in frame.iterrows():
        open_price = _number(row.get("open") or row.get("close"))
        close_price = _number(row.get("close"))
        previous_close = _number(frame.iloc[index - 1].get("close")) if index > 0 else open_price
        filled = False
        if pending == "BUY" and shares == 0:
            allowed, reason, participation, impact_bps = _fill_check(
                row,
                previous_close=previous_close,
                side="BUY",
                model=model,
                notional_krw=cash * model.position_notional_krw,
            )
            max_participation = max(max_participation, participation)
            if allowed:
                buy_cost_bps = model.commission_bps + model.slippage_bps + impact_bps
                execution_price = open_price * (1 + buy_cost_bps / 10_000)
                shares = cash / execution_price
                explicit_cost += max(0.0, cash - shares * open_price)
                entry_value = execution_price
                entry_market_price = open_price
                entry_index = index
                turnover += cash
                cash = 0.0
                filled = True
            else:
                blocked[str(reason)] = blocked.get(str(reason), 0) + 1
        elif pending == "SELL" and shares > 0:
            allowed, reason, participation, impact_bps = _fill_check(
                row,
                previous_close=previous_close,
                side="SELL",
                model=model,
                notional_krw=shares * open_price * model.position_notional_krw,
            )
            max_participation = max(max_participation, participation)
            if allowed:
                tax_bps = model.tax_bps(row.get("date"))
                sell_cost_bps = model.commission_bps + model.slippage_bps + impact_bps + tax_bps
                execution_price = open_price * (1 - sell_cost_bps / 10_000)
                proceeds = shares * execution_price
                explicit_cost += max(0.0, shares * open_price - proceeds)
                turnover += proceeds
                trade_rows.append(
                    {
                        "entry_date": frame.iloc[entry_index]["date"] if entry_index is not None else None,
                        "exit_date": row["date"],
                        "entry_market_price": entry_market_price,
                        "entry_execution_price": entry_value,
                        "exit_market_price": open_price,
                        "exit_execution_price": execution_price,
                        "gross_return": open_price / entry_market_price - 1 if entry_market_price else 0.0,
                        "return": execution_price / entry_value - 1 if entry_value else 0.0,
                        "holding_days": index - entry_index if entry_index is not None else 0,
                        "sell_tax_bps": tax_bps,
                        "impact_bps": impact_bps,
                    }
                )
                cash = proceeds
                shares = 0.0
                entry_value = None
                entry_market_price = None
                entry_index = None
                filled = True
            else:
                blocked[str(reason)] = blocked.get(str(reason), 0) + 1

        if pending:
            if filled:
                pending = None
                pending_days = 0
            else:
                pending_days += 1
                if pending_days > model.max_pending_days:
                    pending = None
                    pending_days = 0
                    cancelled_orders += 1

        equity = cash + shares * close_price
        if shares > 0:
            exposed_days += 1
        benchmark = close_price / first_open if first_open > 0 else 1.0
        equity_rows.append({"date": row["date"], "equity": equity, "benchmark": benchmark})

        if pending is None:
            entry_signal = bool(signal_frame.iloc[index].get("entry", False))
            exit_signal = bool(signal_frame.iloc[index].get("exit", False))
            if shares == 0 and entry_signal and index < len(frame) - 1:
                pending = "BUY"
                pending_days = 0
            elif shares > 0 and exit_signal and index < len(frame) - 1:
                pending = "SELL"
                pending_days = 0

    curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    metrics = performance_metrics(
        curve,
        trade_returns=trades["return"].tolist() if not trades.empty else [],
        holding_days=trades["holding_days"].tolist() if not trades.empty else [],
        turnover=turnover,
        exposure=exposed_days / len(frame) if len(frame) else 0.0,
    )
    metrics.update(
        {
            "blocked_order_count": int(sum(blocked.values())),
            "blocked_order_reasons": blocked,
            "cancelled_order_count": cancelled_orders,
            "unclosed_position": bool(shares > 0),
            "estimated_cost_ratio": explicit_cost,
            "max_participation_rate_observed": max_participation,
            "execution_model": model.public(),
        }
    )
    return BacktestResult(curve, trades, metrics)


def run_backtest(
    data: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    commission_bps: float = 0,
    slippage_bps: float = 5,
    execution_model: ExecutionModel | dict[str, Any] | None = None,
) -> BacktestResult:
    """Long-only. A close signal executes at the next tradable open."""
    model = execution_model_from_mapping(
        execution_model,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
    )
    return _simulate(data, signals, model=model)


def oos_return(curve: pd.DataFrame, oos_ratio: float = 0.2) -> float | None:
    if curve is None or curve.empty or len(curve) < 10:
        return None
    cut = max(1, int(len(curve) * (1 - oos_ratio)))
    tail = curve.iloc[cut - 1 :]
    eq = pd.to_numeric(tail["equity"], errors="coerce").dropna()
    if len(eq) < 2 or float(eq.iloc[0]) <= 0:
        return None
    return float(eq.iloc[-1] / eq.iloc[0] - 1)
