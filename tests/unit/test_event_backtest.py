import pandas as pd
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
