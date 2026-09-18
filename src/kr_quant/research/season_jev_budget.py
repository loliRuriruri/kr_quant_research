"""Daily TypeSafe call budget. Fail closed. Never touches Quant."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from kr_quant.atomic_io import write_json_atomic

KST = ZoneInfo("Asia/Seoul")


def day_kst(now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return current.astimezone(KST).date().isoformat()


def budget_dir(settings) -> Path:
    return Path(settings.data_dir) / "research_snapshots" / "season_jev_shadow" / "_budget"


def ledger_path(settings, day: str) -> Path:
    return budget_dir(settings) / f"{day}.json"


def lock_path(settings, day: str) -> Path:
    return budget_dir(settings) / f"{day}.lock"


class BudgetLock:
    def __init__(self, path: Path, timeout_sec: float = 2.0):
        self.path = Path(path)
        self.timeout_sec = timeout_sec
        self._fh = None
        self._acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout_sec
        self._fh = self.path.open("a+b")
        self._fh.seek(0, 2)
        if self._fh.tell() == 0:
            self._fh.write(b"0")
            self._fh.flush()
        while True:
            try:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._acquired = True
                return True
            except OSError:
                if time.time() >= deadline:
                    self.release()
                    return False
                time.sleep(0.05)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if self._acquired:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None
        self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError("API_BUDGET_UNAVAILABLE")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def _empty_ledger(day: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "day_kst": day,
        "attempted_calls": 0,
        "updated_at": datetime.now(KST).isoformat(),
        "generations": {},
    }


def read_ledger(settings, day: str | None = None) -> dict[str, Any]:
    day = day or day_kst()
    path = ledger_path(settings, day)
    if not path.exists():
        return _empty_ledger(day)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("API_BUDGET_UNAVAILABLE") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("API_BUDGET_UNAVAILABLE")
    if payload.get("day_kst") != day:
        return _empty_ledger(day)
    payload.setdefault("attempted_calls", 0)
    payload.setdefault("generations", {})
    return payload


def write_ledger(settings, payload: dict[str, Any]) -> None:
    day = str(payload.get("day_kst") or day_kst())
    payload["updated_at"] = datetime.now(KST).isoformat()
    write_json_atomic(ledger_path(settings, day), payload)


def reserve_daily_slot(settings, generation_id: str, *, day_cap: int, now: datetime | None = None) -> str:
    """Consume one daily slot. Returns ok | API_CAP_DAILY | API_BUDGET_UNAVAILABLE."""
    day = day_kst(now)
    lock = BudgetLock(lock_path(settings, day))
    if not lock.acquire():
        return "API_BUDGET_UNAVAILABLE"
    try:
        try:
            ledger = read_ledger(settings, day)
        except RuntimeError:
            return "API_BUDGET_UNAVAILABLE"
        attempted = int(ledger.get("attempted_calls") or 0)
        if attempted >= int(day_cap):
            return "API_CAP_DAILY"
        ledger["attempted_calls"] = attempted + 1
        gens = dict(ledger.get("generations") or {})
        gens[str(generation_id)] = int(gens.get(str(generation_id) or 0) or 0) + 1
        ledger["generations"] = gens
        try:
            write_ledger(settings, ledger)
        except OSError:
            return "API_BUDGET_UNAVAILABLE"
        return "ok"
    finally:
        lock.release()


def refund_daily_slot(settings, generation_id: str, *, now: datetime | None = None) -> None:
    day = day_kst(now)
    lock = BudgetLock(lock_path(settings, day))
    if not lock.acquire():
        return
    try:
        try:
            ledger = read_ledger(settings, day)
        except RuntimeError:
            return
        ledger["attempted_calls"] = max(0, int(ledger.get("attempted_calls") or 0) - 1)
        gens = dict(ledger.get("generations") or {})
        gid = str(generation_id)
        if gid in gens:
            gens[gid] = max(0, int(gens.get(gid) or 0) - 1)
            ledger["generations"] = gens
        write_ledger(settings, ledger)
    except OSError:
        return
    finally:
        lock.release()
