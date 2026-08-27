# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.discovery_engine import pattern_from_month_stat, SeasonalityPattern
from kr_quant.strategy.event_explainer import explain_and_score_pattern
from kr_quant.strategy.seasonality import scan_seasonality_discovery
from kr_quant.settings import load_settings

client = TestClient(app)


def test_pattern_from_month_stat_with_playbook():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat, lookback_years=5)
    assert pat is not None
    assert pat.sample_count == 5
    assert pat.win_rate == 0.80
    assert hasattr(pat, "entry_stage")
    assert hasattr(pat, "entry_stage_label")
    assert hasattr(pat, "expected_p50")
    assert hasattr(pat, "expected_p90")
    assert hasattr(pat, "profit_factor")
    assert hasattr(pat, "playbook")
    assert "entry_timing" in pat.playbook
    assert "exit_timing" in pat.playbook
    assert "stop_loss" in pat.playbook


def test_explain_and_score_pattern():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat, lookback_years=5)
    res = explain_and_score_pattern(pat, {"quant_score": 75.0, "return_3m": 0.05})
    assert "seasonality_score" in res
    assert 0.0 <= res["seasonality_score"] <= 100.0
    assert res["grade"] in ["S", "A", "B", "C", "D"]
    assert res["current_status"] in ["ACTIVE", "WATCH", "DISCOVERY", "WEAKENING", "BROKEN", "UNKNOWN"]
    assert "score_breakdown" in res
    assert "entry_stage" in res
    assert "entry_stage_label" in res
    assert "expected_p50" in res
    assert "expected_p90" in res
    assert "profit_factor" in res
    assert "playbook" in res


def test_api_seasonality_discovery_playbook():
    res = client.get("/api/seasonality/discovery?horizon_days=90&lookback_years=5")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["rows"]) > 0
    row = data["rows"][0]
    assert "entry_stage" in row
    assert "entry_stage_label" in row
    assert "expected_p50" in row
    assert "expected_p90" in row
    assert "profit_factor" in row
    assert "playbook" in row
    assert "remaining_peak" in row
    remaining = row["remaining_peak"]
    assert "available" in remaining
    assert "status" in remaining
    if remaining["available"]:
        assert remaining["remaining_p50"] is not None
        assert remaining["peak_price_p50"] is not None
        assert remaining["sample_count"] >= 3
