from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Bank of Korea ECOS Open API. Context only — never written into Quant scores.
# Spec adapted from NomaDamas k-skill bok-ecos-stats (MIT).
BASE = "https://ecos.bok.or.kr/api"
DEMO_KEY = "sample"
SAMPLE_MAX = 10
ALIASES = {
    "기준금리": ("722Y001", "D", "0101000"),
    "원달러환율": ("731Y001", "D", "0000001"),
    "소비자물가지수": ("901Y009", "M", "0"),
    "M2": ("101Y004", "M", "BBHA00"),
    "국고채3년": ("817Y002", "D", "010200000"),
}


def resolve_key(api_key: str | None) -> str:
    key = (api_key or "").strip() or DEMO_KEY
    return key


def parse_rows(payload: dict[str, Any], service: str) -> list[dict[str, Any]]:
    result = payload.get("RESULT")
    if isinstance(result, dict):
        code = str(result.get("CODE") or "")
        if code in {"INFO-200"}:
            return []
        raise RuntimeError(f"ECOS {code}: {result.get('MESSAGE') or ''}")
    body = payload.get(service)
    if not isinstance(body, dict):
        raise RuntimeError("ECOS 응답에 데이터 블록이 없습니다.")
    rows = body.get("row") or []
    return [r for r in rows if isinstance(r, dict)]


def _get(url: str, timeout: int = 20) -> dict[str, Any]:
    import requests

    resp = requests.get(url, headers={"User-Agent": "kr-quant-research/ecos"}, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"ECOS HTTP {resp.status_code}: {resp.text[:160]}")
    return resp.json()


def search_series(api_key: str | None, alias: str, start: str, end: str, limit: int = 8) -> list[dict[str, Any]]:
    if alias not in ALIASES:
        raise RuntimeError(f"지원하지 않는 ECOS alias: {alias}")
    key = resolve_key(api_key)
    cap = min(limit, SAMPLE_MAX) if key == DEMO_KEY else max(1, limit)
    stat, cycle, item = ALIASES[alias]
    url = "/".join([BASE, "StatisticSearch", key, "json", "kr", "1", str(cap), stat, cycle, start, end, item])
    rows = parse_rows(_get(url), "StatisticSearch")
    out = []
    for row in rows:
        try:
            val = float(str(row.get("DATA_VALUE")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "alias": alias,
                "time": row.get("TIME"),
                "value": val,
                "unit": row.get("UNIT_NAME"),
                "name": row.get("ITEM_NAME1") or alias,
            }
        )
    return out


def key_statistics(api_key: str | None, limit: int = 10) -> list[dict[str, Any]]:
    key = resolve_key(api_key)
    cap = min(limit, SAMPLE_MAX) if key == DEMO_KEY else max(1, limit)
    url = "/".join([BASE, "KeyStatisticList", key, "json", "kr", "1", str(cap)]) + "/"
    rows = parse_rows(_get(url), "KeyStatisticList")
    out = []
    for row in rows:
        out.append(
            {
                "class_name": row.get("CLASS_NAME"),
                "name": row.get("KEYSTAT_NAME"),
                "value": row.get("DATA_VALUE"),
                "unit": row.get("UNIT_NAME"),
                "cycle": row.get("CYCLE"),
            }
        )
    return out


def latest_point(api_key: str | None, alias: str) -> dict[str, Any] | None:
    today = date.today()
    stat, cycle, _item = ALIASES[alias]
    if cycle == "D":
        start = (today - timedelta(days=21)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
    else:
        start = (today.replace(day=1) - timedelta(days=400)).strftime("%Y%m")
        end = today.strftime("%Y%m")
    rows = search_series(api_key, alias, start, end, limit=8)
    if not rows:
        return None
    last = dict(rows[-1])
    prev = rows[-2] if len(rows) >= 2 else None
    last["prev_value"] = None if not prev else prev.get("value")
    last["prev_time"] = None if not prev else prev.get("time")
    if last.get("value") is not None and prev and prev.get("value") is not None:
        last["delta"] = float(last["value"]) - float(prev["value"])
    else:
        last["delta"] = None
    last["history"] = rows
    last["spark"] = [r.get("value") for r in rows if r.get("value") is not None]
    return last


def ecos_snapshot(api_key: str | None) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    error = None
    for alias in ("기준금리", "국고채3년", "원달러환율", "소비자물가지수", "M2"):
        try:
            point = latest_point(api_key, alias)
            if point:
                series.append(point)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:180]
            series.append({"alias": alias, "error": error})
    headlines: list[dict[str, Any]] = []
    try:
        headlines = key_statistics(api_key, limit=8)
    except Exception as exc:  # noqa: BLE001
        error = error or str(exc)[:180]
    return {
        "source": "한국은행 ECOS",
        "configured": True,
        "used_in_quant": False,
        "demo_key": resolve_key(api_key) == DEMO_KEY,
        "error": error,
        "series": series,
        "headlines": headlines,
        "disclaimer": "한국은행 공식 통계입니다. Quant 점수에 넣지 않습니다.",
    }
