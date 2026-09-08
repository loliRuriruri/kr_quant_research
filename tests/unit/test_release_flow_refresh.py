from types import SimpleNamespace
from scripts import refresh_release_flow as release


def test_probe_failure_does_not_expose_response_or_credentials(monkeypatch):
    monkeypatch.setattr(release, 'load_settings', lambda: SimpleNamespace(
        toss_client_id='fixture', toss_client_secret='fixture-secret'))
    def fail(*args):
        raise RuntimeError('HTTP 403 fixture-secret private-response')
    monkeypatch.setattr(release, 'get_investor_trading', fail)
    result = release.run()
    assert result['status'] == 'BLOCKED'
    assert result['http_codes'] == ['HTTP 403']
    assert 'fixture-secret' not in str(result)
    assert 'private-response' not in str(result)


def test_refresh_exception_after_successful_probe_is_not_success(tmp_path, monkeypatch):
    from kr_quant.flow import scan
    settings = SimpleNamespace(root=tmp_path, data_dir=tmp_path/'data',
                               toss_client_id='fixture', toss_client_secret='fixture')
    monkeypatch.setattr(release, 'load_settings', lambda: settings)
    monkeypatch.setattr(release, 'get_investor_trading', lambda *a: {'records': []})
    monkeypatch.setattr(release, 'summarize_records', lambda *a, **k: {
        'to': release.expected_price_date().isoformat(), 'days': 5, 'source_complete': True})
    def fail(*args, **kwargs):
        raise OSError('scan failed')
    monkeypatch.setattr(scan, 'scan_flow', fail)
    result = release.run(refresh=True)
    assert result['status'] == 'BLOCKED'
    assert result['published'] is False
