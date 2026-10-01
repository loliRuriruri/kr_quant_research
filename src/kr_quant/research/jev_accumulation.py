"""Sealed natural-generation accumulation; no model performance analysis."""
from __future__ import annotations

import copy
import hashlib
from collections import Counter

from kr_quant.research import jev_calibration as cal

PROTOCOL_ID = 'needsNews-v32-multigen-natural-v1'
PROTOCOL_VERSION = 1
REFERENCE_PROTOCOL_ID = 'needsNews-human-reference-v32-multigen-v1'
TARGET = 129
TRANCHE_FIELDS = ('source_generation_id','season_generation_id','source_bundle_hash',
    'source_as_of','selection_date','shadow_artifact_sha256','candidate_total',
    'semantic_skipped','provider_eligible','generated','reused','error','skipped')


def _counts(rows):
    counts = Counter(r['split'] for r in rows)
    return counts['calibration'], counts['holdout']


def _validate(rows):
    cal.ensure_split_consistency(rows)
    for r in rows:
        if r['split'] != cal.assign_split(ticker=r.get('ticker'),state_hash=r['state_hash']):
            raise cal.CalibrationError('AUTHORITATIVE_SPLIT_MISMATCH')
        if not isinstance(r.get('sample_id'),str) or not r['sample_id']:
            raise cal.CalibrationError('SAMPLE_ID_REQUIRED')


def append_tranche(existing, tranches, tranche, incoming, excluded_ids):
    """Append a complete population, never split/answer-aware scheduling.

    Operator must verify natural/consecutive canonical source provenance before
    supplying a tranche. This function performs deterministic structural checks.
    Caller supplies only validated complete exported model records.
    """
    if all(n >= TARGET for n in _counts([r for r in existing if r['sample_id'] not in excluded_ids])):
        raise ValueError('ACCUMULATION_ALREADY_SUFFICIENT')
    if (tranche.get('status') != 'success' or not tranche.get('natural_update_verified')
            or not tranche.get('consecutive_verified')):
        raise ValueError('NATURAL_CONSECUTIVE_GENERATION_REQUIRED')
    for field in ('source_generation_id','source_bundle_hash','season_generation_id'):
        if not isinstance(tranche.get(field),str) or not tranche[field]:
            raise ValueError('TRANCHE_IDENTITY_REQUIRED')
        if any(t[field] == tranche[field] for t in tranches):
            raise ValueError('DUPLICATE_GENERATION_OR_SOURCE')
    if tranches and (tranche['source_as_of'] < tranches[-1]['source_as_of']
                     or tranche['selection_date'] < tranches[-1]['selection_date']):
        raise ValueError('NONCONSECUTIVE_SOURCE_ORDER')
    all_rows = list(existing) + list(incoming)
    _validate(all_rows)
    by_id = {}
    for r in all_rows:
        old = by_id.get(r['sample_id'])
        if old and any(old.get(k)!=r.get(k) for k in ('ticker','state_hash','split')):
            raise cal.CalibrationError('SAMPLE_ID_BINDING_CONFLICT')
        by_id.setdefault(r['sample_id'],copy.deepcopy(r))
    excluded_count = len(set(by_id) & set(excluded_ids))
    union = [r for sid,r in sorted(by_id.items()) if sid not in excluded_ids]
    _validate(union)
    c,h = _counts(union)
    tranche_record = {k:tranche.get(k) for k in TRANCHE_FIELDS}
    incoming_unique = list({r['sample_id']:r for r in incoming}.values())
    tranche_record.update(complete_unique_count=len(incoming_unique),
                         calibration_count=_counts(incoming_unique)[0],holdout_count=_counts(incoming_unique)[1])
    next_tranches = copy.deepcopy(tranches) + [tranche_record]
    summary = {'protocol_id':PROTOCOL_ID,'protocol_version':PROTOCOL_VERSION,
        'split_method_version':'ticker-grouped-v1','tranches':next_tranches,
        'union_dataset_hash':cal.dataset_hash_v1(union),'unique_sample_count':len(union),
        'calibration_count':c,'holdout_count':h,
        'previously_judged_excluded':excluded_count,
        'first_sufficient_generation':tranche['season_generation_id'] if c>=TARGET and h>=TARGET else None,
        'calibration_shortfall':max(0,TARGET-c),'holdout_shortfall':max(0,TARGET-h)}
    return {'rows':union,'all_complete_rows':[r for _,r in sorted(by_id.items())],
            'tranches':next_tranches,'summary':summary}


def reference_selection(rows):
    """Only after first sufficiency: fixed quota and presealed reserve order."""
    _validate(rows)
    if any(n<TARGET for n in _counts(rows)):
        raise ValueError('REFERENCE_CAPACITY_INSUFFICIENT')
    digest=cal.dataset_hash_v1(rows)
    def key(r):
        return hashlib.sha256((REFERENCE_PROTOCOL_ID+'\n'+digest+'\n'+r['sample_id']).encode()).hexdigest()
    selected,reserve=[],[]
    for split in ('calibration','holdout'):
        ordered=sorted((r for r in rows if r['split']==split),key=key)
        selected.extend(r['sample_id'] for r in ordered[:TARGET])
        reserve.extend(r['sample_id'] for r in ordered[TARGET:])
    return {'protocol_id':REFERENCE_PROTOCOL_ID,'universe_dataset_hash':digest,
            'selected':selected,'reserve':reserve}
