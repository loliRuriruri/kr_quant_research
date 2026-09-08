import copy
import json
from types import SimpleNamespace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from kr_quant.web import season_snapshot as snapshots
from kr_quant.strategy import seasonality as engine


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    s = SimpleNamespace(root=tmp_path, data_dir=tmp_path/'data', staged_dir=tmp_path/'data/staged',
                        output_dir=tmp_path/'data/output', status_csv=tmp_path/'data/status.csv', config={})
    price = s.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    price.write_bytes(b'source 1')
    calls = []
    def scan(*args, **kwargs):
        calls.append(1)
        return [{'ticker': f'{i:06d}', 'pattern_id': str(i), 'company': f'Company {i}',
                 'window_name': f'{date.today().month}월', 'pre_entry_rank': i,
                 'entry_stage': 'PRE_ENTRY_15', 'grade': 'A', 'price_as_of': '2026-09-04'} for i in range(1, 5)]
    monkeypatch.setattr(engine, 'scan_seasonality_discovery', scan)
    monkeypatch.setattr(engine, 'scan_seasonality', lambda *a, **kw: [])
    monkeypatch.setattr(engine, 'seasonality_universe_stats', lambda *a: {
        'data_context': {'price_as_of': '2026-09-04'}, 'universe_scanned': 4, 'universe_listed': 4, 'markets': {}})
    def highlights(settings, *, discovery_rows):
        return {'glance_top3': engine.get_pre_entry_glance(settings, rows=discovery_rows)}
    monkeypatch.setattr(engine, 'get_seasonality_highlights', highlights)
    monkeypatch.setattr(snapshots, '_MEM', {})
    return s, price, calls


def test_restart_reuse_ids_and_copy_isolation(prepared):
    s, price, calls = prepared
    first = snapshots.build_bundle(s)
    assert len(calls) == 1
    assert len({r['signal_id'] for r in first['payload']['rows']}) == 4
    path = snapshots._folder(s)/f"{first['generation_id']}.json"
    original = path.read_bytes()
    first['payload']['rows'].clear()
    snapshots._MEM.clear()
    replay = snapshots.build_bundle(s)
    assert len(replay['payload']['rows']) == 4
    assert path.read_bytes() == original
    assert len(calls) == 1
    assert [r['signal_id'] for r in replay['payload']['highlights']['glance_top3']] == [
        r['signal_id'] for r in snapshots.select_rows(replay)[:3]]


def test_source_change_and_failed_build_preserve_previous(prepared, monkeypatch):
    s, price, calls = prepared
    old = snapshots.build_bundle(s)
    pointer = snapshots._folder(s)/'latest_lb_5.json'
    original = pointer.read_bytes()
    price.write_bytes(b'changed price inputs')
    assert snapshots.read_bundle(s) is None
    original_scan = engine.scan_seasonality_discovery
    def racing(*a, **kw):
        rows = original_scan(*a, **kw)
        price.write_bytes(b'changed during build')
        return rows
    monkeypatch.setattr(engine, 'scan_seasonality_discovery', racing)
    with pytest.raises(RuntimeError, match='원천 자료 변경'):
        snapshots.build_bundle(s)
    assert pointer.read_bytes() == original
    assert (snapshots._folder(s)/f"{old['generation_id']}.json").exists()
    monkeypatch.setattr(engine, 'scan_seasonality_discovery', original_scan)
    new = snapshots.build_bundle(s)
    assert new['generation_id'] != old['generation_id']


def test_integrity_and_lookback_and_filters(prepared):
    s, _, _ = prepared
    old = snapshots.build_bundle(s)
    assert snapshots.build_bundle(s, 2)['generation_id'] != old['generation_id']
    assert [r['pre_entry_rank'] for r in snapshots.select_rows(old, query='000003')] == [3]
    with pytest.raises(ValueError):
        snapshots.read_bundle(s, 999)
    path = snapshots._folder(s)/f"{old['generation_id']}.json"
    damaged = copy.deepcopy(old)
    damaged['payload']['rows'][0]['company'] = 'tampered'
    path.write_text(json.dumps(damaged), encoding='utf-8')
    snapshots._MEM.clear()
    assert snapshots.read_bundle(s) is None
    with pytest.raises(RuntimeError, match='무결성'):
        snapshots.build_bundle(s)


def test_http_reads_shared_generation_without_computing(prepared, monkeypatch):
    from kr_quant.web import app as web
    s, price, calls = prepared
    snapshots.build_bundle(s)
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    client = TestClient(web.app)
    highlights = client.get('/api/seasonality/highlights').json()
    listing = client.get('/api/seasonality/pre-entry').json()
    detail = client.get('/api/seasonality/discovery/000001').json()
    assert highlights['snapshot']['generation_id'] == listing['snapshot']['generation_id'] == detail['snapshot']['generation_id']
    assert highlights['data']['glance_top3'][0]['signal_id'] == listing['rows'][0]['signal_id'] == detail['patterns'][0]['signal_id']
    assert len(calls) == 1
    assert 'identity' not in listing
    assert client.get('/api/seasonality/discovery/000001?generation_id=old').status_code == 409
    price.write_bytes(b'source changed')
    queued = []
    monkeypatch.setattr(snapshots, 'request_build', lambda *a: queued.append(1))
    response = client.get('/api/seasonality/highlights')
    assert response.status_code == 503
    assert response.headers['X-Research-Snapshot'] == 'pending'
    assert len(calls) == 1 and queued == [1]
    assert client.get('/api/seasonality/discovery?lookback_years=999').status_code == 422


def test_background_requests_are_single_flight(prepared, monkeypatch):
    import threading
    s, _, _ = prepared
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def slow(*args):
        calls.append(1)
        entered.set()
        release.wait(3)
        done.set()
    monkeypatch.setattr(snapshots, 'build_bundle', slow)
    snapshots.request_build(s)
    assert entered.wait(1)
    for _ in range(10):
        snapshots.request_build(s)
    assert calls == [1]
    release.set()
    assert done.wait(1)


def test_data_job_schedules_preparation_but_cancel_does_not(prepared, monkeypatch):
    from kr_quant.web import jobs
    from kr_quant.research import selection_tracking
    s, _, _ = prepared
    queued = []
    tracked = []
    monkeypatch.setattr(selection_tracking, 'request_tracking_refresh', lambda *a: tracked.append(1))
    monkeypatch.setattr(jobs, 'load_settings', lambda: s)
    monkeypatch.setattr(jobs, 'record_job_history', lambda *a: None)
    monkeypatch.setattr(jobs, '_maybe_publish', lambda *a: None)
    monkeypatch.setattr(jobs, '_notify_job', lambda *a, **kw: None)
    monkeypatch.setattr(snapshots, 'refresh_after_data_job', lambda *a: queued.append(1))
    runner = jobs.JobRunner()
    runner._run('smart-sync', lambda: {'pipeline_status': 'success'})
    assert queued == [1]
    assert runner.state['status'] == 'success'
    assert tracked == [1]
    runner._run('smart-sync', lambda: {'pipeline_status': 'interrupted', 'cancelled': True})
    assert queued == [1]
    assert tracked == [1]
