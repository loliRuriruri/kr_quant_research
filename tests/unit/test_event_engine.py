# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.event_calendar import get_upcoming_events, EVENT_CATALOG
from kr_quant.strategy.event_exposure import get_stock_event_exposure
from kr_quant.strategy.seasonality import rank_institutional_events
from kr_quant.settings import load_settings

client = TestClient(app)


def test_event_catalog_and_upcoming():
    assert len(EVENT_CATALOG) >= 10
    events = get_upcoming_events(horizon_days=90)
    assert len(events) > 0
    for ev in events:
        assert "event_id" in ev
        assert "target_date" in ev
        assert "d_day" in ev
        assert "default_entry_window" in ev
        assert "invalidating_rule" in ev
        assert "beneficiary_sectors" in ev
        assert "beneficiary_stocks" in ev


def test_event_exposure():
    # Kyungdong Navien should have high exposure to winter heating
    exp = get_stock_event_exposure("009450", "winter_heating_surge")
    assert exp["exposure_score"] >= 0.8
    assert "보일러" in exp["exposure_desc"] or "HVAC" in exp["exposure_desc"]


def test_rank_institutional_events():
    s = load_settings()
    ranked = rank_institutional_events(s, horizon_days=90)
    assert len(ranked) > 0
    top = ranked[0]
    assert "seasonality_score" in top
    assert 0.0 <= top["seasonality_score"] <= 100.0
    assert "grade" in top
    assert top["grade"] in ["S+", "S", "A+", "A", "B", "C", "D"]
    assert "confirmation_state" in top
    assert top["confirmation_state"] in ["STRONG", "CONFIRMED", "NEUTRAL", "WEAK", "CONTRADICTED"]
    assert "score_breakdown" in top
    b = top["score_breakdown"]
    assert "historical_edge" in b
    assert "current_confirmation" in b
    assert "event_quality" in b


def test_api_seasonality_ranked():
    res = client.get("/api/seasonality/ranked?horizon_days=90")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "rows" in data
    assert len(data["rows"]) > 0


def test_api_seasonality_events():
    res = client.get("/api/seasonality/events?horizon_days=90")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "events" in data
    assert len(data["events"]) > 0
