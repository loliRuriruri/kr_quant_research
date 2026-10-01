import copy

import pytest

from kr_quant.research.season_jev_shadow import shadow_execution_identity_matches


def identity(day='2026-10-01'):
    return {'day': day, 'revision': {'day': day, 'schema': 1, 'sources': {'path': 'data', 'stat': 42}},
            'schema': 1, 'root': 'root', 'lookback': 5, 'manifest_sha256': 'abc',
            'config_hash': 'cfg', 'model_hash': 'model',
            'source_file_provenance': [{'path': 'data', 'sha256': 'sha'}]}


def test_exact_and_next_day_without_mutation():
    stored, current = identity(), identity('2026-10-02')
    before = copy.deepcopy((stored, current))
    assert shadow_execution_identity_matches(stored, stored)
    assert shadow_execution_identity_matches(stored, current)
    assert (stored, current) == before


@pytest.mark.parametrize('day', ['2026-10-03', '2026-09-30', None, '', 'invalid', '20261002'])
def test_invalid_or_unbounded_day(day):
    assert not shadow_execution_identity_matches(identity(), identity(day))


@pytest.mark.parametrize('which', ['stored', 'current'])
def test_revision_day_inconsistent(which):
    stored, current = identity(), identity('2026-10-02')
    (stored if which == 'stored' else current)['revision']['day'] = '2026-09-30'
    assert not shadow_execution_identity_matches(stored, current)


@pytest.mark.parametrize('field', ['manifest_sha256', 'config_hash', 'model_hash', 'lookback', 'root', 'schema'])
def test_other_top_level_changes_fail(field):
    stored, current = identity(), identity('2026-10-02')
    current[field] = 'changed'
    assert not shadow_execution_identity_matches(stored, current)


@pytest.mark.parametrize('area,field', [('source_file_provenance', 'sha256'), ('source_file_provenance', 'path'),
                                       ('sources', 'path'), ('sources', 'stat')])
def test_nested_source_changes_fail(area, field):
    stored, current = identity(), identity('2026-10-02')
    target = current[area][0] if area == 'source_file_provenance' else current['revision'][area]
    target[field] = 'changed'
    assert not shadow_execution_identity_matches(stored, current)


@pytest.mark.parametrize('field', ['day', 'revision'])
def test_missing_date_structure_fails(field):
    stored, current = identity(), identity('2026-10-02')
    del current[field]
    assert not shadow_execution_identity_matches(stored, current)


def test_malformed_identity_fails():
    assert not shadow_execution_identity_matches(None, None)
    current = identity('2026-10-02')
    current['revision'] = []
    assert not shadow_execution_identity_matches(identity(), current)
