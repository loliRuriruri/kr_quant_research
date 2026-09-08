from copy import deepcopy

from fastapi.testclient import TestClient

from tests.e2e.harness import GLANCE
from kr_quant.web import app as web
from kr_quant.web.season_snapshot import _copy_bundle


def test_real_endpoints_share_metrics_and_reject_old_generation(monkeypatch):
    rows = deepcopy(GLANCE)
    bundle = {'generation_id': 'season-fixture-v4', 'generated_at': '2026-08-28T20:00:00Z',
              'identity': {'day': '2026-08-28', 'lookback': 5},
              'payload': {'rows': rows, 'themes': [], 'stats': {'data_context': {}},
                          'highlights': {'glance_top3': deepcopy(rows)}}}
    monkeypatch.setattr(web, '_season_bundle', lambda *a, **kw: _copy_bundle(bundle, kw.get('listing_view')))
    with TestClient(web.app) as client:
        top = client.get('/api/seasonality/highlights').json()
        listing = client.get('/api/seasonality/pre-entry?compact=true').json()
        assert top['snapshot']['generation_id'] == listing['snapshot']['generation_id']
        for a, b in zip(top['data']['glance_top3'], listing['rows'], strict=True):
            response = client.get(f"/api/seasonality/discovery/{a['ticker']}?generation_id=season-fixture-v4")
            assert response.status_code == 200
            detail = response.json()['patterns'][0]
            assert a['pattern_id'] == b['pattern_id'] == detail['pattern_id']
            for key in ('window_end_p50', 'window_end_positive_count', 'remaining_p50',
                        'window_adverse_excursion_p50', 'strategy_net_return_p50', 'validation_status'):
                assert a['remaining_peak'][key] == b['remaining_peak'][key] == detail['remaining_peak'][key]
        assert client.get('/api/seasonality/discovery/005380?generation_id=old').status_code == 409
        assert client.get('/api/seasonality/discovery?generation_id=old').status_code == 409
