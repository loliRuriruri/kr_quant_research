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
from kr_quant.strategy.event_calendar import EVENT_CATALOG

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
    assert len(EVENT_PRESETS) >= 12
    assert "index_rebalance" in EVENT_PRESETS
    assert "bio_conference" in EVENT_PRESETS
    assert "ipo_lockup" in EVENT_PRESETS
    for preset in EVENT_PRESETS.values():
        assert preset["label"]
        assert 1 <= int(preset["analysis_month"]) <= 12
        assert preset["tickers"]


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


def test_special_event_mode_ignores_month_and_generic_thresholds():
    january = client.get(
        "/api/seasonality/scan?month=1&preset=winter_heater&min_win_rate=1.1&min_avg_return=9.0"
    )
    december = client.get(
        "/api/seasonality/scan?month=12&preset=winter_heater&min_win_rate=0&min_avg_return=-1"
    )
    assert january.status_code == 200
    assert december.status_code == 200

    jan_data = january.json()
    dec_data = december.json()
    assert jan_data["filter_mode"] == "event"
    assert jan_data["generic_thresholds_applied"] is False
    assert jan_data["target_month"] == EVENT_PRESETS["winter_heater"]["analysis_month"]
    assert {row["ticker"] for row in jan_data["rows"]} == {row["ticker"] for row in dec_data["rows"]}
    assert all(row["event_mode"] is True for row in jan_data["rows"])
    assert all(row["target_month"] == 8 for row in jan_data["rows"])


def test_galaxy_event_catalog_uses_current_krx_tickers():
    galaxy = next(event for event in EVENT_CATALOG if event["event_id"] == "galaxy_s27_cycle")
    mapping = {stock["company"]: stock["ticker"] for stock in galaxy["beneficiary_stocks"]}
    assert mapping["KH바텍"] == "060720"
    assert mapping["뉴프렉스"] == "085670"


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


def test_momentum_portfolio_api(tmp_path, monkeypatch):
    import importlib
    from types import SimpleNamespace
    module = importlib.import_module("kr_quant.web.app")
    monkeypatch.setattr(module, "load_settings", lambda: SimpleNamespace(root=tmp_path, staged_dir=tmp_path / "staged"))
    monkeypatch.setattr(module, "fetch_naver_live_quotes", lambda _: {})
    for code in ("161580", "204270", "178320", "347850"):
        assert client.post("/api/seasonality/momentum-portfolio", json={"item": {"code": code}}).status_code == 200
    # GET test
    res = client.get("/api/seasonality/momentum-portfolio")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "items" in data
    assert len(data["items"]) >= 4

    # Check 4 key user stocks exist
    codes = {item["code"] for item in data["items"]}
    assert "161580" in codes  # 필옵틱스
    assert "204270" in codes  # 제이앤티씨
    assert "178320" in codes  # 서진시스템
    assert "347850" in codes  # 디앤디파마텍

    # POST test
    test_items = list(data["items"])
    test_items[0]["notes"] = "Updated test notes"
    post_res = client.post("/api/seasonality/momentum-portfolio", json={"item": test_items[0]})
    assert post_res.status_code == 200
    assert post_res.json()["ok"] is True
    assert post_res.json()["saved_count"] == len(test_items)
