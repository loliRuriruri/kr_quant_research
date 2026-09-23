# -*- coding: utf-8 -*-
"""Smart-sync A2: artifact-aware self-healing + legacy regressions."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import kr_quant.flow.official as official
import kr_quant.freshness as freshness
import kr_quant.web.jobs as jobs
import kr_quant.web.scheduler as scheduler
from kr_quant.web import smart_ledger
from kr_quant.web.pipeline_plan import InvalidPipelineMode
from kr_quant.web.scheduler import _STATE, _catch_up_due, _fire

KST = ZoneInfo("Asia/Seoul")


def _settings(tmp_path, **extra):
    live = tmp_path / "staged" / "live"
    live.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": tmp_path,
        "staged_dir": tmp_path / "staged",
        "data_dir": tmp_path / "data",
        "kis_app_key": extra.get("kis_app_key", "key"),
        "kis_app_secret": extra.get("kis_app_secret", "secret"),
        "opendart_api_key": extra.get("opendart_api_key", "dart-key"),
        "krx_api_key": "krx",
        "config": {"smart_sync": {"krx_retry_minutes": 25, "krx_max_attempts": 6}},
    }
    payload.update({k: v for k, v in extra.items() if k not in {"kis_app_key", "kis_app_secret"}})
    return SimpleNamespace(**payload)


def _comp(state: str, **extra):
    row = {"state": state}
    row.update(extra)
    return row


def _health_payload(state: dict) -> dict:
    cov = float(state.get("coverage", 16.3))
    cov_state = "HEALTHY" if cov >= 90.0 else "PARTIAL"
    return {
        "pipeline_state": state.get("pipeline_state", "NEEDS_DAILY_UPDATE"),
        "busy": False,
        "repair_required": state.get("dart_essential") in {"MISSING", "CORRUPT"}
        or state.get("krx") in {"MISSING", "CORRUPT", "STALE"}
        or state.get("master") in {"MISSING", "CORRUPT"},
        "components": {
            "krx": _comp(state.get("krx", "STALE")),
            "master": _comp(state.get("master", "HEALTHY")),
            "dart_essential": _comp(state.get("dart_essential", "HEALTHY")),
            "dart_coverage": _comp(
                cov_state,
                coverage_pct=cov,
                tickers=int(state.get("tickers", 414)),
                universe_tickers=2544,
                target_pct=90.0,
            ),
            "quant": _comp(state.get("quant", "STALE")),
            "kis": _comp(state.get("kis", "STALE")),
            "season": _comp(state.get("season", "STALE")),
        },
    }


def _patch_common(
    monkeypatch,
    tmp_path,
    *,
    krx="STALE",
    master="HEALTHY",
    dart_essential="HEALTHY",
    quant="STALE",
    coverage=16.3,
    kis="STALE",
    probe_ready=True,
    quant_job_ok=True,
    quant_health_after="HEALTHY",
    krx_health_after="HEALTHY",
    dart_batches_to_healthy=1,
):
    monkeypatch.setattr(official, "collection_is_current", lambda s: True)
    settings = _settings(tmp_path)
    state = {
        "krx": krx,
        "master": master,
        "dart_essential": dart_essential,
        "quant": quant,
        "coverage": coverage,
        "kis": kis,
        "pipeline_state": "NEEDS_DAILY_UPDATE",
    }
    seen: list[str] = []
    dart_calls = {"n": 0}
    facts_path = settings.staged_dir / "live" / "financial_facts.parquet"
    if dart_essential == "HEALTHY":
        facts_path.write_bytes(b"facts-v1")

    jobs.RUNNER._cancel.clear()
    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(freshness, "wanted_price_date", lambda now=None: date(2026, 8, 31))

    def fake_health(settings_arg=None, ledger=None, **kwargs):
        return _health_payload(state)

    monkeypatch.setattr("kr_quant.web.pipeline_health.pipeline_health", fake_health)
    # also patch name used inside jobs after local import — jobs imports inside function
    import kr_quant.web.pipeline_health as ph

    monkeypatch.setattr(ph, "pipeline_health", fake_health)

    monkeypatch.setattr(
        jobs,
        "probe_expected_krx",
        lambda *args, **kwargs: {
            "ready": probe_ready,
            "missing_markets": [] if probe_ready else ["KOSPI"],
            "retryable": True,
        },
    )

    def fake_krx(*args, **kwargs):
        seen.append("krx")
        state["krx"] = krx_health_after
        if krx_health_after == "HEALTHY":
            state["master"] = "HEALTHY"
        return {"price_rows": 2700, "pipeline_status": "success"}

    monkeypatch.setattr(jobs, "job_krx_prices", fake_krx)

    def fake_live(*args, **kwargs):
        seen.append("quant")
        if not quant_job_ok:
            return {"pipeline_status": "success", "as_of_date": "2026-08-31"}
        state["quant"] = quant_health_after
        return {
            "pipeline_status": "success" if quant_health_after == "HEALTHY" else "partial",
            "as_of_date": "2026-08-31",
        }

    monkeypatch.setattr(jobs, "job_live", fake_live)

    def fake_backfill(settings_arg, expected, batch_size=50, *, mutate_facts=True):
        seen.append("dart")
        dart_calls["n"] += 1
        state["coverage"] = min(99.0, float(state["coverage"]) + 1.0)
        if state["dart_essential"] in {"MISSING", "CORRUPT"}:
            if dart_calls["n"] >= dart_batches_to_healthy:
                state["dart_essential"] = "HEALTHY"
                facts_path.write_bytes(b"facts-repaired")
        elif mutate_facts:
            prev = facts_path.read_bytes() if facts_path.exists() else b""
            facts_path.write_bytes(prev + b"x")
        return {"processed": batch_size}

    monkeypatch.setattr("kr_quant.ingest.live.backfill_dart_financials", fake_backfill)
    import kr_quant.ingest.live as live_mod

    monkeypatch.setattr(live_mod, "backfill_dart_financials", fake_backfill)

    def fake_master(settings_arg, expected):
        seen.append("master_repair")
        state["master"] = "HEALTHY"
        return {"ok": True}

    monkeypatch.setattr(live_mod, "build_live_master", fake_master)

    monkeypatch.setattr(
        official,
        "collect_official",
        lambda value: seen.append("kis") or {"attempted": 40, "saved": 400, "errors": []},
    )

    # recent filings: default no dirty
    import kr_quant.ingest.recent_filings as rf

    monkeypatch.setattr(
        rf,
        "refresh_recent",
        lambda s: {"status": "success", "refreshed_tickers": [], "needs_recalculation": False},
    )

    return settings, state, seen, dart_calls, facts_path


# ----- legacy / runner / scheduler -----


def test_invalid_krx_response_stops_automatic_retry_and_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        jobs,
        "probe_expected_krx",
        lambda *args: {
            "ready": False,
            "retryable": False,
            "failure_kind": "response_invalid",
            "error": "KRX response_invalid",
        },
    )
    result = jobs.job_smart_sync()
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["krx"]["status"] == "failed"
    assert saved["steps"]["krx"]["retry_at"] is None
    assert saved["steps"]["krx"]["failure_kind"] == "response_invalid"
    assert "krx" not in seen and "quant" not in seen
    assert result["pipeline_status"] == "failed"
    assert any("자동 반복 중단" in warning for warning in result["warnings"])


def test_smart_sync_runs_needed_chain_dart_before_quant_when_facts_missing(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch, tmp_path, dart_essential="MISSING", quant="MISSING", coverage=99.9
    )
    result = jobs.job_smart_sync()
    assert seen.index("dart") < seen.index("quant")
    assert "krx" in seen and "kis" in seen
    assert result["kind"] == "smart-sync"
    assert result["pipeline_status"] in {"success", "partial"}
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["dart"]["status"] == "success"
    assert saved["steps"]["quant"]["status"] == "success"


def test_smart_sync_skips_fresh_core(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="HEALTHY",
        coverage=92.0,
        kis="HEALTHY",
    )
    monkeypatch.setattr(jobs, "job_krx_prices", lambda *a, **k: (_ for _ in ()).throw(AssertionError("KRX")))
    monkeypatch.setattr(jobs, "job_live", lambda *a, **k: (_ for _ in ()).throw(AssertionError("quant")))
    settings2 = _settings(tmp_path, kis_app_key=None, kis_app_secret=None, opendart_api_key="dart-key")
    # keep staged_dir from first settings
    settings2.staged_dir = settings.staged_dir
    settings2.root = settings.root
    monkeypatch.setattr(jobs, "load_settings", lambda: settings2)
    # mark kis healthy so plan may still CHECK_PUBLISH only
    state["kis"] = "HEALTHY"
    result = jobs.job_smart_sync()
    assert result["pipeline_status"] == "success"
    kinds = [step["kind"] for step in result["steps"]]
    assert "publish" in kinds
    assert "quant" not in seen and "krx" not in seen


def test_source_not_ready_blocks_quant_allows_kis(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(monkeypatch, tmp_path, probe_ready=False, dart_essential="HEALTHY")
    first = jobs.job_smart_sync()
    assert "quant" not in seen
    assert "kis" in seen
    assert any(step["status"] == "source_not_ready" for step in first["steps"] if step["kind"] == "krx")
    assert first["ledger"]["steps"]["krx"]["retry_at"]
    assert first["pipeline_status"] == "partial"
    assert first["failure_kind"] == "WAITING_SOURCE"

    seen.clear()
    monkeypatch.setattr(jobs, "probe_expected_krx", lambda *a, **k: {"ready": True, "missing_markets": []})
    # health still shows STALE until krx runs
    state["krx"] = "STALE"
    second = jobs.job_smart_sync()
    assert "krx" in seen and "quant" in seen
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["kis"]["status"] in {"success", "skipped_already_success"}


def test_cancel_between_krx_and_quant_keeps_completed_step(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(monkeypatch, tmp_path, dart_essential="HEALTHY")

    def krx(*args, **kwargs):
        seen.append("krx")
        jobs.RUNNER._cancel.set()
        state["krx"] = "HEALTHY"
        state["master"] = "HEALTHY"
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

    monkeypatch.setattr(snapshots, "refresh_after_data_job", lambda *args: None)
    monkeypatch.setattr(tracking, "request_tracking_refresh", lambda *args: None)
    runner._run("smart-sync", lambda: {"pipeline_status": "partial"})
    assert runner.snapshot()["status"] == "partial"
    assert any("일부 완료" in line for line in runner.logs)


def test_failed_pipeline_is_not_logged_complete_or_published(monkeypatch):
    runner = jobs.JobRunner()
    published = []
    monkeypatch.setattr(jobs, "_maybe_publish", lambda kind: published.append(kind))
    monkeypatch.setattr(jobs, "_notify_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "record_job_history", lambda *args: None)
    runner._run("smart-sync", lambda: {"pipeline_status": "failed"})
    assert runner.snapshot()["status"] == "error"
    assert any("작업 실패" in line for line in runner.logs)
    assert not any("작업 완료" in line for line in runner.logs)
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


# ----- matrix 20–28 -----


def test_20_trigger_independent_from_mode(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch, tmp_path, krx="HEALTHY", master="HEALTHY", dart_essential="HEALTHY", quant="HEALTHY", coverage=95.0, kis="HEALTHY"
    )
    result = jobs.job_smart_sync(trigger="manual", mode="recover")
    assert result["trigger"] == "manual"
    assert result["mode"] == "recover"
    saved = smart_ledger.load_ledger(settings)
    assert saved["trigger"] == "manual"
    assert saved["mode"] == "recover"
    snap = smart_ledger.public_snapshot(settings, ledger=saved)
    assert snap["mode"] == "recover"
    assert snap["trigger"] == "manual"


def test_21_invalid_mode_fails_closed_no_ledger_mutation(monkeypatch, tmp_path):
    settings, *_ = _patch_common(monkeypatch, tmp_path)
    assert smart_ledger.load_ledger(settings) is None
    try:
        jobs.job_smart_sync(mode="invalid")
        assert False, "expected InvalidPipelineMode"
    except InvalidPipelineMode:
        pass
    assert smart_ledger.load_ledger(settings) is None


def test_22_ledger_dart_success_facts_missing_still_repairs_before_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch, tmp_path, krx="HEALTHY", master="HEALTHY", dart_essential="MISSING", quant="STALE", coverage=99.9
    )
    run_date = datetime.now(KST).date().isoformat()
    ledger = smart_ledger.new_ledger(run_date=run_date, expected_price_date="2026-08-31", trigger="manual", mode="normal")
    ledger["steps"]["dart"]["status"] = "success"
    smart_ledger.save_ledger(ledger, settings)
    result = jobs.job_smart_sync()
    assert "dart" in seen and "quant" in seen
    assert seen.index("dart") < seen.index("quant")
    assert result["pipeline_status"] in {"success", "partial"}


def test_23_dart_verify_failure_blocks_quant_and_publish(monkeypatch, tmp_path):
    settings, state, seen, dart_calls, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="MISSING",
        quant="STALE",
        dart_batches_to_healthy=99,
    )
    result = jobs.job_smart_sync()
    assert "quant" not in seen
    assert result["pipeline_status"] == "failed"
    assert result["failure_kind"] == "REPAIR_INCOMPLETE"
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["publish"]["status"] == "blocked_dependency"
    assert saved["steps"]["quant"]["status"] in {"pending", "blocked_dependency"}


def test_24_quant_false_success_verify_failed_blocks_publish(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="STALE",
        coverage=95.0,
        quant_job_ok=True,
        quant_health_after="STALE",  # remains unhealthy after job_live
    )
    # force: after job_live, keep quant STALE
    result = jobs.job_smart_sync()
    assert "quant" in seen
    assert result["pipeline_status"] == "failed"
    assert result["failure_kind"] == "VERIFY_FAILED"
    saved = smart_ledger.load_ledger(settings)
    assert saved["steps"]["quant"]["status"] == "verify_failed"
    assert saved["steps"]["publish"]["status"] == "blocked_dependency"


def test_25_krx_false_success_blocks_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="STALE",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="STALE",
        krx_health_after="STALE",
    )
    result = jobs.job_smart_sync()
    assert "krx" in seen
    assert "quant" not in seen
    assert result["failure_kind"] in {"WAITING_SOURCE", "VERIFY_FAILED"}
    assert any(s["kind"] == "krx" and s["status"] in {"source_not_ready", "verify_failed"} for s in result["steps"])


def test_26_cancellation_keeps_verified_steps(monkeypatch, tmp_path):
    test_cancel_between_krx_and_quant_keeps_completed_step(monkeypatch, tmp_path)


def test_27_default_mode_is_normal(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch, tmp_path, krx="HEALTHY", master="HEALTHY", dart_essential="HEALTHY", quant="HEALTHY", coverage=95.0, kis="HEALTHY"
    )
    result = jobs.job_smart_sync(trigger="scheduled")
    assert result["mode"] == "normal"
    saved = smart_ledger.load_ledger(settings)
    assert saved["mode"] == "normal"


def test_28_runner_single_flight(monkeypatch):
    test_scheduler_busy_does_not_consume_slot(monkeypatch)


# ----- regressions 29–38 -----


def test_29_master_missing_local_repair_before_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="MISSING",
        dart_essential="HEALTHY",
        quant="STALE",
        coverage=95.0,
    )
    live = settings.staged_dir / "live"
    (live / "krx_master.parquet").write_bytes(b"km")
    (live / "prices.parquet").write_bytes(b"px")
    result = jobs.job_smart_sync()
    assert "master_repair" in seen
    assert seen.index("master_repair") < seen.index("quant")
    assert result["pipeline_status"] in {"success", "partial"}


def test_30_master_unhealthy_after_repair_blocks_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="MISSING",
        dart_essential="HEALTHY",
        quant="STALE",
        coverage=95.0,
    )
    import kr_quant.ingest.live as live_mod

    def bad_master(*a, **k):
        seen.append("master_repair")
        # leave master MISSING
        return {"ok": False}

    monkeypatch.setattr(live_mod, "build_live_master", bad_master)
    # also make network krx leave master bad
    monkeypatch.setattr(
        jobs,
        "job_krx_prices",
        lambda *a, **k: seen.append("krx") or {"price_rows": 1, "pipeline_status": "success"},
    )
    result = jobs.job_smart_sync()
    assert "quant" not in seen
    assert result["pipeline_status"] == "failed" or result["failure_kind"] == "VERIFY_FAILED"


def test_31_recover_never_dart_maintenance(monkeypatch, tmp_path):
    settings, state, seen, dart_calls, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="HEALTHY",
        coverage=40.0,
        kis="HEALTHY",
    )
    result = jobs.job_smart_sync(mode="recover")
    assert "dart" not in seen
    assert dart_calls["n"] == 0
    assert result["mode"] == "recover"


def test_32_normal_maintenance_changes_facts_reruns_quant(monkeypatch, tmp_path):
    settings, state, seen, dart_calls, facts_path = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="HEALTHY",
        coverage=40.0,
        kis="HEALTHY",
    )
    facts_path.write_bytes(b"facts-v1")
    result = jobs.job_smart_sync(mode="normal")
    assert "dart" in seen
    assert seen.count("quant") >= 1
    assert result["pipeline_status"] in {"success", "partial"}


def test_33_normal_maintenance_unchanged_facts_no_extra_quant(monkeypatch, tmp_path):
    settings, state, seen, dart_calls, facts_path = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="HEALTHY",
        coverage=40.0,
        kis="HEALTHY",
    )
    facts_path.write_bytes(b"facts-stable")
    import kr_quant.ingest.live as live_mod

    def no_mutate(settings_arg, expected, batch_size=50):
        seen.append("dart")
        dart_calls["n"] += 1
        # do not rewrite facts
        return {"processed": batch_size}

    monkeypatch.setattr(live_mod, "backfill_dart_financials", no_mutate)
    result = jobs.job_smart_sync(mode="normal")
    assert "dart" in seen
    assert "quant" not in seen


def test_34_high_coverage_missing_facts_still_essential_repair(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="MISSING",
        quant="STALE",
        coverage=99.9,
    )
    result = jobs.job_smart_sync()
    assert "dart" in seen
    assert seen.index("dart") < seen.index("quant")


def test_35_skipped_sufficient_ledger_cannot_mask_missing_facts(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="MISSING",
        quant="STALE",
        coverage=99.9,
    )
    run_date = datetime.now(KST).date().isoformat()
    ledger = smart_ledger.new_ledger(run_date=run_date, expected_price_date="2026-08-31", trigger="manual")
    ledger["steps"]["dart"]["status"] = "skipped_sufficient"
    smart_ledger.save_ledger(ledger, settings)
    jobs.job_smart_sync()
    assert "dart" in seen


def test_36_kis_failure_does_not_force_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="HEALTHY",
        quant="HEALTHY",
        coverage=95.0,
        kis="STALE",
    )
    monkeypatch.setattr(
        official,
        "collect_official",
        lambda value: (_ for _ in ()).throw(RuntimeError("kis down")),
    )
    result = jobs.job_smart_sync()
    assert "quant" not in seen
    assert any(s["kind"] == "kis" and s["status"] == "warning" for s in result["steps"])


def test_37_missing_dart_key_fail_closed(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="MISSING",
        quant="STALE",
    )
    settings.opendart_api_key = None
    result = jobs.job_smart_sync()
    assert "quant" not in seen
    assert "dart" not in seen
    assert result["pipeline_status"] == "failed"
    assert result["failure_kind"] == "REPAIR_INCOMPLETE"


def test_38_corrupt_facts_never_fed_to_quant(monkeypatch, tmp_path):
    settings, state, seen, *_ = _patch_common(
        monkeypatch,
        tmp_path,
        krx="HEALTHY",
        master="HEALTHY",
        dart_essential="CORRUPT",
        quant="STALE",
        coverage=50.0,
    )
    result = jobs.job_smart_sync()
    assert "quant" not in seen
    assert result["failure_kind"] == "REPAIR_INCOMPLETE"
    assert result["pipeline_status"] == "failed"


def test_old_ledger_without_mode_defaults_normal(tmp_path):
    settings = _settings(tmp_path)
    ledger = {
        "run_date": "2026-08-31",
        "run_id": "abc",
        "expected_price_date": "2026-08-31",
        "trigger": "manual",
        "started_at": datetime.now(KST).isoformat(),
        "heartbeat_at": datetime.now(KST).isoformat(),
        "finished_at": None,
        "overall_status": "success",
        "steps": {name: smart_ledger.empty_step() for name in smart_ledger.STEPS},
    }
    smart_ledger.save_ledger(ledger, settings)
    snap = smart_ledger.public_snapshot(settings)
    assert snap["mode"] == "normal"


def test_decide_overall_verify_failed_is_hard_failure(tmp_path):
    settings = _settings(tmp_path)
    ledger = smart_ledger.new_ledger(run_date="2026-08-31", expected_price_date="2026-08-31", trigger="manual")
    for name in smart_ledger.STEPS:
        ledger["steps"][name]["status"] = "success"
    ledger["steps"]["quant"]["status"] = "verify_failed"
    assert smart_ledger.decide_overall(ledger, settings) == "failed"
    ledger["steps"]["quant"]["status"] = "repair_incomplete"
    assert smart_ledger.decide_overall(ledger, settings) == "failed"
