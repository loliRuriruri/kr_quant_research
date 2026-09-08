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
