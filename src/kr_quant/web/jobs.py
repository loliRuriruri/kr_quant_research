from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import date, datetime, timezone
from typing import Any, Callable

import pandas as pd

from kr_quant.settings import load_settings


class _DequeHandler(logging.Handler):
    def __init__(self, buf: deque[str]) -> None:
        super().__init__(level=logging.INFO)
        self.buf = buf
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buf.append(self.format(record))
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
        }
        self.logs: deque[str] = deque(maxlen=400)
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {**self.state, "logs": list(self.logs)}

    def start(self, kind: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if self.state["status"] == "running":
                raise RuntimeError("이미 실행 중인 작업이 있습니다.")
            self.state = {
                "status": "running",
                "kind": kind,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "error": None,
                "result": None,
                "progress": None,
            }
            self.logs.clear()
            self.logs.append(f"작업 시작: {kind}")
        self._thread = threading.Thread(target=self._run, args=(kind, fn), daemon=True)
        self._thread.start()
        return self.snapshot()

    def is_running(self) -> bool:
        return self.snapshot().get("status") == "running"

    def set_progress(self, progress: dict[str, Any] | None) -> None:
        with self._lock:
            self.state["progress"] = progress

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
                self.state["status"] = finished_status
                self.state["result"] = result
                self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.logs.append(f"작업 {'일부 완료' if finished_status == 'partial' else '완료'}: {kind}")
            _maybe_publish(kind)
            _notify_job(kind, result=result)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.state["status"] = "error"
                self.state["error"] = str(exc)
                self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.logs.append(f"작업 실패: {exc}")
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
    if not skip_ingest:
        if not s.krx_api_key or not s.opendart_api_key:
            raise RuntimeError("실데이터 수집에는 KRX와 OpenDART 키가 필요합니다.")
        info["ingest"] = bootstrap_live(s, d, lookback_days=lookback_days, max_corps=max_corps)
    folder = s.staged_dir / "live"
    result = run_from_staged(s, d, folder, source_mode="live")
    out = _summarize(result)
    out["ingest"] = info.get("ingest")
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
    fresh = freshness_snapshot(s, screen_as_of=out.get("as_of_date"))
    out["freshness"] = fresh
    out["derived"] = derived
    out["pipeline_status"] = (
        "partial"
        if fresh.get("contract_status") != "ready" or any(item.get("status") == "error" for item in derived.values())
        else "success"
    )
    return out


HISTORY_DAYS = 750


def job_krx_prices(as_of: str = "auto", lookback_days: int = 10) -> dict[str, Any]:
    """KRX 일봉·마스터·거래상태를 받는다. OpenDART와 Quant 재계산은 하지 않는다."""
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import fetch_krx_master, fetch_krx_prices_range

    s = load_settings()
    if not s.krx_api_key:
        raise RuntimeError("KRX_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    days = max(3, min(int(lookback_days or 10), 40))
    master = fetch_krx_master(s, d)
    prices = fetch_krx_prices_range(s, d, lookback_days=days)
    status_rows = 0
    if s.status_csv.exists():
        status = pd.read_csv(s.status_csv, dtype={"ticker": str})
        status_rows = int((status["as_of_date"].astype(str) == d.isoformat()).sum())
    fresh = freshness_snapshot(s)
    return {
        "as_of": d.isoformat(),
        "kind": "krx-prices",
        "master_rows": int(len(master)),
        "price_rows": int(len(prices)),
        "status_rows": status_rows,
        "status_path": str(s.status_csv),
        "lookback_days": days,
        "freshness": fresh,
        "used_in_quant": False,
        "note": "KRX 시세·종목기본정보·당일 거래상태를 함께 갱신했습니다.",
    }


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


def job_dart_backfill(as_of: str = "auto", batch_size: int = 50) -> dict[str, Any]:
    """Advance DART full-universe coverage and re-score against the expanded facts."""
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import backfill_dart_financials
    from kr_quant.orchestration.run import run_from_staged

    s = load_settings()
    if not s.opendart_api_key:
        raise RuntimeError("OPENDART_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    backfill = backfill_dart_financials(s, d, batch_size=max(1, min(int(batch_size or 50), 500)))
    result = run_from_staged(s, d, s.staged_dir / "live", source_mode="live")
    out = _summarize(result)
    out["dart_backfill"] = {
        key: value
        for key, value in backfill.items()
        if key not in {"ticker_order", "ticker_outcomes"}
    }
    out["freshness"] = freshness_snapshot(s, screen_as_of=out.get("as_of_date"))
    out["pipeline_status"] = "partial" if out["freshness"].get("required_stale") else "success"
    return out


def probe_expected_krx(settings, as_of: date) -> dict[str, Any]:
    from kr_quant.ingest.live import krx_session_available

    return krx_session_available(settings, as_of)


def _publish_progress(settings, ledger: dict[str, Any]) -> None:
    from kr_quant.web.smart_ledger import public_snapshot

    RUNNER.set_progress(public_snapshot(settings, ledger=ledger))


def job_smart_sync(
    as_of: str = "auto",
    lookback_days: int = 80,
    max_corps: int = 400,
    dart_batch_size: int = 50,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Run only the maintenance steps the current snapshot still needs.

    KRX source-not-ready is not a day-slot success. The next retry fetches
    prices only and leaves a same-day DART/KIS success untouched.
    max_corps is kept for API compatibility; the daily path no longer repeats
    a 400-name bootstrap on top of the resumable DART batch.
    """
    from kr_quant.freshness import expected_price_date, freshness_snapshot
    from kr_quant.web import smart_ledger as ledger_mod

    from zoneinfo import ZoneInfo

    s = load_settings()
    expected = expected_price_date() if not as_of or as_of == "auto" else date.fromisoformat(str(as_of)[:10])
    run_date = datetime.now(ZoneInfo("Asia/Seoul")).date()
    ledger = ledger_mod.begin_or_resume(
        s,
        run_date=run_date.isoformat(),
        expected_price_date=expected.isoformat(),
        trigger=trigger,
        runner_running=True,
    )
    _publish_progress(s, ledger)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    before = freshness_snapshot(s)
    _ = max_corps  # API compatibility; daily DART work is the resumable batch.

    def _step_out(kind: str, label: str, **payload: Any) -> dict[str, Any]:
        row = {"kind": kind, "label": label, **payload}
        steps.append(row)
        return row

    # --- KRX ---
    price_fresh = not bool(before.get("stale_price"))
    if price_fresh:
        ledger_mod.mark_step(ledger, "krx", "skipped_fresh", s, detail="시세 기준일이 이미 기대일과 같습니다.")
        RUNNER.logs.append("[1/5] KRX 시세가 최신이라 재수집을 건너뜁니다.")
        _step_out("krx", "KRX 시세", status="skipped_fresh", as_of=before.get("price_max_date") or expected.isoformat())
    else:
        ledger_mod.mark_step(ledger, "krx", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        RUNNER.logs.append(f"[1/5] KRX {expected.isoformat()} 세션 준비 여부를 확인합니다.")
        probe = probe_expected_krx(s, expected)
        if not probe.get("ready"):
            retry_at = ledger_mod.schedule_krx_retry(ledger, s)
            detail = probe.get("error") or f"미준비 시장: {', '.join(probe.get('missing_markets') or []) or '전체'}"
            ledger_mod.mark_step(
                ledger,
                "krx",
                "source_not_ready",
                s,
                retry_at=retry_at,
                detail=detail,
                missing_markets=probe.get("missing_markets") or [],
            )
            msg = f"KRX {expected.isoformat()} 자료 미준비"
            if retry_at:
                msg += f" · {retry_at[11:16]} KST에 시세 단계만 재시도"
            else:
                msg += " · 당일 자동 재시도 한도에 도달"
            warnings.append(msg)
            RUNNER.logs.append(f"[1/5] {msg}")
            _step_out(
                "krx",
                "KRX 시세",
                status="source_not_ready",
                as_of=expected.isoformat(),
                retry_at=retry_at,
                attempt=(ledger.get("steps") or {}).get("krx", {}).get("attempt"),
            )
        else:
            try:
                prices = job_krx_prices(expected.isoformat(), lookback_days)
                after_prices = freshness_snapshot(s)
                if after_prices.get("stale_price"):
                    retry_at = ledger_mod.schedule_krx_retry(ledger, s)
                    ledger_mod.mark_step(
                        ledger,
                        "krx",
                        "source_not_ready",
                        s,
                        retry_at=retry_at,
                        detail="세션 탐지는 됐으나 저장 시세가 기대일에 못 미쳤습니다.",
                    )
                    warnings.append(f"KRX {expected.isoformat()} 저장 후에도 시세 지연")
                    _step_out("krx", "KRX 시세", status="source_not_ready", as_of=expected.isoformat(), retry_at=retry_at)
                    RUNNER.logs.append("[1/5] KRX 저장 후에도 기대 기준일이 비어 시세 단계만 재시도합니다.")
                else:
                    ledger_mod.mark_step(
                        ledger,
                        "krx",
                        "success",
                        s,
                        retry_at=None,
                        detail=f"price_rows={prices.get('price_rows')}",
                    )
                    RUNNER.logs.append(f"[1/5] KRX 시세 {expected.isoformat()} 저장 완료")
                    _step_out("krx", "KRX 시세", status="success", as_of=expected.isoformat(), price_rows=prices.get("price_rows"))
            except Exception as exc:  # noqa: BLE001
                ledger_mod.mark_step(ledger, "krx", "failed", s, detail=str(exc)[:240])
                warnings.append(f"KRX 시세 실패: {str(exc)[:180]}")
                RUNNER.logs.append(f"[1/5] KRX 시세 실패: {exc}")
                _step_out("krx", "KRX 시세", status="failed")
    _publish_progress(s, ledger)

    krx_ok = ledger_mod.step_done((ledger.get("steps") or {}).get("krx"))

    # --- Quant ---
    current = freshness_snapshot(s)
    quant = ((current.get("sources") or {}).get("quant_ranking") or {})
    if not krx_ok:
        ledger_mod.mark_step(ledger, "quant", "blocked_dependency", s, detail="KRX 시세가 기대일에 도달할 때까지 점수를 다시 계산하지 않습니다.")
        RUNNER.logs.append("[2/5] 퀀트는 KRX 선행 단계가 막혀 건너뜁니다.")
        _step_out("quant", "퀀트 재계산", status="blocked_dependency")
    elif quant.get("state") == "fresh":
        ledger_mod.mark_step(ledger, "quant", "skipped_fresh", s)
        RUNNER.logs.append("[2/5] 퀀트 기준일이 시세와 같아 재계산을 건너뜁니다.")
        _step_out("quant", "퀀트 재계산", status="skipped_fresh", as_of=current.get("screen_as_of"))
    else:
        ledger_mod.mark_step(ledger, "quant", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        RUNNER.logs.append("[2/5] 시세 기준일로 퀀트와 파생 캐시를 다시 계산합니다.")
        try:
            live = job_live(expected.isoformat(), lookback_days, 0, skip_ingest=True)
            status = live.get("pipeline_status") or live.get("status") or "success"
            ledger_mod.mark_step(ledger, "quant", "success" if status != "error" else "failed", s, as_of=live.get("as_of_date"))
            _step_out("quant", "퀀트 재계산", status="success" if status != "error" else "failed", as_of=live.get("as_of_date"))
            RUNNER.logs.append("[2/5] 퀀트 재계산 완료")
        except Exception as exc:  # noqa: BLE001
            ledger_mod.mark_step(ledger, "quant", "failed", s, detail=str(exc)[:240])
            warnings.append(f"퀀트 재계산 실패: {str(exc)[:180]}")
            _step_out("quant", "퀀트 재계산", status="failed")
            RUNNER.logs.append(f"[2/5] 퀀트 재계산 실패: {exc}")
    _publish_progress(s, ledger)

    # --- DART ---
    current = freshness_snapshot(s)
    facts = ((current.get("sources") or {}).get("financial_facts") or {})
    coverage_info = facts.get("coverage") or {}
    coverage = coverage_info.get("usable_pct")
    if coverage is None:
        coverage = coverage_info.get("coverage_pct")
    dart_state = (ledger.get("steps") or {}).get("dart") or {}
    from kr_quant.ingest.live import needs_more_dart_backfill

    if ledger_mod.step_done(dart_state) and dart_state.get("status") != "pending":
        ledger_mod.mark_step(
            ledger,
            "dart",
            "skipped_already_success" if dart_state.get("status") == "success" else dart_state.get("status") or "skipped_already_success",
            s,
            detail="같은 날 이미 완료한 DART 단계를 다시 돌리지 않습니다.",
        )
        RUNNER.logs.append("[3/5] DART는 오늘 이미 끝나 재실행하지 않습니다.")
        _step_out(
            "dart",
            "OpenDART 백필",
            status="skipped_already_success" if dart_state.get("status") == "success" else dart_state.get("status"),
            coverage_pct=coverage,
        )
    elif needs_more_dart_backfill(coverage_info, facts.get("backfill")):
        ledger_mod.mark_step(ledger, "dart", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        try:
            RUNNER.logs.append(f"[3/5] DART 커버리지 {coverage or 0}% · 다음 {dart_batch_size}종목을 이어서 수집합니다.")
            dart = job_dart_backfill(expected.isoformat(), max(1, min(int(dart_batch_size or 50), 100)))
            progress = dart.get("dart_backfill") or {}
            ledger_mod.mark_step(
                ledger,
                "dart",
                progress.get("status") or "success",
                s,
                processed=progress.get("processed_this_run") or 0,
                covered_tickers=progress.get("covered_tickers"),
                coverage_pct=progress.get("coverage_pct"),
            )
            _step_out(
                "dart",
                "OpenDART 전 종목 커버리지 1배치",
                status=progress.get("status") or "success",
                processed=progress.get("processed_this_run") or 0,
                covered_tickers=progress.get("covered_tickers"),
                coverage_pct=progress.get("coverage_pct"),
            )
            RUNNER.logs.append(f"[3/5] DART 백필 완료 · 커버리지 {progress.get('coverage_pct') or coverage or 0}%")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"DART 백필 보류: {str(exc)[:180]}")
            ledger_mod.mark_step(ledger, "dart", "warning", s, detail=str(exc)[:240])
            _step_out("dart", "OpenDART 전 종목 커버리지 1배치", status="warning")
    else:
        ledger_mod.mark_step(ledger, "dart", "skipped_sufficient", s, coverage_pct=coverage)
        RUNNER.logs.append(f"[3/5] DART 커버리지 {coverage}%로 목표를 충족해 백필을 건너뜁니다.")
        _step_out("dart", "OpenDART 커버리지 확인", status="skipped_sufficient", coverage_pct=coverage)
    _publish_progress(s, ledger)

    # --- KIS ---
    kis_state = (ledger.get("steps") or {}).get("kis") or {}
    if ledger_mod.step_done(kis_state) and kis_state.get("status") != "pending":
        ledger_mod.mark_step(
            ledger,
            "kis",
            "skipped_already_success" if kis_state.get("status") == "success" else kis_state.get("status") or "skipped_already_success",
            s,
            detail="같은 날 이미 완료한 KIS 단계를 다시 돌리지 않습니다.",
        )
        RUNNER.logs.append("[4/5] KIS 수급은 오늘 이미 끝나 재실행하지 않습니다.")
        _step_out("kis", "KIS 수급", status="skipped_already_success" if kis_state.get("status") == "success" else kis_state.get("status"))
    elif s.kis_app_key and s.kis_app_secret:
        ledger_mod.mark_step(ledger, "kis", "running", s, ran_this_pass=True)
        _publish_progress(s, ledger)
        try:
            from kr_quant.flow.official import collect_official

            RUNNER.logs.append("[4/5] KIS 관심·고유동성 종목 수급을 갱신합니다.")
            flow = collect_official(s)
            status = "success" if not flow.get("errors") else "partial"
            ledger_mod.mark_step(
                ledger,
                "kis",
                status,
                s,
                attempted=flow.get("attempted") or 0,
                saved=flow.get("saved") or 0,
            )
            _step_out(
                "kis",
                "KIS 관심·고유동성 수급",
                status=status,
                attempted=flow.get("attempted") or 0,
                saved=flow.get("saved") or 0,
            )
            if flow.get("errors"):
                warnings.append(f"KIS 일부 수집 실패 {len(flow.get('errors') or [])}건")
            RUNNER.logs.append(f"[4/5] KIS 수급 완료 · {flow.get('saved') or 0}행 저장")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"KIS 수급 보류: {str(exc)[:180]}")
            ledger_mod.mark_step(ledger, "kis", "warning", s, detail=str(exc)[:240])
            _step_out("kis", "KIS 관심·고유동성 수급", status="warning")
    else:
        ledger_mod.mark_step(ledger, "kis", "skipped_not_configured", s)
        RUNNER.logs.append("[4/5] KIS 키가 없어 수급 갱신을 건너뜁니다.")
        _step_out("kis", "KIS 수급", status="skipped_not_configured")
    _publish_progress(s, ledger)

    # --- Publish readiness (actual upload stays in JobRunner._maybe_publish) ---
    RUNNER.logs.append("[5/5] 최종 최신성·품질 계약을 확인합니다.")
    final = freshness_snapshot(s)
    if final.get("stale_price") or final.get("contract_status") == "blocked":
        ledger_mod.mark_step(
            ledger,
            "publish",
            "blocked_stale",
            s,
            detail="시세가 기대일에 못 미쳐 공개판을 올리지 않습니다.",
        )
        _step_out("publish", "공개판", status="blocked_stale")
        RUNNER.logs.append("[5/5] 공개판은 시세 지연으로 안전 차단합니다.")
    elif not ledger_mod.step_done((ledger.get("steps") or {}).get("quant")):
        ledger_mod.mark_step(ledger, "publish", "blocked_dependency", s, detail="퀀트 단계가 끝나지 않았습니다.")
        _step_out("publish", "공개판", status="blocked_dependency")
    else:
        ledger_mod.mark_step(ledger, "publish", "queued", s, detail="품질 가드 통과 시에만 업로드합니다.")
        _step_out("publish", "공개판", status="queued")

    overall = ledger_mod.decide_overall(ledger, s)
    if warnings and overall == "success":
        overall = "partial"
    ledger_mod.finish(ledger, overall, s)
    _publish_progress(s, ledger)

    final_facts = (((final.get("sources") or {}).get("financial_facts") or {}).get("coverage") or {})
    krx_step = (ledger.get("steps") or {}).get("krx") or {}
    if krx_step.get("status") == "source_not_ready" and krx_step.get("retry_at"):
        next_action = f"KRX 자료가 준비되면 {str(krx_step.get('retry_at'))[11:16]} KST에 시세 단계만 다시 받습니다."
    elif (final_facts.get("coverage_pct") or 0) < 90:
        next_action = "다음 예약 실행에서 DART 백필을 이어갑니다."
    elif overall == "success":
        next_action = "일일 데이터 정상화가 완료되었습니다."
    else:
        next_action = "일부 단계는 다음 실행에서 이어갑니다."

    return {
        "kind": "smart-sync",
        "as_of": expected.isoformat(),
        "steps": steps,
        "warnings": warnings,
        "pipeline_status": overall,
        "freshness": final,
        "ledger": ledger_mod.public_snapshot(s, ledger=ledger),
        "dart_coverage": {
            "tickers": final_facts.get("tickers"),
            "universe_tickers": final_facts.get("universe_tickers"),
            "coverage_pct": final_facts.get("coverage_pct"),
            "target_pct": 90.0,
        },
        "next_action": next_action,
        "used_in_quant": False,
    }


def _maybe_publish(kind: str) -> None:
    try:
        from kr_quant.web.publish import maybe_publish_after_job

        RUNNER.logs.append("공개 스냅샷을 Cloudflare Pages에 올리는 중… (API 키는 로컬에만 있습니다)")
        publish_kind = "live" if kind in {"dart-backfill", "smart-sync"} else kind
        out = maybe_publish_after_job(publish_kind)
        if out is None:
            RUNNER.logs.append("이 작업은 공개 사이트 자동 배포 대상이 아닙니다.")
            return
        if out.get("ok"):
            RUNNER.logs.append(f"공개 사이트 갱신 완료: {out.get('url')}")
            if kind == "smart-sync":
                _record_publish_step("success", url=out.get("url"))
        else:
            reason = str(out.get("error") or "배포 실패")
            blocked = "차단" in reason or "PRICE_DATA_STALE" in reason or "AS_OF_DATE_MISMATCH" in reason
            RUNNER.logs.append(f"공개 사이트 배포 실패: {out.get('error')}" if not blocked else f"공개판 안전 차단: {out.get('error')}")
            if kind == "smart-sync":
                _record_publish_step("blocked_stale" if blocked else "failed", detail=reason)
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
