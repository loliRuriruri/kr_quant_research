from kr_quant.flow.investor import filter_trading, ta_match
from kr_quant.timing.indicators import ichimoku_lines, last_signals, midpoint, stochastic_slow
from kr_quant.timing.snapshot import technical_snapshot


def test_stochastic_known_window():
    high = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    low = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    close = [9, 10, 11, 12, 9.5, 13, 14, 12.2, 16, 17, 18, 17.5]
    k, d = stochastic_slow(high, low, close, k_period=5, k_smooth=3, d_period=3)
    hh, ll = max(high[-5:]), min(low[-5:])
    fast = (close[-1] - ll) / (hh - ll) * 100
    assert 0 <= fast <= 100
    assert k[-1] is not None
    assert 0 <= k[-1] <= 100
    assert d[-1] is not None


def test_midpoint_and_ichimoku_tenkan():
    high = list(range(10, 62))
    low = list(range(1, 53))
    close = [ (h + l) / 2 for h, l in zip(high, low) ]
    assert midpoint(high, low, 8, 9) == (max(high[:9]) + min(low[:9])) / 2
    ichi = ichimoku_lines(high, low, close)
    assert ichi["tenkan"][-1] is not None
    assert ichi["kijun"][-1] is not None
    assert ichi["span_b"][-1] is not None
    assert ichi["cloud_a"][-1] is not None


def test_oversold_signal():
    high = [100] * 30
    low = [0] * 30
    close = [90] * 25 + [2, 2, 2, 2, 2]
    sig = last_signals(high, low, close)
    assert sig["ok"] is True
    assert sig["used_in_quant"] is False
    assert sig["stoch_over_sold"] is True
    assert "과매도" in sig["labels"]


def test_snapshot_empty():
    import pandas as pd

    assert technical_snapshot(pd.DataFrame())["ok"] is False


def test_ta_filter_confluence():
    rows = [
        {
            "ticker": "1",
            "company": "A",
            "in_quant": False,
            "dual": True,
            "pe_buy": False,
            "empty": False,
            "comeback": False,
            "dual_krw": 2e9,
            "pe_krw": 0,
            "empty_krw": 0,
            "ta": {"stoch_over_sold": True, "stoch_golden": False, "ichi_cloud": "below"},
        },
        {
            "ticker": "2",
            "company": "B",
            "in_quant": False,
            "dual": False,
            "pe_buy": False,
            "empty": True,
            "comeback": False,
            "dual_krw": 0,
            "pe_krw": 0,
            "empty_krw": 3e9,
            "ta": {"stoch_over_sold": False, "ichi_cloud": "above"},
        },
    ]
    assert ta_match(rows[0], "stoch_os") is True
    assert ta_match(rows[1], "ichi_above") is True
    hits = filter_trading(rows, mode="setup", exclude_quant=True, ta_mode="confluence")
    assert [r["ticker"] for r in hits] == ["1"]
