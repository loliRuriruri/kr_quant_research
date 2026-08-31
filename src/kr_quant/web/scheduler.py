from __future__ import annotations

import json
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


def _runtime_state_path():
    return load_settings().root / "logs" / "scheduler_state.json"


def _restore_runtime_state() -> None:
    path = _runtime_state_path()
    if not path.exists():
        return
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for key in ("last_fire", "last_error", "last_result"):
        if key in saved:
            _STATE[key] = saved[key]


def _persist_runtime_state() -> None:
    path = _runtime_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: _STATE.get(key) for key in ("last_fire", "last_error", "last_result")}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_scheduler_config() -> dict[str, Any]:
    s = load_settings()
    path = s.root / "config" / "scheduler.yaml"
    if not path.exists():
        return {
            "enabled": False,
            "job_kind": "smart-sync",
            "hour": 19,
            "minute": 10,
            "lookback_days": 80,
            "official_flow": True,
            "timezone": "Asia/Seoul",
            "krx_prices": {"hour": 19, "minute": 10, "lookback_days": 80, "official_flow": True},
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kp = data.get("krx_prices") or {}
    hour = int(data.get("hour", kp.get("hour", 19)))
    minute = int(data.get("minute", kp.get("minute", 10)))
    lookback = int(data.get("lookback_days", kp.get("lookback_days", 80)))
    job_kind = data.get("job_kind", "smart-sync")
    enabled = bool(data.get("enabled", False))
    official_flow = bool(data.get("official_flow", kp.get("official_flow", True)))
    return {
        "enabled": enabled,
        "job_kind": job_kind,
        "hour": hour,
        "minute": minute,
        "lookback_days": lookback,
        "official_flow": official_flow,
        "timezone": data.get("timezone", "Asia/Seoul"),
        "krx_prices": {
            "hour": hour,
            "minute": minute,
            "lookback_days": lookback,
            "official_flow": official_flow,
        },
    }


def save_scheduler_config(cfg: dict[str, Any]) -> dict[str, Any]:
    s = load_settings()
    path = s.root / "config" / "scheduler.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    existing = load_scheduler_config()
    existing.update(cfg)
    hour = int(existing.get("hour", 19))
    minute = int(existing.get("minute", 10))
    lookback = int(existing.get("lookback_days", 80))
    official_flow = bool(existing.get("official_flow", True))
    raw.update(
        {
            "enabled": bool(existing.get("enabled")),
            "job_kind": existing.get("job_kind") or "smart-sync",
            "hour": hour,
            "minute": minute,
            "lookback_days": lookback,
            "official_flow": official_flow,
            "timezone": existing.get("timezone") or "Asia/Seoul",
        }
    )
    raw["krx_prices"] = {
        "hour": hour,
        "minute": minute,
        "lookback_days": lookback,
        "official_flow": official_flow,
    }
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return scheduler_status()


def scheduler_status() -> dict[str, Any]:
    cfg = load_scheduler_config()
    s = load_settings()
    job_kind = cfg.get("job_kind") or "smart-sync"
    enabled = bool(cfg.get("enabled")) and (bool(s.krx_api_key) or job_kind == "demo")
    from kr_quant.web.publish import publish_status

    return {
        **_STATE,
        "enabled": enabled,
        "publish_public": publish_status(),
        "job_kind": job_kind,
        "hour": int(cfg.get("hour") or 19),
        "minute": int(cfg.get("minute") or 10),
        "lookback_days": int(cfg.get("lookback_days") or 80),
        "official_flow": bool(cfg.get("official_flow", True)),
        "timezone": cfg.get("timezone") or "Asia/Seoul",
        "krx_prices": cfg.get("krx_prices") or {},
        "kind": job_kind,
        "used_in_quant": False,
    }


def _next_slot(cfg: dict[str, Any], now: datetime | None = None) -> datetime:
    hour = int(cfg.get("hour") or (cfg.get("krx_prices") or {}).get("hour") or 18)
    minute = int(cfg.get("minute") or (cfg.get("krx_prices") or {}).get("minute") or 30)
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


def _scheduled_evening() -> dict[str, Any]:
    from kr_quant.web.jobs import job_krx_prices

    cfg = load_scheduler_config()
    lookback = int(cfg.get("lookback_days") or (cfg.get("krx_prices") or {}).get("lookback_days") or 10)
    out = job_krx_prices("auto", lookback_days=lookback)
    want_flow = bool(cfg.get("official_flow", (cfg.get("krx_prices") or {}).get("official_flow", True)))
    if want_flow:
        try:
            from kr_quant.flow.official import collect_official
            from kr_quant.settings import load_settings as _ls

            out["official_flow"] = collect_official(_ls())
        except Exception as exc:  # noqa: BLE001
            out["official_flow_error"] = str(exc)[:180]
            logger.warning("scheduled official flow skipped: %s", exc)
    return out


def _scheduled_live() -> dict[str, Any]:
    from kr_quant.web.jobs import job_live

    cfg = load_scheduler_config()
    lookback = int(cfg.get("lookback_days") or 80)
    return job_live("auto", lookback_days=lookback, max_corps=400, skip_ingest=False)


def _scheduled_smart() -> dict[str, Any]:
    from kr_quant.web.jobs import job_smart_sync

    cfg = load_scheduler_config()
    lookback = int(cfg.get("lookback_days") or 80)
    return job_smart_sync("auto", lookback_days=lookback, max_corps=400, dart_batch_size=50)


def _catch_up_due(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    """Return true once when today's scheduled maintenance was missed."""
    current = (now or datetime.now(KST)).astimezone(KST)
    if not is_default_trading_day(current.date()):
        return False
    scheduled = current.replace(
        hour=int(cfg.get("hour") or 19),
        minute=int(cfg.get("minute") or 10),
        second=0,
        microsecond=0,
    )
    if current < scheduled:
        return False
    last_fire = _STATE.get("last_fire")
    if last_fire:
        try:
            if datetime.fromisoformat(str(last_fire)).astimezone(KST).date() == current.date():
                return False
        except ValueError:
            pass
    try:
        from kr_quant.freshness import freshness_snapshot

        fresh = freshness_snapshot(load_settings(), now=current)
        quant = ((fresh.get("sources") or {}).get("quant_ranking") or {})
        if (cfg.get("job_kind") or "smart-sync") in {"smart-sync", "live"}:
            return bool(fresh.get("stale_price")) or quant.get("state") != "fresh"
        return bool(fresh.get("stale_price"))
    except Exception:  # noqa: BLE001
        return True


def _fire() -> None:
    from kr_quant.web.jobs import RUNNER

    cfg = load_scheduler_config()
    job_kind = cfg.get("job_kind") or "smart-sync"
    _STATE["last_fire"] = datetime.now(KST).isoformat()
    _persist_runtime_state()
    try:
        if RUNNER.snapshot().get("status") == "running":
            _STATE["last_error"] = "다른 작업이 실행 중이라 건너뜀"
            return
        if job_kind == "smart-sync":
            snap = RUNNER.start("smart-sync", _scheduled_smart)
        elif job_kind == "live":
            snap = RUNNER.start("live", _scheduled_live)
        else:
            snap = RUNNER.start("krx-prices", _scheduled_evening)
        _STATE["last_error"] = None
        _STATE["last_result"] = {"started": True, "kind": snap.get("kind")}
        _persist_runtime_state()
        logger.info("scheduled %s job started", job_kind)
    except Exception as exc:  # noqa: BLE001
        _STATE["last_error"] = str(exc)[:200]
        _persist_runtime_state()
        logger.warning("scheduled %s skipped: %s", job_kind, exc)


def _loop() -> None:
    while True:
        cfg = load_scheduler_config()
        s = load_settings()
        job_kind = cfg.get("job_kind") or "smart-sync"
        enabled = bool(cfg.get("enabled")) and (bool(s.krx_api_key) or job_kind == "demo")
        _STATE["enabled"] = enabled
        if not enabled:
            _STATE["next_fire"] = None
            time.sleep(60)
            continue
        if _catch_up_due(cfg):
            _fire()
            time.sleep(70)
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
    _restore_runtime_state()
    _STATE["running"] = True
    thread = threading.Thread(target=_loop, name="krx-price-scheduler", daemon=True)
    thread.start()
    logger.info("KRX price scheduler thread started")
