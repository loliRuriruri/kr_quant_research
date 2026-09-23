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
    assert response.status_code == 200
    body = response.json()
    assert body['snapshot']['is_current'] is False
    assert body['snapshot']['state'] == 'stale_while_revalidate'
    assert body['snapshot']['refresh_pending'] is True
    assert body['snapshot']['selection_date']
    assert body['snapshot']['snapshot_as_of'] == body['snapshot']['selection_date']
    assert '_serve_meta' not in body
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


def test_lkg_validation_fail_closed(prepared):
    s, _, _ = prepared
    built = snapshots.build_bundle(s)
    folder = snapshots._folder(s)
    pointer = folder / 'latest_lb_5.json'
    good = pointer.read_text(encoding='utf-8')
    # missing pointer
    pointer.unlink()
    assert snapshots.read_last_known_good(s) is None
    pointer.write_text(good, encoding='utf-8')
    # path-like generation_id
    pointer.write_text('{"generation_id":"../etc/passwd","generated_at":"x"}', encoding='utf-8')
    assert snapshots.read_last_known_good(s) is None
    # non-hex generation_id
    pointer.write_text('{"generation_id":"not-a-hex-digest-value","generated_at":"x"}', encoding='utf-8')
    assert snapshots.read_last_known_good(s) is None
    # pointer to missing generation file
    missing = 'a' * 64
    pointer.write_text(json.dumps({"generation_id": missing, "generated_at": "x"}), encoding='utf-8')
    assert snapshots.read_last_known_good(s) is None
    # restore valid pointer then tamper payload hash
    pointer.write_text(good, encoding='utf-8')
    path = folder / f"{built['generation_id']}.json"
    damaged = json.loads(path.read_text(encoding='utf-8'))
    damaged['payload']['rows'][0]['company'] = 'tampered-lkg'
    path.write_text(json.dumps(damaged), encoding='utf-8')
    snapshots._MEM.clear()
    assert snapshots.read_last_known_good(s) is None
    # lookback mismatch
    path.write_text(json.dumps(built), encoding='utf-8')
    damaged_id = copy.deepcopy(built)
    damaged_id['identity'] = dict(built['identity'])
    damaged_id['identity']['lookback'] = 2
    damaged_id['content_hash'] = snapshots._digest(damaged_id['payload'])
    path.write_text(json.dumps(damaged_id), encoding='utf-8')
    assert snapshots.read_last_known_good(s) is None


def test_lkg_current_first_and_supersede(prepared, monkeypatch):
    s, price, _ = prepared
    first = snapshots.build_bundle(s)
    current = snapshots.read_bundle(s)
    lkg = snapshots.read_last_known_good(s)
    assert current['generation_id'] == first['generation_id'] == lkg['generation_id']
    from kr_quant.web import app as web
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    client = TestClient(web.app)
    ready = client.get('/api/seasonality/highlights').json()['snapshot']
    assert ready['is_current'] is True
    assert ready['state'] == 'ready'
    assert ready['refresh_pending'] is False
    assert 'snapshot_as_of' not in ready
    price.write_bytes(b'identity shift for supersede')
    snapshots._MEM.clear()
    assert snapshots.read_bundle(s) is None
    stale = snapshots.read_last_known_good(s)
    assert stale['generation_id'] == first['generation_id']
    monkeypatch.setattr(snapshots, 'request_build', lambda *a, **k: None)
    stale_http = client.get('/api/seasonality/pre-entry').json()['snapshot']
    assert stale_http['is_current'] is False
    assert stale_http['state'] == 'stale_while_revalidate'
    # rebuild current and confirm supersede
    second = snapshots.build_bundle(s)
    assert second['generation_id'] != first['generation_id']
    snapshots._MEM.clear()
    assert snapshots.read_bundle(s)['generation_id'] == second['generation_id']
    assert client.get('/api/seasonality/highlights').json()['snapshot']['generation_id'] == second['generation_id']
    assert client.get('/api/seasonality/highlights').json()['snapshot']['is_current'] is True


def test_lkg_preparation_failed_and_no_lkg_503(prepared, monkeypatch):
    import time
    s, price, _ = prepared
    first = snapshots.build_bundle(s)
    from kr_quant.web import app as web
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    client = TestClient(web.app)
    price.write_bytes(b'force stale identity')
    snapshots._MEM.clear()
    key = snapshots._key(s, 5)
    with snapshots._LOCK:
        snapshots._ERRORS[key] = (time.monotonic(), 'Boom')
    monkeypatch.setattr(snapshots, 'request_build', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no build')))
    res = client.get('/api/seasonality/themes')
    assert res.status_code == 200
    snap = res.json()['snapshot']
    assert snap['is_current'] is False
    assert snap['refresh_error'] is True
    assert snap['refresh_error_code'] == 'SEASON_BUILD_FAILED'
    assert snap['refresh_pending'] is False
    assert snap['generation_id'] == first['generation_id']
    # remove LKG pointer -> keep hard 503
    (snapshots._folder(s) / 'latest_lb_5.json').unlink()
    assert client.get('/api/seasonality/themes').status_code == 503


def test_lkg_no_shadow_and_no_request_while_runner_busy(prepared, monkeypatch):
    s, price, calls = prepared
    snapshots.build_bundle(s)
    price.write_bytes(b'busy runner identity change')
    snapshots._MEM.clear()
    from kr_quant.web import app as web
    from kr_quant.web import jobs
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    monkeypatch.setattr(jobs.RUNNER, 'is_running', lambda: True)
    queued = []
    shadows = []
    monkeypatch.setattr(snapshots, 'request_build', lambda *a, **k: queued.append(1))
    monkeypatch.setattr(snapshots, '_schedule_shadow', lambda *a, **k: shadows.append(1))
    client = TestClient(web.app)
    body = client.get('/api/seasonality/discovery?view=summary&limit=2').json()
    assert body['snapshot']['is_current'] is False
    assert queued == []
    assert shadows == []
    # LKG serve must not write generation files
    before = {p.name: p.stat().st_mtime_ns for p in snapshots._folder(s).glob('*.json')}
    client.get('/api/seasonality/highlights')
    after = {p.name: p.stat().st_mtime_ns for p in snapshots._folder(s).glob('*.json')}
    assert before == after


def test_lkg_ai_deferred_when_stale(prepared, monkeypatch):
    s, price, _ = prepared
    snapshots.build_bundle(s)
    price.write_bytes(b'stale for ai defer')
    snapshots._MEM.clear()
    from kr_quant.web import app as web
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    monkeypatch.setattr(snapshots, 'request_build', lambda *a, **k: None)
    called = []
    monkeypatch.setattr(web, 'tier1_cached_chat_json', lambda *a, **k: called.append(1) or {'ok': True})
    client = TestClient(web.app)
    res = client.get('/api/seasonality/tier1-briefing').json()
    assert res['ok'] is False
    assert res['error_code'] == 'STALE_SNAPSHOT_AI_DEFERRED'
    assert res['ai_generated'] is False
    assert called == []


def test_lkg_listing_view_and_409_preserved(prepared, monkeypatch):
    s, price, _ = prepared
    built = snapshots.build_bundle(s)
    price.write_bytes(b'stale listing')
    snapshots._MEM.clear()
    from kr_quant.web import app as web
    monkeypatch.setattr(web, 'load_settings', lambda: s)
    monkeypatch.setattr(snapshots, 'request_build', lambda *a, **k: None)
    client = TestClient(web.app)
    summary = client.get('/api/seasonality/discovery?view=summary&limit=1').json()
    assert summary['snapshot']['is_current'] is False
    assert 'rows' in summary
    assert client.get(f"/api/seasonality/discovery/{built['payload']['rows'][0]['ticker']}?generation_id=old").status_code == 409
    assert client.get('/api/seasonality/discovery?generation_id=old').status_code == 409


def test_serve_meta_not_persisted_into_generation(prepared):
    s, _, _ = prepared
    built = snapshots.build_bundle(s)
    snapshots.attach_serve_meta(built, is_current=False, refresh_pending=True, expected_as_of='2099-01-01')
    assert built['_serve_meta']['state'] == 'stale_while_revalidate'
    meta = snapshots.public_meta(built)
    assert meta['is_current'] is False
    assert '_serve_meta' not in meta
    path = snapshots._folder(s) / f"{built['generation_id']}.json"
    on_disk = json.loads(path.read_text(encoding='utf-8'))
    assert '_serve_meta' not in on_disk
    assert on_disk['content_hash'] == snapshots._digest(on_disk['payload'])


def test_lkg_identity_digest_and_root_binding(prepared):
    """LKG fails closed when generation no longer binds to identity, or root is foreign."""
    s, _, _ = prepared
    built = snapshots.build_bundle(s)
    folder = snapshots._folder(s)
    path = folder / f"{built['generation_id']}.json"
    pointer = folder / 'latest_lb_5.json'
    original_bytes = path.read_bytes()
    pointer_bytes = pointer.read_bytes()

    # A. valid generation accepted
    ok = snapshots.read_last_known_good(s)
    assert ok is not None
    assert ok['generation_id'] == built['generation_id']
    assert path.read_bytes() == original_bytes
    assert pointer.read_bytes() == pointer_bytes

    def _mutate_identity(mutator):
        damaged = json.loads(path.read_text(encoding='utf-8'))
        damaged['identity'] = mutator(dict(damaged['identity']))
        # keep generation_id + payload + content_hash unchanged
        path.write_text(json.dumps(damaged), encoding='utf-8')
        snapshots._MEM.clear()
        assert snapshots.read_last_known_good(s) is None
        # no silent rewrite of snapshot or pointer
        assert path.read_text(encoding='utf-8') == json.dumps(damaged)
        assert pointer.read_bytes() == pointer_bytes
        path.write_bytes(original_bytes)

    # B. identity.day changed, generation_id+payload unchanged -> rejected
    _mutate_identity(lambda ident: {**ident, 'day': '1999-01-01'})
    # C. identity.sources changed, generation_id+payload unchanged -> rejected
    _mutate_identity(lambda ident: {**ident, 'sources': [['foreign-source', 1, 2]]})
    # D. identity.model_hash/config_hash changed without recomputing generation -> rejected
    _mutate_identity(lambda ident: {**ident, 'model_hash': '0' * 64, 'config_hash': '1' * 64})

    # Foreign root: recompute generation so digest binds; root check still rejects.
    foreign = json.loads(original_bytes.decode('utf-8'))
    foreign['identity'] = dict(foreign['identity'])
    foreign['identity']['root'] = 'C:/foreign/installation/root'
    new_gen = snapshots._digest(foreign['identity'])
    foreign['generation_id'] = new_gen
    foreign_path = folder / f'{new_gen}.json'
    foreign_path.write_text(json.dumps(foreign), encoding='utf-8')
    pointer.write_text(
        json.dumps({'generation_id': new_gen, 'generated_at': foreign['generated_at']}),
        encoding='utf-8',
    )
    snapshots._MEM.clear()
    assert snapshots.read_last_known_good(s) is None
    # Independent of path-traversal: generation id is valid hex and file stays under folder
    assert snapshots._safe_generation_id(new_gen) == new_gen
    assert foreign_path.resolve().parent == folder.resolve()
    # no mutation of foreign snapshot contents on reject
    assert json.loads(foreign_path.read_text(encoding='utf-8'))['identity']['root'] == 'C:/foreign/installation/root'
    path.write_bytes(original_bytes)
    pointer.write_bytes(pointer_bytes)
    foreign_path.unlink(missing_ok=True)
    assert snapshots.read_last_known_good(s)['generation_id'] == built['generation_id']
