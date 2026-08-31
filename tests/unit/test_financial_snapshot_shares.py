from datetime import date

import pandas as pd

from kr_quant.financials.snapshot import listed_shares_12m_ago


def test_listed_shares_12m_ago_uses_latest_observation_before_cutoff():
    prices = pd.DataFrame(
        {
            "ticker": ["005930"] * 4,
            "trade_date": ["2024-01-02", "2025-08-29", "2025-09-01", "2026-08-31"],
            "listed_shares": [80, 90, 100, 110],
        }
    )

    result = listed_shares_12m_ago(prices, "005930", date(2026, 8, 31))

    assert result == 90


def test_listed_shares_12m_ago_does_not_substitute_shorter_history():
    prices = pd.DataFrame(
        {
            "ticker": ["005930"],
            "trade_date": ["2026-01-02"],
            "listed_shares": [100],
        }
    )

    assert listed_shares_12m_ago(prices, "005930", date(2026, 8, 31)) is None
