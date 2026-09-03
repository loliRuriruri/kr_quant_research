# -*- coding: utf-8 -*-
import pytest
from pathlib import Path
from datetime import date
from types import SimpleNamespace

from kr_quant.web.app import JobIn
from kr_quant.web.jobs import RUNNER, job_dart_backfill


def _mock_ctx():
    return SimpleNamespace(
        run_id="run_20260831_123",
        as_of_date=date(2026, 8, 31),
        status="success",
        warnings=[],
        result_hash="0123456789abcdef",
    )


def test_job_in_supports_continuous():
    job = JobIn(kind="dart-backfill", continuous=True, max_corps=0)
    assert job.continuous is True
    assert job.max_corps == 0

    job_default = JobIn(kind="dart-backfill")
    assert job_default.continuous is False


def test_job_dart_backfill_single_batch(monkeypatch, tmp_path):
    backfill_calls = []
    stage_runs = []

    def fake_backfill(s, d, batch_size=50):
        backfill_calls.append(batch_size)
        return {"status": "success", "processed_this_run": 50, "cursor": 50, "total_targets": 200, "has_retryable": True}

    def fake_stage(s, d, path, source_mode="live"):
        stage_runs.append((d, source_mode))
        return {"context": _mock_ctx(), "names": []}

    monkeypatch.setattr("kr_quant.web.jobs.load_settings", lambda: SimpleNamespace(
        opendart_api_key="TEST_KEY",
        staged_dir=tmp_path,
        output_dir=tmp_path,
    ))
    monkeypatch.setattr("kr_quant.ingest.live.backfill_dart_financials", fake_backfill)
    monkeypatch.setattr("kr_quant.orchestration.run.run_from_staged", fake_stage)
    monkeypatch.setattr("kr_quant.freshness.freshness_snapshot", lambda *a, **k: {})
    monkeypatch.setattr("kr_quant.run_generation.load_manifest", lambda *a: {})

    res = job_dart_backfill("2026-08-31", batch_size=50, continuous=False)
    assert len(backfill_calls) == 1
    assert len(stage_runs) == 1
    assert res.get("dart_backfill", {}).get("processed_this_run") == 50


def test_job_dart_backfill_continuous_until_complete(monkeypatch, tmp_path):
    calls = []
    stage_runs = []

    def fake_backfill(s, d, batch_size=50):
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            return {
                "status": "success",
                "processed_this_run": 50,
                "cursor": len(calls) * 50,
                "total_targets": 150,
                "has_retryable": True,
                "cycle_complete": False,
                "coverage": {"usable_pct": len(calls) * 33.3},
            }
        return {
            "status": "complete",
            "processed_this_run": 50,
            "cursor": 150,
            "total_targets": 150,
            "has_retryable": False,
            "cycle_complete": True,
            "coverage": {"usable_pct": 100.0},
        }

    def fake_stage(s, d, path, source_mode="live"):
        stage_runs.append((d, source_mode))
        return {"context": _mock_ctx(), "names": []}

    monkeypatch.setattr("kr_quant.web.jobs.load_settings", lambda: SimpleNamespace(
        opendart_api_key="TEST_KEY",
        staged_dir=tmp_path,
        output_dir=tmp_path,
    ))
    monkeypatch.setattr("kr_quant.ingest.live.backfill_dart_financials", fake_backfill)
    monkeypatch.setattr("kr_quant.orchestration.run.run_from_staged", fake_stage)
    monkeypatch.setattr("kr_quant.freshness.freshness_snapshot", lambda *a, **k: {})
    monkeypatch.setattr("kr_quant.run_generation.load_manifest", lambda *a: {})

    res = job_dart_backfill("2026-08-31", batch_size=50, continuous=True, max_cycles=10)
    assert len(calls) == 3
    assert len(stage_runs) == 1
    assert res["dart_backfill"]["continuous_cycles_run"] == 3
    assert res["dart_backfill"]["status"] == "complete"


def test_job_dart_backfill_continuous_cancel_requested(monkeypatch, tmp_path):
    calls = []

    def fake_backfill(s, d, batch_size=50):
        calls.append(1)
        RUNNER._cancel.set()
        return {
            "status": "success",
            "processed_this_run": 50,
            "cursor": 50,
            "total_targets": 500,
            "has_retryable": True,
            "cycle_complete": False,
            "coverage": {"usable_pct": 10.0},
        }

    def fake_stage(s, d, path, source_mode="live"):
        return {"context": _mock_ctx(), "names": []}

    RUNNER._cancel.clear()
    monkeypatch.setattr("kr_quant.web.jobs.load_settings", lambda: SimpleNamespace(
        opendart_api_key="TEST_KEY",
        staged_dir=tmp_path,
        output_dir=tmp_path,
    ))
    monkeypatch.setattr("kr_quant.ingest.live.backfill_dart_financials", fake_backfill)
    monkeypatch.setattr("kr_quant.orchestration.run.run_from_staged", fake_stage)
    monkeypatch.setattr("kr_quant.freshness.freshness_snapshot", lambda *a, **k: {})
    monkeypatch.setattr("kr_quant.run_generation.load_manifest", lambda *a: {})

    res = job_dart_backfill("2026-08-31", batch_size=50, continuous=True, max_cycles=10)
    assert len(calls) == 1
    assert any("중단" in line or "cancel" in line.lower() or "마감" in line for line in RUNNER.logs)
    RUNNER._cancel.clear()


def test_dart_backfill_purges_phantom_usable_facts(monkeypatch, tmp_path):
    from kr_quant.ingest.live import _seed_partition_outcomes, DART_USABLE_FACTS
    outcomes = {
        '005930': {'outcome': DART_USABLE_FACTS, 'updated_at': '2026-08-31T00:00:00Z'},
        '000660': {'outcome': DART_USABLE_FACTS, 'updated_at': '2026-08-31T00:00:00Z'},
    }
    # Only 005930 actually exists in fact_tickers
    fact_tickers = {'005930'}
    cleaned = _seed_partition_outcomes(outcomes, {}, now='2026-09-03T00:00:00Z', fact_tickers=fact_tickers)
    assert '005930' in cleaned
    assert '000660' not in cleaned  # Phantom outcome was purged!
