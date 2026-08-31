from dataclasses import replace

import pandas as pd

from kr_quant.quality.corporate_actions import apply_official_adjustments
from kr_quant.strategy.engine import ExecutionModel, run_backtest
from kr_quant.strategy.precision import sample_reliability, ticker_listing_window
from kr_quant.strategy.registry import strategy_registry
from kr_quant.strategy.run import evaluate_ticker


def _ohlc(n=40, close_start=100.0):
    close = [close_start + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-02", periods=n, freq="B"),
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [100_000] * n,
        }
    )


def test_cost_sensitivity_uses_same_params_and_conservative_is_worse():
    data = _ohlc(80)
    result = evaluate_ticker(data, commission_bps=1.5, slippage_bps=5, oos_ratio=0.2, min_days=40)
    row = result["strategies"][0]
    cost = row["cost_sensitivity"]
    assert set(cost) >= {"low", "default", "conservative"}
    assert cost["conservative"]["total_return"] <= cost["low"]["total_return"]
    spec = strategy_registry()[row["strategy_id"]]
    replay = run_backtest(
        data,
        spec.generate_signals(data, row["params"]),
        commission_bps=1.5,
        slippage_bps=5,
    )
    assert row["total_return"] == replay.metrics["total_return"]


def test_capacity_large_can_block_when_volume_is_thin():
    data = _ohlc(12)
    data["volume"] = 10_000
    signals = pd.DataFrame({"entry": [True] + [False] * 11, "exit": [False] * 10 + [True, False]})
    small = run_backtest(
        data,
        signals,
        execution_model=ExecutionModel(
            slippage_bps=0,
            position_notional_krw=100_000,
            max_participation_rate=0.10,
            max_pending_days=3,
        ),
    )
    large = run_backtest(
        data,
        signals,
        execution_model=ExecutionModel(
            slippage_bps=0,
            position_notional_krw=50_000_000,
            max_participation_rate=0.10,
            max_pending_days=3,
        ),
    )
    assert small.metrics["trade_count"] >= 1
    assert large.metrics["blocked_order_reasons"].get("LIQUIDITY_LIMIT", 0) >= 1


def test_thin_sample_hides_representative_sharpe():
    payload = sample_reliability(trade_count=2, oos_trade_count=1)
    assert payload["representative_sharpe"] is False
    assert payload["representative_annualized"] is False
    assert payload["representative_oos_sharpe"] is False
    assert "1~2회" in payload["warning"] or "2회" in payload["warning"]


def test_buy_and_hold_aligns_dates_and_splits_price_vs_total_return():
    prices = pd.DataFrame(
        {
            "ticker": ["000001", "000001", "000001", "000001"],
            "trade_date": pd.to_datetime(["2026-03-25", "2026-03-26", "2026-03-27", "2026-03-30"]),
            "open": [100.0, 100.0, 100.0, 99.0],
            "high": [101.0, 101.0, 101.0, 100.0],
            "low": [99.0, 99.0, 99.0, 98.0],
            "close": [100.0, 100.0, 100.0, 99.0],
            "volume": [1000, 1000, 1000, 1000],
        }
    )
    actions = pd.DataFrame(
        [
            {
                "ticker": "000001",
                "event_type": "DIVIDEND",
                "ex_date": "2026-03-30",
                "cash_amount": 5.0,
                "source": "TEST",
                "confirmed": True,
            }
        ]
    )
    adjusted = apply_official_adjustments(prices, actions)
    data = adjusted.rename(columns={"trade_date": "date"})
    signals = pd.DataFrame({"entry": [False] * 4, "exit": [False] * 4})
    result = run_backtest(data, signals, slippage_bps=0)
    assert result.metrics["benchmark_aligned"] is True
    assert result.metrics["benchmark_aligned_bars"] == 4
    assert result.metrics["benchmark_price_return"] != result.metrics["benchmark_total_return"]
    assert result.metrics["benchmark_total_return"] > result.metrics["benchmark_price_return"]
    dates = pd.to_datetime(result.equity_curve["date"]).dt.date.tolist()
    assert dates == pd.to_datetime(data["date"]).dt.date.tolist()


def test_trade_log_reproduces_entry_and_exit_reason():
    data = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-02", periods=6, freq="B"),
            "open": [100, 100, 100, 110, 110, 110],
            "high": [101, 101, 101, 111, 111, 111],
            "low": [99, 99, 99, 109, 109, 109],
            "close": [100, 100, 100, 110, 110, 110],
            "volume": [1000] * 6,
        }
    )
    spec = strategy_registry()["rsi_reversion"]
    signals = spec.generate_signals(data, {"period": 2, "oversold": 80, "overbought": 20})
    # Force a round trip so the engine copies reasons from the signal bar.
    signals = pd.DataFrame(
        {
            "entry": [True, False, False, False, False, False],
            "exit": [False, False, True, False, False, False],
            "entry_reason": ["RSI 12.0 < 과매도 30", None, None, None, None, None],
            "exit_reason": [None, None, "RSI 80.0 > 과매수 70", None, None, None],
        }
    )
    result = run_backtest(data, signals, slippage_bps=0)
    assert result.metrics["trade_count"] == 1
    trade = result.trades.iloc[0]
    assert "과매도" in str(trade["entry_reason"])
    assert "과매수" in str(trade["exit_reason"])


def test_listing_window_flags_later_listing():
    history = pd.DataFrame(
        [
            {"ticker": "009999", "event_type": "LIST", "event_date": "2026-06-01", "market": "KOSPI", "company": "X", "source": "TEST", "detail": ""},
        ]
    )
    note = ticker_listing_window(history, "009999", "2026-01-01", "2026-08-01")
    assert note["listed_throughout"] is False
    assert note["list_date"] == "2026-06-01"


def test_execution_model_replace_keeps_tax_schedule():
    model = ExecutionModel(sell_tax_bps=20, sell_tax_schedule_bps=(("2026-01-01", 20),))
    cheaper = replace(model, commission_bps=0.5, slippage_bps=2)
    assert cheaper.tax_bps("2026-06-01") == 20
    assert cheaper.commission_bps == 0.5
