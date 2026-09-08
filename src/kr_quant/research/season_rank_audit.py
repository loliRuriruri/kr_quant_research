"""Read-only, frozen-candidate rank sensitivity; never modifies production ranks."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

from kr_quant.strategy.pre_entry_ranking import rank_pre_entry_from_inputs


def without_event_points(row):
    result = deepcopy(row)
    b = row['score_breakdown']
    values = [b[k] for k in ('historical_pattern', 'recent_validation', 'current_confirmation', 'event_explanation')]
    values.append(row['seasonality_score'])
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Invalid score components')
    total = sum(float(b[k]) for k in ('historical_pattern', 'recent_validation', 'current_confirmation', 'event_explanation'))
    penalty = 10 if row.get('pre_pricing_flag') else 0
    original = max(0, min(100, round(total, 1))-penalty)
    if abs(original-float(row['seasonality_score'])) > .011:
        raise ValueError('Stored score does not match component formula')
    result['seasonality_score'] = max(0, min(100, round(total-float(b['event_explanation']), 1))-penalty)
    return result


def compare_ranks(before, after):
    def key(r):
        return r['ticker'], r['pattern_id']
    a, b = {key(r): i+1 for i, r in enumerate(before)}, {key(r): i+1 for i, r in enumerate(after)}
    if len(a) != len(before) or len(b) != len(after):
        raise ValueError('Duplicate pattern identity')
    return {'before_count': len(a), 'after_count': len(b),
            'top3_before': [list(key(r)) for r in before[:3]],
            'top3_after': [list(key(r)) for r in after[:3]],
            'moved': [{'ticker': k[0], 'pattern_id': k[1], 'before': a.get(k), 'after': b.get(k)}
                      for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)]}


def audit(root, snapshot, output):
    from kr_quant.settings import load_settings
    from kr_quant.strategy.run import _prices
    from kr_quant.strategy.remaining_peak import calculate_remaining_peak_upside
    from kr_quant.atomic_io import write_json_atomic

    root, snapshot, output = map(Path, (root, snapshot, output))
    bundle = json.loads(snapshot.read_text(encoding='utf-8'))
    digest = hashlib.sha256(json.dumps(bundle['payload'], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    if digest != bundle['content_hash']:
        raise ValueError('Snapshot content hash mismatch')
    rows = sorted([r for r in bundle['payload']['rows'] if r.get('pre_entry_rank')], key=lambda r: r['pre_entry_rank'])
    if not rows:
        raise ValueError('No archived admitted candidates')
    # Eligibility of excluded tickers is not encoded in the archive. Do not
    # silently declare every archived ticker tradable for a full-universe test.
    clean = {r['ticker'] for r in rows}
    quotes = {r['ticker']: {'last_close': r['last_close'], 'as_of': r['remaining_peak']['price_as_of']} for r in rows}
    def rank(data):
        return rank_pre_entry_from_inputs(data, clean_set=clean, quotes=quotes)
    baseline = rank(rows)
    if [(r['ticker'], r['pattern_id']) for r in baseline] != [(r['ticker'], r['pattern_id']) for r in rows]:
        raise ValueError('Archived ranking not reproducible from stored fields')
    event = rank([without_event_points(r) for r in rows])
    # Load the actual pre-change committed calculator, never rewrite working code.
    old_code = subprocess.check_output(['git', 'show', '1e4be40:src/kr_quant/strategy/remaining_peak.py'], cwd=root).decode('utf-8')
    namespace = {'__name__': 'season_calendar_baseline'}
    exec(compile(old_code, '<trusted-git-baseline-1e4be40>', 'exec'), namespace)
    legacy = namespace['calculate_remaining_peak_upside']
    settings = load_settings(root)
    prices = _prices(settings, tickers=sorted(clean))
    import pandas as pd
    columns = [c for c in ('ticker', 'trade_date', 'close', 'adj_close', 'high', 'low', 'volume') if c in prices]
    price_fingerprint = hashlib.sha256(pd.util.hash_pandas_object(prices[columns], index=False).values.tobytes()).hexdigest()
    by_ticker = {str(t): g for t, g in prices.groupby('ticker')}
    before, after, changes = [], [], []
    mismatched = 0
    for index, row in enumerate(rows):
        old_rem = row['remaining_peak']
        kwargs = {'as_of_date': old_rem['price_as_of'], 'lookback_years': bundle['identity']['lookback']}
        args = (by_ticker[row['ticker']], row['ticker'], old_rem['target_month'])
        previous, current = legacy(*args, **kwargs), calculate_remaining_peak_upside(*args, **kwargs)
        if any(previous.get(k) != old_rem.get(k) for k in ('available', 'remaining_p50', 'historical_peak_day', 'entry_stage')):
            mismatched += 1
        for dest, metric in ((before, previous), (after, current)):
            dest.append({**row, 'remaining_peak': metric, 'entry_stage': metric.get('entry_stage')})
        keys = ('target_peak_date', 'historical_peak_day', 'entry_stage', 'available', 'remaining_p50')
        if any(previous.get(k) != current.get(k) for k in keys):
            changes.append({'ticker': row['ticker'], 'pattern_id': row['pattern_id'],
                            'before': {k: previous.get(k) for k in keys}, 'after': {k: current.get(k) for k in keys}})
        if (index+1) % 50 == 0:
            print(f'Compared {index+1}/{len(rows)} candidates', flush=True)
    result = {'verified': False, 'generation_id': bundle['generation_id'], 'snapshot_hash': digest,
              'snapshot_path': str(snapshot), 'lookback': bundle['identity']['lookback'],
              'loaded_price_fingerprint': price_fingerprint,
              'legacy_code_sha256': hashlib.sha256(old_code.encode()).hexdigest(),
              'current_code_sha256': hashlib.sha256((root/'src/kr_quant/strategy/remaining_peak.py').read_bytes()).hexdigest(),
              'scope': 'FROZEN_ARCHIVED_ADMITTED_POOL_NOT_FULL_UNIVERSE', 'candidate_count': len(rows),
              'distinct_ticker_count': len(clean),
              'archived_total_patterns': len(bundle['payload']['rows']),
              'event_ablation': compare_ranks(baseline, event),
              'calendar_comparison': compare_ranks(rank(before), rank(after)), 'calendar_metric_changes': changes,
              'legacy_recomputed_vs_archive_mismatch_count': mismatched,
              'event_modes': {mode: sum(r.get('event_explanation_mode') == mode for r in rows)
                              for mode in sorted({r.get('event_explanation_mode', 'UNKNOWN') for r in rows})},
              'limitations': ['Archived eligibility pool held fixed; excluded candidates cannot be certified eligible.',
                  'Event ablation recomputes score ordering only, not grade/status eligibility or historical returns.',
                  'Calendar old/new use identical currently stored adjusted prices, not proven original vintages.',
                  'Event source availability, expiry, corporate actions and OOS performance remain unverified.']}
    write_json_atomic(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.root, args.snapshot, args.output)
    print(json.dumps({'candidate_count': result['candidate_count'],
                      'event_rank_moves': len(result['event_ablation']['moved']),
                      'calendar_rank_moves': len(result['calendar_comparison']['moved']),
                      'calendar_metric_changes': len(result['calendar_metric_changes']),
                      'archive_mismatches': result['legacy_recomputed_vs_archive_mismatch_count']}, ensure_ascii=False))
