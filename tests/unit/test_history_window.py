from datetime import date

import pandas as pd

from kr_quant.pit.filings import history_window


def test_history_window_caps_each_ticker_and_excludes_future_rows():
    rows = []
    for ticker in ("000001", "000002"):
        for index, trade_date in enumerate(pd.date_range("2026-01-01", periods=8, freq="D")):
            rows.append({"ticker": ticker, "trade_date": trade_date, "close": 100 + index})
    prices = pd.DataFrame(rows)

    result = history_window(prices, date(2026, 1, 6), lookback=3)

    assert len(result) == 6
    assert result.groupby("ticker").size().to_dict() == {"000001": 3, "000002": 3}
    assert max(result["trade_date"]) <= date(2026, 1, 6)
