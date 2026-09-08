from datetime import date
from dataclasses import replace
import threading
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from kr_quant.settings import load_settings
from kr_quant.research.season_holdout import evaluate_season_holdout
from kr_quant.research import season_holdout_store as store


@pytest.fixture
def history():
    days = pd.bdate_range('2016-01-01', '2026-12-31')
    values = []
    for day in days:
        if day.month == 9:
            # Training years have September peaks on day 15. In 2023 it fails.
            value = (120-abs(day.day-15)*.4) if day.year < 2023 else 100-day.day*.5
        elif day.month == 6 and day.year >= 2023:
            value = 100+day.day
        else:
            value = 100-day.day*.02
        values.append(value)
    return pd.DataFrame({'ticker': '005930', 'trade_date': days, 'open': 100., 'close': values, 'volume': 100.})


def run(frame, lookback=5, sessions=None):
    return evaluate_season_holdout(frame, ticker='005930', as_of=date(2026, 9, 7),
                                   sessions=frame.trade_date if sessions is None else sessions, lookback_years=lookback)


def fold(report, year):
    return next(f for f in report['folds'] if f['test_year'] == year)


def test_train_selects_month_and_fixed_exit_before_test_year(history):
    report = run(history)
    f = fold(report, 2023)
    assert f['selection']['month'] == 9  # NOT this year's winning June.
    assert max(f['selection']['train_years']) == 2022
    assert f['selection']['exit_day'] == 15
    assert f['entry_date'] == '2023-09-01' and f['exit_date'] == '2023-09-15'
    assert f['diagnostic_return'] == -.075  # 92.5 / 100 - 1, independently known.
    assert f['cost_scenarios']['50'] == -.08
    assert f['verified_return'] is None
    assert report['summary']['verified_count'] == 0
    assert max(f['test_year'] for f in report['folds']) == 2025


def test_optional_execution_keeps_fixed_open_outcome_separate(history):
    from kr_quant.strategy.engine import ExecutionModel
    result = evaluate_season_holdout(history, ticker='005930', as_of=date(2026, 9, 7),
                                    sessions=history.trade_date,
                                    execution_model=ExecutionModel(slippage_bps=5))
    item = fold(result, 2023)
    diagnostic = item['execution_diagnostic']
    assert diagnostic['entry']['date'] == '2023-09-01'
    assert diagnostic['exit']['date'] == '2023-09-15'
    assert diagnostic['gross_return'] == 0  # Both opens are 100, unlike exit close.
    assert diagnostic['net_return'] < 0
    assert item['diagnostic_return'] == -.075
    assert result['summary']['verified_count'] == 0


def test_optional_execution_retains_unfilled_fold(history):
    from kr_quant.strategy.engine import ExecutionModel
    history.loc[history.trade_date.between('2023-09-01', '2023-09-05'), 'open'] = float('nan')
    result = evaluate_season_holdout(history, ticker='005930', as_of=date(2026, 9, 7),
                                    sessions=history.trade_date, execution_model=ExecutionModel())
    item = fold(result, 2023)
    assert item['execution_diagnostic']['status'] == 'ENTRY_UNFILLED'
    assert item['execution_diagnostic']['net_return'] is None


def test_future_price_changes_cannot_change_past_selection_or_exit_result(history):
    original = run(history)
    changed = history.copy()
    # This includes dates AFTER the preselected exit but within the test month.
    changed.loc[changed.trade_date > '2023-09-15', ['open', 'close']] = 99999
    later = run(changed)
    assert fold(later, 2023) == fold(original, 2023)
    assert fold(later, 2022) == fold(original, 2022)


def test_whole_test_year_can_change_outcome_but_not_its_selection(history):
    before = fold(run(history), 2023)
    changed = history.copy()
    changed.loc[changed.trade_date.dt.year == 2023, 'close'] = 100
    after = fold(run(changed), 2023)
    assert after['selection'] == before['selection']
    assert after['candidates'] == before['candidates']
    assert after['diagnostic_return'] == 0 and before['diagnostic_return'] < 0


def test_month_boundary_jump_cannot_escape_quality_gate(history):
    bad = history.copy()
    bad.loc[bad.trade_date == '2023-08-31', 'close'] = 200
    result = fold(run(bad), 2023)
    assert result['selection']['month'] == 9
    assert result['status'] == 'PRICE_DISCONTINUITY'
    assert result['diagnostic_return'] is None


def test_all_history_and_small_window_meaning(history):
    all_years = fold(run(history, 0), 2025)
    recent = fold(run(history, 5), 2025)
    assert len(all_years['candidates'][0]['train_years']) == 9
    assert len(recent['candidates'][0]['train_years']) == 5
    two = run(history, 2)
    assert two['summary']['diagnostic_count'] == 0
    assert two['summary']['mean'] is None


@pytest.mark.parametrize('kind,status', [('missing','PRICE_PATH_MISSING'), ('zero','NO_TRADING_VOLUME'),
                                        ('invalid','INVALID_PRICE'), ('jump','PRICE_DISCONTINUITY')])
def test_bad_test_paths_stay_in_denominator(history, kind, status):
    bad = history.copy()
    mask = bad.trade_date == '2023-09-04'
    if kind == 'missing': bad = bad[~mask]
    elif kind == 'zero': bad.loc[mask, 'volume'] = 0
    elif kind == 'invalid': bad.loc[mask, 'close'] = np.nan
    else: bad.loc[mask, 'close'] = 200
    report = run(bad, sessions=history.trade_date)
    assert fold(report, 2023)['status'] == status
    assert report['summary']['folds_total'] == 9
    assert fold(report, 2023)['diagnostic_return'] is None


def test_duplicates_fail_without_silent_dedup(history):
    with pytest.raises(ValueError, match='중복'):
        run(pd.concat([history, history.iloc[:1]]))


def test_disk_reuse_source_invalidation_and_read_only_response(tmp_path, history, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    price = settings.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    history.to_parquet(price)
    first = store.build_report(settings, '005930', 5)
    assert store.build_report(settings, '005930', 5) == first
    monkeypatch.setattr(store, 'build_report', lambda *a: pytest.fail('ready read must not recompute'))
    assert store.get_or_queue(settings, '005930', 5)['report'] == first
    from kr_quant.web import app as web
    monkeypatch.setattr(web, 'load_settings', lambda: settings)
    client = TestClient(web.app)
    assert client.get('/api/research/season-holdout/005930').json()['state'] == 'READY'
    assert client.get('/api/research/season-holdout/bad').status_code == 422
    assert client.get('/api/research/season-holdout/005930?lookback_years=99').status_code == 422
    p = store.destination(settings, first['identity'])
    damaged = json.loads(p.read_text(encoding='utf-8'))
    damaged['payload']['summary']['mean'] = 900
    p.write_text(json.dumps(damaged), encoding='utf-8')
    assert client.get('/api/research/season-holdout/005930').status_code == 503
    old_id = first['identity']
    changed = history.copy()
    changed.loc[0, 'close'] = 100
    changed.to_parquet(price)
    assert store.identity(settings, '005930', 5) != old_id


def test_cold_requests_are_single_flight(tmp_path, history, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    price = settings.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    history.to_parquet(price)
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def slow(*a):
        calls.append(1); entered.set(); release.wait(3); done.set()
    monkeypatch.setattr(store, 'build_report', slow)
    assert store.get_or_queue(settings, '005930')['state'] == 'PENDING'
    assert entered.wait(1)
    for _ in range(10): assert store.get_or_queue(settings, '005930')['state'] == 'PENDING'
    assert calls == [1]
    release.set()
    assert done.wait(1)


def test_ui_preserves_zero_and_labels_reference_rule():
    js = (load_settings().root/'src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    assert 'currentV11Lookback || 5' not in js
    assert '기존 선취매 전체 모델의 검증 결과가 아닙니다.' in js
    assert 'if (!details.open || loading) return;' in js
    assert 'class="season-holdout-fold"' in js


def test_queue_is_bounded(tmp_path, history, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    price = settings.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    history.to_parquet(price)
    monkeypatch.setattr(store, '_PENDING', set(str(i) for i in range(8)))
    assert store.get_or_queue(settings, '005930')['state'] == 'BUSY'


def test_changed_code_requires_restart_instead_of_wrong_cache_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(store, '_code_hash', lambda: 'modified-on-disk')
    with pytest.raises(ValueError, match='재시작'):
        store.identity(replace(load_settings(), root=tmp_path), '005930', 5)


def test_source_change_during_build_does_not_publish(tmp_path, history, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    price = settings.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    history.to_parquet(price)
    token = store.identity(settings, '005930', 5)
    evaluate = store.season_holdout.evaluate_season_holdout
    def changing(*args, **kwargs):
        result = evaluate(*args, **kwargs)
        revised = history.copy()
        revised.loc[0, 'close'] += 1
        revised.to_parquet(price)
        return result
    monkeypatch.setattr(store.season_holdout, 'evaluate_season_holdout', changing)
    with pytest.raises(ValueError, match='원천 변경'):
        store.build_report(settings, '005930')
    assert not store.destination(settings, token).exists()
