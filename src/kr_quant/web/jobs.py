from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import date, datetime, timezone
from typing import Any, Callable

import pandas as pd

from kr_quant.settings import load_settings

_JOB_HISTORY: list[dict[str, Any]] = []
_HISTORY_LOADED = False


def _history_path():
    return load_settings().root / "logs" / "job_history.json"


def _load_job_history() -> None:
    global _HISTORY_LOADED
    if _HISTORY_LOADED:
        return
    path = _history_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                _JOB_HISTORY[:] = [item for item in payload if isinstance(item, dict)][:30]
        except (OSError, json.JSONDecodeError, TypeError, NameError):
            pass
    _HISTORY_LOADED = True


def record_job_history(entry: dict[str, Any]) -> None:
    _load_job_history()
    item = {**entry, "recorded_at": datetime.now(timezone.utc).isoformat()}
    _JOB_HISTORY.insert(0, item)
    del _JOB_HISTORY[30:]
    try:
        path = _history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(_JOB_HISTORY, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def job_history_summary() -> dict[str, Any]:
    _load_job_history()

    def pick(*statuses: str) -> dict[str, Any] | None:
        for item in _JOB_HISTORY:
            if item.get("status") in statuses:
                return item
        return None

    return {
        "recent": _JOB_HISTORY[:8],
        "last_success": pick("success"),
        "last_partial": pick("partial"),
        "last_error": pick("error"),
    }


class _DequeHandler(logging.Handler):
    def __init__(self, buf: deque[str]) -> None:
        super().__init__(level=logging.INFO)
        self.buf = buf
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buf.append(self.format(record))
            RUNNER.set_progress(None)
        except Exception:  # noqa: BLE001
            pass


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {
            "status": "idle",
            "kind": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "result": None,
            "progress": None,
            "heartbeat_at": None,
            "elapsed_sec": 0,
            "cancel_requested": False,
        }
        self.logs: deque[str] = deque(maxlen=400)
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._reap_locked()
            self._pulse_locked()
            state = {**self.state, "logs": list(self.logs)}
            if state['status'] != 'running' and self._thread is not None and self._thread.is_alive():
                state['computation_status'] = state['status']
                state['status'] = 'running'
                state['postprocessing'] = True
                state['progress'] = {**(state.get('progress') or {}), 'current_step': '후처리·공개판 확인'}
        state["history"] = job_history_summary()
        return state

    def busy_reason(self) -> str | None:
        snap = self.snapshot()
        if snap.get("status") != "running":
            return None
        kind = snap.get("kind") or "작업"
        step = (snap.get("progress") or {}).get("current_step")
        started = str(snap.get("started_at") or "")[:19].replace("T", " ")
        extra = f", 단계 {step}" if step else ""
        return f"이미 실행 중인 작업이 있습니다: {kind} (시작 {started}{extra})"

    def start(self, kind: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            self._reap_locked()
            if self.state["status"] == "running" or (self._thread is not None and self._thread.is_alive()):
                kind_now = self.state.get("kind") or "작업"
                step = (self.state.get("progress") or {}).get("current_step")
                started = str(self.state.get("started_at") or "")[:19].replace("T", " ")
                extra = f", 단계 {step}" if step else ""
                raise RuntimeError(f"이미 실행 중인 작업이 있습니다: {kind_now} (시작 {started}{extra})")
            now = datetime.now(timezone.utc).isoformat()
            self._cancel.clear()
            self.state = {
                "status": "running",
                "kind": kind,
                "started_at": now,
                "finished_at": None,
                "error": None,
                "result": None,
                "progress": {"current_step": kind, "targets": None, "done": 0, "failed": 0},
                "heartbeat_at": now,
                "elapsed_sec": 0,
                "cancel_requested": False,
            }
            self.logs.clear()
            self.logs.append(f"작업 시작: {kind}")
        self._thread = threading.Thread(target=self._run, args=(kind, fn), daemon=True)
        self._thread.start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        return self.snapshot()

    def is_running(self) -> bool:
        return self.snapshot().get("status") == "running" or bool(self._thread and self._thread.is_alive())

    def request_cancel(self) -> dict[str, Any]:
        with self._lock:
            self._reap_locked()
            if self.state["status"] == "running":
                self._cancel.set()
                self.state["cancel_requested"] = True
                self.logs.append("중단 요청: 현재 단계가 끝나는 시점에 멈춥니다.")
        return self.snapshot()

    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def set_progress(self, progress: dict[str, Any] | None) -> None:
        with self._lock:
            current = dict(self.state.get("progress") or {})
            if progress:
                current.update(progress)
            self.state["progress"] = current
            self._pulse_locked()

    def _pulse_locked(self) -> None:
        if self.state.get("status") != "running":
            return
        now = datetime.now(timezone.utc)
        self.state["heartbeat_at"] = now.isoformat()
        started = self.state.get("started_at")
        if started:
            try:
                t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                if t0.tzinfo is None:
                    t0 = t0.replace(tzinfo=timezone.utc)
                self.state["elapsed_sec"] = max(0, int((now - t0).total_seconds()))
            except ValueError:
                pass

    def _reap_locked(self) -> None:
        if self.state.get("status") != "running":
            return
        thread = self._thread
        if thread is None or thread.is_alive():
            return
        self.state["status"] = "error"
        self.state["error"] = "작업 스레드가 사라졌습니다. 실행 중 체크포인트를 중단으로 복구합니다."
        self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.logs.append(self.state["error"])
        try:
            from kr_quant.web.smart_ledger import recover_interrupted

            recover_interrupted(runner_running=False)
        except Exception:  # noqa: BLE001
            pass
        record_job_history(
            {
                "kind": self.state.get("kind"),
                "status": "error",
                "started_at": self.state.get("started_at"),
                "finished_at": self.state.get("finished_at"),
                "error": self.state.get("error"),
            }
        )

    def _heartbeat_loop(self) -> None:
        import time

        while True:
            time.sleep(5)
            with self._lock:
                if self.state.get("status") != "running":
                    return
                self._pulse_locked()

    def _run(self, kind: str, fn: Callable[[], dict[str, Any]]) -> None:
        logger = logging.getLogger("kr_quant")
        handler = _DequeHandler(self.logs)
        logger.addHandler(handler)
        try:
            result = fn()
            pipeline = str(result.get("pipeline_status") or "success")
            finished_status = {
                "partial": "partial",
                "blocked": "partial",
                "failed": "error",
                "interrupted": "partial",
            }.get(pipeline, "success")
            with self._lock:
                self._pulse_locked()
                self.state["status"] = finished_status
                self.state["result"] = result
                self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
                history_row = {
                    "kind": kind,
                    "status": finished_status,
                    "started_at": self.state.get("started_at"),
                    "finished_at": self.state.get("finished_at"),
                    "elapsed_sec": self.state.get("elapsed_sec"),
                    "pipeline_status": pipeline,
                    "cancelled": bool(result.get("cancelled")),
                    "steps": result.get("steps"),
                }
            if pipeline == "interrupted" or result.get("cancelled"):
                self.logs.append(f"작업 중단: {kind} · 완료된 단계는 유지됩니다.")
            else:
                label = {'partial': '일부 완료', 'error': '실패'}.get(finished_status, '완료')
                self.logs.append(f"작업 {label}: {kind}")
                follow = result.get("next_action") or result.get("note")
                if follow:
                    self.logs.append(str(follow)[:400])
            record_job_history(history_row)
            if pipeline != "interrupted" and not result.get("cancelled"):
                if finished_status in {"success", "partial"} and kind in {
                    "live", "screen", "refresh-local", "krx-prices", "krx-history", "dart-backfill", "smart-sync"
                }:
                    from kr_quant.web.season_snapshot import refresh_after_data_job
                    refresh_after_data_job(load_settings())
                    from kr_quant.research.selection_tracking import request_tracking_refresh
                    request_tracking_refresh(load_settings())
                    self.logs.append("시즌 메뉴 공통 자료를 백그라운드에서 준비합니다. 완료 후 같은 세대로 전환합니다.")
                if kind == "refresh-local":
                    self.logs.append("로컬 재계산 전용 작업: 공개 배포를 실행하지 않습니다.")
                elif finished_status != "error":
                    _maybe_publish(kind)
                else:
                    self.logs.append("실패한 작업이므로 공개판 자동 배포를 건너뜁니다.")
                _notify_job(kind, result=result)
            else:
                self.logs.append("중단되어 공개판 업로드와 알림을 건너뜁니다.")
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.state["status"] = "error"
                self.state["error"] = str(exc)
                self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
                history_row = {
                    "kind": kind,
                    "status": "error",
                    "started_at": self.state.get("started_at"),
                    "finished_at": self.state.get("finished_at"),
                    "error": str(exc)[:240],
                }
            self.logs.append(f"작업 실패: {exc}")
            record_job_history(history_row)
            _notify_job(kind, error=str(exc))
        finally:
            logger.removeHandler(handler)


RUNNER = JobRunner()


def resolve_as_of(as_of: str) -> date:
    if as_of and as_of != "auto":
        return date.fromisoformat(as_of)
    from datetime import timedelta

    from kr_quant.ingest.krx import KrxOpenApiAdapter

    s = load_settings()
    if not s.krx_api_key:
        return date.today()
    adapter = KrxOpenApiAdapter(s.krx_api_key, s.config["ingest"]["krx_base_url"])
    cur = date.today()
    for _ in range(10):
        if adapter.fetch_daily_maybe(cur, "KOSPI"):
            return cur
        cur -= timedelta(days=1)
    return date.today()


def job_demo(as_of: str) -> dict[str, Any]:
    from kr_quant.orchestration.run import run_demo

    s = load_settings()
    d = date.fromisoformat(as_of) if as_of and as_of != "auto" else date(2024, 12, 30)
    result = run_demo(s, d)
    return _summarize(result)


def job_screen(as_of: str, source: str) -> dict[str, Any]:
    from kr_quant.orchestration.run import run_from_staged

    s = load_settings()
    d = resolve_as_of(as_of)
    folder = s.staged_dir / ("live" if source == "live" else "demo")
    if not (folder / "prices.parquet").exists():
        raise FileNotFoundError(f"{folder} 에 시세가 없습니다. 먼저 데모 또는 실데이터 수집을 실행하세요.")
    result = run_from_staged(s, d, folder, source_mode=source)
    return _summarize(result)


def job_live(as_of: str, lookback_days: int, max_corps: int, skip_ingest: bool) -> dict[str, Any]:
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import bootstrap_live
    from kr_quant.orchestration.run import run_from_staged
    from kr_quant.strategy.run import scan_strategies

    s = load_settings()
    d = resolve_as_of(as_of)
    info: dict[str, Any] = {"as_of": d.isoformat()}
    recent = None
    if s.opendart_api_key and (s.staged_dir / 'live' / 'financial_facts.parquet').exists():
        from kr_quant.ingest.recent_filings import refresh_recent
        recent = refresh_recent(s)
        if recent['status'] != 'success':
            raise RuntimeError('최근 DART 정정 재무 갱신 미완료: 재계산을 보류합니다.')
    if not skip_ingest:
        if not s.krx_api_key or not s.opendart_api_key:
            raise RuntimeError("실데이터 수집에는 KRX와 OpenDART 키가 필요합니다.")
        info["ingest"] = bootstrap_live(s, d, lookback_days=lookback_days, max_corps=max_corps)
    folder = s.staged_dir / "live"
    result = run_from_staged(s, d, folder, source_mode="live")
    out = _summarize(result)
    out["ingest"] = info.get("ingest")
    out['recent_filings'] = recent
    derived: dict[str, Any] = {}
    try:
        strategy = scan_strategies(s)
        derived["strategy_cache"] = {
            "status": "success",
            "source_price_as_of": strategy.get("source_price_as_of"),
            "tickers": len(strategy.get("rows") or []),
        }
    except Exception as exc:  # noqa: BLE001
        derived["strategy_cache"] = {"status": "error", "error": str(exc)[:240]}
        logger = logging.getLogger("kr_quant")
        logger.warning("strategy cache refresh failed after live run: %s", exc)
    from kr_quant.run_generation import load_manifest

    committed = load_manifest(s) or {}
    screen_as_of = committed.get("as_of_date") or out.get("as_of_date")
    fresh = freshness_snapshot(s, screen_as_of=screen_as_of)
    out["freshness"] = fresh
    out["derived"] = derived
    out["pipeline_status"] = (
        "partial"
        if fresh.get("contract_status") != "ready" or any(item.get("status") == "error" for item in derived.values())
        else "success"
    )
    if recent is not None and out["pipeline_status"] == "success":
        from kr_quant.ingest.recent_filings import acknowledge_recalculation
        acknowledge_recalculation(s)
    return out


HISTORY_DAYS = 750


def job_krx_prices(as_of: str = "auto", lookback_days: int = 10) -> dict[str, Any]:
    """KRX 일봉·마스터·거래상태를 받는다. OpenDART와 Quant 재계산은 하지 않는다.

    auto는 이미 공개된 이전 세션으로 되돌아가지 않는다. 기대 기준일을 받지
    못하면 기존 parquet를 유지한 채 partial로 끝낸다. 완료는 저장 종가가
    기대일과 같을 때만 반환한다.
    """
    from kr_quant.exceptions import SourceNotReady
    from kr_quant.freshness import freshness_snapshot, wanted_price_date
    from kr_quant.ingest.live import fetch_krx_master, fetch_krx_prices_range

    s = load_settings()
    if not s.krx_api_key:
        raise RuntimeError("KRX_API_KEY가 없습니다.")
    d = wanted_price_date() if not as_of or as_of == "auto" else date.fromisoformat(str(as_of)[:10])
    days = max(3, min(int(lookback_days or 10), 40))
    before = freshness_snapshot(s)
    stored = before.get("price_max_date") or "없음"
    probe = probe_expected_krx(s, d)

    def _result(*, pipeline_status: str, note: str, master_rows: int = 0, price_rows: int = 0, status_rows: int = 0, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        fresh = freshness_snapshot(s)
        stored_now = fresh.get("price_max_date") or stored
        payload = {
            "as_of": d.isoformat(),
            "kind": "krx-prices",
            "master_rows": master_rows,
            "price_rows": price_rows,
            "status_rows": status_rows,
            "status_path": str(s.status_csv),
            "lookback_days": days,
            "freshness": fresh,
            "used_in_quant": False,
            "source_ready": pipeline_status == "success",
            "pipeline_status": pipeline_status,
            "note": note,
        }
        if pipeline_status != "success":
            payload["next_action"] = (
                f"KRX {d.isoformat()} 일봉이 저장되지 않았습니다. "
                f"저장 종가는 {stored_now}입니다. {note}"
            )
        if extra:
            payload.update(extra)
        return payload

    if not probe.get("ready"):
        failure_kind = probe.get("failure_kind")
        retryable = bool(probe.get("retryable", True))
        if failure_kind in {"authorization", "configuration"} or not retryable:
            raise RuntimeError(probe.get("error") or f"KRX {d.isoformat()} 인증·설정 오류")
        missing = ", ".join(probe.get("missing_markets") or []) or "전체"
        note = f"KRX가 {d.isoformat()} 일봉을 아직 공개하지 않았습니다 (빈 시장: {missing})."
        RUNNER.logs.append(f"{note} 저장 종가 {stored}를 유지합니다. 완료로 처리하지 않습니다.")
        return _result(
            pipeline_status="partial",
            note=note,
            extra={"failure_kind": failure_kind, "missing_markets": probe.get("missing_markets") or []},
        )

    master = fetch_krx_master(s, d)
    try:
        prices = fetch_krx_prices_range(s, d, lookback_days=days, require_as_of=True)
    except SourceNotReady as exc:
        RUNNER.logs.append(str(exc))
        return _result(pipeline_status="partial", note=str(exc), master_rows=int(len(master)))

    status_rows = 0
    if s.status_csv.exists():
        status = pd.read_csv(s.status_csv, dtype={"ticker": str})
        status_rows = int((status["as_of_date"].astype(str) == d.isoformat()).sum())
    fresh = freshness_snapshot(s)
    stored_now = fresh.get("price_max_date")
    if fresh.get("stale_price") or stored_now != d.isoformat():
        note = f"수집 후에도 저장 종가 {stored_now or '없음'}, 기대일 {d.isoformat()}."
        RUNNER.logs.append(note)
        return _result(
            pipeline_status="partial",
            note=note,
            master_rows=int(len(master)),
            price_rows=int(len(prices)),
            status_rows=status_rows,
        )
    note = f"KRX 시세 {d.isoformat()} 저장 완료. 저장 종가 {stored_now}."
    RUNNER.logs.append(note)
    return _result(
        pipeline_status="success",
        note=note,
        master_rows=int(len(master)),
        price_rows=int(len(prices)),
        status_rows=status_rows,
    )


def job_krx_history(as_of: str = "auto", lookback_days: int = HISTORY_DAYS) -> dict[str, Any]:
    """이미 있는 날짜는 건너뛰고, 과거 거래일을 더 받아 전략·모멘텀 이력을 채운다."""
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import fetch_krx_master, fetch_krx_prices_range

    s = load_settings()
    if not s.krx_api_key:
        raise RuntimeError("KRX_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    days = max(80, min(int(lookback_days or HISTORY_DAYS), 2600))
    master = fetch_krx_master(s, d)
    prices = fetch_krx_prices_range(s, d, lookback_days=days, sleep_sec=0.08)
    status_rows = 0
    if s.status_csv.exists():
        status = pd.read_csv(s.status_csv, dtype={"ticker": str})
        status_rows = int((status["as_of_date"].astype(str) == d.isoformat()).sum())
    fresh = freshness_snapshot(s)
    n_dates = 0
    if prices is not None and not getattr(prices, "empty", True) and "trade_date" in prices.columns:
        n_dates = int(prices["trade_date"].nunique())
    return {
        "as_of": d.isoformat(),
        "kind": "krx-history",
        "master_rows": int(len(master)),
        "price_rows": int(len(prices)),
        "price_days": n_dates,
        "status_rows": status_rows,
        "status_path": str(s.status_csv),
        "lookback_days": days,
        "freshness": fresh,
        "used_in_quant": False,
        "note": f"KRX 일봉을 최대 {days}거래일까지 채웠습니다. 전략 랩은 이력이 늘어난 뒤 다시 돌리세요.",
    }


def job_dart_backfill(
    as_of: str = "auto",
    batch_size: int = 50,
    *,
    continuous: bool = False,
    max_cycles: int = 100,
) -> dict[str, Any]:
    """Advance DART full-universe coverage and re-score against the expanded facts.

    When continuous=True, loops through successive batches until all universe targets
    are covered or the user requests cancellation, re-scoring quant factors only once at the end.
    """
    import time
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import backfill_dart_financials
    from kr_quant.orchestration.run import run_from_staged

    s = load_settings()
    if not s.opendart_api_key:
        raise RuntimeError("OPENDART_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    eff_batch = max(1, min(int(batch_size or 50), 500))

    if not continuous:
        backfill = backfill_dart_financials(s, d, batch_size=eff_batch)
        result = run_from_staged(s, d, s.staged_dir / "live", source_mode="live")
        out = _summarize(result)
        out["dart_backfill"] = {
            key: value
            for key, value in backfill.items()
            if key not in {"ticker_order", "ticker_outcomes"}
        }
        from kr_quant.run_generation import load_manifest

        committed = load_manifest(s) or {}
        out["freshness"] = freshness_snapshot(s, screen_as_of=committed.get("as_of_date") or out.get("as_of_date"))
        out["pipeline_status"] = "partial" if out["freshness"].get("required_stale") else "success"
        return out

    # Continuous mode: loop through batches until target is reached or canceled
    RUNNER.logs.append("🚀 OpenDART 전 종목 목표 커버리지 자동 연속 수집을 시작합니다.")
    cycle_count = 0
    consecutive_zero_runs = 0
    last_backfill: dict[str, Any] = {}

    while cycle_count < max_cycles:
        is_cancelled = RUNNER.cancel_requested() if callable(getattr(RUNNER, "cancel_requested", None)) else bool(getattr(RUNNER, "cancel_requested", False))
        if is_cancelled:
            RUNNER.logs.append("⏹️ 사용자 중단 요청을 수신했습니다. 현재까지 수집된 데이터를 안전하게 보존하고 마감합니다.")
            break

        cycle_count += 1

        try:
            backfill = backfill_dart_financials(s, d, batch_size=eff_batch)
            last_backfill = backfill
        except Exception as exc:
            err_str = str(exc).lower()
            RUNNER.logs.append(f"⚠️ DART 수집 중 일시적 오류 발생: {exc}")
            if "020" in err_str or "limit" in err_str or "한도" in err_str:
                RUNNER.logs.append("🛑 OpenDART 일일 호출 한도에 도달하여 수집을 안전하게 마감합니다.")
                break
            time.sleep(1.0)
            continue

        status = backfill.get("status")
        processed = int(backfill.get("processed_this_run") or 0)
        cursor = int(backfill.get("cursor") or 0)
        total = int(backfill.get("total_targets") or 0)
        coverage = backfill.get("coverage") or {}
        usable_pct = float(coverage.get("usable_pct") or 0.0)

        RUNNER.set_progress({"current_step": "dart-backfill", "done": cursor, "targets": total})
        RUNNER.logs.append(
            f"[DART 배치 {cycle_count}] 진행: {cursor}/{total} 종목 ({usable_pct:.1f}% 커버리지, 이번 배치 {processed}개 적재)"
        )

        if processed == 0:
            consecutive_zero_runs += 1
        else:
            consecutive_zero_runs = 0

        # Terminate when cycle completed or no more retryables
        if status == "complete" or bool(backfill.get("cycle_complete")) or (consecutive_zero_runs >= 2 and not backfill.get("has_retryable")):
            RUNNER.logs.append("🎉 OpenDART 전 종목 재무 커버리지 백필 목표를 달성했습니다!")
            break

        time.sleep(0.2)

    RUNNER.logs.append("📊 수집된 전 종목 재무 데이터를 바탕으로 퀀트 순위 및 팩터 점수를 전체 재계산합니다...")
    result = run_from_staged(s, d, s.staged_dir / "live", source_mode="live")
    out = _summarize(result)
    out["dart_backfill"] = {
        key: value
        for key, value in last_backfill.items()
        if key not in {"ticker_order", "ticker_outcomes"}
    }
    out["dart_backfill"]["continuous_cycles_run"] = cycle_count
    from kr_quant.run_generation import load_manifest

    committed = load_manifest(s) or {}
    out["freshness"] = freshness_snapshot(s, screen_as_of=committed.get("as_of_date") or out.get("as_of_date"))
    out["pipeline_status"] = "partial" if out["freshness"].get("required_stale") else "success"
    return out


def probe_expected_krx(settings, as_of: date) -> dict[str, Any]:
    from kr_quant.ingest.live import krx_session_available

    return krx_session_available(settings, as_of)


def _publish_progress(settings, ledger: dict[str, Any]) -> None:
    from kr_quant.web.smart_ledger import STEPS, public_snapshot

    snap = public_snapshot(settings, ledger=ledger) or {}
    rows = snap.get("steps") or {}
    done = sum(1 for name in STEPS if (rows.get(name) or {}).get("status") not in {None, "pending", "running"})
    failed = sum(
        1
        for name in STEPS
        if (rows.get(name) or {}).get("status") in {"failed", "interrupted", "warning"}
    )
    snap.update({"targets": len(STEPS), "done": done, "failed": failed})
    RUNNER.set_progress(snap)


ESSENTIAL_REPAIR_MAX_BATCHES = 3


def job_smart_sync(
    as_of: str = "auto",
    lookback_days: int = 80,
    max_corps: int = 400,
    dart_batch_size: int = 50,
    trigger: str = "manual",
    mode: str = "normal",
) -> dict[str, Any]:
    """Artifact-aware self-healing daily sync driven by pipeline health/plan."""
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from kr_quant.freshness import wanted_price_date
    from kr_quant.ingest.live import backfill_dart_financials, build_live_master
    from kr_quant.web import smart_ledger as ledger_mod
    from kr_quant.web.pipeline_health import pipeline_health
    from kr_quant.web.pipeline_plan import VALID_MODES, InvalidPipelineMode, action_kinds, plan_pipeline

    mode = mode or "normal"
    if mode not in VALID_MODES:
        raise InvalidPipelineMode(f"invalid pipeline mode: {mode!r}")

    s = load_settings()
    expected = wanted_price_date() if not as_of or as_of == "auto" else date.fromisoformat(str(as_of)[:10])
    run_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    ledger = ledger_mod.begin_or_resume(
        s,
        run_date=run_date.isoformat(),
        expected_price_date=expected.isoformat(),
        trigger=trigger,
        mode=mode,
        runner_running=True,
    )
    _publish_progress(s, ledger)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    failure_kind: str | None = None
    _ = max_corps
    section_t0 = time.monotonic()
    live_dir = s.staged_dir / "live"

    def _lap() -> float:
        nonlocal section_t0
        elapsed = round(time.monotonic() - section_t0, 3)
        section_t0 = time.monotonic()
        return elapsed

    def _step_out(kind: str, label: str, **payload: Any) -> dict[str, Any]:
        row = {"kind": kind, "label": label, **payload, "duration_sec": _lap()}
        steps.append(row)
        return row

    def _health():
        # Do not pass busy=True: this job already owns the RUNNER slot.
        return pipeline_health(s, ledger=ledger)

    def _result(*, pipeline_status: str, next_action: str, cancelled: bool = False, **extra: Any) -> dict[str, Any]:
        final = _health()
        facts = ((final.get("components") or {}).get("dart_coverage") or {})
        out = {
            "kind": "smart-sync",
            "as_of": expected.isoformat(),
            "mode": mode,
            "trigger": trigger,
            "steps": steps,
            "warnings": warnings,
            "pipeline_status": pipeline_status,
            "failure_kind": failure_kind,
            "cancelled": cancelled,
            "health": final,
            "ledger": ledger_mod.public_snapshot(s, ledger=ledger),
            "dart_coverage": {
                "tickers": facts.get("tickers"),
                "universe_tickers": facts.get("universe_tickers"),
                "coverage_pct": facts.get("coverage_pct"),
                "target_pct": facts.get("target_pct") or 90.0,
            },
            "next_action": next_action,
            "used_in_quant": False,
        }
        out.update(extra)
        return out

    def _stop_if_cancelled() -> dict[str, Any] | None:
        if not RUNNER.cancel_requested():
            return None
        note = "중단 요청으로 현재 단계 경계에서 멈춥니다. 완료된 단계는 유지됩니다."
        RUNNER.logs.append(note)
        warnings.append(note)
        for name, step in (ledger.get("steps") or {}).items():
            if isinstance(step, dict) and step.get("status") == "running":
                ledger_mod.mark_step(ledger, name, "interrupted", s, detail=note)
        ledger_mod.finish(ledger, "interrupted", s)
        _publish_progress(s, ledger)
        return _result(
            pipeline_status="interrupted",
            cancelled=True,
            next_action="완료된 단계는 유지됩니다. 다시 누르면 남은 단계부터 이어갑니다.",
        )

    def _comp(health: dict[str, Any], name: str) -> dict[str, Any]:
        row = ((health.get("components") or {}).get(name) or {})
        return row if isinstance(row, dict) else {}

    def _state(health: dict[str, Any], name: str) -> str:
        return str(_comp(health, name).get("state") or "")

    def _verify_core(health: dict[str, Any], *names: str) -> bool:
        return all(_state(health, name) == "HEALTHY" for name in names)

    def _artifact_sig(path: Path) -> tuple[int, int] | None:
        if not path.exists():
            return None
        st = path.stat()
        return (int(st.st_mtime_ns), int(st.st_size))

    def _ensure_master(health: dict[str, Any]) -> dict[str, Any]:
        """Restore master.parquet from local KRX prerequisites when possible."""
        if _state(health, "master") == "HEALTHY":
            return health
        krx_master = live_dir / "krx_master.parquet"
        prices = live_dir / "prices.parquet"
        if krx_master.exists() and prices.exists():
            try:
                RUNNER.logs.append("로컬 KRX 전제로부터 master.parquet을 재구성합니다.")
                build_live_master(s, expected)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"master 로컬 복구 실패: {str(exc)[:160]}")
        return _health()

    def _run_krx(health: dict[str, Any], *, reason: str) -> dict[str, Any]:
        nonlocal failure_kind
        stopped = _stop_if_cancelled()
        if stopped:
            return {"_cancelled": stopped}
        needs_price = _state(health, "krx") in {"STALE", "MISSING", "CORRUPT"}
        needs_master = _state(health, "master") in {"MISSING", "CORRUPT"}
        if not needs_price and not needs_master:
            ledger_mod.mark_step(ledger, "krx", "skipped_fresh", s, detail="KRX/master 이미 정상")
            _step_out("krx", "KRX 시세", status="skipped_fresh", reason=reason)
            return {"health": health, "ok": True}

        if needs_price:
            ledger_mod.mark_step(ledger, "krx", "running", s, ran_this_pass=True)
            _publish_progress(s, ledger)
            RUNNER.logs.append(f"KRX {expected.isoformat()} 세션 준비 여부를 확인합니다. ({reason})")
            probe = probe_expected_krx(s, expected)
            if not probe.get("ready"):
                retryable = probe.get("retryable", True)
                probe_status = "source_not_ready" if retryable else "failed"
                retry_at = ledger_mod.schedule_krx_retry(ledger, s) if retryable else None
                detail = probe.get("error") or f"미준비 시장: {', '.join(probe.get('missing_markets') or []) or '전체'}"
                ledger_mod.mark_step(
                    ledger, "krx", probe_status, s,
                    retry_at=retry_at, detail=detail,
                    missing_markets=probe.get("missing_markets") or [],
                    failure_kind=probe.get("failure_kind"),
                    market_rows=probe.get("market_rows") or {},
                )
                failure_kind = "WAITING_SOURCE" if probe_status == "source_not_ready" else "VERIFY_FAILED"
                is_unpublished = probe.get("failure_kind") in (None, "not_published")
                msg = f"KRX {expected.isoformat()} " + ("자료 미준비" if is_unpublished else "인증·응답 오류")
                if retry_at:
                    msg += f" · {retry_at[11:16]} KST에 시세 단계만 재시도"
                elif retryable:
                    msg += " · 당일 자동 재시도 한도에 도달"
                else:
                    msg += " · 자동 반복 중단, API 설정·응답 형식 확인 후 스마트 실행으로 재시도"
                warnings.append(msg)
                RUNNER.logs.append(msg)
                _step_out("krx", "KRX 시세", status=probe_status, failure_kind=probe.get("failure_kind"), retry_at=retry_at)
                return {"health": _health(), "ok": False, "waiting_source": probe_status == "source_not_ready"}
            try:
                prices = job_krx_prices(expected.isoformat(), lookback_days)
                health = _ensure_master(_health())
                if _state(health, "krx") != "HEALTHY":
                    retry_at = ledger_mod.schedule_krx_retry(ledger, s)
                    ledger_mod.mark_step(
                        ledger, "krx", "source_not_ready", s,
                        retry_at=retry_at,
                        detail="세션 탐지/저장 후에도 health 기준 시세가 기대일에 못 미쳤습니다.",
                    )
                    failure_kind = "WAITING_SOURCE"
                    warnings.append(f"KRX {expected.isoformat()} 저장 후에도 시세 지연")
                    _step_out("krx", "KRX 시세", status="source_not_ready", verify="VERIFY_FAILED", retry_at=retry_at)
                    return {"health": health, "ok": False, "waiting_source": True}
                if _state(health, "master") != "HEALTHY":
                    ledger_mod.mark_step(
                        ledger, "krx", "verify_failed", s,
                        detail="KRX 작업 후에도 master.parquet이 정상화되지 않았습니다.",
                    )
                    failure_kind = "VERIFY_FAILED"
                    _step_out("krx", "KRX 시세", status="verify_failed")
                    return {"health": health, "ok": False}
                ledger_mod.mark_step(
                    ledger, "krx", "success", s, retry_at=None,
                    detail=f"price_rows={prices.get('price_rows')}",
                )
                _step_out("krx", "KRX 시세", status="success", price_rows=prices.get("price_rows"))
                RUNNER.logs.append(f"KRX 시세 {expected.isoformat()} 저장·검증 완료")
                return {"health": health, "ok": True}
            except Exception as exc:  # noqa: BLE001
                ledger_mod.mark_step(ledger, "krx", "failed", s, detail=str(exc)[:240])
                warnings.append(f"KRX 시세 실패: {str(exc)[:180]}")
                _step_out("krx", "KRX 시세", status="failed")
                failure_kind = "VERIFY_FAILED"
                return {"health": _health(), "ok": False}

        # prices healthy, master only
        health = _ensure_master(health)
        if _state(health, "master") == "HEALTHY":
            ledger_mod.mark_step(ledger, "krx", "success", s, detail="master 로컬 복구 완료", ran_this_pass=True)
            _step_out("krx", "KRX/master", status="success", reason="local_master_repair")
            return {"health": health, "ok": True}
        # fall through to network KRX refresh
        ledger_mod.mark_step(ledger, "krx", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        try:
            probe = probe_expected_krx(s, expected)
            if probe.get("ready"):
                job_krx_prices(expected.isoformat(), lookback_days)
            health = _ensure_master(_health())
            if _state(health, "master") != "HEALTHY" or _state(health, "krx") != "HEALTHY":
                ledger_mod.mark_step(ledger, "krx", "verify_failed", s, detail="master 복구 실패")
                failure_kind = "VERIFY_FAILED"
                _step_out("krx", "KRX/master", status="verify_failed")
                return {"health": health, "ok": False}
            ledger_mod.mark_step(ledger, "krx", "success", s, detail="master restored via KRX refresh")
            _step_out("krx", "KRX/master", status="success")
            return {"health": health, "ok": True}
        except Exception as exc:  # noqa: BLE001
            ledger_mod.mark_step(ledger, "krx", "failed", s, detail=str(exc)[:240])
            failure_kind = "VERIFY_FAILED"
            _step_out("krx", "KRX/master", status="failed")
            return {"health": _health(), "ok": False}

    def _run_dart_essential(health: dict[str, Any]) -> dict[str, Any]:
        nonlocal failure_kind
        stopped = _stop_if_cancelled()
        if stopped:
            return {"_cancelled": stopped}
        state = _state(health, "dart_essential")
        if state == "HEALTHY":
            ledger_mod.mark_step(ledger, "dart", "skipped_fresh", s, detail="필수 재무 artifact 정상")
            _step_out("dart", "OpenDART Essential", status="skipped_fresh")
            return {"health": health, "ok": True}
        if state == "CORRUPT":
            # Fail closed: do not delete or feed corrupt facts to Quant.
            ledger_mod.mark_step(
                ledger, "dart", "repair_incomplete", s,
                detail="financial_facts corrupt — reversible quarantine not implemented in A2",
            )
            failure_kind = "REPAIR_INCOMPLETE"
            _step_out("dart", "OpenDART Essential", status="repair_incomplete")
            warnings.append("재무 artifact가 손상되어 자동 복구하지 않습니다.")
            return {"health": health, "ok": False}
        if not getattr(s, "opendart_api_key", None):
            ledger_mod.mark_step(ledger, "dart", "repair_incomplete", s, detail="OpenDART API key missing")
            failure_kind = "REPAIR_INCOMPLETE"
            _step_out("dart", "OpenDART Essential", status="repair_incomplete")
            warnings.append("OpenDART 키가 없어 필수 재무 복구를 할 수 없습니다.")
            return {"health": health, "ok": False, "next_action": "OpenDART API 키를 설정한 뒤 자동 복구를 다시 실행하세요."}

        # Ledger/coverage success must not suppress missing-artifact repair.
        ledger_mod.mark_step(ledger, "dart", "running", s, ran_this_pass=True, detail="essential repair overrides ledger success")
        _publish_progress(s, ledger)
        batch_size = max(1, min(int(dart_batch_size or 50), 100))
        for i in range(ESSENTIAL_REPAIR_MAX_BATCHES):
            stopped = _stop_if_cancelled()
            if stopped:
                return {"_cancelled": stopped}
            RUNNER.logs.append(f"DART Essential 복구 배치 {i + 1}/{ESSENTIAL_REPAIR_MAX_BATCHES}")
            try:
                backfill_dart_financials(s, expected, batch_size=batch_size)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"DART Essential 배치 실패: {str(exc)[:160]}")
                ledger_mod.mark_step(ledger, "dart", "repair_incomplete", s, detail=str(exc)[:240])
                failure_kind = "REPAIR_INCOMPLETE"
                _step_out("dart", "OpenDART Essential", status="repair_incomplete")
                return {"health": _health(), "ok": False}
            health = _health()
            if _state(health, "dart_essential") == "HEALTHY":
                ledger_mod.mark_step(ledger, "dart", "success", s, detail=f"essential repaired in {i + 1} batch(es)")
                _step_out("dart", "OpenDART Essential", status="success", batches=i + 1)
                RUNNER.logs.append("DART Essential artifact 검증 통과")
                return {"health": health, "ok": True}
        ledger_mod.mark_step(ledger, "dart", "repair_incomplete", s, detail="bounded essential repair exhausted")
        failure_kind = "REPAIR_INCOMPLETE"
        _step_out("dart", "OpenDART Essential", status="repair_incomplete")
        return {"health": _health(), "ok": False}

    def _recent_filings_dirty(health: dict[str, Any]) -> bool:
        if _state(health, "dart_essential") != "HEALTHY":
            return False
        if not getattr(s, "opendart_api_key", None):
            return False
        if not (live_dir / "financial_facts.parquet").exists():
            return False
        from kr_quant.ingest.recent_filings import refresh_recent

        try:
            recent_check = refresh_recent(s)
            if recent_check.get("status") != "success":
                raise RuntimeError("최근 정정 공시 재무 대조 미완료")
            return bool(recent_check.get("refreshed_tickers")) or bool(recent_check.get("needs_recalculation"))
        except Exception:
            ledger_mod.mark_step(ledger, "quant", "failed", s, detail="recent_filings_failed")
            raise RuntimeError("DART 최근 공시 대조 실패: 재계산·공개 갱신 보류") from None

    def _run_quant(health: dict[str, Any], *, reason: str) -> dict[str, Any]:
        nonlocal failure_kind
        stopped = _stop_if_cancelled()
        if stopped:
            return {"_cancelled": stopped}
        if not _verify_core(health, "krx", "master", "dart_essential"):
            ledger_mod.mark_step(ledger, "quant", "blocked_dependency", s, detail="upstream not healthy")
            _step_out("quant", "퀀트 재계산", status="blocked_dependency")
            return {"health": health, "ok": False}

        try:
            dirty = _recent_filings_dirty(health)
        except RuntimeError as exc:
            failure_kind = "VERIFY_FAILED"
            warnings.append(str(exc))
            _step_out("quant", "퀀트 재계산", status="failed")
            return {"health": _health(), "ok": False}

        if _state(health, "quant") == "HEALTHY" and not dirty and reason != "maintenance_dirty":
            ledger_mod.mark_step(ledger, "quant", "skipped_fresh", s)
            _step_out("quant", "퀀트 재계산", status="skipped_fresh")
            return {"health": health, "ok": True}

        ledger_mod.mark_step(ledger, "quant", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        RUNNER.logs.append(f"퀀트 재계산 시작 ({reason})")
        try:
            live = job_live(expected.isoformat(), lookback_days, 0, skip_ingest=True)
            status = live.get("pipeline_status") or live.get("status") or "success"
            health = _health()
            if status == "error" or _state(health, "quant") != "HEALTHY":
                ledger_mod.mark_step(
                    ledger, "quant", "verify_failed", s,
                    detail="job returned success-like but committed quant health unhealthy"
                    if status != "error" else "job_live error",
                    as_of=live.get("as_of_date"),
                )
                failure_kind = "VERIFY_FAILED"
                _step_out("quant", "퀀트 재계산", status="verify_failed", job_status=status)
                return {"health": health, "ok": False}
            ledger_mod.mark_step(ledger, "quant", "success", s, as_of=live.get("as_of_date"))
            _step_out("quant", "퀀트 재계산", status="success", as_of=live.get("as_of_date"))
            RUNNER.logs.append("퀀트 재계산·검증 완료")
            return {"health": health, "ok": True}
        except Exception as exc:  # noqa: BLE001
            ledger_mod.mark_step(ledger, "quant", "failed", s, detail=str(exc)[:240])
            warnings.append(f"퀀트 재계산 실패: {str(exc)[:180]}")
            _step_out("quant", "퀀트 재계산", status="failed")
            failure_kind = "VERIFY_FAILED"
            return {"health": _health(), "ok": False}

    def _run_dart_maintenance(health: dict[str, Any]) -> dict[str, Any]:
        stopped = _stop_if_cancelled()
        if stopped:
            return {"_cancelled": stopped}
        if mode != "normal":
            return {"health": health, "changed": False}
        if _state(health, "dart_essential") != "HEALTHY":
            return {"health": health, "changed": False}
        facts_path = live_dir / "financial_facts.parquet"
        before = _artifact_sig(facts_path)
        batch_size = max(1, min(int(dart_batch_size or 50), 100))
        RUNNER.logs.append("DART maintenance 1배치 (normal only)")
        try:
            backfill_dart_financials(s, expected, batch_size=batch_size)
            after = _artifact_sig(facts_path)
            changed = before != after
            _step_out("dart_maintenance", "OpenDART maintenance", status="success", changed=changed)
            return {"health": _health(), "changed": changed}
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"DART maintenance 보류: {str(exc)[:160]}")
            _step_out("dart_maintenance", "OpenDART maintenance", status="warning")
            return {"health": _health(), "changed": False}

    def _run_kis(health: dict[str, Any]) -> dict[str, Any]:
        stopped = _stop_if_cancelled()
        if stopped:
            return {"_cancelled": stopped}
        kis_state = (ledger.get("steps") or {}).get("kis") or {}
        from kr_quant.flow.official import collection_is_current

        kis_current = not (s.kis_app_key and s.kis_app_secret) or collection_is_current(s)
        if ledger_mod.step_done(kis_state) and kis_state.get("status") != "pending" and kis_current:
            ledger_mod.mark_step(
                ledger, "kis",
                "skipped_already_success" if kis_state.get("status") == "success" else kis_state.get("status") or "skipped_already_success",
                s,
                detail="같은 날 이미 완료한 KIS 단계",
            )
            _step_out("kis", "KIS 수급", status="skipped_already_success")
            return {"health": health}
        if s.kis_app_key and s.kis_app_secret:
            ledger_mod.mark_step(ledger, "kis", "running", s, ran_this_pass=True)
            _publish_progress(s, ledger)
            try:
                from kr_quant.flow.official import collect_official

                flow = collect_official(s)
                status = flow.get("pipeline_status") or ("success" if not flow.get("errors") and flow.get("saved") else "partial")
                ledger_mod.mark_step(ledger, "kis", status, s, attempted=flow.get("attempted") or 0, saved=flow.get("saved") or 0)
                _step_out("kis", "KIS 수급", status=status, attempted=flow.get("attempted") or 0, saved=flow.get("saved") or 0)
                if flow.get("errors"):
                    warnings.append(f"KIS 일부 수집 실패 {len(flow.get('errors') or [])}건")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"KIS 수급 보류: {str(exc)[:180]}")
                ledger_mod.mark_step(ledger, "kis", "warning", s, detail=str(exc)[:240])
                _step_out("kis", "KIS 수급", status="warning")
        else:
            ledger_mod.mark_step(ledger, "kis", "skipped_not_configured", s)
            _step_out("kis", "KIS 수급", status="skipped_not_configured")
        return {"health": _health()}

    # ----- main flow -----
    health = _health()
    plan = plan_pipeline(health, mode=mode)
    planned = action_kinds(plan)
    RUNNER.logs.append(f"smart-sync mode={mode} plan={planned}")

    # KRX / master
    if "REFRESH_KRX" in planned or _state(health, "krx") != "HEALTHY" or _state(health, "master") != "HEALTHY":
        out = _run_krx(health, reason="plan_or_prerequisite")
        if out.get("_cancelled"):
            return out["_cancelled"]
        health = out["health"]
        # Non-ok KRX: still allow later DART essential repair; Quant stays blocked by health gates.
        _publish_progress(s, ledger)
    else:
        ledger_mod.mark_step(ledger, "krx", "skipped_fresh", s, detail="KRX/master already healthy")
        _step_out("krx", "KRX 시세", status="skipped_fresh")

    stopped = _stop_if_cancelled()
    if stopped:
        return stopped

    # Re-plan after KRX
    health = _health()
    plan = plan_pipeline(health, mode=mode)
    planned = action_kinds(plan)

    waiting_krx = _state(health, "krx") != "HEALTHY"
    master_ok = _state(health, "master") == "HEALTHY"

    # DART essential before Quant
    if "REPAIR_DART_ESSENTIAL" in planned or _state(health, "dart_essential") in {"MISSING", "CORRUPT"}:
        out = _run_dart_essential(health)
        if out.get("_cancelled"):
            return out["_cancelled"]
        health = out["health"]
        if not out.get("ok"):
            ledger_mod.mark_step(ledger, "publish", "blocked_dependency", s, detail="DART essential incomplete")
            overall = "failed"
            ledger_mod.finish(ledger, overall, s)
            _publish_progress(s, ledger)
            return _result(
                pipeline_status="failed",
                next_action=out.get("next_action") or "필수 재무 artifact 복구 후 다시 실행하세요.",
            )
        _publish_progress(s, ledger)
    else:
        ledger_mod.mark_step(ledger, "dart", "skipped_fresh", s, detail="필수 재무 artifact 정상")
        _step_out("dart", "OpenDART Essential", status="skipped_fresh")

    health = _health()
    plan = plan_pipeline(health, mode=mode)
    planned = action_kinds(plan)

    # Quant
    quant_needed = (
        "REBUILD_QUANT" in planned
        or _state(health, "quant") != "HEALTHY"
    )
    if waiting_krx or not master_ok or _state(health, "dart_essential") != "HEALTHY":
        ledger_mod.mark_step(ledger, "quant", "blocked_dependency", s, detail="upstream not ready")
        _step_out("quant", "퀀트 재계산", status="blocked_dependency")
        quant_ok = False
    elif quant_needed:
        out = _run_quant(health, reason="plan")
        if out.get("_cancelled"):
            return out["_cancelled"]
        health = out["health"]
        quant_ok = bool(out.get("ok"))
        if not quant_ok:
            ledger_mod.mark_step(ledger, "publish", "blocked_dependency", s, detail="Quant verify failed")
            ledger_mod.finish(ledger, "failed", s)
            _publish_progress(s, ledger)
            return _result(pipeline_status="failed", next_action="퀀트 산출물 검증 실패. 로그를 확인하세요.")
    else:
        ledger_mod.mark_step(ledger, "quant", "skipped_fresh", s)
        _step_out("quant", "퀀트 재계산", status="skipped_fresh")
        quant_ok = True

    # Optional maintenance (normal only)
    health = _health()
    plan = plan_pipeline(health, mode=mode)
    if mode == "normal" and "DART_MAINTENANCE_BATCH" in action_kinds(plan) and _state(health, "dart_essential") == "HEALTHY":
        out = _run_dart_maintenance(health)
        if out.get("_cancelled"):
            return out["_cancelled"]
        health = out["health"]
        if out.get("changed") and quant_ok and not waiting_krx and master_ok:
            outq = _run_quant(health, reason="maintenance_dirty")
            if outq.get("_cancelled"):
                return outq["_cancelled"]
            health = outq["health"]
            quant_ok = bool(outq.get("ok"))
            if not quant_ok:
                ledger_mod.finish(ledger, "failed", s)
                _publish_progress(s, ledger)
                return _result(pipeline_status="failed", next_action="maintenance 이후 퀀트 검증 실패")

    # KIS
    out = _run_kis(_health())
    if out.get("_cancelled"):
        return out["_cancelled"]
    health = out["health"]
    _publish_progress(s, ledger)

    # Final verification / publish readiness
    health = _health()
    core_ok = _verify_core(health, "krx", "master", "dart_essential", "quant")
    if failure_kind in {"VERIFY_FAILED", "REPAIR_INCOMPLETE"}:
        ledger_mod.mark_step(ledger, "publish", "blocked_dependency", s, detail=failure_kind)
        _step_out("publish", "공개판", status="blocked_dependency")
        overall = "failed"
    elif _state(health, "krx") != "HEALTHY":
        ledger_mod.mark_step(ledger, "publish", "blocked_stale", s, detail="시세가 기대일에 못 미침")
        _step_out("publish", "공개판", status="blocked_stale")
        overall = "partial" if failure_kind == "WAITING_SOURCE" or True else "partial"
    elif not core_ok:
        ledger_mod.mark_step(ledger, "publish", "blocked_dependency", s, detail="core not verified")
        _step_out("publish", "공개판", status="blocked_dependency")
        overall = "failed" if failure_kind else "partial"
    else:
        ledger_mod.mark_step(ledger, "publish", "queued", s, detail="품질 가드 통과 시에만 업로드")
        _step_out("publish", "공개판", status="queued")
        overall = "success"

    decided = ledger_mod.decide_overall(ledger, s)
    if decided == "failed":
        overall = "failed"
    elif warnings and overall == "success":
        overall = "partial"
    elif decided in {"partial", "blocked"} and overall == "success":
        overall = decided if decided != "blocked" else "partial"

    ledger_mod.finish(ledger, overall, s)
    _publish_progress(s, ledger)

    if failure_kind == "WAITING_SOURCE":
        next_action = "KRX 자료가 준비되면 시세 단계부터 다시 받습니다."
    elif overall == "failed":
        next_action = "필수 artifact 복구/검증 실패. 자동 복구 또는 로그를 확인하세요."
    elif overall == "success":
        next_action = "일일 데이터 정상화가 완료되었습니다."
    else:
        next_action = "일부 단계는 다음 실행에서 이어갑니다."

    return _result(pipeline_status=overall, next_action=next_action)


def _maybe_publish(kind: str) -> None:
    try:
        from kr_quant.web.publish import maybe_publish_after_job

        RUNNER.logs.append("공개판 갱신 가능 여부를 검사합니다.")
        publish_kind = "live" if kind in {"dart-backfill", "smart-sync"} else kind
        out = maybe_publish_after_job(publish_kind)
        if out is None:
            RUNNER.logs.append("이 작업은 공개 사이트 자동 배포 대상이 아닙니다.")
            return
        if out.get("ok"):
            RUNNER.logs.append(f"공개 사이트 갱신 완료: {out.get('url')}")
            if kind == "smart-sync":
                _record_publish_step("success", url=out.get("url"))
            return
        reason = str(out.get("error") or "배포 실패")
        blocked = bool(out.get("blocked")) or "PUBLICATION_BLOCKED" in reason
        if blocked:
            RUNNER.logs.append(f"공개판 안전 차단: {reason}")
            if kind == "smart-sync":
                _record_publish_step("blocked_stale", detail=reason)
            return
        RUNNER.logs.append(f"공개 사이트 배포 실패: {out.get('error')}")
        if kind == "smart-sync":
            _record_publish_step("failed", detail=reason)
    except Exception as exc:  # noqa: BLE001
        RUNNER.logs.append(f"공개 사이트 배포 생략: {exc}")
        if kind == "smart-sync":
            _record_publish_step("failed", detail=str(exc)[:240])


def _record_publish_step(status: str, **fields: Any) -> None:
    try:
        from kr_quant.web import smart_ledger as ledger_mod

        s = load_settings()
        ledger = ledger_mod.load_ledger(s)
        if not ledger:
            return
        ledger_mod.mark_step(ledger, "publish", status, s, **fields)
        if status in {"failed"}:
            ledger_mod.finish(ledger, "partial", s)
        _publish_progress(s, ledger)
    except Exception:  # noqa: BLE001
        pass


def _notify_job(kind: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    try:
        from kr_quant.ingest.telegram import format_job_error, format_screen_done, notify_safe

        s = load_settings()
        if error:
            text = format_job_error(kind, error)
        else:
            text = format_screen_done(result or {"status": kind})
        out = notify_safe(s.telegram_bot_token, s.telegram_chat_id, text)
        if out.get("ok"):
            RUNNER.logs.append("텔레그램 알림을 보냈습니다.")
        elif out.get("error"):
            RUNNER.logs.append(f"텔레그램 알림 실패: {out['error']}")
    except Exception as exc:  # noqa: BLE001
        RUNNER.logs.append(f"텔레그램 알림 생략: {exc}")


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    ctx = result["context"]
    top20 = result.get("top20")
    n20 = 0 if top20 is None or getattr(top20, "empty", True) else int(len(top20))
    names: list[dict[str, Any]] = []
    if top20 is not None and not getattr(top20, "empty", True):
        keep = [c for c in ("ticker", "company", "quant_score", "quant_rank") if c in top20.columns]
        for rec in top20.head(10)[keep].to_dict("records"):
            ticker = str(rec.get("ticker") or "").zfill(6)
            score = rec.get("quant_score")
            try:
                score = None if score is None else float(score)
            except (TypeError, ValueError):
                score = None
            names.append({"ticker": ticker, "company": rec.get("company"), "quant_score": score})
    return {
        "run_id": ctx.run_id,
        "status": ctx.status,
        "as_of_date": ctx.as_of_date.isoformat(),
        "warnings": ctx.warnings,
        "top20_count": n20,
        "result_hash": ctx.result_hash,
        "top": names,
    }
