# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.seasonality import get_seasonality_highlights
from kr_quant.settings import load_settings

client = TestClient(app)


def test_get_seasonality_highlights():
    s = load_settings()
    data = get_seasonality_highlights(s)
    assert "current_month" in data
    assert "next_month" in data
    assert "current_champions" in data
    assert "upcoming_champions" in data
    assert "active_presets" in data
    assert "glance_top3" in data
    assert len(data["current_champions"]) <= 3
    assert len(data["upcoming_champions"]) <= 3
    assert len(data["glance_top3"]) <= 3
    assert data["universe_scanned"] > 100
    if data["glance_top3"]:
        pick = data["glance_top3"][0]
        assert pick["rank"] == 1
        assert pick["ticker"]
        assert pick["company"]
        assert pick.get("entry_stage") in {"TODAY_ENTRY", "PRE_ENTRY_15", "PRE_ENTRY_30", "ACCUMULATE_60"}


def test_api_seasonality_highlights():
    from kr_quant.web.season_snapshot import build_bundle
    build_bundle(load_settings())
    res = client.get("/api/seasonality/highlights")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["ok"] is True
    assert "data" in json_data
    d = json_data["data"]
    assert "current_champions" in d
    assert "upcoming_champions" in d
    assert "glance_top3" in d
    assert "universe_scanned" in d
