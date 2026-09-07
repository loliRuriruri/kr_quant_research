"""Recent periodic receipt reconciliation; check is read-only, refresh is explicit."""
import json
from datetime import date, timedelta
import pandas as pd
from kr_quant.settings import load_settings
from kr_quant.ingest.opendart import OpenDartAdapter
from kr_quant.freshness import now_kst


def check(settings=None):
    s = settings or load_settings()
    facts = pd.read_parquet(s.staged_dir / 'live' / 'financial_facts.parquet', columns=['corp_code', 'ticker', 'rcept_no', 'available_date'])
    codes = set(facts.corp_code.astype(str).str.zfill(8))
    receipts = set(facts.rcept_no.dropna().astype(str))
    end = now_kst().date()
    start = end - timedelta(days=14)
    checkpoint = s.staged_dir / 'live' / 'dart_recent_check.json'
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding='utf-8'))
        if previous.get('status') == 'success' and previous.get('to'):
            start = min(start, date.fromisoformat(previous['to']) - timedelta(days=1))
    if (end - start).days > 89:
        raise RuntimeError('DART verification gap exceeds bounded 89-day window; historical reconciliation required')
    adapter = OpenDartAdapter(s.opendart_api_key or '', s.config['ingest']['opendart_base_url'])
    rows = []
    for kind in ['A001', 'A002', 'A003']:
        page = 1
        while True:
            payload = adapter.fetch_list_range(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), page_no=page, pblntf_detail_ty=kind)
            if str(payload.get('status')) == '013':
                break
            if str(payload.get('status')) != '000' or not isinstance(payload.get('list'), list):
                raise RuntimeError('DART list contract invalid')
            rows.extend(payload['list'])
            pages = int(payload.get('total_page') or 0)
            if pages < 1 or pages > 100:
                raise RuntimeError('DART pagination outside bounded audit')
            if page >= pages:
                break
            page += 1
    relevant = [r for r in rows if str(r.get('corp_code')).zfill(8) in codes]
    missing = [r for r in relevant if str(r.get('rcept_no')) not in receipts]
    probes = []
    unmapped = []
    import re
    for item in missing:
        match = re.search(r'\((\d{4})\.(\d{2})\)', item.get('report_nm', ''))
        if not match:
            unmapped.append(str(item.get('rcept_no')))
            continue
        year = match.group(1)
        code = '11011' if '사업보고서' in item['report_nm'] else ('11012' if '반기보고서' in item['report_nm'] else {'03':'11013', '09':'11014'}.get(match.group(2)))
        if code is None:
            unmapped.append(str(item.get('rcept_no')))
            continue
        for fs in ['CFS', 'OFS']:
            response = adapter.fetch_financials(item['corp_code'], year, code, fs)
            status = str(response.get('status'))
            if status not in {'000', '013'} or (status == '000' and not response.get('list')):
                raise RuntimeError('DART financial response invalid or unavailable; reconciliation incomplete')
            returned = sorted({str(r.get('rcept_no')) for r in response.get('list', [])})
            probes.append({'ticker': item.get('stock_code'), 'corp_code': item['corp_code'], 'year': int(year), 'report_code': code, 'fs': fs, 'status': response.get('status'),
                           'requested_receipt': item['rcept_no'], 'returned_receipts': returned,
                           'stored_receipts': sorted(set(facts.loc[facts.corp_code.astype(str).str.zfill(8) == item['corp_code'], 'rcept_no'].astype(str)))})
    return {'checked_at': now_kst().isoformat(), 'from': str(start), 'to': str(end),
            'official_periodic_filings': len(rows), 'stored_company_filings': len(relevant), 'financial_api_probes': probes,
            'unmapped_receipts': unmapped,
            'unmatched_receipts': [{k:r.get(k) for k in ['corp_code', 'corp_name', 'stock_code', 'report_nm', 'rcept_no', 'rcept_dt']} for r in missing],
            'scope': 'recent periodic receipts for stored companies; missing receipt may be superseded or unmapped, requires review'}

def refresh_recent(settings):
    from kr_quant.ingest.live import fetch_dart_financials
    from kr_quant.atomic_io import write_json_atomic
    checkpoint = settings.staged_dir / 'live' / 'dart_recent_check.json'
    previous = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    report = check(settings)
    jobs = {}
    for row in report['financial_api_probes']:
        if set(row['returned_receipts']) - set(row['stored_receipts']):
            jobs[(row['ticker'], row['year'], row['report_code'])] = row
    master = pd.read_parquet(settings.staged_dir / 'live' / 'master.parquet')
    if jobs:
        import shutil
        backup = settings.root / 'data' / 'research_snapshots' / 'financial_revisions'
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.staged_dir / 'live' / 'financial_facts.parquet',
                     backup / (now_kst().strftime('%Y%m%dT%H%M%S%f') + '.parquet'))
        # Persist before mutation so a failed score run cannot hide a revision
        # behind a same-date success ledger on the next invocation.
        write_json_atomic(checkpoint, {**previous, 'needs_recalculation': True})
    refreshed = []
    for (ticker, year, code), row in jobs.items():
        target = master[master.ticker.astype(str) == ticker].to_dict('records')
        if not target:
            raise RuntimeError('Recent filing has no matching master target')
        fetch_dart_financials(settings, target, reports=[(year, code)], force_refresh=True)
        refreshed.append(ticker)
    final = check(settings) if refreshed else report
    pending = [r['ticker'] for r in final['financial_api_probes'] if set(r['returned_receipts']) - set(r['stored_receipts'])]
    result = {'status': 'partial' if pending or final.get('unmapped_receipts') else 'success', 'refreshed_tickers': refreshed,
            'needs_recalculation': bool(jobs) or bool(previous.get('needs_recalculation')),
            'unmapped_receipts': final.get('unmapped_receipts', []),
            'pending_tickers': sorted(set(pending)), 'from': final['from'], 'to': final['to'],
            'scope': 'recent periodic filings for stored companies; not all historical disclosures',
            'official_periodic_filings': final['official_periodic_filings']}
    result['checked_at'] = now_kst().isoformat()
    write_json_atomic(settings.staged_dir / 'live' / 'dart_recent_check.json', result)
    return result


def acknowledge_recalculation(settings):
    from kr_quant.atomic_io import write_json_atomic
    path = settings.staged_dir / 'live' / 'dart_recent_check.json'
    if path.exists():
        state = json.loads(path.read_text(encoding='utf-8'))
        state['needs_recalculation'] = False
        state['recalculated_at'] = now_kst().isoformat()
        write_json_atomic(path, state)
