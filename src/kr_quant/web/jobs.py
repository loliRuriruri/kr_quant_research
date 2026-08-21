from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import date, datetime, timezone
from typing import Any, Callable

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
            with self._lock:
                self.state["status"] = "success"
                self.state["result"] = result
                self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.logs.append(f"작업 완료: {kind}")
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
    result = run_from_staged(s, d, folder)
    return _summarize(result)


def job_live(as_of: str, lookback_days: int, max_corps: int, skip_ingest: bool) -> dict[str, Any]:
    from kr_quant.ingest.live import bootstrap_live
    from kr_quant.orchestration.run import run_from_staged

    s = load_settings()
    d = resolve_as_of(as_of)
    info: dict[str, Any] = {"as_of": d.isoformat()}
    if not skip_ingest:
        if not s.krx_api_key or not s.opendart_api_key:
            raise RuntimeError("실데이터 수집에는 KRX와 OpenDART 키가 필요합니다.")
        info["ingest"] = bootstrap_live(s, d, lookback_days=lookback_days, max_corps=max_corps)
    folder = s.staged_dir / "live"
    result = run_from_staged(s, d, folder)
    out = _summarize(result)
    out["ingest"] = info.get("ingest")
    return out


HISTORY_DAYS = 750


def job_krx_prices(as_of: str = "auto", lookback_days: int = 10) -> dict[str, Any]:
    """KRX 일봉·마스터만 받는다. OpenDART와 Quant 재계산은 하지 않는다."""
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import fetch_krx_master, fetch_krx_prices_range

    s = load_settings()
    if not s.krx_api_key:
        raise RuntimeError("KRX_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    days = max(3, min(int(lookback_days or 10), 40))
    master = fetch_krx_master(s, d)
    prices = fetch_krx_prices_range(s, d, lookback_days=days)
    fresh = freshness_snapshot(s)
    return {
        "as_of": d.isoformat(),
        "kind": "krx-prices",
        "master_rows": int(len(master)),
        "price_rows": int(len(prices)),
        "lookback_days": days,
        "freshness": fresh,
        "used_in_quant": False,
        "note": "시세만 갱신했습니다.",
    }


def job_krx_history(as_of: str = "auto", lookback_days: int = HISTORY_DAYS) -> dict[str, Any]:
    """이미 있는 날짜는 건너뛰고, 과거 거래일을 더 받아 전략·모멘텀 이력을 채운다."""
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.ingest.live import fetch_krx_master, fetch_krx_prices_range

    s = load_settings()
    if not s.krx_api_key:
        raise RuntimeError("KRX_API_KEY가 없습니다.")
    d = resolve_as_of(as_of)
    days = max(80, min(int(lookback_days or HISTORY_DAYS), 1250))
    master = fetch_krx_master(s, d)
    prices = fetch_krx_prices_range(s, d, lookback_days=days, sleep_sec=0.08)
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
        "lookback_days": days,
        "freshness": fresh,
        "used_in_quant": False,
        "note": f"KRX 일봉을 최대 {days}거래일까지 채웠습니다. 전략 랩은 이력이 늘어난 뒤 다시 돌리세요.",
    }


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
