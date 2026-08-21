from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

INDEXES: list[dict[str, Any]] = [
    {"symbol": "^KS11", "label": "코스피 (KOSPI)", "category": "index", "unit": "pt"},
    {"symbol": "^KQ11", "label": "코스닥 (KOSDAQ)", "category": "index", "unit": "pt"},
    {"symbol": "^GSPC", "label": "S&P 500", "category": "index", "unit": "pt"},
    {"symbol": "^IXIC", "label": "나스닥 (NASDAQ)", "category": "index", "unit": "pt"},
    {"symbol": "^N225", "label": "일본 닛케이 225", "category": "index", "unit": "pt"},
    {"symbol": "DX-Y.NYB", "label": "달러 인덱스 (DXY)", "category": "fx", "unit": "pt"},
    {"symbol": "KRW=X", "label": "원/달러 (USD/KRW)", "category": "fx", "unit": "원"},
    {"symbol": "JPY=X", "label": "엔/달러 (USD/JPY)", "category": "fx", "unit": "엔"},
    {"symbol": "JPYKRW=X", "label": "100엔/원 (JPY/KRW)", "category": "fx", "unit": "원"},
    {"symbol": "GC=F", "label": "금 선물 (Gold)", "category": "commodity", "unit": "$"},
    {"symbol": "CL=F", "label": "WTI 원유", "category": "commodity", "unit": "$"},
    {"symbol": "HG=F", "label": "구리 선물 (Copper)", "category": "commodity", "unit": "$"},
    {"symbol": "BTC-USD", "label": "비트코인 (BTC)", "category": "crypto", "unit": "$"},
    {"symbol": "ETH-USD", "label": "이더리움 (ETH)", "category": "crypto", "unit": "$"},
    {"symbol": "^TNX", "label": "미국 10년물 국채", "category": "rate", "unit": "%"},
]

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 90


def kr_yahoo_symbol(ticker: str | None, market: str | None = None) -> str:
    digits = "".join(ch for ch in str(ticker or "") if ch.isdigit()).zfill(6)
    mkt = (market or "").upper()
    if "KOSDAQ" in mkt:
        return f"{digits}.KQ"
    return f"{digits}.KS"


def yahoo_quote_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{symbol}"


def _as_date(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def parse_chart(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        err = (chart.get("error") or {}).get("description") or "차트 없음"
        raise RuntimeError(str(err))
    block = results[0] if isinstance(results[0], dict) else {}
    meta = block.get("meta") or {}
    stamps = block.get("timestamp") or []
    quote = ((block.get("indicators") or {}).get("quote") or [{}])[0] or {}
    closes = quote.get("close") or []
    bars: list[dict[str, Any]] = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        try:
            val = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(val):
            continue
        bars.append({"date": _as_date(int(ts)), "close": val})
    return {
        "symbol": meta.get("symbol"),
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "last": meta.get("regularMarketPrice"),
        "bars": bars,
    }


def _ret(last: float, older: float | None) -> float | None:
    if older is None or older == 0:
        return None
    return (last / older) - 1.0


def _close_on_or_before(bars: list[dict[str, Any]], target: str) -> float | None:
    for row in reversed(bars):
        if str(row.get("date") or "") <= target:
            return float(row["close"])
    return None


def summarize_bars(bars: list[dict[str, Any]], last_override: float | None = None) -> dict[str, Any]:
    if not bars:
        return {}
    last_date = str(bars[-1]["date"])
    last = float(last_override if last_override is not None else bars[-1]["close"])
    last_dt = date.fromisoformat(last_date)
    window = bars[-252:] if len(bars) >= 50 else bars
    high_52w = max(float(r["close"]) for r in window)
    dist_52w = None if high_52w <= 0 else (last / high_52w) - 1.0
    ma50 = None
    ma200 = None
    if len(bars) >= 50:
        ma50 = sum(float(r["close"]) for r in bars[-50:]) / 50
    if len(bars) >= 200:
        ma200 = sum(float(r["close"]) for r in bars[-200:]) / 200
    prev = float(bars[-2]["close"]) if len(bars) >= 2 else None
    return {
        "as_of": last_date,
        "last": last,
        "ret_1d": _ret(last, prev),
        "ret_1m": _ret(last, _close_on_or_before(bars, (last_dt - timedelta(days=31)).isoformat())),
        "ret_3m": _ret(last, _close_on_or_before(bars, (last_dt - timedelta(days=93)).isoformat())),
        "ret_6m": _ret(last, _close_on_or_before(bars, (last_dt - timedelta(days=183)).isoformat())),
        "ret_1y": _ret(last, _close_on_or_before(bars, (last_dt - timedelta(days=365)).isoformat())),
        "high_52w": high_52w,
        "high_52w_distance": dist_52w,
        "ma50": ma50,
        "ma200": ma200,
        "bars": len(bars),
        "used_in_quant": False,
    }


def _chart_http(symbol: str, range_: str = "1y", timeout: int = 20) -> dict[str, Any]:
    import requests

    resp = requests.get(
        CHART_URL.format(symbol=symbol),
        params={"interval": "1d", "range": range_},
        headers=HEADERS,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Yahoo {symbol} HTTP {resp.status_code}: {resp.text[:160]}")
    return parse_chart(resp.json())


def _chart_yfinance(symbol: str, period: str = "1y") -> dict[str, Any]:
    import yfinance as yf  # type: ignore

    hist = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
    if hist is None or getattr(hist, "empty", True):
        raise RuntimeError(f"yfinance {symbol} 빈 시계열")
    bars: list[dict[str, Any]] = []
    closes = hist["Close"]
    for idx, val in closes.items():
        if val is None or (isinstance(val, float) and not math.isfinite(val)):
            continue
        day = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        bars.append({"date": day, "close": float(val)})
    return {"symbol": symbol, "currency": None, "exchange": None, "last": float(closes.iloc[-1]), "bars": bars}


def fetch_chart(symbol: str, range_: str = "1y", *, refresh: bool = False) -> dict[str, Any]:
    cache_key = f"yf:{symbol}:{range_}"
    now = time.time()
    hit = _cache.get(cache_key)
    if not refresh and hit and now - hit[0] < _TTL:
        return hit[1]
    data: dict[str, Any] | None = None
    source = "yahoo-http"
    try:
        data = _chart_http(symbol, range_)
        source = "yahoo-http"
    except Exception as http_exc:
        try:
            data = _chart_yfinance(symbol, "1y" if range_ in {"1y", "ytd"} else range_)
            source = "yfinance"
        except Exception:  # noqa: BLE001
            raise http_exc from None
    data["source"] = source
    data["used_in_quant"] = False
    _cache[cache_key] = (now, data)
    return data


def snapshot_from_chart(
    symbol: str,
    label: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    raw = fetch_chart(symbol, refresh=refresh)
    stats = summarize_bars(raw.get("bars") or [], last_override=_as_float(raw.get("last")))
    bars = raw.get("bars") or []
    spark = [float(b["close"]) for b in bars[-60:] if b.get("close") is not None]
    bars_30d = [{"date": b["date"], "close": float(b["close"])} for b in bars[-30:] if b.get("close") is not None]
    stats.update(
        {
            "symbol": raw.get("symbol") or symbol,
            "label": label or symbol,
            "category": category or "index",
            "unit": unit or "pt",
            "currency": raw.get("currency"),
            "exchange": raw.get("exchange"),
            "source": raw.get("source"),
            "page": yahoo_quote_url(symbol),
            "spark": spark,
            "bars_30d": bars_30d,
            "used_in_quant": False,
        }
    )
    return stats


def _as_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def index_snapshot(*, refresh: bool = False) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    error = None
    for spec in INDEXES:
        try:
            rows.append(
                snapshot_from_chart(
                    spec["symbol"],
                    spec["label"],
                    spec.get("category"),
                    spec.get("unit"),
                    refresh=refresh,
                )
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:180]
            rows.append(
                {
                    "symbol": spec["symbol"],
                    "label": spec["label"],
                    "category": spec.get("category", "index"),
                    "unit": spec.get("unit", "pt"),
                    "error": error,
                    "used_in_quant": False,
                }
            )
    return {"configured": True, "used_in_quant": False, "error": error, "indexes": rows}


def stock_research_quote(ticker: str, market: str | None = None) -> dict[str, Any]:
    digits = "".join(ch for ch in str(ticker or "") if ch.isdigit()).zfill(6)
    primary = kr_yahoo_symbol(ticker, market)
    alt = f"{digits}.KQ" if primary.endswith(".KS") else f"{digits}.KS"
    tried: list[str] = []
    last_exc: Exception | None = None
    raw = None
    for symbol in (primary, alt):
        if symbol in tried:
            continue
        tried.append(symbol)
        try:
            raw = fetch_chart(symbol)
            primary = symbol
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            raw = None
    if raw is None:
        raise RuntimeError(str(last_exc) if last_exc else f"Yahoo {primary} 실패")
    stats = summarize_bars(raw.get("bars") or [], last_override=_as_float(raw.get("last")))
    bench = None
    try:
        kospi = snapshot_from_chart("^KS11", "KOSPI")
        rel = None
        if stats.get("ret_6m") is not None and kospi.get("ret_6m") is not None:
            rel = float(stats["ret_6m"]) - float(kospi["ret_6m"])
        bench = {"symbol": "^KS11", "ret_6m": kospi.get("ret_6m"), "relative_6m": rel}
    except Exception:  # noqa: BLE001
        bench = None
    stats.update(
        {
            "symbol": primary,
            "tried": tried,
            "source": raw.get("source"),
            "currency": raw.get("currency") or "KRW",
            "page": yahoo_quote_url(primary),
            "vs_kospi": bench,
            "used_in_quant": False,
            "disclaimer": "yfinance/Yahoo는 연구·비교용입니다. Quant 점수와 KRX 공식 시세를 대체하지 않습니다.",
        }
    )
    return stats
