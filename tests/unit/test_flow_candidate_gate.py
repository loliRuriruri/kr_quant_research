import copy
import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from kr_quant.settings import load_settings
from kr_quant.flow import reliability as gate


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = replace(load_settings(), root=tmp_path)
    s.status_csv.parent.mkdir(parents=True)
    pd.DataFrame([dict(ticker=code, as_of_date='2026-09-07', status=status,
                       krx_risk_class='', close=100, volume=10)
                  for code, status in [('005930', 'ACTIVE'), ('000660', 'SUSPENDED')]]).to_csv(s.status_csv, index=False)
    monkeypatch.setattr(gate, 'expected_price_date', lambda: date(2026, 9, 7))
    return s


def row():
    return dict(ticker='005930', to='2026-09-07', daily=[
        dict(date='2026-09-07', foreign=1, institution=2)], foreign_net=1, institution_net=2)


@pytest.mark.parametrize('change', ['old', 'future', 'halted', 'unknown', 'no_daily',
                                  'duplicate', 'short_window', 'nan', 'provisional'])
def test_every_candidate_list_is_gated_without_mutating_history(settings, change):
    bad = row()
    window = 1
    if change == 'old': bad['to'] = '2026-09-04'
    if change == 'future': bad['daily'][0]['date'] = '2026-09-08'
    if change == 'halted': bad['ticker'] = '000660'
    if change == 'unknown': bad['ticker'] = '123456'
    if change == 'no_daily': bad['daily'] = []
    if change == 'duplicate': bad['daily'] *= 2
    if change == 'short_window': window = 5
    if change == 'nan': bad['daily'][0]['foreign'] = float('inf')
    if change == 'provisional': bad['daily'][0]['is_final'] = False
    payload = {key: [bad] for key in gate.FLOW_LISTS}
    payload.update(days=window, stats={'old_hit_rate': 1})
    original = copy.deepcopy(payload)
    result = gate.gate_toss_payload(payload, settings)
    assert all(result[key] == [] for key in gate.FLOW_LISTS)
    assert result['stats'] == {}
    assert result['reliability']['excluded_rows'] == 1
    assert payload == original


def test_current_candidates_pass_and_status_change_invalidates_immediately(settings):
    payload = dict(rows=[row()], dual=[row()], days=1)
    assert len(gate.gate_toss_payload(payload, settings)['dual']) == 1
    table = pd.read_csv(settings.status_csv, dtype={'ticker':str})
    table.loc[table.ticker == '005930', 'status'] = 'SUSPENDED'
    table.to_csv(settings.status_csv, index=False)
    assert gate.gate_toss_payload(payload, settings)['rows'] == []


def test_official_requires_current_both_parties_and_drops_old_fund(settings):
    rows = [dict(ticker='005930', trade_date='2026-09-07', investor_type=kind, is_final=True, net_value=10)
            for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    old = dict(ticker='005930', trade_date='2026-09-04', investor_type='FUND', is_final=True)
    assert gate.gate_official_rows(rows + [old], settings) == rows
    assert gate.gate_official_rows([rows[0], old], settings) == []
    assert gate.gate_official_rows([{**r, 'is_final': False} for r in rows], settings) == []


@pytest.mark.parametrize('bad_value', [None, '', float('nan'), float('inf'), True])
def test_official_missing_amount_never_falls_back_to_quantity(settings, bad_value):
    rows = [dict(ticker='005930', trade_date='2026-09-07', investor_type=kind,
                 is_final=True, net_value=10, net_qty=1)
            for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    rows.append({**rows[0], 'trade_date':'2026-09-04', 'net_value':bad_value})
    assert gate.gate_official_rows(rows, settings) == []


def test_official_duplicate_day_cannot_double_totals(settings):
    rows = [dict(ticker='005930', trade_date='2026-09-07', investor_type=kind,
                 is_final=True, net_value=10) for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    assert gate.gate_official_rows(rows + [rows[0]], settings) == []


def test_toss_source_missing_is_distinct_from_explicit_zero(settings):
    from kr_quant.flow.investor import summarize_records
    raw = dict(date='2026-09-07', institution={'netBuyVolume': 10})
    summary = dict(ticker='005930', **summarize_records([raw], 1))
    assert gate.gate_toss_payload(dict(rows=[summary], days=1), settings)['rows'] == []
    raw['foreigner'] = {'netBuyVolume': 0}
    summary = dict(ticker='005930', **summarize_records([raw], 1))
    assert len(gate.gate_toss_payload(dict(rows=[summary], days=1), settings)['rows']) == 1


def test_calendar_and_screener_share_gate(settings):
    from kr_quant.screens import _flow_tickers
    from kr_quant.strategy.seasonality import _load_flow_confirmation_map
    path = settings.data_dir / 'cache' / 'investor_flow.json'
    path.parent.mkdir(parents=True)
    bad = {**row(), 'ticker':'000660'}
    path.write_text(json.dumps(dict(rows=[row(), bad], dual=[row(), bad], days=1)), encoding='utf-8')
    assert _flow_tickers(settings, 'dual') == {'005930'}
    assert set(_load_flow_confirmation_map(settings)) == {'005930'}


def test_missing_status_fails_closed(settings):
    settings.status_csv.unlink()
    assert gate.gate_toss_payload(dict(rows=[row()]), settings)['rows'] == []


def test_latest_status_universe_used_when_expected_status_date_missing(settings, monkeypatch):
    monkeypatch.setattr(gate, 'expected_price_date', lambda: date(2026, 9, 8))
    rows = [dict(ticker='005930', trade_date='2026-09-08', investor_type=kind, is_final=True, net_value=10)
            for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    assert gate.gate_official_rows(rows, settings) == rows
    halted = [dict(ticker='000660', trade_date='2026-09-08', investor_type=kind, is_final=True, net_value=10)
              for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    assert gate.gate_official_rows(halted, settings) == []


def test_toss_uses_warehouse_session_when_clock_expected_missing(settings, monkeypatch):
    monkeypatch.setattr(gate, 'expected_price_date', lambda: date(2026, 9, 8))
    payload = dict(rows=[row()], dual=[row()], days=1)
    result = gate.gate_toss_payload(payload, settings)
    assert len(result['rows']) == 1
    assert len(result['dual']) == 1
    assert result['reliability']['expected_date'] == '2026-09-07'
    assert result['reliability']['clock_expected'] == '2026-09-08'
    assert result['reliability']['session_fallback'] is True
    assert result['need_scan'] is False


def test_toss_stale_cache_older_than_warehouse_still_fails_closed(settings, monkeypatch):
    monkeypatch.setattr(gate, 'expected_price_date', lambda: date(2026, 9, 8))
    stale = row()
    stale['to'] = '2026-09-04'
    stale['daily'][0]['date'] = '2026-09-04'
    result = gate.gate_toss_payload(dict(rows=[stale], dual=[stale], days=1), settings)
    assert result['rows'] == []
    assert result['dual'] == []
    assert result['need_scan'] is True


def test_technical_price_date_and_category_copies_agree(settings):
    from kr_quant.timing.snapshot import attach_technicals
    payload = dict(rows=[row()], trading=[copy.deepcopy(row())], candidate_as_of='2026-09-07')
    price = pd.DataFrame([dict(ticker='005930', trade_date='2026-09-04', high=100, low=90, close=95)])
    result = attach_technicals(payload, settings, prices=price)
    assert result['rows'][0]['ta'] == result['trading'][0]['ta']
    assert result['trading'][0]['ta']['ok'] is False
    assert result['trading'][0]['ta']['reason'] == 'TECHNICAL_PRICE_DATE_MISMATCH'


def test_duplicate_candidates_fail_closed_and_groups_use_canonical_row(settings):
    assert gate.gate_toss_payload(dict(rows=[row(), row()]), settings)['rows'] == []
    result = gate.gate_toss_payload(dict(rows=[row()], dual=[{**row(), 'foreign_net':999}]), settings)
    assert result['rows'][0] == result['dual'][0]


def test_ticker_windows_use_filtered_single_party_amounts(settings, monkeypatch):
    from types import SimpleNamespace
    from kr_quant.flow import official
    rows = [dict(ticker='005930', trade_date=day, investor_type=kind,
                 is_final=True, net_value=amount)
            for day, amount in [('2026-09-07', 20), ('2026-09-04', 10)]
            for kind in ['FOREIGN', 'INSTITUTION_TOTAL']]
    rows += [dict(ticker='005930', trade_date='2026-09-07', investor_type='FUND',
                  is_final=True, net_value=None, net_qty=999999)]
    monkeypatch.setattr(official, 'open_settings', lambda s: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(official, 'load_ticker', lambda *a: rows)
    result = official.ticker_payload(settings, '005930')
    assert result['rows'] == rows  # Original history is not deleted.
    assert result['windows']['w5'] == 30
    assert result['window_party'] == 'INSTITUTION_TOTAL'
    assert result['unit'] == 'KRW'
    assert all('FUND' not in point for point in result['chart'])
