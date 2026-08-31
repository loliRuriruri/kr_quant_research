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
            }
            self.logs.clear()
            self.logs.append(f"작업 시작: {kind}")
        self._thread = threading.Thread(target=self._run, args=(kind, fn), daemon=True)
        self._thread.start()
        return self.snapshot()

    def _run(self, kind: str, fn: Callable[[], dict[str, Any]]) -> None:
        logger = logging.getLogger("kr_quant")
        handler = _DequeHandler(self.logs)
        logger.addHandler(handler)
        try:
            result = fn()
            finished_status = "partial" if result.get("pipeline_status") == "partial" else "success"
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
    out["dart_backfill"] = {key: value for key, value in backfill.items() if key != "ticker_order"}
    out["freshness"] = freshness_snapshot(s, screen_as_of=out.get("as_of_date"))
    out["pipeline_status"] = "partial" if out["freshness"].get("required_stale") else "success"
    return out


def job_smart_sync(
    as_of: str = "auto",
    lookback_days: int = 80,
    max_corps: int = 400,
    dart_batch_size: int = 50,
) -> dict[str, Any]:
    """Run only the maintenance steps that the current local snapshot needs.

    The daily action deliberately limits the full-universe DART work to one
    resumable batch.  This keeps the one-click path bounded while steadily
    improving coverage on every successful trading-day run.
    """
    from kr_quant.freshness import freshness_snapshot

    s = load_settings()
    d = resolve_as_of(as_of)
    before = freshness_snapshot(s)
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []

    quant = ((before.get("sources") or {}).get("quant_ranking") or {})
    needs_core_refresh = bool(before.get("stale_price")) or quant.get("state") != "fresh"
    if needs_core_refresh:
        RUNNER.logs.append("[1/4] KRX·OpenDART 우선수집과 퀀트 재계산을 시작합니다.")
        live = job_live(as_of, lookback_days, max_corps, skip_ingest=False)
        steps.append(
            {
                "kind": "live",
                "label": "KRX·OpenDART 우선수집·퀀트 재계산",
                "status": live.get("pipeline_status") or live.get("status") or "success",
                "as_of": live.get("as_of_date") or d.isoformat(),
            }
        )
        RUNNER.logs.append("[1/4] 시세·퀀트 갱신 완료")
    else:
        steps.append(
            {
                "kind": "live",
                "label": "KRX·퀀트 기준일 확인",
                "status": "skipped_fresh",
                "as_of": before.get("screen_as_of") or d.isoformat(),
            }
        )
        RUNNER.logs.append("[1/4] 시세·퀀트가 최신이라 무거운 재수집을 건너뜁니다.")

    current = freshness_snapshot(s)
    facts = ((current.get("sources") or {}).get("financial_facts") or {})
    coverage = (facts.get("coverage") or {}).get("coverage_pct")
    if coverage is None or float(coverage) < 90.0:
        try:
            RUNNER.logs.append(f"[2/4] DART 커버리지 {coverage or 0}% · 다음 {dart_batch_size}종목을 이어서 수집합니다.")
            dart = job_dart_backfill(as_of, max(1, min(int(dart_batch_size or 50), 100)))
            progress = dart.get("dart_backfill") or {}
            steps.append(
                {
                    "kind": "dart-backfill",
                    "label": "OpenDART 전 종목 커버리지 1배치",
                    "status": progress.get("status") or "success",
                    "processed": progress.get("processed_this_run") or 0,
                    "covered_tickers": progress.get("covered_tickers"),
                    "coverage_pct": progress.get("coverage_pct"),
                }
            )
            RUNNER.logs.append(f"[2/4] DART 백필 완료 · 커버리지 {progress.get('coverage_pct') or coverage or 0}%")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"DART 백필 보류: {str(exc)[:180]}")
            steps.append({"kind": "dart-backfill", "label": "OpenDART 전 종목 커버리지 1배치", "status": "warning"})
    else:
        steps.append(
            {
                "kind": "dart-backfill",
                "label": "OpenDART 커버리지 확인",
                "status": "skipped_sufficient",
                "coverage_pct": coverage,
            }
        )
        RUNNER.logs.append(f"[2/4] DART 커버리지 {coverage}%로 목표를 충족해 백필을 건너뜁니다.")

    if s.kis_app_key and s.kis_app_secret:
        try:
            from kr_quant.flow.official import collect_official

            RUNNER.logs.append("[3/4] KIS 관심·고유동성 종목 수급을 갱신합니다.")
            flow = collect_official(s)
            steps.append(
                {
                    "kind": "investor-kis",
                    "label": "KIS 관심·고유동성 수급",
                    "status": "success" if not flow.get("errors") else "partial",
                    "attempted": flow.get("attempted") or 0,
                    "saved": flow.get("saved") or 0,
                }
            )
            if flow.get("errors"):
                warnings.append(f"KIS 일부 수집 실패 {len(flow.get('errors') or [])}건")
            RUNNER.logs.append(f"[3/4] KIS 수급 완료 · {flow.get('saved') or 0}행 저장")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"KIS 수급 보류: {str(exc)[:180]}")
            steps.append({"kind": "investor-kis", "label": "KIS 관심·고유동성 수급", "status": "warning"})
    else:
        steps.append({"kind": "investor-kis", "label": "KIS 수급", "status": "skipped_not_configured"})
        RUNNER.logs.append("[3/4] KIS 키가 없어 수급 갱신을 건너뜁니다.")

    RUNNER.logs.append("[4/4] 최종 최신성·품질 계약을 확인합니다.")
    final = freshness_snapshot(s)
    final_facts = (((final.get("sources") or {}).get("financial_facts") or {}).get("coverage") or {})
    has_required_stale = bool(final.get("required_stale"))
    return {
        "kind": "smart-sync",
        "as_of": d.isoformat(),
        "steps": steps,
        "warnings": warnings,
        "pipeline_status": "partial" if has_required_stale or warnings else "success",
        "freshness": final,
        "dart_coverage": {
            "tickers": final_facts.get("tickers"),
            "universe_tickers": final_facts.get("universe_tickers"),
            "coverage_pct": final_facts.get("coverage_pct"),
            "target_pct": 90.0,
        },
        "next_action": (
            "다음 예약 실행에서 DART 백필을 이어갑니다."
            if (final_facts.get("coverage_pct") or 0) < 90
            else "일일 데이터 정상화가 완료되었습니다."
        ),
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
        else:
            RUNNER.logs.append(f"공개 사이트 배포 실패: {out.get('error')}")
    except Exception as exc:  # noqa: BLE001
        RUNNER.logs.append(f"공개 사이트 배포 생략: {exc}")


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
