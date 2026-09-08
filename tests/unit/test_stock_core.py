from fastapi.testclient import TestClient
from kr_quant.web import app as web


def test_core_keeps_saved_values_without_external_research(monkeypatch):
    row = {"ticker": "105560", "company": "KB금융", "per": None, "value_score": 0}
    monkeypatch.setattr(web, '_load_stock_row', lambda ticker, as_of: (dict(row), '2026-09-07'))
    def forbidden(*args, **kwargs):
        raise AssertionError('core must not call external/profile/full research')
    monkeypatch.setattr(web, '_load_profile', forbidden)
    monkeypatch.setattr(web, '_dart_company', forbidden)
    monkeypatch.setattr(web, 'api_stock', forbidden)
    with TestClient(web.app) as client:
        response = client.get('/api/results/stock/105560/core')
    assert response.status_code == 200
    data = response.json()
    assert data['row'] == row
    assert data['partial'] is True
    assert data['as_of'] == '2026-09-07'
    assert len(data['pending']) == 3
