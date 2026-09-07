"""Read-only source audit; never prints keys or calls token issuance endpoints."""
import json
from datetime import date
import duckdb
import pandas as pd
from kr_quant.settings import load_settings
from kr_quant.freshness import freshness_snapshot, now_kst
from kr_quant.ingest.krx import KrxOpenApiAdapter


def audit(probe=False):
    s = load_settings()
    snapshot = freshness_snapshot(s)
    result = {'checked_at': now_kst().isoformat(), 'freshness': snapshot}
    live = s.staged_dir / 'live'
    facts = pd.read_parquet(live / 'financial_facts.parquet')
    result['financial_columns'] = list(facts.columns)
    result['financial_rows'] = len(facts)
    price = pd.read_parquet(live / 'prices.parquet', columns=['ticker', 'trade_date', 'market'])
    latest = pd.to_datetime(price.trade_date).max()
    result['latest_price_partition'] = price[pd.to_datetime(price.trade_date) == latest].groupby('market').size().to_dict()
    result['duplicate_price_keys'] = int(price.duplicated(['ticker', 'trade_date']).sum())
    latest_periods = pd.to_datetime(facts.period_end, errors='coerce').groupby(facts.ticker).max()
    result['financial_latest_period_counts'] = {str(k.date()): int(v) for k, v in latest_periods.value_counts().items()}
    for col in ['available_date', 'period_end']:
        if col in facts:
            dates = pd.to_datetime(facts[col], errors='coerce')
            result[col] = {'min': str(dates.min()), 'max': str(dates.max()), 'missing': int(dates.isna().sum())}
    if s.db_path.exists():
        try:
            with duckdb.connect(str(s.db_path), read_only=True) as con:
                result['official_flow'] = con.execute('SELECT source, max(trade_date)::VARCHAR, count(*), count(DISTINCT ticker), max(fetched_at)::VARCHAR FROM investor_flows_daily GROUP BY source').fetchall()
                result['official_flow_latest_by_ticker'] = con.execute('SELECT latest::VARCHAR, count(*) FROM (SELECT ticker, max(trade_date) latest FROM investor_flows_daily GROUP BY ticker) GROUP BY latest ORDER BY latest DESC').fetchall()
        except Exception as exc:
            result['flow_access_error'] = type(exc).__name__
    if probe:
        adapter = KrxOpenApiAdapter(s.krx_api_key or '', s.config['ingest']['krx_base_url'], timeout=15)
        result['krx_probe'] = []
        for day in sorted(set([snapshot['expected_price_date'], snapshot['price_max_date']])):
            for market in ['KOSPI', 'KOSDAQ']:
                try:
                    rows = adapter.fetch_daily_maybe(date.fromisoformat(day), market)
                    result['krx_probe'].append({'date': day, 'market': market, 'rows': len(rows), 'result': 'validated_response'})
                except Exception as exc:
                    result['krx_probe'].append({'date': day, 'market': market, 'error_type': type(exc).__name__})
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    result = audit(args.probe)
    if args.output:
        from pathlib import Path
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('x', encoding='utf-8') as out:
            json.dump(result, out, ensure_ascii=False, default=str, indent=2)
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
