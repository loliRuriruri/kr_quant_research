# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.theme_engine import calculate_theme_seasonality, THEME_DEFINITIONS

client = TestClient(app)


def test_theme_definitions():
    assert len(THEME_DEFINITIONS) >= 8
    t0 = THEME_DEFINITIONS[0]
    assert "theme_id" in t0
    assert "theme_name" in t0
    assert "emoji" in t0
    assert "color" in t0
    assert "catalyst" in t0


def test_calculate_theme_seasonality():
    sample_rows = [
        {
            "ticker": "042700",
            "company": "한미반도체",
            "market": "KOSPI",
            "common_event_cluster": "반도체 HBM 장비 수주 사이클",
            "expected_p50": 0.28,
            "median_return": 0.28,
            "median_alpha": 0.21,
            "win_rate": 1.0,
            "seasonality_score": 94.0,
        },
        {
            "ticker": "009450",
            "company": "경동나비엔",
            "market": "KOSPI",
            "common_event_cluster": "겨울 난방 보일러 온수기 성수기",
            "expected_p50": 0.18,
            "median_return": 0.18,
            "median_alpha": 0.12,
            "win_rate": 0.85,
            "seasonality_score": 88.0,
        },
    ]
    themes = calculate_theme_seasonality(sample_rows)
    assert len(themes) >= 8
    for t in themes:
        assert "theme_id" in t
        assert "weight_share_pct" in t
        assert "avg_return" in t
        assert "avg_win_rate" in t
        assert "top_leader_name" in t


def test_api_seasonality_themes():
    res = client.get("/api/seasonality/themes?horizon_days=90&lookback_years=5")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["themes"]) >= 8
