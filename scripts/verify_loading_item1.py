"""Read-only local equivalence and HTTP measurements. No collection or publishing."""
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import httpx
import pandas as pd
from kr_quant.atomic_io import write_json_atomic
from kr_quant.context.market import derive_market_components
from kr_quant.settings import load_settings


def run():
    result = {'baseline_commit': '3d9b3ef', 'network': [], 'checks': {}}
    s = load_settings()
    path = s.staged_dir / 'live/prices.parquet'
    prices = pd.read_parquet(path, columns=['ticker', 'trade_date', 'close', 'trading_value'])
    old = {'__name__': 'prior_market'}
    source = subprocess.check_output(['git', 'show', '3d9b3ef:src/kr_quant/context/market.py'], cwd=ROOT).decode()
    exec(compile(source, '<baseline_market>', 'exec'), old)
    start = time.perf_counter()
    baseline = old['derive_market_components'](prices)
    result['market_baseline_seconds'] = round(time.perf_counter() - start, 3)
    start = time.perf_counter()
    current = derive_market_components(prices)
    result['market_current_seconds'] = round(time.perf_counter() - start, 3)
    assert baseline == current, 'Market calculation changed'
    result['checks']['full_history_market_exact_equal'] = True
    result['price_rows'] = len(prices)
    del prices
    with httpx.Client(base_url='http://127.0.0.1:8790', timeout=30) as client:
        paths = ['/api/results/top?n=30', '/api/flow?days=5&compact=true', '/api/watchlist',
                 '/api/market', '/api/sectors', '/api/screens', '/api/strategy',
                 '/api/seasonality/highlights', '/api/seasonality/themes',
                 '/api/seasonality/pre-entry?compact=true', '/api/seasonality/discovery?view=summary']
        for route in paths:
            for attempt in range(3):
                start = time.perf_counter()
                response = client.get(route)
                result['network'].append({'path': route, 'attempt': attempt + 1,
                    'ms': round((time.perf_counter() - start) * 1000), 'status': response.status_code,
                    'decoded_bytes': len(response.content), 'wire_bytes': response.headers.get('content-length'),
                    'encoding': response.headers.get('content-encoding')})
                assert response.status_code == 200, route
        full = client.get('/api/flow?days=5').json()
        packed = client.get('/api/flow?days=5&compact=true').json()
        table = packed.pop('_row_transport')
        for key, refs in table['groups'].items():
            packed[key] = [copy.deepcopy(table['pool'][i]) for i in refs]
        assert packed == full, 'Flow transport lost data'
        result['checks']['actual_flow_transport_exact_equal'] = True
        from kr_quant.web.season_listing import pre_entry_card
        full = client.get('/api/seasonality/pre-entry').json()
        compact = client.get('/api/seasonality/pre-entry?compact=true').json()
        assert [r['signal_id'] for r in full['rows']] == [r['signal_id'] for r in compact['rows']]
        assert [pre_entry_card(r, 5) for r in full['rows']] == compact['rows']
        result['checks']['pre_entry_cards_exact_projection_and_order'] = True
    write_json_atomic(ROOT / 'output/item1-verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    run()
