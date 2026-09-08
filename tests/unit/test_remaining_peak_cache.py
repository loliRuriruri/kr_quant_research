from types import SimpleNamespace
import pandas as pd
from kr_quant.strategy import seasonality as module


def test_disk_peak_cache_survives_restart_and_invalidates_sources(tmp_path, monkeypatch):
    # Other endpoint tests can still have background snapshot builders running.
    # Isolate module globals so this cache test never patches their calculator.
    import importlib.util
    import sys
    original_module = module
    spec = importlib.util.spec_from_file_location('kr_quant.strategy._peak_cache_under_test', original_module.__file__)
    isolated_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, isolated_module)
    spec.loader.exec_module(isolated_module)
    monkeypatch.setattr(sys.modules[__name__], 'module', isolated_module)
    s = SimpleNamespace(root=tmp_path, staged_dir=tmp_path/'data/staged', output_dir=tmp_path/'data/output',
                        status_csv=tmp_path/'data/raw/status/krx_status.csv')
    price = s.staged_dir/'live/prices.parquet'
    price.parent.mkdir(parents=True)
    price.write_bytes(b'input signature only')
    calls = []
    monkeypatch.setattr(module, '_REMAINING_PEAK_CACHE', {'signature': None, 'values': {}})
    monkeypatch.setattr(module, '_prices', lambda *a, **kw: pd.DataFrame({'ticker': ['005930'], 'close': [100]}))

    def calc(*args, **kwargs):
        calls.append(1)
        return {'available': False, 'status': 'INSUFFICIENT_SAMPLE', 'sample_count': 1}

    monkeypatch.setattr(module, 'calculate_remaining_peak_upside', calc)
    rows = [{'ticker': '005930', 'window_name': '9월'}]
    first = module._enrich_remaining_peak_rows(s, rows, lookback_years=5)
    assert len(calls) == 1
    module._REMAINING_PEAK_CACHE.update(signature=None, values={})
    assert module._enrich_remaining_peak_rows(s, rows, lookback_years=5) == first
    assert len(calls) == 1
    action = s.staged_dir/'live/corporate_actions.parquet'
    action.write_bytes(b'new official adjustment')
    module._enrich_remaining_peak_rows(s, rows, lookback_years=5)
    assert len(calls) == 2
    module._enrich_remaining_peak_rows(s, rows, lookback_years=3)
    assert len(calls) == 3
    cache = tmp_path/'data/cache/remaining_peak_metrics_v1.json'
    cache.write_text('broken cache', encoding='utf-8')
    module._REMAINING_PEAK_CACHE.update(signature=None, values={})
    module._enrich_remaining_peak_rows(s, rows, lookback_years=5)
    assert len(calls) == 4
    import json
    stored = json.loads(cache.read_text(encoding='utf-8'))
    assert stored['signature'][0] == 2
    stored['signature'][0] = 1  # Legacy cache had 0 -> one-year semantics.
    cache.write_text(json.dumps(stored), encoding='utf-8')
    module._REMAINING_PEAK_CACHE.update(signature=None, values={})
    module._enrich_remaining_peak_rows(s, rows, lookback_years=5)
    assert len(calls) == 5
    s.status_csv.parent.mkdir(parents=True)
    s.status_csv.write_text('ticker,as_of_date,status\n005930,2026-09-07,SUSPENDED\n', encoding='utf-8')
    module._enrich_remaining_peak_rows(s, rows, lookback_years=5)
    assert len(calls) == 6  # A changed trading status must invalidate cached upside.
