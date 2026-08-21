from kr_quant.context.macro_brief import compute_commodity_crypto_brief, compute_yencarry_monitor
from kr_quant.ingest.yahoo import INDEXES


def test_indexes_spec():
    symbols = [s["symbol"] for s in INDEXES]
    assert "^N225" in symbols
    assert "JPY=X" in symbols
    assert "GC=F" in symbols
    assert "BTC-USD" in symbols


def test_yencarry_monitor_stable():
    mock_indexes = [
        {"symbol": "JPY=X", "last": 156.0, "ret_5d": 0.005, "ret_1m": 0.02},
        {"symbol": "^N225", "last": 39000.0, "ret_1m": 0.03},
        {"symbol": "^TNX", "last": 4.3},
    ]
    yc = compute_yencarry_monitor(mock_indexes)
    assert yc["used_in_quant"] is False
    assert yc["risk_level"] in {"STABLE", "WATCH"}
    assert yc["unwind_score"] < 65


def test_yencarry_monitor_unwind_risk():
    mock_indexes = [
        {"symbol": "JPY=X", "last": 139.0, "ret_5d": -0.03, "ret_1m": -0.06},
        {"symbol": "^N225", "last": 34000.0, "ret_1m": -0.08},
        {"symbol": "^TNX", "last": 3.8},
    ]
    yc = compute_yencarry_monitor(mock_indexes)
    assert yc["risk_level"] == "UNWIND_RISK"
    assert yc["risk_ko"] == "청산 경보"
    assert yc["unwind_score"] >= 65


def test_commodity_crypto_brief():
    mock_indexes = [
        {"symbol": "GC=F", "last": 2750.0, "ret_1d": 0.01, "ret_1m": 0.05},
        {"symbol": "CL=F", "last": 72.0, "ret_1d": -0.01, "ret_1m": -0.02},
        {"symbol": "HG=F", "last": 4.4, "ret_1d": 0.005, "ret_1m": 0.03},
        {"symbol": "BTC-USD", "last": 95000.0, "ret_1d": 0.02, "ret_1m": 0.12},
    ]
    res = compute_commodity_crypto_brief(mock_indexes)
    assert res["used_in_quant"] is False
    ids = [it["id"] for it in res["items"]]
    assert "gold" in ids
    assert "oil" in ids
    assert "copper" in ids
    assert "btc" in ids
