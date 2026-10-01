import pytest

from kr_quant.research import season_jev_shadow as shadow
from test_season_jev_shadow import _bundle, _settings, _ok_runner


@pytest.mark.parametrize('mode,status,thesis,reason', [
    ('DOMAIN_UNMAPPED', 'UNMAPPED', None, 'SEMANTIC_MAPPING_UNMAPPED'),
    ('DOMAIN_AMBIGUOUS', 'AMBIGUOUS', None, 'SEMANTIC_MAPPING_AMBIGUOUS'),
    ('INSUFFICIENT_EVIDENCE', 'MAPPED', None, 'SEMANTIC_EVIDENCE_INSUFFICIENT'),
    ('RULE_BASED', 'MAPPED', '  ', 'SEMANTIC_THESIS_UNAVAILABLE'),
    ('RULE_BASED', None, 'thesis', 'SEMANTIC_MAPPING_UNMAPPED'),
    ('RULE_BASED', 'INVALID_STATUS', 'thesis', 'SEMANTIC_MAPPING_UNMAPPED'),
    ('RULE_BASED', 'AMBIGUOUS', 'thesis', 'SEMANTIC_MAPPING_AMBIGUOUS'),
    ('FUTURE_MODE', 'MAPPED', 'thesis', 'SEMANTIC_MODE_UNSUPPORTED'),
])
def test_semantic_skip_precedes_reuse_budget_and_runner(tmp_path, monkeypatch, mode, status, thesis, reason):
    s = _settings(tmp_path)
    bundle = _bundle()
    row = bundle['payload']['rows'][0]
    row.update(event_explanation_mode=mode, event_mapping_status=status, event_hypothesis=thesis,
               event_mapping_version='normalized-domain-v2.1')
    monkeypatch.setattr(shadow, 'provider_key', lambda cfg: 'test-only')
    monkeypatch.setattr(shadow, 'source_identity', lambda *a, **k: bundle['identity'])
    monkeypatch.setattr('kr_quant.strategy.seasonality.rank_institutional_events', lambda *a, **k: [])
    candidates = shadow.collect_candidates(s, bundle)
    class ForbiddenReuse(dict):
        def get(self, *a, **k):
            pytest.fail('ineligible row reached reuse lookup')
    monkeypatch.setattr(shadow, 'load_reuse_index', lambda *a: ForbiddenReuse())
    monkeypatch.setattr('kr_quant.research.season_jev_budget.reserve_daily_slot',
                        lambda *a, **k: pytest.fail('ineligible row reserved budget'))
    calls = []
    result = shadow.evaluate_generation(s, bundle, runner=_ok_runner(calls))
    assert calls == []
    assert result['candidate_count'] == len(candidates) == 1
    assert result['results'][0]['status'] == 'SKIPPED'
    assert result['results'][0]['skip_reason'] == reason


@pytest.mark.parametrize('mode,status', [('RULE_BASED', 'MAPPED'), ('CURATED_TICKER', None)])
def test_authoritative_admission_accepts_usable_modes(mode, status):
    assert shadow.season_jev_admission({'event_explanation_mode': mode,
        'event_mapping_status': status, 'event_hypothesis': 'usable thesis'})['eligible'] is True


def test_admission_rejects_non_string_thesis():
    assert not shadow.season_jev_admission({'event_explanation_mode': 'CURATED_TICKER',
                                           'event_hypothesis': ['not a thesis']})['eligible']


def test_matching_reuse_is_skipped_and_calendar_still_runs(tmp_path, monkeypatch):
    from kr_quant.research import jev_calibration as cal
    from test_season_jev_shadow import _complete_answers
    s = _settings(tmp_path)
    bundle = _bundle()
    bundle['payload']['rows'][0].update(event_explanation_mode='DOMAIN_UNMAPPED', event_hypothesis=None)
    calendar = {'event_id': 'event', 'ticker': '000001', 'target_date': '2026-10-10',
                'event_title': 'explicit event', 'exposure_desc': 'exposure', 'invalidating_rule': 'rule'}
    monkeypatch.setattr('kr_quant.strategy.seasonality.rank_institutional_events', lambda *a, **k: [calendar])
    monkeypatch.setattr(shadow, 'provider_key', lambda cfg: 'test-only')
    monkeypatch.setattr(shadow, 'source_identity', lambda *a, **k: bundle['identity'])
    candidates = shadow.collect_candidates(s, bundle)
    key = shadow.reuse_key('season-jev-shadow-v1', 'typesafe_direct', 'jev-latest', candidates[0]['state_hash'])
    monkeypatch.setattr(shadow, 'load_reuse_index', lambda *a: {
        key: {'record': {'answers': _complete_answers()}, 'original_generation': 'old'}})
    calls = []
    result = shadow.evaluate_generation(s, bundle, runner=_ok_runner(calls))
    assert calls == [[candidates[1]['id']]]
    assert result['candidate_count'] == 2
    assert result['results'][0]['status'] == 'SKIPPED'
    assert result['results'][1]['status'] == 'GENERATED'
    exported = cal.export_candidates_from_shadow(result, provider='typesafe_direct',
        requested_model='jev-latest', evaluator_version='season-jev-shadow-v1')
    assert len(exported) == 1
    assert exported[0]['candidate_type'] == 'calendar_event_stock'


@pytest.mark.parametrize('mode,status', [('RULE_BASED', 'MAPPED'), ('CURATED_TICKER', None)])
def test_usable_season_reaches_runner_without_local_admission_fields(tmp_path, monkeypatch, mode, status):
    s = _settings(tmp_path)
    bundle = _bundle()
    bundle['payload']['rows'][0].update(event_explanation_mode=mode,
        event_hypothesis='usable thesis', event_mapping_status=status, event_mapping_version='normalized-domain-v2.1')
    monkeypatch.setattr('kr_quant.strategy.seasonality.rank_institutional_events', lambda *a, **k: [])
    monkeypatch.setattr(shadow, 'provider_key', lambda cfg: 'test-only')
    monkeypatch.setattr(shadow, 'source_identity', lambda *a, **k: bundle['identity'])
    calls = []
    def runner(settings, payload, timeout):
        assert 'semantic_input' not in payload['candidates'][0]
        assert 'quant_reference' not in payload['candidates'][0]
        return _ok_runner(calls)(settings, payload, timeout)
    result = shadow.evaluate_generation(s, bundle, runner=runner)
    assert calls == [['sig-1']]
    assert result['results'][0]['status'] == 'GENERATED'
