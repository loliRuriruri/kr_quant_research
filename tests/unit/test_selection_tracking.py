import copy
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from kr_quant.settings import load_settings
from kr_quant.run_generation import publish_run_generation
from kr_quant.research import selection_ledger as ledger
from kr_quant.research import selection_tracking as tracking
from kr_quant.research.selection_outcomes import observe_selection_outcomes


@pytest.fixture
def generation(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    rows = pd.DataFrame([
        {'ticker': '000001', 'company': 'Selected', 'run_id': 'observed-test', 'as_of_date': '2026-09-04',
         'quant_rank': 1, 'quant_score': 0., 'universe_eligible': True, 'top100_eligible': True,
         'exclusion_reasons': [], 'metric_values': {'roe': None, 'per': 0}},
        {'ticker': '00104K', 'company': 'Excluded', 'run_id': 'observed-test', 'as_of_date': '2026-09-04',
         'quant_rank': None, 'quant_score': 90., 'universe_eligible': False, 'top100_eligible': False,
         'exclusion_reasons': ['suspended'], 'metric_values': {'roe': None, 'per': 1}},
    ])
    manifest = publish_run_generation(
        settings, run_id='observed-test', as_of='2026-09-04', all_stocks=rows,
        top100=rows.iloc[:1], top20=rows.iloc[:1],
        quality={'run_id': 'observed-test', 'as_of_date': '2026-09-04', 'source_mode': 'live', 'status': 'success'},
        universe_evidence={'as_of': '2026-09-04'}, universe_snapshot=rows,
        price_integrity_issues=pd.DataFrame([{'ticker': '000001'}]))
    return settings, manifest


def test_capture_freezes_first_observation_and_all_decisions(generation):
    settings, manifest = generation
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    first = ledger.capture_quant_selection(settings, now=now)
    p = first['payload']
    assert p['observed_at'] == now.isoformat()
    assert p['source_as_of'] == '2026-09-04'
    assert p['selected_count'] == 1 and p['universe_count'] == 2
    assert p['selected'][0]['quant_score'] == 0
    assert p['selected'][0]['metric_values'] == {'roe': None, 'per': 0}
    assert p['universe_decisions'][1]['universe_eligible'] is False
    assert p['universe_decisions'][1]['ticker'] == '00104K'
    assert p['exclusion_counts'] == {'suspended': 1}
    assert ledger.capture_quant_selection(settings, now=now+timedelta(days=1)) == first
    assert ledger.latest_index(settings)['observed_at'] == p['observed_at']


def test_capture_rejects_corrupt_source_and_preserves_record(generation):
    from pathlib import Path
    settings, manifest = generation
    first = ledger.capture_quant_selection(settings)
    index_before = (ledger.folder(settings)/'latest.json').read_bytes()
    (Path(manifest['generation_dir'])/'data_quality_report.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='해시'):
        ledger.capture_quant_selection(settings)
    assert (ledger.folder(settings)/'latest.json').read_bytes() == index_before
    path = ledger.folder(settings)/f"{first['payload']['batch_id']}.json"
    damaged = json.loads(path.read_text(encoding='utf-8'))
    damaged['payload']['selected_count'] = 999
    path.write_text(json.dumps(damaged), encoding='utf-8')
    with pytest.raises(ValueError, match='무결성'):
        ledger.read_verified(path)


def test_capture_rejects_naive_or_backdated_clock(generation):
    settings, _ = generation
    with pytest.raises(ValueError, match='시간대'):
        ledger.capture_quant_selection(settings, now=datetime(2026, 9, 7))
    with pytest.raises(ValueError, match='이른 관측'):
        ledger.capture_quant_selection(settings, now=datetime(2026, 9, 4, 23, tzinfo=timezone.utc))


@pytest.mark.parametrize('column,value,message', [
    ('run_id', 'different', '혼합'), ('as_of_date', '2026-09-03', '혼합'),
    ('quant_rank', 0, '순위'), ('quant_rank', 1.5, '순위'),
    ('quant_score', float('nan'), '점수'), ('ticker', 'bad!', '코드'),
])
def test_semantic_source_gates(generation, monkeypatch, column, value, message):
    settings, _ = generation
    reader = ledger.pd.read_parquet
    def altered(*a, **kw):
        frame = reader(*a, **kw)
        frame.loc[0, column] = value
        return frame
    monkeypatch.setattr(ledger.pd, 'read_parquet', altered)
    with pytest.raises(ValueError, match=message):
        ledger.capture_quant_selection(settings)
    assert ledger.latest_index(settings) is None


def test_in_progress_generation_not_recorded(generation, monkeypatch):
    monkeypatch.setattr(ledger, 'is_updating', lambda s: True)
    with pytest.raises(ValueError, match='완성된'):
        ledger.capture_quant_selection(generation[0])


@pytest.mark.parametrize('mode,status', [('demo', 'success'), ('live', 'partial')])
def test_non_live_success_generations_not_recorded(generation, monkeypatch, mode, status):
    from pathlib import Path
    from kr_quant.hashing import sha256_file
    settings, manifest = generation
    changed = copy.deepcopy(manifest)
    quality_path = Path(manifest['generation_dir'])/'data_quality_report.json'
    quality = json.loads(quality_path.read_text(encoding='utf-8'))
    quality.update(source_mode=mode, status=status)
    quality_path.write_text(json.dumps(quality), encoding='utf-8')
    changed['files']['data_quality_report.json']['sha256'] = sha256_file(quality_path)
    monkeypatch.setattr(ledger, 'load_manifest', lambda s: changed)
    with pytest.raises(ValueError, match='성공 세대'):
        ledger.capture_quant_selection(settings)


def test_integrity_error_on_valid_json_wrong_shape(tmp_path):
    path = tmp_path/'broken.json'
    path.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='무결성'):
        ledger.read_verified(path)


def test_concurrent_first_writer_wins_without_overwrite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path/'once.json'
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda n: ledger.write_once(path, {'value': n}), range(12)))
    assert all(v == values[0] for v in values)
    assert ledger.read_verified(path) == values[0]


@pytest.fixture
def cohort():
    return {'batch_id': 'batch', 'source_as_of': '2026-09-04', 'observed_at': '2026-09-07T10:00:00+00:00',
            'selected': [{'signal_id': 's1', 'ticker': '000001', 'company': 'A', 'quant_rank': 1}]}


def prices():
    days = pd.bdate_range('2026-09-08', periods=20)
    return pd.DataFrame({'trade_date': days, 'ticker': '000001', 'open': 100.,
                         'close': [101.+i for i in range(20)], 'volume': 10.})


def observe(cohort, px=None, **kwargs):
    px = prices() if px is None else px
    return observe_selection_outcomes(cohort, px, pd.bdate_range('2026-09-08', periods=20),
                                      observed_through=kwargs.pop('observed_through', date(2026, 10, 5)), **kwargs)


def test_future_horizons_not_backdated_or_filled_with_zero(cohort):
    report = observe(cohort, observed_through=date(2026, 9, 7))
    assert all(s['observed'] == 0 and s['win_rate'] is None and s['mean_return'] is None
               and s['status_counts'] == {'PENDING_ENTRY': 1} for s in report['summary'].values())
    partial = observe(cohort, observed_through=date(2026, 9, 8), corporate_actions_verified=True)
    assert partial['rows'][0]['horizons']['1']['entry_date'] == '2026-09-08'
    assert partial['rows'][0]['horizons']['1']['gross_return'] == .01
    assert partial['rows'][0]['horizons']['5']['status'] == 'PENDING_HORIZON'


def test_price_basis_cost_and_benchmark_are_explicit(cohort):
    raw = observe(cohort)
    assert raw['rows'][0]['horizons']['5']['status'] == 'PRICE_BASIS_UNVERIFIED'
    px = prices()
    px['adj_close'] = px['close'] * .5
    assert observe(cohort, px)['rows'][0]['horizons']['5']['status'] == 'PRICE_BASIS_UNVERIFIED'
    benchmark = px[['trade_date', 'open', 'close']].copy()
    benchmark['close'] = 102.
    result = observe(cohort, px, adjusted_prices_verified=True, round_trip_cost_bps=100, benchmark=benchmark, benchmark_name='Synthetic fixture')
    h = result['rows'][0]['horizons']['5']
    assert h['gross_return'] == .05 and h['net_scenario_return'] == .04 and h['excess_return'] == .03
    assert h['price_basis'] == 'ADJUSTED_CLOSE_WITH_ADJUSTED_OPEN'
    no_cost = observe(cohort, px, adjusted_prices_verified=True)['rows'][0]['horizons']['5']
    assert no_cost['net_scenario_return'] is None and no_cost['excess_return'] is None
    with pytest.raises(ValueError, match='비용'):
        observe(cohort, round_trip_cost_bps=-1)


@pytest.mark.parametrize('case,status', [
    ('missing_entry', 'ENTRY_DATA_MISSING'), ('suspended_entry', 'ENTRY_UNAVAILABLE'),
    ('missing_path', 'PRICE_PATH_MISSING'), ('suspended_exit', 'EXIT_UNAVAILABLE'),
    ('zero_price', 'INVALID_PRICE'), ('jump', 'PRICE_DISCONTINUITY'),
])
def test_unavailable_names_remain_visible_in_denominator(cohort, case, status):
    px = prices()
    if case == 'missing_entry': px = px.iloc[1:]
    elif case == 'suspended_entry': px.loc[0, 'volume'] = 0
    elif case == 'missing_path': px = px.drop(index=2)
    elif case == 'suspended_exit': px.loc[4, 'volume'] = 0
    elif case == 'zero_price': px.loc[3, 'close'] = 0
    elif case == 'jump': px.loc[3, 'close'] = 200
    result = observe(cohort, px, corporate_actions_verified=True)
    assert result['rows'][0]['horizons']['5']['status'] == status
    assert result['summary']['5']['total_signals'] == 1
    assert result['summary']['5']['win_rate'] is None


def test_duplicate_prices_and_signals_fail_instead_of_silent_deduplication(cohort):
    px = prices()
    with pytest.raises(ValueError, match='중복 가격'):
        observe(cohort, pd.concat([px, px.iloc[:1]]))
    cohort['selected'] *= 2
    with pytest.raises(ValueError, match='ID 중복'):
        observe(cohort)


def test_missing_signal_is_not_removed_from_coverage(cohort):
    cohort['selected'].append({'signal_id': 's2', 'ticker': '000002'})
    result = observe(cohort, corporate_actions_verified=True)
    assert result['summary']['5'] == {'total_signals': 2, 'observed': 1,
                                     'status_counts': {'OBSERVED': 1, 'ENTRY_DATA_MISSING': 1},
                                     'mean_return': .05, 'win_rate': 1.}


def test_background_materialization_and_read_only_http(generation, monkeypatch):
    from kr_quant.web import app as web
    settings, _ = generation
    path = settings.staged_dir/'live/prices.parquet'
    path.parent.mkdir(parents=True)
    # Only pre-observation data: no retroactive return can be produced.
    pd.DataFrame({'trade_date': pd.to_datetime(['2026-09-04']), 'ticker': ['000001'],
                  'open': [100.], 'close': [110.], 'volume': [10.]}).to_parquet(path)
    report = tracking.refresh_tracking(settings)
    assert report['summary']['5']['status_counts'] == {'PENDING_ENTRY': 1}
    assert tracking.refresh_tracking(settings) == report
    monkeypatch.setattr(web, 'load_settings', lambda: settings)
    monkeypatch.setattr(tracking, 'refresh_tracking', lambda *a: pytest.fail('GET must not compute'))
    client = TestClient(web.app)
    response = client.get('/api/research/selection-tracking')
    assert response.status_code == 200 and response.json()['current_generation'] is True
    assert response.json()['state'] == 'READY'
    assert 'generation_dir' not in response.text
    # A changed price source is not silently described as up-to-date.
    with path.open('ab') as stream: stream.write(b'changed')
    assert client.get('/api/research/selection-tracking').json()['state'] == 'OUTCOMES_STALE'
    pointer = ledger.folder(settings)/'latest.json'
    damaged = json.loads(pointer.read_text(encoding='utf-8'))
    damaged['payload']['selected_count'] = 999
    pointer.write_text(json.dumps(damaged), encoding='utf-8')
    assert client.get('/api/research/selection-tracking').status_code == 503


def test_unrecorded_is_not_fake_empty_success(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    assert tracking.tracking_response(settings)['state'] == 'NOT_RECORDED'


def test_background_refresh_single_flight(tmp_path, monkeypatch):
    import threading
    settings = replace(load_settings(), root=tmp_path)
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def slow(*a):
        calls.append(1)
        entered.set()
        release.wait(3)
        done.set()
    monkeypatch.setattr(tracking, 'refresh_tracking', slow)
    tracking.request_tracking_refresh(settings)
    assert entered.wait(1)
    for _ in range(10): tracking.request_tracking_refresh(settings)
    assert calls == [1]
    release.set()
    assert done.wait(1)


def test_ui_tracking_is_lazy():
    settings = load_settings()
    js = (settings.root/'src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    html = (settings.root/'src/kr_quant/web/static/index.html').read_text(encoding='utf-8')
    assert '<details id="quant-observation-panel">' in html
    assert 'if (event.currentTarget.open) loadQuantObservations();' in js
    assert '관측 표본 내 상승 비율' in js
