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
    assert len(data["current_champions"]) <= 3
    assert len(data["upcoming_champions"]) <= 3


def test_api_seasonality_highlights():
    res = client.get("/api/seasonality/highlights")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["ok"] is True
    assert "data" in json_data
    d = json_data["data"]
    assert "current_champions" in d
    assert "upcoming_champions" in d
