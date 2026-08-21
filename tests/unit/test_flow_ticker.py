# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from kr_quant.web.app import app

client = TestClient(app)


def test_flow_ticker_diagnosis():
    res = client.get("/api/flow/ticker/005930")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert "row" in data
    row = data["row"]
    assert row["ticker"] == "005930"
    assert "setups" in row
