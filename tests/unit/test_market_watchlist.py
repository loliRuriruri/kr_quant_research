from pathlib import Path

import pandas as pd

from kr_quant.context.explain import interpret_row
from kr_quant.context.market import derive_market_components, market_regime
from kr_quant.context.watchlist import add_ticker, load_watchlist, remove_ticker
from kr_quant.timing import STUB


def test_timing_stub_does_not_touch_quant():
    assert STUB["used_in_quant"] is False


def test_market_regime_not_in_quant():
    dates = pd.date_range("2025-01-02", periods=80, freq="B")
    rows = []
    for ticker, start in (("005930", 100.0), ("000660", 80.0)):
        for i, d in enumerate(dates):
            close = start * (1.002 ** i)
            rows.append({"ticker": ticker, "trade_date": d, "close": close, "trading_value": 1e9})
    prices = pd.DataFrame(rows)
    components = derive_market_components(prices)
    assert components["trend"] is not None
    cfg = {
        "market_regime": {
            "weights": {"trend": 20, "breadth": 20, "liquidity": 15, "volatility": 15, "momentum": 10},
            "risk_on_min": 70,
            "neutral_min": 40,
        }
    }
    out = market_regime(components, cfg)
    assert out["used_in_quant"] is False
    assert out["regime"] in {"RISK_ON", "NEUTRAL", "RISK_OFF"}


def test_watchlist_roundtrip(tmp_path: Path):
    add_ticker(tmp_path, "5930", "삼성전자", "메모")
    rows = load_watchlist(tmp_path)
    assert rows[0]["ticker"] == "005930"
    remove_ticker(tmp_path, "005930")
    assert load_watchlist(tmp_path) == []


def test_explain_holds_when_coverage_low():
    out = interpret_row({"weighted_metric_coverage": 0.3, "data_confidence": 40, "universe_eligible": True})
    assert "보류" in out["conclusion"] or "낮" in "".join(out["cautions"])
    assert out["used_in_quant"] is False
