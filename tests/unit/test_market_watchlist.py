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
    assert components["trend"]["as_of"]
    assert components["trend"]["available"] is True
    assert out["score_check"]["reproducible"] is True


def test_missing_rates_and_fx_are_excluded_not_zeroed():
    dates = pd.date_range("2025-01-02", periods=80, freq="B")
    rows = []
    for ticker, start in (("005930", 100.0), ("000660", 80.0)):
        for i, d in enumerate(dates):
            close = start * (1.002 ** i)
            rows.append({"ticker": ticker, "trade_date": d, "close": close, "trading_value": 1e9})
    components = derive_market_components(pd.DataFrame(rows))
    cfg = {
        "market_regime": {
            "weights": {
                "trend": 20,
                "breadth": 20,
                "liquidity": 15,
                "volatility": 15,
                "rates": 10,
                "fx": 10,
                "momentum": 10,
            },
            "risk_on_min": 70,
            "neutral_min": 40,
        }
    }
    out = market_regime(components, cfg)
    assert out["rates"] is None
    assert out["fx"] is None
    assert set(out["missing"]) >= {"rates", "fx"}
    assert out["confidence"] == 0.8
    assert "재분배" in out["confidence_label"] or "제외" in out["confidence_label"]
    contrib_sum = round(sum(item["contribution"] for item in out["contributions"]), 2)
    assert abs(contrib_sum - out["regime_score"]) <= 0.05
    assert all(item["id"] not in {"rates", "fx"} for item in out["contributions"])


def test_attach_macro_keeps_fred_as_of_and_does_not_mix_vix_into_score():
    from kr_quant.context.market import attach_macro

    dates = pd.date_range("2025-01-02", periods=80, freq="B")
    rows = []
    for i, d in enumerate(dates):
        rows.append({"ticker": "005930", "trade_date": d, "close": 100 + i, "trading_value": 1e9})
    components = derive_market_components(pd.DataFrame(rows))
    krx_as_of = components["_meta"]["as_of"]
    fred = [
        {"id": "T10Y2Y", "label": "장단기", "value": 0.4, "date": "2025-04-01", "delta": 0.1, "history": [{"value": 0.2}, {"value": 0.4}]},
        {"id": "DEXKOUS", "label": "원/달러", "value": 1400.0, "prev_value": 1390.0, "date": "2025-04-01", "delta": 10.0, "history": []},
        {"id": "VIXCLS", "label": "VIX", "value": 18.5, "date": "2025-04-01"},
        {"id": "DGS2", "label": "2Y", "value": 4.1, "date": "2025-04-01"},
        {"id": "DGS10", "label": "10Y", "value": 4.5, "date": "2025-04-01"},
    ]
    attached = attach_macro(components, fred, krx_as_of=krx_as_of)
    assert attached["rates"]["as_of"] == "2025-04-01"
    assert attached["rates"]["source"] == "FRED T10Y2Y"
    assert attached["fx"]["as_of"] == "2025-04-01"
    related = [item["id"] for item in (attached["volatility"].get("related") or [])]
    assert "VIXCLS" in related
    cfg = {
        "market_regime": {
            "weights": {"trend": 20, "breadth": 20, "liquidity": 15, "volatility": 15, "rates": 10, "fx": 10, "momentum": 10},
            "risk_on_min": 70,
            "neutral_min": 40,
        }
    }
    scored = market_regime(attached, cfg)
    assert scored["confidence"] == 1.0
    assert "rates" not in scored["missing"]


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
