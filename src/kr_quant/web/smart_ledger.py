# -*- coding: utf-8 -*-
"""Per-day smart-sync step ledger.

The scheduler used to stamp last_fire before the job actually started, so a
busy runner or a KRX source-not-ready evening still consumed the day. This
ledger keeps step outcomes so a later retry can fetch prices only.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from kr_quant.settings import load_settings

KST = ZoneInfo("Asia/Seoul")
LEDGER_NAME = "smart_run_ledger.json"
STEPS = ("krx", "quant", "dart", "kis", "publish")
SUCCESS_STATUSES = frozenset(
    {
        "success",
        "skipped_fresh",
        "skipped_sufficient",
        "skipped_not_configured",
        "skipped_already_success",
    }
)
RETRYABLE_KRX = frozenset({"source_not_ready", "interrupted", "pending", "running"})
DEFAULT_RETRY_MINUTES = 25
DEFAULT_MAX_ATTEMPTS = 6


def now_kst(now: datetime | None = None) -> datetime:
    if now is None:
        current = datetime.now(KST)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=KST)
    else:
        current = now.astimezone(KST)
    return current


def now_iso(now: datetime | None = None) -> str:
    return now_kst(now).isoformat()


def ledger_path(settings=None):
    root = (settings or load_settings()).root
    return root / "logs" / LEDGER_NAME


def retry_config(settings=None) -> dict[str, int]:
    block: dict[str, Any] = {}
    if settings is not None:
        cfg = getattr(settings, "config", None)
        if isinstance(cfg, dict):
            block = dict(cfg.get("smart_sync") or {})
        extra = getattr(settings, "smart_sync", None)
        if isinstance(extra, dict) and not block:
            block = dict(extra)
    else:
        try:
            block = load_scheduler_retry_block()
        except Exception:  # noqa: BLE001
            block = {}
    return {
        "retry_minutes": int(block.get("krx_retry_minutes") or DEFAULT_RETRY_MINUTES),
        "max_attempts": int(block.get("krx_max_attempts") or DEFAULT_MAX_ATTEMPTS),
    }


def load_scheduler_retry_block() -> dict[str, Any]:
    import yaml

    path = load_settings().root / "config" / "scheduler.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("smart_sync") or {}


def empty_step() -> dict[str, Any]:
    return {
        "status": "pending",
        "attempt": 0,
        "updated_at": None,
        "retry_at": None,
        "detail": None,
        "ran_this_pass": False,
    }


def new_ledger(*, run_date: str, expected_price_date: str, trigger: str, now: datetime | None = None) -> dict[str, Any]:
    stamp = now_iso(now)
    return {
        "run_date": run_date,
        "run_id": uuid4().hex[:12],
        "expected_price_date": expected_price_date,
        "trigger": trigger,
        "started_at": stamp,
        "heartbeat_at": stamp,
        "finished_at": None,
        "overall_status": "running",
        "steps": {name: empty_step() for name in STEPS},
    }


def load_ledger(settings=None) -> dict[str, Any] | None:
    path = ledger_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_ledger(ledger: dict[str, Any], settings=None) -> dict[str, Any]:
    path = ledger_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return ledger


def recover_interrupted(settings=None, *, runner_running: bool, now: datetime | None = None) -> dict[str, Any] | None:
    ledger = load_ledger(settings)
    if not ledger:
        return None
    if ledger.get("overall_status") != "running" or runner_running:
        return ledger
    stamp = now_iso(now)
    ledger["overall_status"] = "interrupted"
    ledger["finished_at"] = stamp
    ledger["heartbeat_at"] = stamp
    for step in (ledger.get("steps") or {}).values():
        if isinstance(step, dict) and step.get("status") == "running":
            step["status"] = "interrupted"
            step["updated_at"] = stamp
            step["detail"] = "서버가 재시작되어 실행 중 체크포인트를 중단으로 복구했습니다."
    save_ledger(ledger, settings)
    return ledger


def begin_or_resume(
    settings,
    *,
    run_date: str,
    expected_price_date: str,
    trigger: str,
    runner_running: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    recover_interrupted(settings, runner_running=runner_running, now=now)
    ledger = load_ledger(settings)
    stamp = now_iso(now)
    if not ledger or ledger.get("run_date") != run_date:
        ledger = new_ledger(run_date=run_date, expected_price_date=expected_price_date, trigger=trigger, now=now)
        return save_ledger(ledger, settings)
    if ledger.get("expected_price_date") != expected_price_date:
        ledger["expected_price_date"] = expected_price_date
        for name in ("krx", "quant", "publish"):
            previous = dict(ledger.get("steps", {}).get(name) or empty_step())
            reset = empty_step()
            reset["attempt"] = int(previous.get("attempt") or 0)
            ledger.setdefault("steps", {})[name] = reset
    ledger["overall_status"] = "running"
    ledger["finished_at"] = None
    ledger["trigger"] = trigger
    ledger["heartbeat_at"] = stamp
    if not ledger.get("started_at"):
        ledger["started_at"] = stamp
    for step in (ledger.get("steps") or {}).values():
        if isinstance(step, dict):
            step["ran_this_pass"] = False
    return save_ledger(ledger, settings)


def heartbeat(ledger: dict[str, Any], settings=None, now: datetime | None = None) -> dict[str, Any]:
    ledger["heartbeat_at"] = now_iso(now)
    return save_ledger(ledger, settings)


def mark_step(
    ledger: dict[str, Any],
    name: str,
    status: str,
    settings=None,
    *,
    now: datetime | None = None,
    ran_this_pass: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    steps = ledger.setdefault("steps", {})
    current = dict(steps.get(name) or empty_step())
    current["status"] = status
    current["updated_at"] = now_iso(now)
    current["ran_this_pass"] = ran_this_pass
    if "attempt" in fields:
        current["attempt"] = int(fields.pop("attempt"))
    elif ran_this_pass and name == "krx":
        current["attempt"] = int(current.get("attempt") or 0) + 1
    for key, value in fields.items():
        current[key] = value
    steps[name] = current
    ledger["heartbeat_at"] = current["updated_at"]
    return save_ledger(ledger, settings)


def finish(ledger: dict[str, Any], overall: str, settings=None, now: datetime | None = None) -> dict[str, Any]:
    stamp = now_iso(now)
    ledger["overall_status"] = overall
    ledger["finished_at"] = stamp
    ledger["heartbeat_at"] = stamp
    return save_ledger(ledger, settings)


def step_done(step: dict[str, Any] | None) -> bool:
    return bool(step) and step.get("status") in SUCCESS_STATUSES


def schedule_krx_retry(ledger: dict[str, Any], settings=None, now: datetime | None = None) -> str | None:
    cfg = retry_config(settings)
    current = now_kst(now)
    step = (ledger.get("steps") or {}).get("krx") or {}
    attempt = int(step.get("attempt") or 0)
    if attempt >= int(cfg["max_attempts"]):
        return None
    retry_at = (current + timedelta(minutes=int(cfg["retry_minutes"]))).isoformat()
    return retry_at


def next_retry_at(ledger: dict[str, Any] | None) -> datetime | None:
    if not ledger:
        return None
    raw = ((ledger.get("steps") or {}).get("krx") or {}).get("retry_at")
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return now_kst(value)


def retry_due(ledger: dict[str, Any] | None, now: datetime | None = None, settings=None) -> bool:
    if not ledger:
        return False
    current = now_kst(now)
    if ledger.get("run_date") != current.date().isoformat():
        return False
    krx = (ledger.get("steps") or {}).get("krx") or {}
    if krx.get("status") != "source_not_ready":
        return False
    cfg = retry_config(settings)
    if int(krx.get("attempt") or 0) >= int(cfg["max_attempts"]):
        return False
    due = next_retry_at(ledger)
    return bool(due and current >= due)


def current_step(ledger: dict[str, Any] | None) -> str | None:
    if not ledger:
        return None
    for name in STEPS:
        status = ((ledger.get("steps") or {}).get(name) or {}).get("status")
        if status == "running":
            return name
    if ledger.get("overall_status") == "running":
        for name in STEPS:
            status = ((ledger.get("steps") or {}).get(name) or {}).get("status")
            if status in {"pending", "source_not_ready", "blocked_dependency"}:
                return name
    return None


def blocked_dependencies(ledger: dict[str, Any] | None) -> list[str]:
    if not ledger:
        return []
    steps = ledger.get("steps") or {}
    blocked: list[str] = []
    krx_status = (steps.get("krx") or {}).get("status")
    if (steps.get("quant") or {}).get("status") == "blocked_dependency":
        blocked.append(f"quant ← krx:{krx_status or 'pending'}")
    if (steps.get("publish") or {}).get("status") in {"blocked_stale", "blocked_dependency"}:
        blocked.append(f"publish ← {(steps.get('publish') or {}).get('status')}")
    return blocked


def public_snapshot(settings=None, ledger: dict[str, Any] | None = None, now: datetime | None = None) -> dict[str, Any] | None:
    payload = ledger if ledger is not None else load_ledger(settings)
    if not payload:
        return None
    started = payload.get("started_at")
    elapsed_sec = None
    if started:
        try:
            started_dt = now_kst(datetime.fromisoformat(str(started)))
            end_raw = payload.get("finished_at") or now_iso(now)
            ended = now_kst(datetime.fromisoformat(str(end_raw)))
            elapsed_sec = max(0, int((ended - started_dt).total_seconds()))
        except ValueError:
            elapsed_sec = None
    retry = next_retry_at(payload)
    krx = (payload.get("steps") or {}).get("krx") or {}
    cfg = retry_config(settings)
    return {
        "run_date": payload.get("run_date"),
        "run_id": payload.get("run_id"),
        "expected_price_date": payload.get("expected_price_date"),
        "overall_status": payload.get("overall_status"),
        "trigger": payload.get("trigger"),
        "started_at": payload.get("started_at"),
        "heartbeat_at": payload.get("heartbeat_at"),
        "finished_at": payload.get("finished_at"),
        "elapsed_sec": elapsed_sec,
        "current_step": current_step(payload),
        "next_retry_at": None if retry is None else retry.isoformat(),
        "krx_attempt": int(krx.get("attempt") or 0),
        "krx_max_attempts": int(cfg["max_attempts"]),
        "blocked_dependencies": blocked_dependencies(payload),
        "steps": payload.get("steps") or {},
    }


def decide_overall(ledger: dict[str, Any], settings=None) -> str:
    steps = ledger.get("steps") or {}
    statuses = [str((steps.get(name) or {}).get("status") or "pending") for name in STEPS]
    if any(status == "failed" for status in statuses):
        return "failed"
    krx = (steps.get("krx") or {}).get("status")
    if krx == "source_not_ready":
        cfg = retry_config(settings)
        attempt = int((steps.get("krx") or {}).get("attempt") or 0)
        return "blocked" if attempt >= int(cfg["max_attempts"]) and not (steps.get("krx") or {}).get("retry_at") else "partial"
    if any(status in {"warning", "partial", "blocked_dependency", "blocked_stale", "interrupted"} for status in statuses):
        return "partial"
    if all(status in SUCCESS_STATUSES or status == "queued" for status in statuses):
        return "success"
    return "partial"
