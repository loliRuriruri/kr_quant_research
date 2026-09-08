# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import pytest

from kr_quant.quality.corporate_actions import (
    apply_official_adjustments,
    audit_adjustment_impact,
    explain_breaks_with_actions,
    normalize_actions,
)
from kr_quant.quality.price_integrity import attach_official_action_explanations, latest_clean_price_segments


def _split_prices() -> pd.DataFrame:
    # 50:1 split: raw close 50_000 -> 1_000. Official adj should stay near 1_000.
    closes = [50_000, 50_200, 1_000, 1_010, 1_020]
    shares = [1_000, 1_000, 50_000, 50_000, 50_000]
    dates = pd.date_range("2018-04-27", periods=5, freq="B")
    return pd.DataFrame(
        {
            "ticker": ["005930"] * 5,
            "trade_date": dates,
            "open": closes,
            "high": [value + 10 for value in closes],
            "low": [value - 10 for value in closes],
            "close": closes,
            "volume": [1_000] * 5,
            "listed_shares": shares,
            "market_cap": [c * s for c, s in zip(closes, shares)],
        }
    )


def _split_event() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "event_type": "SPLIT",
                "ex_date": "2018-05-01",
                "event_date": "2018-04-30",
                "ratio": 50.0,
                "cash_amount": None,
                "source": "KRX_TEST_FIXTURE",
                "confirmed": True,
                "notes": "50-for-1 test split",
            }
        ]
    )


def test_unexplained_split_is_not_joined_on_raw():
    prices = _split_prices()
    clean, issues, summary = latest_clean_price_segments(prices)
    assert clean["close"].tolist() == [1_000, 1_010, 1_020]
    assert "UNEXPLAINED_PRICE_DISCONTINUITY" in set(issues["issue_code"]) or "LIKELY_SHARE_CHANGE_PRICE_RESET" in set(
        issues["issue_code"]
    )
    assert summary["corporate_action_confirmation"] is False


def test_official_split_adjusts_history_without_inventing_events():
    prices = _split_prices()
    adjusted = apply_official_adjustments(prices, _split_event())
    pre = adjusted.iloc[0]
    post = adjusted.iloc[2]
    assert abs(float(pre["adj_close"]) - float(post["adj_close"])) < 50
    assert float(pre["close"]) == 50_000
    assert float(post["close"]) == 1_000
    assert float(pre["adj_factor"]) == pytest.approx(1 / 50)


def test_official_split_adj_close_is_continuous():
    adjusted = apply_official_adjustments(_split_prices(), _split_event())
    adj = adjusted["adj_close"].astype(float).tolist()
    assert adj[0] == 1_000
    assert adj[2] == 1_000


def test_future_action_and_paid_rights_do_not_become_split_factors():
    event = _split_event()
    event['ex_date'] = '2030-01-01'
    assert apply_official_adjustments(_split_prices(), event)['adj_factor'].eq(1).all()
    event['ex_date'] = '2018-05-01'
    event['event_type'] = 'RIGHTS'
    assert apply_official_adjustments(_split_prices(), event)['adj_factor'].eq(1).all()


def test_unsorted_prices_preserve_order_but_returns_use_time_order():
    prices = _split_prices()
    before = apply_official_adjustments(prices, _split_event())
    reversed_prices = prices.iloc[::-1]
    after = apply_official_adjustments(reversed_prices, _split_event())
    pd.testing.assert_series_equal(before['price_return'], after['price_return'].sort_index())
    assert list(after.index) == list(reversed_prices.index)


def test_unconfirmed_or_sourceless_event_is_ignored():
    events = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "event_type": "SPLIT",
                "ex_date": "2018-05-01",
                "ratio": 50,
                "source": "",
                "confirmed": True,
            },
            {
                "ticker": "005930",
                "event_type": "SPLIT",
                "ex_date": "2018-05-01",
                "ratio": 50,
                "source": "KRX",
                "confirmed": False,
            },
        ]
    )
    assert normalize_actions(events).empty
    adjusted = apply_official_adjustments(_split_prices(), events)
    assert float(adjusted.iloc[0]["adj_close"]) == 50_000


def test_break_is_labeled_but_raw_segment_stays_isolated():
    prices = _split_prices()
    clean, issues, summary = latest_clean_price_segments(prices)
    explained, payload = attach_official_action_explanations(issues, summary, _split_event())
    assert payload["corporate_action_confirmation"] is True
    assert payload["official_events_matched"] >= 1
    assert clean["close"].tolist() == [1_000, 1_010, 1_020]
    assert bool(explained["explained_by_official_action"].any())


def test_dividend_separates_price_and_total_return():
    prices = pd.DataFrame(
        {
            "ticker": ["000001", "000001"],
            "trade_date": pd.to_datetime(["2026-03-27", "2026-03-30"]),
            "open": [100.0, 99.0],
            "high": [101.0, 100.0],
            "low": [99.0, 98.0],
            "close": [100.0, 99.0],
            "volume": [1000, 1000],
        }
    )
    events = pd.DataFrame(
        [
            {
                "ticker": "000001",
                "event_type": "DIVIDEND",
                "ex_date": "2026-03-30",
                "ratio": None,
                "cash_amount": 5.0,
                "source": "TEST",
                "confirmed": True,
            }
        ]
    )
    adjusted = apply_official_adjustments(prices, events)
    assert float(adjusted.iloc[1]["price_return"]) == pytest.approx(-0.01)
    assert float(adjusted.iloc[1]["dividend_return"]) == pytest.approx(0.05)
    assert float(adjusted.iloc[1]["total_return"]) == pytest.approx(0.04)


def test_audit_table_reports_raw_vs_adjusted():
    audit = audit_adjustment_impact(_split_prices(), _split_event())
    assert audit["corporate_action_confirmation"] is True
    assert audit["isolated_raw_rows"] < audit["raw_rows"]
    assert audit["adjusted_rows"] == audit["raw_rows"]
    assert abs(audit["adjusted_span_return"] or 0) < abs(audit["raw_span_return"] or 99)
    assert {"raw_rows", "isolated_raw_rows", "adjusted_span_return", "unexplained_breaks"} <= set(audit)
