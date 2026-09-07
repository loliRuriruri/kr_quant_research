from dataclasses import replace
import pandas as pd
import pytest
from kr_quant.settings import load_settings
from kr_quant.ingest import recent_filings as recent


@pytest.mark.parametrize('response', [{'status':'020'}, {'status':'000', 'list':[]}])
def test_financial_provider_error_is_not_success(tmp_path, monkeypatch, response):
    settings = replace(load_settings(), root=tmp_path)
    folder = settings.staged_dir / 'live'
    folder.mkdir(parents=True)
    pd.DataFrame([dict(ticker='388610', corp_code='01221752', rcept_no='old',
                       available_date='2026-08-13')]).to_parquet(folder / 'financial_facts.parquet')
    monkeypatch.setattr(recent.OpenDartAdapter, 'fetch_list_range', lambda *a, **k:
                        {'status':'000', 'total_page':1, 'list':[
                            dict(corp_code='01221752', rcept_no='new', stock_code='388610',
                                 report_nm='반기보고서 (2026.06)')]})
    monkeypatch.setattr(recent.OpenDartAdapter, 'fetch_financials', lambda *a, **k: response)
    with pytest.raises(RuntimeError, match='reconciliation incomplete'):
        recent.check(settings)


def test_only_changed_provider_receipt_forces_refresh_and_preserves_backup(tmp_path, monkeypatch):
    from kr_quant.ingest import live
    settings = replace(load_settings(), root=tmp_path)
    folder = settings.staged_dir / 'live'
    folder.mkdir(parents=True)
    pd.DataFrame([{'ticker':'388610', 'corp_code':'01221752'}]).to_parquet(folder / 'master.parquet')
    pd.DataFrame([{'ticker':'388610', 'rcept_no':'old'}]).to_parquet(folder / 'financial_facts.parquet')
    row = {'ticker':'388610', 'year':2026, 'report_code':'11012', 'returned_receipts':['new'], 'stored_receipts':['old']}
    report = {'financial_api_probes':[row], 'from':'2026-08-25', 'to':'2026-09-08', 'official_periodic_filings':1}
    calls=[]
    monkeypatch.setattr(recent, 'check', lambda s: report)
    def fetch(s, targets, reports, force_refresh=False):
        calls.append((targets[0]['ticker'], reports, force_refresh))
        row['stored_receipts'] = ['new']
    monkeypatch.setattr(live, 'fetch_dart_financials', fetch)
    result = recent.refresh_recent(settings)
    assert result['status'] == 'success'
    assert calls == [('388610', [(2026, '11012')], True)]
    assert len(list((settings.root/'data/research_snapshots/financial_revisions').glob('*.parquet'))) == 1
    assert result['needs_recalculation'] is True
    assert recent.refresh_recent(settings)['needs_recalculation'] is True
    recent.acknowledge_recalculation(settings)
    assert recent.refresh_recent(settings)['needs_recalculation'] is False


def test_publication_is_unconditionally_skipped_for_local_recalculation():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2]/'src/kr_quant/web/jobs.py').read_text(encoding='utf-8')
    assert 'if kind == "refresh-local":' in source
    assert 'elif finished_status != "error":' in source


def test_postprocessing_is_busy_even_after_computation_success(monkeypatch):
    from kr_quant.web.jobs import JobRunner
    from types import SimpleNamespace
    import pytest
    runner = JobRunner()
    runner.state['status'] = 'success'
    runner._thread = SimpleNamespace(is_alive=lambda: True)
    assert runner.snapshot()['status'] == 'running'
    assert runner.snapshot()['postprocessing'] is True
    with pytest.raises(RuntimeError):
        runner.start('refresh-local', lambda: {})
