# -*- coding: utf-8 -*-
"""Fixture API contract used by browser E2E. No live KRX/OpenDART."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.e2e.harness import create_app, public_snapshot_files


def test_fixture_top30_and_hyundai_search():
    client = TestClient(create_app())
    top = client.get("/api/results/top?n=30").json()
    assert len(top["rows"]) == 30
    assert top["rows"][0]["ticker"] == "005380"
    assert top["rows"][0]["company"] == "현대차"

    by_name = client.get("/api/stocks/search", params={"q": "현대차"}).json()
    by_code = client.get("/api/stocks/search", params={"q": "005380"}).json()
    assert by_name["items"][0]["ticker"] == "005380"
    assert by_code["items"][0]["company"] == "현대차"


def test_fixture_glance_matches_discovery_pre_entry_rank():
    client = TestClient(create_app())
    glance = client.get("/api/seasonality/highlights").json()["data"]["glance_top3"]
    discovery = client.get("/api/seasonality/discovery").json()["rows"]
    assert [row["ticker"] for row in glance] == [row["ticker"] for row in discovery[:3]]
    assert [row["pre_entry_rank"] for row in discovery[:3]] == [1, 2, 3]
    assert all(row["entry_stage"] == "PRE_ENTRY_15" for row in discovery[:3])


def test_fixture_event_preset_is_independent_of_month():
    client = TestClient(create_app())
    event = client.get("/api/seasonality/scan", params={"preset": "winter_heater", "month": 1}).json()
    month = client.get("/api/seasonality/scan", params={"month": 1}).json()
    assert event["filter_mode"] == "event"
    assert event["generic_thresholds_applied"] is False
    assert event["rows"][0]["ticker"] == "009450"
    assert month["rows"][0]["ticker"] == "005930"


def test_fixture_flow_and_strategy_and_stock_links():
    client = TestClient(create_app())
    flow = client.get("/api/flow?days=5").json()
    assert flow["configured"] is True
    assert flow["dual"][0]["daily"][0]["date"] == "2026-08-28"
    assert flow["empty"][0]["empty"] is True
    assert flow["rows"][0]["ta"]["stoch_over_sold"] is True

    strategy = client.get("/api/strategy").json()
    assert "잘리면 안 되는 회귀 문구" in strategy["rows"][0]["best_params_ko"]
    assert strategy["need_run"] is False

    stock = client.get("/api/results/stock/005380").json()
    urls = [item["url"] for item in stock["links"]]
    assert any("finance.naver.com" in url and "005380" in url for url in urls)
    assert any("tossinvest.com" in url and "005380" in url for url in urls)


def test_public_preview_snapshot_manifest_covers_dash_routes():
    files = public_snapshot_files()
    manifest = files["manifest.json"]
    client = TestClient(create_app())
    listed = client.get("/data/api/manifest.json").json()
    assert listed["routes"]["/api/results/top"] == manifest["routes"]["/api/results/top"]
    top = client.get("/data/api/api-results-top.json").json()
    assert top["rows"][0]["company"] == "현대차"
    status = client.get("/data/api/api-status.json").json()
    assert status["public_mode"] is True
