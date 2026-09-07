from datetime import date
from types import SimpleNamespace

import pytest
import requests

from kr_quant.ingest.krx import KrxOpenApiAdapter, KrxResponseError, daily_rows
from kr_quant.ingest.live import krx_session_available

DAY = date(2026, 9, 7)


@pytest.mark.parametrize('payload', [None, [], {'message': 'secret'}, {'OutBlock_1': None},
    {'OutBlock_1': {}}, {'OutBlock_1': ['bad']}, {'OutBlock_1': [{}]},
    {'OutBlock_1': [{'BAS_DD': '20260907'}, {'BAS_DD': '20260904'}]}])
def test_invalid_or_mixed_day_payload_never_becomes_requested_day(payload):
    with pytest.raises(KrxResponseError) as caught:
        daily_rows(payload, DAY, 'KOSPI')
    assert 'secret' not in str(caught.value)


def test_genuine_empty_and_alternate_row_key():
    assert daily_rows({'OutBlock_1': []}, DAY, 'KOSPI') == []
    row = {'basDd': '20260907', 'ISU_CD': '005930'}
    assert daily_rows({'output': [row]}, DAY, 'KOSPI') == [row]


@pytest.mark.parametrize('method', ['fetch_daily', 'fetch_daily_maybe'])
def test_all_daily_paths_validate_dates(monkeypatch, method):
    adapter = KrxOpenApiAdapter('test', 'https://example.test')
    monkeypatch.setattr(adapter, '_get', lambda *args: {'OutBlock_1': [{'BAS_DD': '20260904'}]})
    with pytest.raises(KrxResponseError):
        getattr(adapter, method)(DAY, 'KOSPI')


def settings():
    return SimpleNamespace(krx_api_key='secret', config={
        'ingest': {'krx_base_url': 'https://example.test'},
        'universe': {'markets': ['KOSPI', 'KOSDAQ']}})


def test_probe_reports_per_market_empty_not_authorization(monkeypatch):
    monkeypatch.setattr(KrxOpenApiAdapter, 'fetch_daily_maybe',
                        lambda self, day, market: [{'BAS_DD': '20260907'}] if market == 'KOSPI' else [])
    result = krx_session_available(settings(), DAY)
    assert result['market_rows'] == {'KOSPI': 1, 'KOSDAQ': 0}
    assert result['missing_markets'] == ['KOSDAQ']
    assert result['failure_kind'] == 'not_published'
    assert result['retryable'] is True


@pytest.mark.parametrize('error,kind,retryable', [
    (KrxResponseError('secret'), 'response_invalid', False),
    (requests.Timeout('secret'), 'request_error', True),
    (requests.ConnectionError('secret'), 'request_error', True),
])
def test_probe_sanitizes_and_classifies_errors(monkeypatch, error, kind, retryable):
    def fail(*args):
        raise error
    monkeypatch.setattr(KrxOpenApiAdapter, 'fetch_daily_maybe', fail)
    result = krx_session_available(settings(), DAY)
    assert result['failure_kind'] == kind
    assert result['retryable'] is retryable
    assert 'secret' not in result['error']


@pytest.mark.parametrize('status,retryable', [(401, False), (403, False), (429, True), (503, True)])
def test_probe_http_recovery_policy(monkeypatch, status, retryable):
    response = requests.Response()
    response.status_code = status
    def fail(*args):
        raise requests.HTTPError('secret', response=response)
    monkeypatch.setattr(KrxOpenApiAdapter, 'fetch_daily_maybe', fail)
    result = krx_session_available(settings(), DAY)
    assert result['retryable'] is retryable
    assert result['failure_kind'] == ('authorization' if status in (401, 403) else 'request_error')
    assert 'secret' not in result['error']
