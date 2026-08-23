# -*- coding: utf-8 -*-
import pandas as pd
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.seasonality import (
    calculate_stock_seasonality,
    scan_seasonality,
    EVENT_PRESETS,
    ticker_meta_map,
    get_pre_entry_glance,
)
from kr_quant.settings import load_settings

client = TestClient(app)


def test_calculate_stock_seasonality():
    dates = pd.date_range("2023-01-01", "2026-08-20", freq="B")
    hist = pd.DataFrame({
        "date": dates,
        "open": 50000.0,
        "high": 52000.0,
        "low": 49000.0,
        "close": 51000.0,
        "volume": 100000,
    })
    stats = calculate_stock_seasonality(hist)
    assert len(stats) == 12
    assert stats[0]["month"] == 1
    assert "win_rate" in stats[0]
    assert "avg_return" in stats[0]


def test_event_presets_structure():
    assert "winter_heater" in EVENT_PRESETS
    assert "summer_heat" in EVENT_PRESETS
    assert "galaxy_phone" in EVENT_PRESETS
    assert "dividend_play" in EVENT_PRESETS
    assert "shopping_frenzy" in EVENT_PRESETS
    assert "009450" in EVENT_PRESETS["winter_heater"]["tickers"]


def test_seasonality_scan_api():
    res = client.get("/api/seasonality/scan?month=8&min_win_rate=0.5&min_avg_return=0.0")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "presets" in data
    assert "rows" in data
    assert len(data["rows"]) > 0
    assert data["universe_scanned"] > 100
    assert data["universe_listed"] >= data["universe_scanned"]
    markets = {str(r.get("market") or "") for r in data["rows"]}
    assert "KOSPI" in markets
    assert "KOSDAQ" in markets


def test_seasonality_preset_api():
    res = client.get("/api/seasonality/scan?month=7&preset=winter_heater&min_win_rate=0.0&min_avg_return=-1.0")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert any(r["ticker"] == "009450" for r in data["rows"])


def test_seasonality_ticker_api():
    res = client.get("/api/seasonality/ticker/009450")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "stock" in data
    assert data["stock"]["ticker"] == "009450"
    assert len(data["stock"]["months"]) == 12
    assert data["stock"]["market"] in {"KOSPI", "KOSDAQ"}


def test_ticker_meta_map_covers_kospi_and_kosdaq():
    s = load_settings()
    meta = ticker_meta_map(s)
    assert len(meta) > 1000
    markets = {info["market"] for info in meta.values()}
    assert "KOSPI" in markets
    assert "KOSDAQ" in markets


def test_pre_entry_glance_excludes_season_end():
    s = load_settings()
    picks = get_pre_entry_glance(s, n=3, lookback_years=5)
    assert len(picks) <= 3
    for pick in picks:
        assert pick["entry_stage"] in {"TODAY_ENTRY", "PRE_ENTRY_15", "PRE_ENTRY_30", "ACCUMULATE_60"}
        assert pick["rank"] >= 1
        assert pick["ticker"]
