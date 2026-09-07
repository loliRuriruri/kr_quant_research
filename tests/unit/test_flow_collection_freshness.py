from dataclasses import replace
from datetime import date
from kr_quant.settings import load_settings
from kr_quant.flow import official


def test_empty_provider_response_is_not_success(tmp_path, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    class Adapter:
        def __init__(self, *args): pass
        def configured(self): return True
        def token(self, **kwargs): return 'test-only'
        def collect_stock(self, ticker): return []
    monkeypatch.setattr(official, 'KisInvestorAdapter', Adapter)
    monkeypatch.setattr(official, 'collect_universe', lambda *a, **k: [{'ticker':'005930'}])
    monkeypatch.setattr(official.time, 'sleep', lambda _: None)
    result = official.collect_official(settings)
    assert result['pipeline_status'] == 'partial'
    assert result['stale_tickers'] == ['005930']
    assert result['saved'] == 0


def test_changed_collection_universe_requires_refresh(tmp_path, monkeypatch):
    from kr_quant.flow.store import open_settings, upsert_flows
    import kr_quant.freshness as freshness
    settings = replace(load_settings(), root=tmp_path)
    monkeypatch.setattr(freshness, 'expected_price_date', lambda: date(2026,9,7))
    monkeypatch.setattr(official, 'collect_universe', lambda s: [{'ticker':'005930'}, {'ticker':'000660'}])
    con = open_settings(settings)
    upsert_flows(con, [{'ticker':'005930', 'trade_date':date(2026,9,7), 'investor_type':'FOREIGN'},
                       {'ticker':'000660', 'trade_date':date(2026,9,4), 'investor_type':'FOREIGN'}])
    con.close()
    assert official.collection_is_current(settings) is False


def test_premarket_row_does_not_hide_previous_session_or_become_final(tmp_path, monkeypatch):
    import kr_quant.freshness as freshness
    import duckdb
    settings = replace(load_settings(), root=tmp_path)
    monkeypatch.setattr(freshness, 'expected_price_date', lambda: date(2026,9,7))
    class Adapter:
        def __init__(self, *args): pass
        def configured(self): return True
        def token(self, **kwargs): return 'test-only'
        def collect_stock(self, ticker):
            return [{'ticker':ticker, 'trade_date':day, 'investor_type':'FOREIGN', 'is_final':True} for day in ['2026-09-07','2026-09-08']]
    monkeypatch.setattr(official, 'KisInvestorAdapter', Adapter)
    monkeypatch.setattr(official, 'collect_universe', lambda *a, **k: [{'ticker':'005930'}])
    monkeypatch.setattr(official.time, 'sleep', lambda _: None)
    result = official.collect_official(settings)
    assert result['pipeline_status'] == 'success'
    assert official.collection_is_current(settings)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        assert con.execute('SELECT is_final FROM investor_flows_daily ORDER BY trade_date').fetchall() == [(True,), (False,)]
