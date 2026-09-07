from __future__ import annotations

import pandas as pd

from kr_quant.strategy.remaining_peak import calculate_remaining_peak_upside


def _seasonal_prices(years: range, *, ticker: str = "005930") -> pd.DataFrame:
    rows = []
    for year in years:
        dates = pd.date_range(f"{year}-08-15", f"{year}-09-20", freq="B")
        for dt in dates:
            distance = abs((dt.date() - pd.Timestamp(f"{year}-09-15").date()).days)
            close = 110.0 - min(distance, 20) * 0.5
            rows.append({
                "ticker": ticker,
                "trade_date": dt,
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "adj_close": close,
                "volume": 100_000,
            })
    return pd.DataFrame(rows)


def test_remaining_peak_uses_actual_daily_path_and_current_price():
    prices = _seasonal_prices(range(2021, 2026))
    current = pd.DataFrame([{
        "ticker": "005930",
        "trade_date": pd.Timestamp("2026-08-26"),
        "close": 200.0,
        "high": 202.0,
        "low": 198.0,
        "adj_close": 200.0,
        "volume": 120_000,
    }])
    prices = pd.concat([prices, current], ignore_index=True)

    result = calculate_remaining_peak_upside(
        prices,
        "005930",
        9,
        as_of_date="2026-08-26",
        lookback_years=5,
    )

    assert result["available"] is True
    assert result["sample_count"] == 5
    assert result["historical_peak_day"] == 15
    assert result["target_peak_date"] == "2026-09-15"
    assert result["remaining_p50"] == 0.1
    assert result["peak_price_p50"] == 220.0
    assert result["entry_window_str"] == "08/16 ~ 08/31"
    assert result["entry_stage"] == "TODAY_ENTRY"
    assert result["price_basis"] == "ADJUSTED_CLOSE"


def test_remaining_peak_fails_closed_when_sample_is_too_small():
    prices = _seasonal_prices(range(2024, 2026))
    prices = pd.concat([
        prices,
        pd.DataFrame([{
            "ticker": "005930",
            "trade_date": pd.Timestamp("2026-08-26"),
            "close": 200.0,
            "high": 202.0,
            "low": 198.0,
            "adj_close": 200.0,
            "volume": 120_000,
        }]),
    ], ignore_index=True)

    result = calculate_remaining_peak_upside(
        prices,
        "005930",
        9,
        as_of_date="2026-08-26",
        lookback_years=5,
    )

    assert result["available"] is False
    assert result["status"] == "LOW_SAMPLE"
    assert result["sample_count"] == 2
    assert any("최소 3개년" in warning for warning in result["warnings"])


def test_zero_lookback_means_all_years_not_one():
    prices = _seasonal_prices(range(2016, 2026))
    current = _seasonal_prices(range(2026, 2027))
    prices = pd.concat([prices, current], ignore_index=True)
    all_years = calculate_remaining_peak_upside(prices, '005930', 9, as_of_date='2026-08-26', lookback_years=0)
    recent = calculate_remaining_peak_upside(prices, '005930', 9, as_of_date='2026-08-26', lookback_years=5)
    assert all_years['sample_count'] == 10
    assert recent['sample_count'] == 5
    assert [p['year'] for p in all_years['paths']] == list(range(2016, 2026))


def test_negative_lookback_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        calculate_remaining_peak_upside(_seasonal_prices(range(2020, 2026)), '005930', 9, lookback_years=-1)


def test_remaining_peak_excludes_zero_volume_current_quote():
    prices = _seasonal_prices(range(2021, 2026))
    prices = pd.concat([
        prices,
        pd.DataFrame([{
            "ticker": "005930",
            "trade_date": pd.Timestamp("2026-08-26"),
            "close": 200.0,
            "high": 200.0,
            "low": 200.0,
            "adj_close": 200.0,
            "volume": 0,
        }]),
    ], ignore_index=True)

    result = calculate_remaining_peak_upside(
        prices,
        "005930",
        9,
        as_of_date="2026-08-26",
    )

    assert result["available"] is False
    assert any("거래량이 0" in warning for warning in result["warnings"])
