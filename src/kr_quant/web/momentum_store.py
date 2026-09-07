"""Validated atomic JSON transactions for the single-process local server."""
from __future__ import annotations

import json
import math
import re
import threading
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from kr_quant.atomic_io import write_json_atomic

_LOCK = threading.RLock()


def _code(value) -> str:
    code = str(value or "")
    if not re.fullmatch(r"[0-9]{6}", code) or code == "000000":
        raise HTTPException(422, "종목코드는 6자리 숫자여야 합니다.")
    return code


def _validate(rows: list) -> list:
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(422, "포트폴리오 항목 형식 오류")
        code = _code(row.get("code"))
        if code in seen:
            raise HTTPException(422, "중복 종목코드")
        seen.add(code)
        for key in ("entry_price", "target_price"):
            val = row.get(key)
            if val is not None and (isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0):
                raise HTTPException(422, f"{key}: 유한한 양수 가격이 필요합니다.")
        for key in ("entry_date", "peak_date"):
            if row.get(key):
                try:
                    date.fromisoformat(row[key])
                except (ValueError, TypeError):
                    raise HTTPException(422, f"{key}: YYYY-MM-DD 형식이 필요합니다.")
        if row.get("entry_date") and row.get("peak_date") and row["peak_date"] < row["entry_date"]:
            raise HTTPException(422, "목표일은 진입일보다 빠를 수 없습니다.")
    return rows


def read_portfolio(path: Path) -> list:
    with _LOCK:
        if not path.exists():
            return []
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError("expected array")
            return _validate(rows)
        except (ValueError, OSError, HTTPException) as exc:
            raise HTTPException(409, "포트폴리오 파일을 읽지 못했습니다. 원본을 보존했으며 복구가 필요합니다.") from exc


def update_portfolio(path: Path, body: dict) -> int:
    with _LOCK:
        rows = read_portfolio(path)
        if "item" in body and isinstance(body["item"], dict):
            item = dict(body["item"])
            code = _code(item.get("code"))
            found = next((i for i, row in enumerate(rows) if row["code"] == code), None)
            if found is None:
                item.setdefault("id", f"stock-{code}")
                rows.insert(0, item)
            else:
                rows[found] = {**rows[found], **item}
        elif "delete_code" in body:
            code = _code(body["delete_code"])
            rows = [row for row in rows if row["code"] != code]
        else:
            raise HTTPException(422, "item 수정 또는 delete_code 삭제를 사용하세요. 화면을 새로고침하세요.")
        _validate(rows)
        write_json_atomic(path, rows)
        return len(rows)
