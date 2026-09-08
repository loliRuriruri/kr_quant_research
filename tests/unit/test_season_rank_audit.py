from copy import deepcopy

import pytest

from kr_quant.research.season_rank_audit import without_event_points, compare_ranks


def test_event_ablation_recomputes_cap_then_penalty_without_mutation():
    row = {'seasonality_score': 90, 'pre_pricing_flag': True,
           'score_breakdown': {'historical_pattern': 50, 'recent_validation': 30,
                               'current_confirmation': 15, 'event_explanation': 10}}
    original = deepcopy(row)
    assert without_event_points(row)['seasonality_score'] == 85  # NOT 90-10.
    assert row == original


def test_event_ablation_preserves_non_score_fields():
    row = {'seasonality_score': 7, 'grade': 'D', 'entry_stage': 'TODAY_ENTRY',
           'score_breakdown': {'historical_pattern': 0, 'recent_validation': 0,
                               'current_confirmation': 0, 'event_explanation': 7}}
    result = without_event_points(row)
    assert result['seasonality_score'] == 0
    assert result['grade'] == 'D' and result['entry_stage'] == 'TODAY_ENTRY'


@pytest.mark.parametrize('score', [999, float('nan'), True, -1])
def test_inconsistent_scores_are_not_silently_reconstructed(score):
    row = {'seasonality_score': score,
           'score_breakdown': {'historical_pattern': 0, 'recent_validation': 0,
                               'current_confirmation': 0, 'event_explanation': 7}}
    with pytest.raises(ValueError):
        without_event_points(row)


def test_rank_diff_retains_admissions_and_exclusions():
    a = {'ticker': '000001', 'pattern_id': 'one'}
    b = {'ticker': '000002', 'pattern_id': 'two'}
    result = compare_ranks([a], [b])
    assert result['moved'][0]['after'] is None
    assert result['moved'][1]['before'] is None
    with pytest.raises(ValueError):
        compare_ranks([a, a], [b])
