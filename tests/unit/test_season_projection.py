import copy

import pytest

from kr_quant.web import season_snapshot as snapshots


def bundle():
    return {'generation_id': 'same', 'generated_at': '2026-09-07T00:00:00Z',
            'identity': {'day': '2026-09-07', 'lookback': 0},
            'payload': {'rows': [{'ticker': '005930', 'window_name': '9월',
                'years_track': [{'year': 2025, 'return': -.1}], 'failed_analysis': ['unverified old claim'],
                'event_hypothesis': 'repeated hypothesis', 'event_explanation_mode': 'RULE_BASED',
                'remaining_peak': {'samples': [1, 2]}, 'playbook': {'text': 'large'}}],
                'stats': {'data_context': {'as_of': '2026-09-04'}}, 'themes': [1], 'highlights': {}}}


@pytest.mark.parametrize('view', ['summary', 'explanation'])
def test_nested_projection_isolation(view):
    original = bundle()
    saved = copy.deepcopy(original)
    result = snapshots._copy_bundle(original, view)
    assert 'remaining_peak' not in result['payload']['rows'][0]
    assert 'themes' not in result['payload']
    result['payload']['rows'][0]['years_track'][0]['return'] = 999
    result['payload']['stats']['data_context'].clear()
    result['identity'].clear()
    assert original == saved


def test_unused_heavy_fields_are_never_copied():
    class Forbidden:
        def __deepcopy__(self, memo):
            raise AssertionError('unused full payload copied')
    original = bundle()
    original['payload']['rows'][0]['remaining_peak'] = Forbidden()
    original['payload']['themes'] = Forbidden()
    assert snapshots._copy_bundle(original, 'summary')['payload']['rows'][0]['ticker'] == '005930'


def test_read_cache_does_not_leak_projection_mutation(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from kr_quant import run_generation
    s = SimpleNamespace(root=tmp_path)
    original = bundle()
    identity = original['identity']
    monkeypatch.setattr(run_generation, 'is_updating', lambda _: False)
    monkeypatch.setattr(snapshots, 'source_identity', lambda *args: identity)
    monkeypatch.setattr(snapshots, '_MEM', {(str(tmp_path.resolve()), 0): (snapshots._digest(identity), original)})
    projected = snapshots.read_bundle(s, 0, listing_view='summary')
    projected['payload']['rows'][0]['years_track'].clear()
    full = snapshots.read_bundle(s, 0)
    assert len(full['payload']['rows'][0]['years_track']) == 1
    assert full == original and full is not original


def test_explanation_repairs_only_page_and_legacy_year_fallback(monkeypatch):
    from kr_quant.web import app as web
    from kr_quant.research import failure_observations as observations
    original = bundle()
    row = original['payload']['rows'][0]
    row['failed_years'] = row.pop('years_track')
    original['payload']['rows'] = [copy.deepcopy(row) for _ in range(40)]
    monkeypatch.setattr(web, '_season_bundle', lambda *args, **kwargs: snapshots._copy_bundle(original, kwargs.get('listing_view')))
    calls = []
    original_fn = observations.failure_observations
    def counted(years):
        calls.append(years)
        return original_fn(years)
    monkeypatch.setattr(observations, 'failure_observations', counted)
    result = web.api_seasonality_discovery_get(view='explanation', offset=10, limit=5)
    assert len(calls) == 5
    assert all('원인 미확인' in r['failed_analysis'][0] for r in result['rows'])
    assert original['payload']['rows'][0]['failed_analysis'] == ['unverified old claim']
