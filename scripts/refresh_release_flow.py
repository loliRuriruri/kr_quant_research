"""Bounded provider probe; --refresh scans only after current source is verified.

Preserves the previous cache, never logs credentials or response bodies, and
never publishes. A missing provider partition is not successful refresh.
"""
import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from kr_quant.atomic_io import write_json_atomic
from kr_quant.flow.investor import summarize_records
from kr_quant.flow.reliability import day
from kr_quant.freshness import expected_price_date
from kr_quant.ingest.tossinvest import get_investor_trading
from kr_quant.settings import load_settings


def run(refresh=False):
    settings = load_settings()
    expected = expected_price_date().isoformat()
    result = {'observed_at': datetime.now(timezone.utc).isoformat(),
              'expected_date': expected, 'published': False, 'status': 'BLOCKED'}
    try:
        if not settings.toss_client_id or not settings.toss_client_secret:
            raise RuntimeError('PROVIDER_NOT_CONFIGURED')
        payload = get_investor_trading(settings.toss_client_id, settings.toss_client_secret, '005930')
        records = [r for r in payload.get('records', []) if isinstance(r, dict)
                   and day(r.get('date')) and day(r['date']) <= expected and r.get('is_final') is not False]
        records.sort(key=lambda r: day(r['date']), reverse=True)
        summary = summarize_records(records, days=5)
        result.update(probe_rows=len(records), probe_to=summary.get('to'),
                      source_complete=summary.get('source_complete'))
        if day(summary.get('to')) != expected or summary.get('days', 0) < 5 or not summary.get('source_complete'):
            result['reason'] = 'CURRENT_COMPLETE_SOURCE_UNAVAILABLE'
            return result
        result['status'] = 'PROBE_READY'
        if refresh:
            from kr_quant.flow.scan import scan_flow, cache_path
            old = cache_path(settings.root)
            if old.exists():
                backup = settings.data_dir / 'research_snapshots' / 'release_backups' / (
                    datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '-investor_flow.json')
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, backup)
                result['backup'] = str(backup.relative_to(settings.root))
            scanned = scan_flow(settings, days=5, force=True)
            result.update(reliability=scanned.get('reliability'), scan_errors=scanned.get('errors'),
                          status='SUCCESS' if scanned.get('reliability', {}).get('current_rows', 0) > 0
                          and not scanned.get('errors') else 'PARTIAL')
    except Exception as exc:
        result.update(status='BLOCKED', error_type=type(exc).__name__,
                      http_codes=re.findall(r'HTTP [0-9]{3}', str(exc)))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output path to preserve prior evidence')
    result = run(args.refresh)
    write_json_atomic(args.output, result)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result['status'] in ('SUCCESS', 'PROBE_READY') else 2)
