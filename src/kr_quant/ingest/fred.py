from __future__ import annotations

import time
from typing import Any

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# Quant 점수에는 넣지 않는다. 리서치·대시보드 맥락 전용.
SERIES: list[dict[str, str]] = [
    {"id": "FEDFUNDS", "label": "연준 기준금리", "unit": "%"},
    {"id": "DGS10", "label": "미국 10년 금리", "unit": "%"},
    {"id": "DGS2", "label": "미국 2년 금리", "unit": "%"},
    {"id": "T10Y2Y", "label": "장단기 스프레드(10Y-2Y)", "unit": "%p"},
    {"id": "CPIAUCSL", "label": "미국 CPI", "unit": "index"},
    {"id": "UNRATE", "label": "미국 실업률", "unit": "%"},
    {"id": "DEXKOUS", "label": "원/달러", "unit": "USD/KRW"},
]

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 6 * 3600


def parse_observations(payload: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("observations") or []:
        if not isinstance(raw, dict):
            continue
        value = str(raw.get("value") or "").strip()
        if not value or value == ".":
            continue
        try:
            num = float(value)
        except ValueError:
            continue
        rows.append({"date": raw.get("date"), "value": num})
        if len(rows) >= limit:
            break
    return rows


def summarize_series(obs: list[dict[str, Any]], spec: dict[str, str]) -> dict[str, Any]:
    latest = obs[0] if obs else None
    prev = obs[1] if len(obs) > 1 else None
    delta = None
    if latest and prev and prev.get("value") is not None:
        delta = float(latest["value"]) - float(prev["value"])
    return {
        "id": spec["id"],
        "label": spec["label"],
        "unit": spec["unit"],
        "date": None if not latest else latest.get("date"),
        "value": None if not latest else latest.get("value"),
        "prev_date": None if not prev else prev.get("date"),
        "prev_value": None if not prev else prev.get("value"),
        "delta": delta,
        "used_in_quant": False,
    }


def normalize_api_key(api_key: str | None) -> str:
    return (api_key or "").strip().lower()


def fetch_series(api_key: str, series_id: str, timeout: int = 20) -> list[dict[str, Any]]:
    import requests

    api_key = normalize_api_key(api_key)
    if not api_key:
        raise RuntimeError("FRED API 키가 없습니다.")
    if len(api_key) != 32 or not api_key.isalnum():
        raise RuntimeError("FRED API 키는 32자 영숫자여야 합니다.")
    cache_key = f"fred:{series_id}"
    hit = _cache.get(cache_key)
    now = time.time()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    last_exc: Exception | None = None
    for attempt in range(2):
        resp = requests.get(
            FRED_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 12,
            },
            timeout=timeout,
        )
        if resp.status_code >= 500 and attempt == 0:
            last_exc = RuntimeError(f"FRED {series_id} HTTP {resp.status_code}")
            time.sleep(0.4)
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"FRED {series_id} HTTP {resp.status_code}: {resp.text[:160]}")
        obs = parse_observations(resp.json())
        _cache[cache_key] = (now, obs)
        return obs
    raise last_exc or RuntimeError(f"FRED {series_id} 실패")


def macro_snapshot(api_key: str | None) -> dict[str, Any]:
    if not api_key:
        return {
            "configured": False,
            "source": "FRED",
            "used_in_quant": False,
            "error": "FRED_API_KEY 없음. https://fred.stlouisfed.org/docs/api/api_key.html 에서 무료 발급.",
            "series": [],
        }
    series: list[dict[str, Any]] = []
    error = None
    for spec in SERIES:
        try:
            obs = fetch_series(api_key, spec["id"])
            series.append(summarize_series(obs, spec))
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:180]
            series.append({**summarize_series([], spec), "error": error})
    return {
        "configured": True,
        "source": "FRED",
        "used_in_quant": False,
        "error": error,
        "series": series,
    }
