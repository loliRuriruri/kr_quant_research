"""Read-only menu/source/publication audit; never starts jobs or publishes.

Use --probe-source for three bounded official KRX GETs (control + expected date).
Only non-secret counts/dates/statuses are saved. Existing source data is untouched.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fastapi.testclient import TestClient
from kr_quant.atomic_io import write_json_atomic
from kr_quant.freshness import KST, freshness_snapshot
from kr_quant.settings import load_settings
from kr_quant.web.app import app
from kr_quant.web.publish import publication_readiness


def run(probe_source=False):
    settings = load_settings(ROOT)
    fresh = freshness_snapshot(settings)
    out = {'checked_at': datetime.now(KST).isoformat(), 'checks': {},
           'freshness': {k: fresh.get(k) for k in ('expected_price_date', 'price_max_date', 'screen_as_of', 'stale_price', 'stale_screen')}}
    # Importing the ASGI app, unlike the normal launcher, does not start scheduler.
    client = TestClient(app)
    def get(path):
        res = client.get(path)
        res.raise_for_status()
        return res.json()
    high = get('/api/seasonality/highlights')
    pre = get('/api/seasonality/pre-entry?compact=true')
    themes = get('/api/seasonality/themes')
    # Default UI applies the canonical backend rank, not raw transport order.
    stages = {'TODAY_ENTRY', 'PRE_ENTRY_15', 'PRE_ENTRY_30', 'ACCUMULATE_60'}
    rows = sorted((row for row in pre['rows'] if row.get('entry_stage') in stages
                   and row.get('pre_entry_rank') is not None), key=lambda row: int(row['pre_entry_rank']))
    picks = high['data']['glance_top3']
    generation = pre['snapshot']['generation_id']
    checks = out['checks']
    import pandas as pd
    statuses = pd.read_csv(settings.status_csv, dtype={'ticker': str})
    statuses = statuses[statuses['as_of_date'].astype(str) == fresh['expected_price_date']]
    active = set(statuses.loc[
        (statuses['status'] == 'ACTIVE')
        & (pd.to_numeric(statuses['close'], errors='coerce') > 0)
        & (pd.to_numeric(statuses['volume'], errors='coerce') > 0), 'ticker'])
    invalid = sorted({str(row['ticker']) for row in rows} - active)
    checks['preentry_current_active_positive_price_volume'] = bool(rows) and not invalid
    out['candidate_status_audit'] = {'checked': len(rows), 'invalid_tickers': invalid,
                                     'as_of': fresh['expected_price_date']}
    checks['same_generation_highlights_preentry_themes'] = all(
        value['snapshot']['generation_id'] == generation for value in (high, themes))
    checks['dashboard_top3_equals_calendar_top3'] = (
        [row['signal_id'] for row in picks] == [row['signal_id'] for row in rows[:3]])
    fields = ('ticker', 'price_as_of', 'entry_stage', 'entry_window_str', 'exit_window_str', 'last_close')
    checks['dashboard_top3_card_facts_equal'] = all(
        all(pick.get(k) == row.get(k) for k in fields) for pick, row in zip(picks, rows))
    checks['preentry_signal_ids_unique'] = len({r['signal_id'] for r in rows}) == len(rows)
    inspected = []
    for row in rows[:10]:
        detail = get(f"/api/seasonality/discovery/{row['ticker']}?generation_id={generation}")
        match = [r for r in detail['patterns'] if r['signal_id'] == row['signal_id']]
        inspected.append(len(match) == 1 and all(match[0].get(k) == row.get(k) for k in fields))
    checks['top10_detail_same_signal_facts'] = bool(inspected) and all(inspected)
    checks['old_generation_rejected'] = client.get(
        f"/api/seasonality/discovery/{rows[0]['ticker']}?generation_id=invalid").status_code == 409 if rows else None
    out['season'] = {'generation': generation, 'selection_date': pre['snapshot']['selection_date'],
                     'count': len(rows), 'top3': [r['ticker'] for r in picks],
                     'price_dates': sorted({str(r.get('price_as_of')) for r in rows}),
                     'detail_checked': len(inspected)}
    flow = get('/api/flow?days=5')
    events = get('/api/investor/events')
    from kr_quant.flow.reliability import FLOW_LISTS
    flow_rows = [r for key in FLOW_LISTS for r in flow.get(key, [])]
    checks['all_flow_categories_current_active'] = all(
        r.get('to') == fresh['expected_price_date'] and r['ticker'] in active for r in flow_rows)
    checks['flow_exclusion_counts_reconcile'] = (
        flow['reliability']['source_rows'] == flow['reliability']['current_rows'] + flow['reliability']['excluded_rows'])
    from kr_quant.screens import _flow_tickers
    from kr_quant.strategy.seasonality import _load_flow_confirmation_map
    checks['screen_and_calendar_use_same_current_flow'] = (
        _flow_tickers(settings, 'dual') == {r['ticker'] for r in flow.get('dual', [])}
        and set(_load_flow_confirmation_map(settings)) == {r['ticker'] for r in flow.get('rows', [])})
    official = events.get('official') or {}
    official_rows = [r for key in ('consecutive', 'paired', 'turns', 'cum5', 'cum20', 'cum60')
                     for r in official.get(key, [])]
    checks['official_event_candidates_current_active'] = all(r['ticker'] in active for r in official_rows)
    out['flow'] = {'toss': flow['reliability'], 'official': events['reliability'],
                   'note': 'An empty current Toss candidate set is valid when saved sources are stale; positive paths covered by fixtures.'}
    ready = publication_readiness(ROOT)
    out['publication'] = {k: ready.get(k) for k in ('ready', 'errors', 'price_max_date', 'as_of_date', 'expected_price_date', 'eligible_rows')}
    if probe_source:
        from kr_quant.ingest.krx import KrxOpenApiAdapter
        adapter = KrxOpenApiAdapter(settings.krx_api_key, settings.config['ingest']['krx_base_url'], timeout=10)
        probes = [(fresh['price_max_date'], 'KOSPI'), (fresh['expected_price_date'], 'KOSPI'), (fresh['expected_price_date'], 'KOSDAQ')]
        out['source_probes'] = []
        for day, market in probes:
            try:
                source_rows = adapter.fetch_daily_maybe(date.fromisoformat(day), market)
                out['source_probes'].append({'date': day, 'market': market, 'rows': len(source_rows),
                    'returned_days': sorted({r.get('BAS_DD') or r.get('basDd') for r in source_rows})})
            except Exception as exc:
                out['source_probes'].append({'date': day, 'market': market, 'error_type': type(exc).__name__})
    write_json_atomic(ROOT / 'output/item2-integration-audit.json', out)
    print(json.dumps(out, ensure_ascii=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe-source', action='store_true')
    run(parser.parse_args().probe_source)
