from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from kr_quant.calendar import is_default_trading_day
from kr_quant.settings import load_settings

logger = logging.getLogger("kr_quant.scheduler")
KST = ZoneInfo("Asia/Seoul")
_STATE: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "next_fire": None,
    "last_fire": None,
    "last_error": None,
    "last_result": None,
}


def load_scheduler_config() -> dict[str, Any]:
    s = load_settings()
    path = s.root / "config" / "scheduler.yaml"
    if not path.exists():
        return {"enabled": False, "krx_prices": {"hour": 18, "minute": 30, "lookback_days": 10}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("krx_prices", {})
    data["krx_prices"].setdefault("hour", 18)
    data["krx_prices"].setdefault("minute", 30)
    data["krx_prices"].setdefault("lookback_days", 10)
    return data


def scheduler_status() -> dict[str, Any]:
    cfg = load_scheduler_config()
    return {
        **_STATE,
        "enabled": bool(cfg.get("enabled")) and bool(load_settings().krx_api_key),
        "hour": int((cfg.get("krx_prices") or {}).get("hour") or 18),
        "minute": int((cfg.get("krx_prices") or {}).get("minute") or 30),
        "lookback_days": int((cfg.get("krx_prices") or {}).get("lookback_days") or 10),
        "timezone": cfg.get("timezone") or "Asia/Seoul",
        "kind": "krx-prices",
        "used_in_quant": False,
    }


def _next_slot(cfg: dict[str, Any], now: datetime | None = None) -> datetime:
    hour = int((cfg.get("krx_prices") or {}).get("hour") or 18)
    minute = int((cfg.get("krx_prices") or {}).get("minute") or 30)
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    for _ in range(10):
        if is_default_trading_day(candidate.date()):
            return candidate
        candidate += timedelta(days=1)
    return candidate


def _fire() -> None:
    from kr_quant.web.jobs import RUNNER, job_krx_prices

    _STATE["last_fire"] = datetime.now(KST).isoformat()
    try:
        if RUNNER.snapshot().get("status") == "running":
            _STATE["last_error"] = "다른 작업이 실행 중이라 건너뜀"
            return
        snap = RUNNER.start("krx-prices", lambda: job_krx_prices("auto", lookback_days=int(scheduler_status()["lookback_days"])))
        _STATE["last_error"] = None
        _STATE["last_result"] = {"started": True, "kind": snap.get("kind")}
        logger.info("scheduled krx-prices job started")
    except Exception as exc:  # noqa: BLE001
        _STATE["last_error"] = str(exc)[:200]
        logger.warning("scheduled krx-prices skipped: %s", exc)


def _loop() -> None:
    while True:
        cfg = load_scheduler_config()
        s = load_settings()
        enabled = bool(cfg.get("enabled")) and bool(s.krx_api_key)
        _STATE["enabled"] = enabled
        if not enabled:
            _STATE["next_fire"] = None
            time.sleep(60)
            continue
        nxt = _next_slot(cfg)
        _STATE["next_fire"] = nxt.isoformat()
        wait = max(5.0, (nxt - datetime.now(KST)).total_seconds())
        time.sleep(min(wait, 3600))
        if datetime.now(KST) >= nxt - timedelta(seconds=2):
            _fire()
            time.sleep(70)


def start_price_scheduler() -> None:
    if _STATE.get("running"):
        return
    _STATE["running"] = True
    thread = threading.Thread(target=_loop, name="krx-price-scheduler", daemon=True)
    thread.start()
    logger.info("KRX price scheduler thread started")
