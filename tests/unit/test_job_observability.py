from datetime import datetime, timedelta, timezone
import threading
import time

import pytest
import requests

import kr_quant.ingest.http_retry as http_retry
import kr_quant.web.jobs as jobs
from fastapi.testclient import TestClient

from kr_quant.web import smart_ledger
from kr_quant.web.app import app


@pytest.fixture
def isolated_history(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_history_path", lambda: tmp_path / "job_history.json")
    jobs._JOB_HISTORY.clear()
    jobs._HISTORY_LOADED = False
    yield tmp_path / "job_history.json"
    jobs._JOB_HISTORY.clear()
    jobs._HISTORY_LOADED = False


def test_heartbeat_moves_and_elapsed_passes_60s():
    runner = jobs.JobRunner()
    started = datetime.now(timezone.utc) - timedelta(seconds=70)
    runner.state.update(
        {
            "status": "running",
            "started_at": started.isoformat(),
            "heartbeat_at": started.isoformat(),
            "elapsed_sec": 0,
        }
    )
    with runner._lock:
        runner._pulse_locked()
    first = runner.state["heartbeat_at"]
    assert runner.state["elapsed_sec"] >= 60
    time.sleep(0.02)
    with runner._lock:
        runner._pulse_locked()
    assert runner.state["heartbeat_at"] != first
    assert runner.state["elapsed_sec"] >= 60


def test_dead_running_thread_is_reaped(monkeypatch, isolated_history):
    monkeypatch.setattr(smart_ledger, "recover_interrupted", lambda **kwargs: None)
    runner = jobs.JobRunner()
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    runner._thread = dead
    runner.state["status"] = "running"
    runner.state["kind"] = "smart-sync"
    snap = runner.snapshot()
    assert snap["status"] == "error"
    assert "사라졌" in (snap.get("error") or "")
    assert jobs.job_history_summary()["last_error"]["status"] == "error"


def test_request_cancel_does_not_deadlock_when_idle():
    runner = jobs.JobRunner()
    snap = runner.request_cancel()
    assert snap["status"] == "idle"
    assert snap["cancel_requested"] is False


def test_busy_start_explains_kind_and_step():
    runner = jobs.JobRunner()
    hold = threading.Event()

    def hang():
        hold.wait(2)

    alive = threading.Thread(target=hang)
    alive.start()
    runner._thread = alive
    runner.state.update(
        {
            "status": "running",
            "kind": "smart-sync",
            "started_at": "2026-09-01T10:00:00+00:00",
            "progress": {"current_step": "dart"},
        }
    )
    try:
        with pytest.raises(RuntimeError, match="이미 실행 중인 작업이 있습니다: smart-sync"):
            runner.start("live", lambda: {})
        with pytest.raises(RuntimeError, match="단계 dart"):
            runner.start("live", lambda: {})
    finally:
        hold.set()
        alive.join(timeout=2)
        runner.state["status"] = "idle"
        runner._thread = None


def test_history_picks_last_success_partial_error(isolated_history):
    jobs.record_job_history({"kind": "a", "status": "error"})
    jobs.record_job_history({"kind": "b", "status": "partial"})
    jobs.record_job_history({"kind": "c", "status": "success"})
    jobs.record_job_history({"kind": "d", "status": "partial"})
    summary = jobs.job_history_summary()
    assert summary["last_success"]["kind"] == "c"
    assert summary["last_partial"]["kind"] == "d"
    assert summary["last_error"]["kind"] == "a"
    assert [row["kind"] for row in summary["recent"]] == ["d", "c", "b", "a"]


def test_interrupted_pipeline_is_partial_and_skips_publish(monkeypatch, isolated_history):
    runner = jobs.JobRunner()
    published: list[str] = []
    monkeypatch.setattr(jobs, "_maybe_publish", lambda kind: published.append(kind))
    monkeypatch.setattr(jobs, "_notify_job", lambda *args, **kwargs: None)
    runner._run("smart-sync", lambda: {"pipeline_status": "interrupted", "cancelled": True, "steps": []})
    snap = runner.snapshot()
    assert snap["status"] == "partial"
    assert published == []
    assert jobs.job_history_summary()["last_partial"]["cancelled"] is True
    assert any("중단" in line for line in runner.logs)


def test_jobs_busy_returns_409_and_cancel_endpoint(monkeypatch, isolated_history):
    hold = threading.Event()

    def hang():
        hold.wait(3)
        return {"pipeline_status": "success"}

    monkeypatch.setattr(jobs, "_maybe_publish", lambda kind: None)
    monkeypatch.setattr(jobs, "_notify_job", lambda *args, **kwargs: None)
    jobs.RUNNER._cancel.clear()
    if jobs.RUNNER.snapshot().get("status") == "running":
        pytest.skip("global runner already busy")
    jobs.RUNNER.start("smart-sync", hang)
    client = TestClient(app)
    try:
        busy = client.post("/api/jobs", json={"kind": "demo"})
        assert busy.status_code == 409
        assert "smart-sync" in busy.json()["detail"]
        snap = client.get("/api/jobs").json()
        assert "history" in snap
        assert snap["status"] == "running"
        cancelled = client.post("/api/jobs/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested"] is True
        hist = client.get("/api/jobs/history").json()
        assert "last_success" in hist
    finally:
        hold.set()
        jobs.RUNNER._cancel.clear()
        if jobs.RUNNER._thread is not None:
            jobs.RUNNER._thread.join(timeout=3)


class _FakeResp:
    def __init__(self, code: int) -> None:
        self.status_code = code


def test_http_retry_skips_most_4xx(monkeypatch):
    calls: list[int] = []

    def fake(method, url, **kwargs):
        calls.append(400)
        return _FakeResp(400)

    monkeypatch.setattr(http_retry.requests, "request", fake)
    resp = http_retry.request_with_retry("GET", "http://example.invalid", retries=2, backoff_sec=0)
    assert resp.status_code == 400
    assert len(calls) == 1


def test_http_retry_retries_429_and_timeout(monkeypatch):
    calls: list[int] = []

    def fake_429(method, url, **kwargs):
        calls.append(429)
        return _FakeResp(429 if len(calls) < 3 else 200)

    monkeypatch.setattr(http_retry.requests, "request", fake_429)
    resp = http_retry.request_with_retry("GET", "http://example.invalid", retries=2, backoff_sec=0)
    assert resp.status_code == 200
    assert len(calls) == 3

    calls.clear()

    def fake_timeout(method, url, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise requests.Timeout("slow")
        return _FakeResp(200)

    monkeypatch.setattr(http_retry.requests, "request", fake_timeout)
    resp = http_retry.request_with_retry("GET", "http://example.invalid", retries=2, backoff_sec=0)
    assert resp.status_code == 200
    assert len(calls) == 3
