import runpy
from pathlib import Path


def test_evaluation_cases_cover_boundaries_without_live_calls():
    namespace = runpy.run_path(str(Path(__file__).parents[2] / 'scripts/evaluate_season_ai.py'))
    fixtures = dict(namespace['cases']())
    assert set(fixtures) == {'normal', 'weak', 'small_sample', 'missing', 'stale'}
    def candidate(name):
        return fixtures[name]['data']['glance_top3'][0]
    assert candidate('weak')['remaining_peak']['window_end_p50'] < 0
    assert candidate('small_sample')['remaining_peak']['sample_count'] == 2
    assert candidate('missing')['current_confirmation_evidence'] == []
    assert fixtures['stale']['snapshot']['selection_date'] < fixtures['normal']['snapshot']['selection_date']
    assert all(candidate(name)['ticker'] == '000000' for name in fixtures)


def test_error_category_never_returns_arbitrary_text():
    namespace = runpy.run_path(str(Path(__file__).parents[2] / 'scripts/evaluate_season_ai.py'))
    classify = namespace['safe_error_category']
    assert classify(RuntimeError('secret 502 overloaded')) == 'PROVIDER_UNAVAILABLE'
    assert classify(RuntimeError('secret 401')) == 'AUTHORIZATION'
    assert classify(RuntimeError('secret 429')) == 'RATE_LIMIT'
    assert classify(RuntimeError('secret timed out')) == 'TIMEOUT'
    assert classify(RuntimeError('secret')) == 'OTHER_ERROR'


def test_evaluation_wall_clock_timeout(monkeypatch):
    import time
    import pytest
    namespace = runpy.run_path(str(Path(__file__).parents[2] / 'scripts/evaluate_season_ai.py'))
    bounded = namespace['bounded_call']
    monkeypatch.setitem(bounded.__globals__, 'call_chat', lambda *a, **k: time.sleep(.05))
    with pytest.raises(TimeoutError):
        bounded(None, [], deadline=.001)


def test_paid_evaluation_requires_explicit_flag():
    import pytest
    namespace = runpy.run_path(str(Path(__file__).parents[2] / 'scripts/evaluate_season_ai.py'))
    with pytest.raises(RuntimeError, match='allow-paid'):
        namespace['run']('xai', False)
