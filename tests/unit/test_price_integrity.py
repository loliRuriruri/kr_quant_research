from __future__ import annotations

import pandas as pd

from kr_quant.quality.price_integrity import latest_clean_price_segments


def _rows(close: list[float], shares: list[float] | None = None) -> pd.DataFrame:
    shares = shares or [1_000.0] * len(close)
    return pd.DataFrame(
        {
            "ticker": ["000001"] * len(close),
            "trade_date": pd.date_range("2026-01-02", periods=len(close), freq="B"),
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1_000] * len(close),
            "listed_shares": shares,
            "market_cap": [value * count for value, count in zip(close, shares)],
        }
    )


def test_share_change_price_reset_starts_new_clean_segment():
    prices = _rows([100, 101, 50, 51, 52], [1_000, 1_000, 2_000, 2_000, 2_000])

    clean, issues, summary = latest_clean_price_segments(prices)

    assert clean["close"].tolist() == [50, 51, 52]
    assert issues["issue_code"].tolist() == ["LIKELY_SHARE_CHANGE_PRICE_RESET"]
    assert summary["corporate_action_confirmation"] is False
    assert summary["excluded_pre_break_rows"] == 2


def test_unexplained_price_jump_is_critical_and_not_counted_across():
    prices = _rows([100, 101, 180, 181])

    clean, issues, summary = latest_clean_price_segments(prices)

    assert clean["close"].tolist() == [180, 181]
    assert issues.iloc[0]["issue_code"] == "UNEXPLAINED_PRICE_DISCONTINUITY"
    assert issues.iloc[0]["severity"] == "CRITICAL"
    assert summary["critical_issue_count"] == 1


def test_invalid_ohlc_bar_is_removed_and_breaks_history():
    prices = _rows([100, 101, 102, 103])
    prices.loc[2, "high"] = 90

    clean, issues, _ = latest_clean_price_segments(prices)

    assert clean["close"].tolist() == [103]
    assert issues.iloc[0]["issue_code"] == "INVALID_OHLC_RANGE"


def test_zero_volume_placeholder_is_dropped_without_resetting_segment():
    prices = _rows([100, 100, 101])
    prices.loc[1, ["open", "high", "low", "volume"]] = 0

    clean, issues, summary = latest_clean_price_segments(prices)

    assert clean["close"].tolist() == [100, 101]
    assert issues["issue_code"].tolist() == ["NO_TRADE_BAR_DROPPED"]
    assert summary["tickers_with_breaks"] == 0
    assert summary["non_trading_bar_count"] == 1


def test_multiple_tickers_keep_each_latest_segment():
    first = _rows([100, 101, 102])
    second = _rows([10, 20, 21])
    second["ticker"] = "000002"

    clean, issues, summary = latest_clean_price_segments(pd.concat([first, second], ignore_index=True))

    assert len(clean[clean["ticker"] == "000001"]) == 3
    assert clean[clean["ticker"] == "000002"]["close"].tolist() == [20, 21]
    assert len(issues) == 1
    assert summary["tickers_analyzed"] == 2
