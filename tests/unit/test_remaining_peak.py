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
    assert result["metric_version"] == 4


def test_missing_adjusted_lows_are_not_reported_as_zero_risk():
    prices = _seasonal_prices(range(2021, 2027))
    prices["low"] = float("nan")
    result = calculate_remaining_peak_upside(prices, "005930", 9, as_of_date="2026-08-26")
    assert result["window_adverse_excursion_p50"] is None
    assert result["window_close_max_drawdown_p50"] < 0


def test_actual_month_end_and_leap_year_dates():
    from kr_quant.strategy.remaining_peak import _safe_date
    assert str(_safe_date(2024, 2, 31)) == '2024-02-29'
    assert str(_safe_date(2025, 2, 31)) == '2025-02-28'
    assert str(_safe_date(2026, 4, 31)) == '2026-04-30'
    assert str(_safe_date(2026, 7, 31)) == '2026-07-31'


def test_month_end_peak_is_not_pulled_back_to_28_and_rolls_year():
    rows = []
    for year in range(2021, 2027):
        for dt in pd.date_range(f'{year}-06-20', f'{year}-08-10'):
            close = 110 - abs((dt-pd.Timestamp(f'{year}-07-31')).days)*.2
            rows.append({'ticker': '005930', 'trade_date': dt, 'open': close, 'close': close,
                         'adj_close': close, 'high': close, 'low': close, 'volume': 10000})
    frame = pd.DataFrame(rows)
    result = calculate_remaining_peak_upside(frame, '005930', 7, as_of_date='2026-07-10')
    assert result['historical_peak_day'] == 31
    assert result['target_peak_date'] == '2026-07-31'
    assert result['entry_window_str'] == '07/01 ~ 07/16'
    assert result['timing_day_unit'] == 'CALENDAR_DAYS_NOT_TRADING_SESSIONS'
    assert result['peak_day_p25'] == result['peak_day_p75'] == 31
    rolled = calculate_remaining_peak_upside(frame, '005930', 7, as_of_date='2026-08-10')
    assert rolled['target_peak_date'] == '2027-07-31'


def test_window_uncertainty_uses_same_years_not_future_win_probability():
    result = calculate_remaining_peak_upside(_seasonal_prices(range(2021, 2027)), '005930', 9, as_of_date='2026-08-26')
    stats = result['window_end_uncertainty']
    assert stats['n'] == result['sample_count']
    assert stats['wins'] == result['window_end_positive_count']
    assert stats['verified'] is False
    assert stats['wilson95'][0] < stats['positive_fraction']
    loo = result['window_end_leave_one_year_out']
    assert loo['min_median'] <= loo['max_median']
    assert loo['verified'] is False
    assert 'NOT_RETRAINED_OOS' in loo['method']


def test_corrected_calendar_can_change_candidate_eligibility_explicitly():
    from datetime import date
    from kr_quant.strategy.remaining_peak import _stage_for
    from kr_quant.strategy.pre_entry_ranking import rank_pre_entry_from_inputs
    def ranked(peak_day):
        stage, _ = _stage_for(date(2026, 7, 15), date(2026, 7, peak_day))
        row = {'ticker': '005930', 'pattern_id': 'month-end', 'entry_stage': stage,
               'seasonality_score': 60, 'remaining_peak': {'available': True, 'remaining_p50': .1,
                                                        'price_as_of': '2026-07-15'}}
        return rank_pre_entry_from_inputs([row], clean_set={'005930'},
               quotes={'005930': {'last_close': 2000, 'as_of': '2026-07-15'}})
    assert ranked(28) == []  # Old clamp incorrectly put this in the rally stage.
    assert ranked(31)[0]['ticker'] == '005930'


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
