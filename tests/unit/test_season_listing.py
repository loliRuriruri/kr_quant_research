import copy
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from kr_quant.web.season_listing import project_page, LIST_FIELDS, EXPLANATION_FIELDS


@pytest.fixture
def listing(monkeypatch):
    from kr_quant.web import app as web
    rows = [{'ticker': f'{i // 2:06d}', 'company': f'Company {i}',
             'window_name': f'{date.today().month}월', 'pattern_id': f'p{i}',
             'signal_id': f's{i}', 'generation_id': 'same', 'grade': 'A',
             'current_status': 'ACTIVE', 'pre_entry_rank': i + 1,
             'years_track': [{'year': 2025, 'return': .1}],
             'playbook': {'evidence': 'x' * 4000}, 'remaining_peak': {'samples': list(range(500))},
             'all_months': list(range(12)), 'common_event_cluster': 'observed event',
             'failed_analysis': ['evidence'], 'invalidating_conditions': 'rule'} for i in range(123)]
    bundle = {'generation_id': 'same', 'generated_at': '2026-09-07T00:00:00Z',
              'identity': {'day': date.today().isoformat(), 'lookback': 0},
              'payload': {'rows': rows, 'stats': {'data_context': {}}, 'themes': []}}
    monkeypatch.setattr(web, '_season_bundle', lambda lookback, **kwargs: copy.deepcopy(bundle))
    return TestClient(web.app), rows


def test_summary_pages_preserve_every_signal_and_order(listing):
    client, source = listing
    collected = []
    offset = 0
    while offset is not None:
        result = client.get(f'/api/seasonality/discovery?view=summary&limit=50&offset={offset}&lookback_years=0&generation_id=same').json()
        assert result['count'] == len(source)
        assert result['returned_count'] <= 50
        assert result['snapshot']['generation_id'] == 'same'
        for row in result['rows']:
            original = source[int(row['signal_id'][1:])]
            assert row['lookback_years'] == 0 and row['detail_required']
            assert {k: v for k, v in row.items() if k in LIST_FIELDS} == {k: v for k, v in original.items() if k in LIST_FIELDS}
            assert not {'playbook', 'remaining_peak', 'all_months'} & row.keys()
        collected.extend(r['signal_id'] for r in result['rows'])
        offset = result['next_offset']
    assert collected == [r['signal_id'] for r in source]


def test_full_legacy_and_exact_detail_unchanged(listing):
    client, rows = listing
    assert client.get('/api/seasonality/discovery').json()['rows'] == rows
    detail = client.get('/api/seasonality/discovery/000000?lookback_years=0&generation_id=same').json()
    assert detail['patterns'] == rows[:2]
    assert client.get('/api/seasonality/discovery?view=summary&generation_id=old').status_code == 409
    assert client.get('/api/seasonality/discovery/000000?generation_id=old').status_code == 409


def test_filters_apply_before_pagination_and_empty(listing):
    client, rows = listing
    result = client.get('/api/seasonality/discovery?query=Company%201&view=summary&limit=5&offset=5').json()
    matching = [r for r in rows if 'Company 1' in r['company']]
    assert result['count'] == len(matching)
    assert [r['signal_id'] for r in result['rows']] == [r['signal_id'] for r in matching[5:10]]
    empty = client.get('/api/seasonality/discovery?view=summary&query=absent').json()
    assert empty['count'] == 0 and empty['rows'] == [] and empty['next_offset'] is None


@pytest.mark.parametrize('query', ['view=invalid', 'view=summary&limit=0', 'limit=101', 'offset=-1'])
def test_invalid_page_contract(listing, query):
    assert listing[0].get('/api/seasonality/discovery?' + query).status_code == 422


def test_explanation_projection_payload_and_copy_isolation(listing):
    client, rows = listing
    page = project_page(rows, view='explanation')
    assert page['returned_count'] == 30
    assert page['rows'][0]['failed_analysis'] == ['evidence']
    assert EXPLANATION_FIELDS > LIST_FIELDS
    assert len(json.dumps(page)) < len(json.dumps(rows)) * .1
    page['rows'][0]['years_track'].clear()
    assert len(rows[0]['years_track']) == 1
    assert project_page(rows, view='summary')['limit'] == 50


def test_ui_contracts():
    js = Path('src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    assert 'view: "summary", offset, limit: 50' in js
    assert 'view=explanation&limit=30&offset=' in js
    assert 'if (request !== discoveryListRequest) return' in js
    assert 'if (request !== explanationListRequest) return' in js
    assert 'p.signal_id === row.signal_id' in js
    assert 'params.set("generation_id", row.generation_id)' in js
    assert 'openSeasonListRegistration(rowData)' in js
