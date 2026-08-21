"""Recent OpenDART filings + lite next-bar overlay. used_in_quant=false."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from kr_quant.events.classify import classify_row
from kr_quant.settings import Settings

_CACHE: dict[str, Any] = {}
TTL = 1800


def _fwd_return(prices: Any, ticker: str, event_date: str, horizon: int) -> float | None:
    import pandas as pd

    if prices is None or getattr(prices, "empty", True) or not event_date:
        return None
    code = str(ticker).zfill(6)
    hist = prices[prices["ticker"].astype(str).str.zfill(6) == code].copy()
    if hist.empty:
        return None
    hist["trade_date"] = pd.to_datetime(hist["trade_date"]).dt.strftime("%Y-%m-%d")
    hist = hist.sort_values("trade_date")
    later = hist[hist["trade_date"] > event_date]
    if later.empty:
        return None
    start = float(pd.to_numeric(later["close"].iloc[0], errors="coerce") or 0)
    if start <= 0:
        return None
    idx = min(horizon, len(later) - 1)
    if idx < 1:
        return None
    end = float(pd.to_numeric(later["close"].iloc[idx], errors="coerce") or 0)
    if end <= 0:
        return None
    return round(end / start - 1.0, 4)


def load_ticker_events(
    settings: Settings,
    ticker: str,
    corp_code: str | None = None,
    *,
    lookback_days: int = 90,
) -> dict[str, Any]:
    code = "".join(ch for ch in str(ticker) if ch.isdigit()).zfill(6)
    now = time.time()
    cached = _CACHE.get(code)
    if cached and now - float(cached.get("at") or 0) < TTL:
        return cached["payload"]
    empty = {
        "used_in_quant": False,
        "ticker": code,
        "rows": [],
        "n": 0,
        "configured": bool(settings.opendart_api_key),
        "disclaimer": "OpenDART 공시 제목으로 분류합니다. Quant에 넣지 않으며 매수 신호가 아닙니다.",
    }
    if not settings.opendart_api_key:
        empty["error"] = "OpenDART 키가 없습니다."
        return empty
    corp = str(corp_code or "").zfill(8)
    if corp in {"", "00000000"}:
        empty["error"] = "고유번호가 없습니다."
        return empty
    from kr_quant.ingest.opendart import OpenDartAdapter

    adapter = OpenDartAdapter(
        settings.opendart_api_key,
        "https://opendart.fss.or.kr/api",
        sleep_sec=float(getattr(settings, "opendart_sleep_sec", None) or 0.15),
    )
    end = date.today()
    bgn = end - timedelta(days=min(90, max(14, int(lookback_days))))
    try:
        data = adapter.fetch_list(corp, bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    except Exception as exc:  # noqa: BLE001
        empty["error"] = str(exc)[:180]
        return empty
    items = data.get("list") if isinstance(data, dict) else None
    rows = [classify_row(x) for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    for row in rows:
        if not row.get("ticker"):
            row["ticker"] = code
    prices = None
    try:
        from kr_quant.layers.context import load_price_frame

        prices = load_price_frame(settings)
    except Exception:  # noqa: BLE001
        prices = None
    for row in rows:
        if row.get("event_type") == "OTHER":
            continue
        ret5 = _fwd_return(prices, code, str(row.get("report_date") or ""), 5)
        if ret5 is not None:
            row["ret_5d"] = ret5
            row["fwd_note"] = "접수일 다음 거래일 종가 기준 5일. 장중 공시 시점은 반영하지 않습니다."
        else:
            row["sample"] = "LOW_SAMPLE"
    interesting = [r for r in rows if r.get("event_type") != "OTHER"]
    payload = {
        "used_in_quant": False,
        "ticker": code,
        "corp_code": corp,
        "rows": interesting[:40],
        "all_n": len(rows),
        "n": min(40, len(interesting)),
        "configured": True,
        "disclaimer": empty["disclaimer"],
    }
    _CACHE[code] = {"at": now, "payload": payload}
    return payload
