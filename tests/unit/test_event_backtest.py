import pandas as pd
import pytest
from kr_quant.events.backtest import backtest_events, calculate_event_forward_returns, summarize_event_backtest


def test_event_forward_returns_and_summary():
    dates = pd.date_range("2024-01-01", periods=30, freq="B").strftime("%Y-%m-%d").tolist()
    
    # 2 tickers: 005930 (rises), 000660 (falls)
    px_rows = []
    for i, d in enumerate(dates):
        px_rows.append({"ticker": "005930", "trade_date": d, "close": 1000 + i * 10})
        px_rows.append({"ticker": "000660", "trade_date": d, "close": 2000 - i * 10})
    prices = pd.DataFrame(px_rows)

    events = [
        {"ticker": "005930", "report_date": dates[0], "event_type": "BUYBACK", "title": "자기주식취득"},
        {"ticker": "005930", "report_date": dates[5], "event_type": "LARGE_CONTRACT", "title": "단일판매공급계약"},
        {"ticker": "000660", "report_date": dates[0], "event_type": "CB_ISSUE", "title": "전환사채발행"},
    ]

    res = backtest_events(events, prices, horizons=(1, 5, 20))
    assert res["used_in_quant"] is False
    assert res["total_events"] == 3
    assert "BUYBACK" in res["by_type"]
    assert "CB_ISSUE" in res["by_type"]
    
    buyback_stat = res["by_type"]["BUYBACK"]["horizons"]["5d"]
    assert buyback_stat["win_rate"] == 100.0
    assert buyback_stat["mean_return"] > 0
    
    cb_stat = res["by_type"]["CB_ISSUE"]["horizons"]["5d"]
    assert cb_stat["win_rate"] == 0.0
    assert cb_stat["mean_return"] < 0


def test_no_nominal_price_benchmark_or_missing_zero():
    prices = pd.DataFrame([
        {"ticker": t, "date": d, "close": v}
        for t, vals in [("005930", [100, 110]), ("000660", [1000000, 900000])]
        for d, v in zip(["2026-09-03", "2026-09-04"], vals)
    ])
    result = backtest_events([{"ticker": "005930", "report_date": "2026-09-03"}], prices, horizons=(1, 5))
    ev = result["events"][0]
    assert ev["ret_1d"] == .1
    assert ev["excess_1d"] is None and ev["ret_5d"] is None
    stat = result["by_type"]["OTHER"]["horizons"]["1d"]
    assert stat["mean_excess_return"] is None and stat["excess_win_rate"] is None
    assert stat["benchmark_samples"] == 0
    assert not result["methodology"]["is_executable_backtest"]


def test_named_benchmark_uses_exact_dates_and_missing_does_not_fill():
    prices = pd.DataFrame({"ticker": ["005930"] * 3, "date": ["2026-09-02", "2026-09-03", "2026-09-04"], "close": [100, 110, 120]})
    bm = pd.DataFrame({"date": ["2026-09-02", "2026-09-03"], "close": [200, 210]})
    events = [{"ticker": "005930", "report_date": "2026-09-02"}]
    row = calculate_event_forward_returns(events, prices, (1, 2), benchmark_prices=bm, benchmark_name="TEST_INDEX")[0]
    assert row["excess_1d"] == .05
    assert row["excess_2d"] is None
    assert row["benchmark_name"] == "TEST_INDEX"
    assert row["observation_start_date"] == "2026-09-02"


def test_duplicate_prices_rejected_and_nonfinite_are_missing():
    px = pd.DataFrame({"ticker": ["005930"] * 2, "date": ["2026-09-03", "2026-09-04"], "close": [100, float('inf')]})
    ev = [{"ticker": "005930", "report_date": "2026-09-03"}]
    assert calculate_event_forward_returns(ev, px, (1,))[0]["ret_1d"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        calculate_event_forward_returns(ev, pd.concat([px, px]), (1,))
