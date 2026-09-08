"""Reproduce residual flow risks using synthetic inputs; read production DB only.

Does not collect, patch source data, run a scheduler, or claim risks are fixed.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import duckdb
import pandas as pd

from kr_quant.flow.events import from_official_rows
from kr_quant.flow.investor import summarize_records
from kr_quant.flow.reliability import gate_official_rows, gate_toss_payload
from kr_quant.research.selection_ledger import write_once


def audit(root):
    expected = '2026-09-07'
    with TemporaryDirectory(prefix='kr-quant-flow-audit-') as temporary:
        status = Path(temporary) / 'status.csv'
        pd.DataFrame([dict(ticker='005930', as_of_date=expected, status='ACTIVE',
                           krx_risk_class='', close=100, volume=10)]).to_csv(status, index=False)
        settings = SimpleNamespace(status_csv=status)
        missing = [dict(ticker='005930', trade_date=expected, investor_type=kind, is_final=True)
                   for kind in ('FOREIGN', 'INSTITUTION_TOTAL')]
        accepted = gate_official_rows(missing, settings, expected)
        raw = [dict(date=expected, institution={'netBuyVolume': 100})]
        normalized = dict(ticker='005930', **summarize_records(raw, days=1))
        toss = gate_toss_payload(dict(rows=[normalized], days=1), settings, expected)
        mixed = [dict(ticker='005930', trade_date=day, investor_type=kind, is_final=True,
                      net_value=value, net_qty=qty)
                 for day, value, qty in [(expected, 1000000, 10), ('2026-09-04', None, 10)]
                 for kind in ('FOREIGN', 'INSTITUTION_TOTAL')]
        events = from_official_rows(gate_official_rows(mixed, settings, expected))
        result = {'observed_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Synthetic failure-mode reproduction; not evidence of live affected trades',
                  'probes': {
                      'official_missing_numeric_rows_accepted': len(accepted),
                      'toss_missing_foreign_coerced_to_zero': normalized['daily'][0]['foreign'] == 0,
                      'toss_missing_foreign_candidate_accepted': len(toss['rows']) == 1,
                      'mixed_value_quantity_cumulative': events['consecutive'][0]['cumulative'] if events['consecutive'] else None,
                      'mixed_unit_candidates': events['tickers'],
                  }}
    database = root / 'db/screener.duckdb'
    if database.exists():
        try:
            with duckdb.connect(str(database), read_only=True) as connection:
                rows = connection.execute('''SELECT count(*) AS rows,
                    count(*) FILTER (WHERE net_value IS NULL AND net_qty IS NULL) AS both_missing,
                    count(*) FILTER (WHERE net_value IS NOT NULL) AS with_value,
                    count(*) FILTER (WHERE net_value IS NULL AND net_qty IS NOT NULL) AS quantity_fallback
                    FROM investor_flows_daily''').fetchone()
                result['stored_official'] = dict(zip(('rows', 'both_missing', 'with_value', 'quantity_fallback'), rows))
                result['mixed_series_count'] = connection.execute('''SELECT count(*) FROM (
                    SELECT ticker, investor_type FROM investor_flows_daily WHERE is_final = true
                    GROUP BY ticker, investor_type HAVING
                    count(*) FILTER (WHERE net_value IS NOT NULL) > 0 AND
                    count(*) FILTER (WHERE net_value IS NULL AND net_qty IS NOT NULL) > 0
                )''').fetchone()[0]
        except duckdb.Error as exc:
            result['stored_official'] = {'status': 'UNAVAILABLE', 'error_type': type(exc).__name__}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; select a new evidence file')
    output = write_once(args.output, audit(args.root.resolve()))
    print(json.dumps(output, ensure_ascii=False))
