from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import kr_quant.flow.official as official
import kr_quant.freshness as freshness
import kr_quant.web.jobs as jobs
import kr_quant.web.scheduler as scheduler
from kr_quant.web import smart_ledger
from kr_quant.web.scheduler import _STATE, _catch_up_due, _fire

KST = ZoneInfo("Asia/Seoul")


def test_invalid_krx_response_stops_automatic_retry_and_quant(monkeypatch, tmp_path):
    settings, state, seen = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(jobs, 'probe_expected_krx', lambda *args: {
        'ready': False, 'retryable': False, 'failure_kind': 'response_invalid',
        'error': 'KRX response_invalid'})
    result = jobs.job_smart_sync()
    saved = smart_ledger.load_ledger(settings)
    assert saved['steps']['krx']['status'] == 'failed'
    assert saved['steps']['krx']['retry_at'] is None
    assert saved['steps']['krx']['failure_kind'] == 'response_invalid'
    assert 'krx' not in seen and 'quant' not in seen
    assert result['pipeline_status'] == 'failed'
    assert any('자동 반복 중단' in warning for warning in result['warnings'])


def _snapshot(*, stale: bool, quant_state: str, coverage: float) -> dict:
    return {
        "stale_price": stale,
        "screen_as_of": "2026-08-31",
        "price_max_date": "2026-08-28" if stale else "2026-08-31",
        "required_stale": ["krx_prices"] if stale else [],
        "contract_status": "blocked" if stale else "ready",
        "sources": {
            "quant_ranking": {"state": quant_state},
            "financial_facts": {
                "coverage": {
                    "tickers": 414,
                    "universe_tickers": 2544,
                    "coverage_pct": coverage,
                }
            },
        },
    }


def _settings(tmp_path, **extra):
    payload = {
        "root": tmp_path,
        "kis_app_key": extra.get("kis_app_key", "key"),
        "kis_app_secret": extra.get("kis_app_secret", "secret"),
        "krx_api_key": "krx",
        "config": {"smart_sync": {"krx_retry_minutes": 25, "krx_max_attempts": 6}},
    }
    payload.update({key: value for key, value in extra.items() if key not in {"kis_app_key", "kis_app_secret"}})
    return SimpleNamespace(**payload)


def _patch_common(monkeypatch, tmp_path, *, stale=True, quant_state="stale", coverage=16.3, probe_ready=True):
    settings = _settings(tmp_path)
    state = {"stale": stale, "quant": quant_state, "coverage": coverage}
    seen: list[str] = []

    jobs.RUNNER._cancel.clear()
    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(freshness, "expected_price_date", lambda now=None: date(2026, 8, 31))
    monkeypatch.setattr(
        freshness,
        "freshness_snapshot",
        lambda value, **kwargs: _snapshot(stale=state["stale"], quant_state=state["quant"], coverage=state["coverage"]),
    )
    monkeypatch.setattr(jobs, "probe_expected_krx", lambda *args, **kwargs: {"ready": probe_ready, "missing_markets": [] if probe_ready else ["KOSPI"]})
    monkeypatch.setattr(
        jobs,
        "job_krx_prices",
        lambda *args, **kwargs: seen.append("krx") or state.__setitem__("stale", False) or {"price_rows": 2700, "pipeline_status": "success"},
    )
    monkeypatch.setattr(
        jobs,
        "job_live",
        lambda *args, **kwargs: seen.append("quant")
        or state.__setitem__("quant", "fresh")
        or {"pipeline_status": "success", "as_of_date": "2026-08-31"},
    )
    monkeypatch.setattr(
        jobs,
        "job_dart_backfill",
        lambda *args, **kwargs: seen.append("dart")
        or state.__setitem__("coverage", 18.2)
        or {
            "dart_backfill": {
                "status": "success",
                "processed_this_run": 50,
                "covered_tickers": 464,
                "coverage_pct": 18.2,
            }
        },
    )
    monkeypatch.setattr(
        official,
        "collect_official",
        lambda value: seen.append("kis") or {"attempted": 40, "saved": 400, "errors": []},
    )
    return settings, state, seen


def test_smart_sync_runs_only_needed_daily_chain(monkeypatch, tmp_path):
    settings, state, seen = _patch_common(monkeypatch, tmp_path)

    result = jobs.job_smart_sync()

    assert seen == ["krx", "quant", "dart", "kis"]
    assert result["kind"] == "smart-sync"
    assert result["pipeline_status"] in {"success", "partial"}
    assert result["dart_coverage"]["coverage_pct"] == 18.2
    assert [step["kind"] for step in result["steps"]] == ["krx", "quant", "dart", "kis", "publish"]
    assert result["ledger"]["steps"]["krx"]["status"] == "success"
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["dart"]["status"] == "success"
    assert saved["steps"]["kis"]["status"] == "success"


def test_smart_sync_skips_fresh_core_and_sufficient_dart(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, stale=False, quant_state="fresh", coverage=92.0)
    monkeypatch.setattr(jobs, "job_krx_prices", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("KRX should be skipped")))
    monkeypatch.setattr(jobs, "job_live", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("quant should be skipped")))
    monkeypatch.setattr(jobs, "job_dart_backfill", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DART should be skipped")))
    settings = _settings(tmp_path, kis_app_key=None, kis_app_secret=None)
    monkeypatch.setattr(jobs, "load_settings", lambda: settings)

    result = jobs.job_smart_sync()

    assert result["pipeline_status"] == "success"
    assert result["steps"][0]["status"] == "skipped_fresh"
    assert result["steps"][1]["status"] == "skipped_fresh"
    assert result["steps"][2]["status"] == "skipped_sufficient"
    assert result["steps"][3]["status"] == "skipped_not_configured"


def test_source_not_ready_retries_krx_only(monkeypatch, tmp_path):
    settings, state, seen = _patch_common(monkeypatch, tmp_path, probe_ready=False)

    first = jobs.job_smart_sync()

    assert seen == ["dart", "kis"]
    assert first["steps"][0]["status"] == "source_not_ready"
    assert first["steps"][1]["status"] == "blocked_dependency"
    assert first["ledger"]["steps"]["krx"]["retry_at"]
    assert first["pipeline_status"] == "partial"

    seen.clear()
    monkeypatch.setattr(jobs, "probe_expected_krx", lambda *args, **kwargs: {"ready": True, "missing_markets": []})
    second = jobs.job_smart_sync()

    assert seen == ["krx", "quant"]
    assert "dart" not in seen
    assert "kis" not in seen
    assert second["steps"][0]["status"] == "success"
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["dart"]["status"] in {"success", "skipped_already_success"}
    assert saved["steps"]["kis"]["status"] in {"success", "skipped_already_success"}


def test_cancel_between_krx_and_quant_keeps_completed_step(monkeypatch, tmp_path):
    settings, state, seen = _patch_common(monkeypatch, tmp_path)

    def krx(*args, **kwargs):
        seen.append("krx")
        jobs.RUNNER._cancel.set()
        state["stale"] = False
        return {"price_rows": 2700, "pipeline_status": "success"}

    monkeypatch.setattr(jobs, "job_krx_prices", krx)
    result = jobs.job_smart_sync()
    jobs.RUNNER._cancel.clear()

    assert result["cancelled"] is True
    assert result["pipeline_status"] == "interrupted"
    assert seen == ["krx"]
    assert "quant" not in seen
    saved = smart_ledger.load_ledger(settings)
    assert saved["overall_status"] == "interrupted"
    assert saved["steps"]["krx"]["status"] == "success"
    assert saved["steps"]["quant"]["status"] == "pending"


def test_job_runner_exposes_partial_pipeline_status(monkeypatch):
    runner = jobs.JobRunner()
    monkeypatch.setattr(jobs, "_maybe_publish", lambda kind: None)
    monkeypatch.setattr(jobs, "_notify_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "record_job_history", lambda *args: None)
    import kr_quant.web.season_snapshot as snapshots
    import kr_quant.research.selection_tracking as tracking
    monkeypatch.setattr(snapshots, 'refresh_after_data_job', lambda *args: None)
    monkeypatch.setattr(tracking, 'request_tracking_refresh', lambda *args: None)

    runner._run("smart-sync", lambda: {"pipeline_status": "partial"})

    assert runner.snapshot()["status"] == "partial"
    assert any("일부 완료" in line for line in runner.logs)


def test_failed_pipeline_is_not_logged_complete_or_published(monkeypatch):
    runner = jobs.JobRunner()
    published = []
    monkeypatch.setattr(jobs, '_maybe_publish', lambda kind: published.append(kind))
    monkeypatch.setattr(jobs, '_notify_job', lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, 'record_job_history', lambda *args: None)
    runner._run('smart-sync', lambda: {'pipeline_status': 'failed'})
    assert runner.snapshot()['status'] == 'error'
    assert any('작업 실패' in line for line in runner.logs)
    assert not any('작업 완료' in line for line in runner.logs)
    assert published == []


def test_running_ledger_recovers_to_interrupted(tmp_path):
    settings = _settings(tmp_path)
    ledger = smart_ledger.new_ledger(run_date="2026-08-31", expected_price_date="2026-08-31", trigger="scheduled")
    ledger["steps"]["krx"]["status"] = "running"
    smart_ledger.save_ledger(ledger, settings)

    recovered = smart_ledger.recover_interrupted(settings, runner_running=False)

    assert recovered["overall_status"] == "interrupted"
    assert recovered["steps"]["krx"]["status"] == "interrupted"


def test_running_ledger_stays_if_runner_alive(tmp_path):
    settings = _settings(tmp_path)
    ledger = smart_ledger.new_ledger(run_date="2026-08-31", expected_price_date="2026-08-31", trigger="manual")
    ledger["steps"]["krx"]["status"] = "running"
    smart_ledger.save_ledger(ledger, settings)

    kept = smart_ledger.recover_interrupted(settings, runner_running=True)

    assert kept["overall_status"] == "running"
    assert kept["steps"]["krx"]["status"] == "running"


def test_scheduler_busy_does_not_consume_slot(monkeypatch):
    prior = {key: _STATE.get(key) for key in ("last_fire", "last_error", "last_skip", "last_result")}
    try:
        _STATE.update({"last_fire": None, "last_error": None, "last_skip": None, "last_result": None})
        monkeypatch.setattr(jobs.RUNNER, "snapshot", lambda: {"status": "running"})
        monkeypatch.setattr(scheduler, "load_scheduler_config", lambda: {"job_kind": "smart-sync"})
        _fire()
        assert _STATE["last_fire"] is None
        assert "실행 중" in (_STATE["last_error"] or "")
        assert _STATE["last_skip"]
    finally:
        _STATE.update(prior)


def test_scheduler_retry_due_after_source_not_ready(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(smart_ledger, "load_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "load_settings", lambda: settings)
    ledger = smart_ledger.new_ledger(
        run_date=datetime.now(KST).date().isoformat(),
        expected_price_date="2026-08-31",
        trigger="scheduled",
    )
    ledger["steps"]["krx"] = {
        "status": "source_not_ready",
        "attempt": 1,
        "retry_at": datetime(2020, 1, 1, tzinfo=KST).isoformat(),
        "ran_this_pass": False,
    }
    smart_ledger.save_ledger(ledger, settings)
    assert smart_ledger.retry_due(smart_ledger.load_ledger(settings), now=datetime.now(KST), settings=settings) is True


def test_catch_up_still_skips_when_last_fire_today(monkeypatch):
    cfg = {"job_kind": "smart-sync", "hour": 19, "minute": 10}
    now = datetime(2026, 8, 25, 20, 0, tzinfo=KST)
    previous = _STATE.get("last_fire")
    try:
        _STATE["last_fire"] = now.isoformat()
        monkeypatch.setattr(
            freshness,
            "freshness_snapshot",
            lambda *args, **kwargs: {"stale_price": True, "sources": {"quant_ranking": {"state": "stale"}}},
        )
        assert _catch_up_due(cfg, now) is False
    finally:
        _STATE["last_fire"] = previous
