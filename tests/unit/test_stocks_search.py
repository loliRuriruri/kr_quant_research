# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from kr_quant.web.app import app

client = TestClient(app)


def test_stocks_search_by_name():
    res = client.get("/api/stocks/search?q=경동")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    tickers = [it["ticker"] for it in data["items"]]
    assert "009450" in tickers  # 경동나비엔


def test_stocks_search_by_ticker():
    res = client.get("/api/stocks/search?q=005930")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) >= 1
    assert data["items"][0]["ticker"] == "005930"


def test_stocks_search_by_chosung():
    res = client.get("/api/stocks/search?q=ㅅㅅㅈㅈ")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert any("삼성" in it["company"] for it in data["items"])


def test_stocks_search_ranks_full_name_first():
    res = client.get("/api/stocks/search?q=삼성전자")
    assert res.status_code == 200
    items = res.json()["items"]
    assert items
    assert items[0]["ticker"] == "005930"
    assert "삼성전자" in items[0]["company"]


def test_stocks_search_partial_korean_name():
    res = client.get("/api/stocks/search?q=하이닉스")
    assert res.status_code == 200
    tickers = [it["ticker"] for it in res.json()["items"]]
    assert "000660" in tickers
