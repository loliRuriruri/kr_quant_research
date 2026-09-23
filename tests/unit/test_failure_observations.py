import copy
import subprocess
from pathlib import Path

import pytest
from kr_quant.research.failure_observations import failure_observations
from kr_quant.strategy.discovery_engine import pattern_from_month_stat
from kr_quant.strategy import event_explainer as explainer


def test_nonpositive_only_missing_is_not_zero():
    result = failure_observations([{'year': 2020, 'return': -.1}, {'year': 2021, 'return': 0},
        {'year': 2022, 'return': .1}, {'year': 2023, 'return': None},
        {'year': 2024, 'return': float('nan')}, {'year': 2025, 'return': True}])
    assert [r['year'] for r in result] == [2020, 2021]
    assert [r['outcome'] for r in result] == ['하락', '보합']
    assert all(r['cause_status'] == 'UNVERIFIED' and r['cause_sources'] == [] for r in result)
    assert all('원인 미확인' in r['text'] for r in result)


@pytest.mark.parametrize('ticker', ['009450', '999999'])
def test_curated_and_fallback_do_not_invent_causes(ticker, monkeypatch):
    stat = {'month': 9, 'history_records': [{'year': y, 'return': ret} for y, ret in
        [(2021, -.2), (2022, 0), (2023, .1), (2024, -.1), (2025, .2)]]}
    pattern = pattern_from_month_stat(ticker, 'Test', 'KOSPI', stat, lookback_years=5)
    row = {'quant_score': 70, 'return_3m': .05}
    original = explainer.explain_and_score_pattern(pattern, row)
    assert len(original['failure_observations']) == 3
    assert all('원인 미확인' in text for text in original['failed_analysis'])
    if ticker in explainer.EVENT_KNOWLEDGE_BASE:
        kb = copy.deepcopy(explainer.EVENT_KNOWLEDGE_BASE[ticker])
        kb['failed_causes'] = {'2021': 'UNSUPPORTED_CAUSE'}
        monkeypatch.setitem(explainer.EVENT_KNOWLEDGE_BASE, ticker, kb)
        changed = explainer.explain_and_score_pattern(pattern, row)
        assert changed == original


def test_old_snapshot_causes_repaired_without_mutating_memory(monkeypatch):
    from kr_quant.web import app as web, season_snapshot
    rows = [{'ticker': '005930', 'years_track': [{'year': 2021, 'return': -.2}],
             'failed_analysis': ['UNSUPPORTED_CAUSE'], 'seasonality_score': 73.2}]
    stored = {'payload': {'rows': rows}}
    monkeypatch.setattr(web, 'load_settings', lambda: object())
    monkeypatch.setattr(season_snapshot, 'read_bundle', lambda *a, **kw: copy.deepcopy(stored))
    result = web._season_bundle()
    assert '원인 미확인' in result['payload']['rows'][0]['failed_analysis'][0]
    assert rows[0]['failed_analysis'] == ['UNSUPPORTED_CAUSE']
    assert result['payload']['rows'][0]['seasonality_score'] == rows[0]['seasonality_score']


def test_old_new_explainer_same_scores_and_rules():
    # Compare the actual previous commit's function, not a rewritten approximation.
    old_source = subprocess.check_output(['git', 'show', '3e9a12f:src/kr_quant/strategy/event_explainer.py']).decode('utf-8')
    old = {}
    exec(compile(old_source, 'old_event_explainer', 'exec'), old)
    changed_fields = {'failed_analysis', 'failure_observations'}
    for ticker in ['009450', '999999']:
        for history in [[-.2, 0, .1, -.1, .2], [.1, -.1], [.3, .2, .1]]:
            pat = pattern_from_month_stat(ticker, 'Test', 'KOSPI', {'month': 9, 'history': history}, lookback_years=5)
            for inputs in [{}, {'quant_score': 70, 'return_3m': .05}, {'quant_score': 40, 'return_3m': -.2}]:
                before = old['explain_and_score_pattern'](pat, inputs)
                after = explainer.explain_and_score_pattern(pat, inputs)
                assert {k: v for k, v in before.items() if k not in changed_fields} == {k: v for k, v in after.items() if k not in changed_fields}


def test_ui_does_not_reuse_unverified_legacy_causes():
    js = Path('src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    assert '실패 원인 정밀 분석' not in js
    assert '실패 연도 원인 분석' not in js
    assert '원자재·환율 충격 등 외부 변수와 겹친 경우가 많음' not in js
    assert 'seasonFailureObservations(r)' in js
