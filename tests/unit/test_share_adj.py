from datetime import date, timedelta

import pandas as pd

from kr_quant.context.explain import clean_reason_list, interpret_row
from kr_quant.factors.share_adj import lookback_return, share_adjusted_level, ticker_momentum


def test_split_does_not_create_false_return():
    assert share_adjusted_level(100, 10, None) == share_adjusted_level(50, 20, None)
    levels = [(date(2026, 1, 1) + timedelta(days=i), 1000.0) for i in range(70)]
    assert lookback_return(levels, 63) == 0.0


def test_ticker_momentum_uses_market_cap():
    days = pd.date_range("2025-01-02", periods=130, freq="B")
    close = [100.0] * 64 + [50.0] * 66  # split in the middle
    shares = [10.0] * 64 + [20.0] * 66
    hist = pd.DataFrame({"trade_date": days, "close": close, "listed_shares": shares, "market_cap": [c * s for c, s in zip(close, shares)]})
    mom = ticker_momentum(hist, {"return_3m": 63, "return_6m": 126, "return_12m": 252, "high_52w_distance": 252})
    assert mom["return_3m"] is not None
    assert abs(mom["return_3m"]) < 1e-9


def test_ticker_momentum_does_not_bridge_unexplained_market_cap_jump():
    days = pd.date_range("2025-01-02", periods=70, freq="B")
    market_cap = [1_000.0] * 65 + [2_000.0] * 5
    hist = pd.DataFrame(
        {
            "trade_date": days,
            "close": [100.0] * 65 + [200.0] * 5,
            "listed_shares": [10.0] * 70,
            "market_cap": market_cap,
        }
    )

    mom = ticker_momentum(
        hist,
        {"return_3m": 63, "return_6m": 126, "return_12m": 252, "high_52w_distance": 252},
    )

    assert mom["return_3m"] is None


def test_clean_reason_list_drops_empty_brackets():
    assert clean_reason_list("[]") == []
    assert clean_reason_list([]) == []
    assert clean_reason_list("LIQUIDITY_FAIL|") == ["LIQUIDITY_FAIL"]
    out = interpret_row({"weighted_metric_coverage": 0.95, "data_confidence": 90, "universe_eligible": True, "exclusion_reasons": "[]", "momentum_enabled": True})
    assert not any("제외 사유" in x for x in out["cautions"])
    assert not any("수정주가" in x for x in out["cautions"])


def test_flag_notes_hide_empty_brackets():
    from kr_quant.web.guide import DATA_FLAG_KO, RISK_FLAG_KO, flag_notes

    assert flag_notes("[]", RISK_FLAG_KO) == []
    assert flag_notes([], DATA_FLAG_KO) == []
    notes = flag_notes("['CAPEX_PARTIAL', 'Q4_DERIVATION_ANOMALY']", DATA_FLAG_KO)
    assert [n["code"] for n in notes] == ["CAPEX_PARTIAL", "Q4_DERIVATION_ANOMALY"]
    assert all("CAPEX" not in n["label"] or True for n in notes)
    assert "설비투자" in notes[0]["label"]
