import pandas as pd
from kr_quant.context.market_sentiment import compute_kr_market_sentiment


def test_market_sentiment_calculation():
    dates = pd.date_range("2024-01-01", periods=130, freq="B").strftime("%Y-%m-%d").tolist()
    px_rows = []
    for i, d in enumerate(dates):
        px_rows.append({"ticker": "005930", "trade_date": d, "close": 50000 + i * 200, "trading_value": 1e11})
        px_rows.append({"ticker": "000660", "trade_date": d, "close": 100000 + i * 400, "trading_value": 1e11})
    prices = pd.DataFrame(px_rows)

    res = compute_kr_market_sentiment(prices, foreign_net_5d=500e9)
    assert res["used_in_quant"] is False
    assert 0 <= res["score"] <= 100
    assert res["state"] in {"GREED", "EXTREME_GREED"}
    assert "momentum" in res["components"]
    assert "breadth" in res["components"]
