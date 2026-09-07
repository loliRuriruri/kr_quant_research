import copy
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from kr_quant.web import quotes, season_snapshot
from kr_quant.web.transport import pack_rows


def test_transport_preserves_different_versions_and_order():
    a = {'ticker': '005930', 'daily': [{'price': 123}], 'value': 1}
    b = {**a, 'value': 2}
    data = {'rows': [a, b], 'dual': [a, a], 'empty': [], 'nested': {'count': 2}}
    saved = copy.deepcopy(data)
    packed = pack_rows(data)
    t = packed.pop('_row_transport')
    assert len(t['pool']) == 2
    for key, refs in t['groups'].items():
        packed[key] = [copy.deepcopy(t['pool'][i]) for i in refs]
    assert packed == saved == data
    packed['dual'][0]['daily'].clear()
    assert packed['dual'][1]['daily']


@pytest.mark.parametrize('raw', ['', '../bad', '005930/abc', '12345', ',005930', ','.join(f'{i:06}' for i in range(51))])
def test_quote_input_bounded(raw):
    with pytest.raises(ValueError):
        quotes.parse_codes(raw)


def test_quote_canonical_batch():
    assert quotes.parse_codes('005930,000660,005930') == ('000660', '005930')


def quote(**changes):
    return {'itemCode': '005930', 'closePriceRaw': '100',
            'localTradedAt': '2026-09-07T15:30:00+09:00', 'marketStatus': 'CLOSE', **changes}


def test_quote_dates_and_unknowns():
    now = datetime.fromisoformat('2026-09-08T10:00:00+09:00')
    assert quotes.normalize_quote(quote(), now)['kind'] == 'close'
    assert quotes.normalize_quote(quote(localTradedAt='2026-09-04T15:30:00+09:00'), now)['kind'] == 'stale'
    assert quotes.normalize_quote(quote(localTradedAt='2026-09-08T09:59:30+09:00', marketStatus='OPEN'), now)['kind'] == 'intraday'
    assert quotes.normalize_quote(quote(localTradedAt='2026-09-08T09:00:00+09:00', marketStatus='OPEN'), now)['kind'] == 'stale'
    for change in [{'closePriceRaw': 'NaN'}, {'closePriceRaw': '0'}, {'localTradedAt': '2026-09-08'},
                   {'localTradedAt': '2026-09-09T10:00:00+09:00'}]:
        assert quotes.normalize_quote(quote(**change), now) is None


def test_partial_quotes_never_invent_prices(monkeypatch):
    monkeypatch.setattr(quotes, 'fetch_quotes', lambda codes: {'items': [quote()], 'fetched_at': 'time'})
    data = quotes.quote_payload('005930,000660')
    assert data['missing'] == ['000660'] and len(data['rows']) == 1
    assert data['used_in_quant'] is False
    assert data['rows'][0]['realtime_verified'] is False


@pytest.mark.parametrize('part', ['themes', 'highlights', 'pre-entry'])
def test_season_parts_skip_irrelevant_detail(part):
    class Forbidden:
        def __deepcopy__(self, memo):
            raise AssertionError('unused row copied')
    bundle = {'identity': {}, 'generation_id': 'g', 'generated_at': 't',
              'payload': {'stats': {}, 'rows': [{'pre_entry_rank': None, 'heavy': Forbidden()},
                                             {'pre_entry_rank': 1, 'ticker': '005930'}],
                          'themes': [{'name': 'theme'}], 'highlights': {'rows': []}}}
    result = season_snapshot._copy_bundle(bundle, part)
    if part == 'pre-entry':
        assert len(result['payload']['rows']) == 1
    else:
        assert 'rows' not in result['payload']
    result['identity']['new'] = True
    assert bundle['identity'] == {}


def test_public_split_is_lossless_and_idempotent(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from optimize_public_data import optimize
    data = {'ok': True, 'lookback_years': 5, 'horizon_days': 365, 'snapshot': {'generation_id': 'g'},
            'rows': [{'ticker': '005930', 'signal_id': 's', 'generation_id': 'g', 'window_name': '9월', 'grade': 'S',
                      'remaining_peak': {'samples': list(range(300))}}]}
    (tmp_path / 'manifest.json').write_text(json.dumps({'routes': {'/api/seasonality/discovery': 'season.json'}}))
    (tmp_path / 'season.json').write_text(json.dumps(data))
    optimize(tmp_path)
    index = json.loads((tmp_path / 'season.json').read_text(encoding='utf-8'))
    detail = json.loads((tmp_path / 'season-details/005930.json').read_text(encoding='utf-8'))
    assert detail['patterns'] == data['rows']
    assert detail['snapshot'] == data['snapshot']
    chunk = json.loads((tmp_path / 'season-list/0.json').read_text(encoding='utf-8'))
    assert chunk['rows'][0]['detail_required'] is True
    assert 'remaining_peak' not in chunk['rows'][0]
    assert index['rows'][0]['_chunk'] == 0
    assert optimize(tmp_path) == {}


def test_watchlist_reads_only_its_tickers(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import pandas as pd
    from kr_quant.layers import context
    from kr_quant.strategy import run
    s = SimpleNamespace(root=tmp_path, output_dir=tmp_path, staged_dir=tmp_path)
    monkeypatch.setattr(context, 'load_watchlist', lambda _: [{'ticker': '005930'}])
    def prices(settings, *, tickers):
        assert tickers == ['005930']
        return pd.DataFrame([{'ticker': '005930', 'trade_date': '2026-09-07', 'close': 100}])
    monkeypatch.setattr(run, '_prices', prices)
    result = context.watchlist_state(s)
    assert result['rows'][0]['close_price'] == 100
    assert result['rows'][0]['price_as_of'] == '2026-09-07'


def test_market_component_cache_isolated_and_versioned(monkeypatch, tmp_path):
    import pandas as pd
    from kr_quant.layers import context
    from kr_quant.context import market_sentiment
    from kr_quant.web.cache import invalidate_cache
    path = tmp_path / 'prices.parquet'
    pd.DataFrame([{'ticker': '005930', 'trade_date': '2026-09-07', 'close': 100}]).to_parquet(path)
    calls = []
    monkeypatch.setattr(context, 'derive_market_components', lambda p: calls.append(len(p)) or {'score': 1})
    monkeypatch.setattr(market_sentiment, 'compute_kr_market_sentiment', lambda _: {})
    invalidate_cache('_market_price_components')
    a = context._market_price_components(str(path), 1, 10)
    a['components']['score'] = 999
    assert context._market_price_components(str(path), 1, 10)['components']['score'] == 1
    context._market_price_components(str(path), 2, 10)
    assert calls == [1, 1]


def test_flow_get_never_calls_external_quote_batches(monkeypatch):
    from kr_quant.flow import scan
    from types import SimpleNamespace
    data = {'days': 5, 'flow_schema': scan.FLOW_SCHEMA, 'empty': [], 'rows': [{'ticker': '005930', 'last': 100}]}
    monkeypatch.setattr(scan, '_load_cache', lambda _: copy.deepcopy(data))
    monkeypatch.setattr(scan, 'attach_company_names', lambda p, s: p)
    monkeypatch.setattr(scan, 'attach_technicals', lambda p, s: p)
    monkeypatch.setattr(scan, '_with_comments', lambda p: p)
    def forbidden(*args):
        raise AssertionError('external quotes on GET')
    monkeypatch.setattr(scan, 'attach_live_quotes', forbidden)
    result = scan.load_flow(SimpleNamespace(root=Path('.')))
    assert result['rows'][0]['last'] == 100 and result['quotes_live'] is False


def test_legacy_public_without_selection_ids_is_not_faked(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from optimize_public_data import optimize
    data = {'ok': True, 'rows': [{'ticker': '005930', 'playbook': {'old': True}}]}
    (tmp_path / 'manifest.json').write_text(json.dumps({'routes': {'/api/seasonality/discovery': 'season.json'}}))
    original = json.dumps(data)
    (tmp_path / 'season.json').write_text(original)
    optimize(tmp_path)
    assert (tmp_path / 'season.json').read_text() == original
    assert 'season_details' not in json.loads((tmp_path / 'manifest.json').read_text())


def test_market_first_paint_uses_no_external_sources_or_partial_cache(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import pandas as pd
    from kr_quant.layers import context
    from kr_quant import freshness
    from kr_quant.ingest import ecos, fear_greed, fred
    from kr_quant.context.market import derive_market_components
    dates = pd.date_range('2025-01-01', periods=90)
    frame = pd.DataFrame({'ticker': ['005930'] * 90, 'trade_date': dates, 'close': range(100, 190)})
    monkeypatch.setattr(context, 'market_price_components', lambda _: {'components': derive_market_components(frame), 'sentiment': {}})
    monkeypatch.setattr(freshness, 'freshness_snapshot', lambda _: {})
    def forbidden(*args, **kwargs):
        raise AssertionError('external source or recording partial market result')
    monkeypatch.setattr(ecos, 'ecos_snapshot', forbidden)
    monkeypatch.setattr(fear_greed, 'fear_greed_snapshot', forbidden)
    monkeypatch.setattr(fred, 'macro_snapshot', forbidden)
    monkeypatch.setattr(context, '_store_market_cache', forbidden)
    s = SimpleNamespace(root=tmp_path, bok_ecos_api_key='not-used', fred_api_key='not-used')
    result = context.build_market_snapshot(s, local_only=True)
    assert result['partial'] is True
    assert result['label'].startswith('KRX 부분 계산')
    assert result['macro']['configured'] is False


def test_frontend_stale_chip_and_asof_ownership():
    import re
    import shutil
    import subprocess
    if not shutil.which('node'):
        pytest.skip('Node is required for frontend helper regression')
    source = (Path(__file__).resolve().parents[2] / 'src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    chip = re.search(r'function renderFreshChip\(fresh\) \{.*?\n\}', source, re.S).group()
    asof = re.search(r'function setPageAsOf\(text, tip, owner = currentView\) \{.*?\n\}', source, re.S).group()
    script = '''
const assert = require('node:assert/strict');
const el = {textContent:'', setAttribute(){}, classList:{toggle(){}, add(){}}};
const $ = () => el;
let currentView = 'rank', label = '', tip = '';
const pageAsOfByView = {};
const setChip = (el, l, t) => { label = l; tip = t; };
const applyPriceChrome = () => {};
let session = {isPreMarket:true,todayStr:'2026-09-08'};
const getMarketSessionInfo = () => session;
''' + chip + '\n' + asof + '''
renderFreshChip({price_max_date:'2026-09-04',expected_price_date:'2026-09-07',stale_price:true});
assert(label.includes('갱신 필요')); assert(!label.includes('전일'));
session = {isMarketOpen:true,todayStr:'2026-09-08'};
renderFreshChip({price_max_date:'2026-09-07',status:'fresh'});
assert(!label.includes('실시간')); assert(!tip.includes('실시간 틱으로'));
setPageAsOf('rank-date','rank-tip');
setPageAsOf('13F-date','13F-tip','us13f');
assert.equal(el.textContent,'rank-date');
assert.equal(pageAsOfByView.us13f.text,'13F-date');
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_market_disk_cache_restart_invalidation_and_corruption(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from kr_quant.layers import context
    s = SimpleNamespace(root=tmp_path, staged_dir=tmp_path / 'data/staged')
    path = s.staged_dir / 'live/prices.parquet'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'price-v1')
    calls = []
    monkeypatch.setattr(context, '_market_price_components', lambda *args: calls.append(1) or {'components': {'x': 1}, 'sentiment': {}})
    first = context.market_price_components(s)
    first['components']['x'] = 999
    assert context.market_price_components(s)['components']['x'] == 1
    assert len(calls) == 1
    cache = next((tmp_path / 'data/cache/market-components').glob('*.json'))
    cache.write_text('{corrupt')
    context.market_price_components(s)
    assert len(calls) == 2
    path.write_bytes(b'price-v2-changed')
    context.market_price_components(s)
    assert len(calls) == 3
