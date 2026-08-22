# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.discovery_engine import pattern_from_month_stat, SeasonalityPattern
from kr_quant.strategy.event_explainer import explain_and_score_pattern
from kr_quant.strategy.seasonality import scan_seasonality_discovery
from kr_quant.settings import load_settings

client = TestClient(app)


def test_pattern_from_month_stat():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat)
    assert pat is not None
    assert pat.ticker == "009450"
    assert pat.sample_count == 5
    assert pat.win_rate == 0.80
    assert len(pat.years_track) == 5
    assert len(pat.failed_years) == 1
    assert pat.failed_years[0]["return"] == -0.02


def test_explain_and_score_pattern():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat)
    res = explain_and_score_pattern(pat, {"quant_score": 75.0, "return_3m": 0.05})
    assert "seasonality_score" in res
    assert 0.0 <= res["seasonality_score"] <= 100.0
    assert res["grade"] in ["S", "A", "B", "C", "D"]
    assert res["current_status"] in ["ACTIVE", "WATCH", "DISCOVERY", "WEAKENING", "BROKEN", "UNKNOWN"]
    assert "score_breakdown" in res
    b = res["score_breakdown"]
    assert "historical_pattern" in b
    assert "recent_validation" in b
    assert "current_confirmation" in b
    assert "event_explanation" in b
    assert "common_event_cluster" in res
    assert "failed_analysis" in res


def test_api_seasonality_discovery():
    res = client.get("/api/seasonality/discovery?horizon_days=90")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "rows" in data
    assert len(data["rows"]) > 0


def test_api_seasonality_discovery_ticker():
    res = client.get("/api/seasonality/discovery/009450")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["ticker"] == "009450"
    assert "patterns" in data
    assert len(data["patterns"]) > 0
