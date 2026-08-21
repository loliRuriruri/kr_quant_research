from __future__ import annotations

import time
from typing import Any

SOURCE_PAGE = "https://feargreed.co.kr/"
SOURCE_API = "https://feargree-api.vercel.app/api"
CNN_API = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 60

BANDS = (
    (25, "EXTREME_FEAR", "극단적 공포"),
    (45, "FEAR", "공포"),
    (55, "NEUTRAL", "중립"),
    (75, "GREED", "탐욕"),
    (101, "EXTREME_GREED", "극단적 탐욕"),
)


def band_for(score: float | None) -> dict[str, Any]:
    if score is None:
        return {"id": None, "label": "미연결", "hint": "데이터를 아직 받지 못했습니다."}
    val = max(0.0, min(100.0, float(score)))
    for hi, bid, label in BANDS:
        if val < hi:
            return {"id": bid, "label": label, "score": round(val, 1)}
    return {"id": "EXTREME_GREED", "label": "극단적 탐욕", "score": round(val, 1)}


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _normalize_side(raw: dict[str, Any] | None, fallback_source: str) -> dict[str, Any]:
    raw = raw or {}
    score = _num(raw.get("score"))
    band = band_for(score)
    indicators = []
    for item in raw.get("indicators") or []:
        if not isinstance(item, dict):
            continue
        indicators.append(
            {
                "name": item.get("name"),
                "value": _num(item.get("value")),
                "raw": item.get("raw"),
                "unit": item.get("unit") or "",
            }
        )
    return {
        "score": None if score is None else round(score, 1),
        "label": raw.get("label") or band["label"],
        "band": band["id"],
        "previous_close": _num(raw.get("previous_close")),
        "previous_1_week": _num(raw.get("previous_1_week")),
        "kospi_price": _num(raw.get("kospi_price")),
        "kospi_change": _num(raw.get("kospi_change")),
        "kosdaq_change": _num(raw.get("kosdaq_change")),
        "vkospi": _num(raw.get("vkospi")),
        "indicators": indicators,
        "source": raw.get("source") or fallback_source,
    }


def _from_vercel() -> dict[str, Any]:
    import requests

    resp = requests.get(
        SOURCE_API,
        timeout=15,
        headers={
            "User-Agent": "kr-quant-research/fear-greed",
            "Referer": SOURCE_PAGE,
            "Origin": "https://feargreed.co.kr",
            "Accept": "application/json",
        },
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"feargreed API HTTP {resp.status_code}")
    payload = resp.json()
    if not payload.get("success") and "kr" not in payload and "us" not in payload:
        raise RuntimeError("feargreed API 응답이 비었습니다.")
    return {
        "kr": _normalize_side(payload.get("kr") if isinstance(payload.get("kr"), dict) else {}, "feargreed.co.kr"),
        "us": _normalize_side(payload.get("us") if isinstance(payload.get("us"), dict) else {}, "CNN Fear & Greed"),
        "history": payload.get("history") or [],
        "timestamp": payload.get("timestamp"),
        "provider": "feargreed.co.kr",
    }


def _cnn_us() -> dict[str, Any]:
    import requests

    resp = requests.get(
        CNN_API,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cnn.com/markets/fear-and-greed"},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"CNN Fear & Greed HTTP {resp.status_code}")
    body = resp.json().get("fear_and_greed") or {}
    return _normalize_side(
        {
            "score": body.get("score"),
            "label": None,
            "previous_close": body.get("previous_close"),
            "previous_1_week": body.get("previous_1_week"),
            "source": "CNN Fear & Greed Index",
        },
        "CNN Fear & Greed Index",
    )


def fear_greed_snapshot(*, refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    hit = _cache.get("fg")
    if not refresh and hit and now - hit[0] < _TTL:
        return hit[1]
    error = None
    try:
        data = _from_vercel()
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:180]
        us = {}
        try:
            us = _cnn_us()
        except Exception as cnn_exc:  # noqa: BLE001
            error = f"{error}; CNN {str(cnn_exc)[:80]}"
        data = {"kr": {}, "us": us, "history": [], "timestamp": None, "provider": "fallback"}
    out = {
        "configured": bool((data.get("kr") or {}).get("score") is not None or (data.get("us") or {}).get("score") is not None),
        "used_in_quant": False,
        "page": SOURCE_PAGE,
        "error": error,
        **data,
        "disclaimer": "공포·탐욕 지수는 시장 심리 참고용입니다. Quant 점수에 넣지 않으며 매수·매도 지시가 아닙니다.",
    }
    if out["configured"]:
        _cache["fg"] = (now, out)
    return out
