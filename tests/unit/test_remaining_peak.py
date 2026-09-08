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


def test_falling_paths_keep_losses_separate_from_zero_hindsight_peak():
    prices = _seasonal_prices(range(2021, 2027))
    for year in range(2021, 2027):
        mask = prices.trade_date.dt.year == year
        values = [200.0 - i for i in range(int(mask.sum()))]
        for column in ("close", "adj_close", "high", "low"):
            prices.loc[mask, column] = values
    result = calculate_remaining_peak_upside(prices, "005930", 9, as_of_date="2026-08-26")
    assert result["available"]
    assert result["remaining_p50"] == 0
    assert result["window_end_p50"] < 0
    assert result["window_end_positive_count"] == 0
    assert result["window_end_positive_rate"] == 0
    assert result["window_adverse_excursion_p50"] < 0
    assert result["window_close_max_drawdown_p50"] < 0
    assert result["strategy_net_return_p50"] is None
    assert result["strategy_net_status"] == "EXECUTION_NOT_VALIDATED"
    assert result["costs_included"] is False
    for path in result["paths"]:
        assert path["window_end_date"] >= path["peak_date"]
        assert path["window_adverse_excursion"] <= path["downside_before_peak"]


def test_drawdown_uses_running_high_not_entry_baseline():
    prices = _seasonal_prices(range(2021, 2027))
    result = calculate_remaining_peak_upside(prices, "005930", 9, as_of_date="2026-08-26")
    assert result["window_close_max_drawdown_p50"] < result["window_adverse_excursion_p50"]
    assert result["metric_version"] == 3


def test_missing_adjusted_lows_are_not_reported_as_zero_risk():
    prices = _seasonal_prices(range(2021, 2027))
    prices["low"] = float("nan")
    result = calculate_remaining_peak_upside(prices, "005930", 9, as_of_date="2026-08-26")
    assert result["window_adverse_excursion_p50"] is None
    assert result["window_close_max_drawdown_p50"] < 0


def test_summary_preserves_metric_contract_without_heavy_paths():
    from kr_quant.web.season_listing import pre_entry_card
    result = calculate_remaining_peak_upside(_seasonal_prices(range(2021, 2027)), "005930", 9, as_of_date="2026-08-26")
    card = pre_entry_card({"ticker": "005930", "remaining_peak": result}, 5)
    for key in ("metric_version", "window_end_positive_count", "window_adverse_excursion_p50",
                "window_close_max_drawdown_p50", "strategy_net_return_p50", "strategy_net_status",
                "validation_status", "costs_included"):
        assert card["remaining_peak"][key] == result[key]
    assert "paths" not in card["remaining_peak"]


def test_season_ui_formats_missing_and_large_returns_without_unit_guessing():
    import json
    from pathlib import Path
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the real JS formatter regression")
    js = (Path(__file__).parents[2] / "src/kr_quant/web/static/app.js").read_text(encoding="utf-8")
    start = js.index("function seasonPct(")
    end = js.index("function renderDiscDeepPlaybook(", start)
    script = js[start:end] + '''
console.log(JSON.stringify({missing: seasonPct(null), large: seasonPct(3), zero: seasonPct(0),
  old: seasonObservation({available:true, sample_count:5}),
  unavailable: seasonObservation({available:false, window_end_p50:0.2}),
  ready: seasonObservation({available:true, sample_count:5, window_end_positive_count:2, window_end_p50:-0.1})}));
'''
    values = json.loads(subprocess.check_output([node, "-e", script], text=True, encoding="utf-8"))
    assert values["missing"] == "—"
    assert values["large"] == "+300.0%"
    assert values["zero"] == "0.0%"
    assert values["old"]["end"] == "—"
    assert values["old"]["wins"] == "집계 대기"
    assert values["unavailable"]["end"] == "산출 불가"
    assert values["ready"]["end"] == "-10.0%"
    assert values["ready"]["wins"] == "2/5회 상승"
