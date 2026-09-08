# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from kr_quant.web.app import app

client = TestClient(app)


def test_flow_ticker_diagnosis(tmp_path, monkeypatch):
    from dataclasses import replace
    import pandas as pd
    from kr_quant.settings import load_settings
    from kr_quant.web import app as web
    from kr_quant.flow import scan
    settings = replace(load_settings(), root=tmp_path)
    settings.output_dir.mkdir(parents=True)
    pd.DataFrame([{'ticker':'005930', 'company':'삼성전자'}]).to_parquet(
        settings.output_dir/'latest_all_stocks.parquet')
    monkeypatch.setattr(web, 'load_settings', lambda: settings)
    # Endpoint contract uses an already gated scan. Raw eligibility cases are
    # independently exercised in test_flow_candidate_gate; no live provider.
    monkeypatch.setattr(scan, 'load_flow', lambda *a, **kw: {
        'rows':[{'ticker':'005930', 'setups':['dual']}]})
    res = client.get("/api/flow/ticker/005930")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert "row" in data
    row = data["row"]
    assert row["ticker"] == "005930"
    assert "setups" in row
