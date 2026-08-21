from __future__ import annotations

import html
import re
import time
from typing import Any

HUB_BASE = "https://naverapihub.apigw.ntruss.com"
LEGACY_BASE = "https://openapi.naver.com/v1/search"

ENDPOINTS = {
    "news": ("/search/v1/news", "news.json"),
    "encyc": ("/search/v1/encyc", "encyc.json"),
    "webkr": ("/search/v1/webkr", "webkr.json"),
}


def strip_html(text: str | None) -> str:
    raw = html.unescape(text or "")
    return re.sub(r"<[^>]+>", "", raw).strip()


def company_query(company: str | None, ticker: str | None) -> str:
    name = (company or "").strip()
    code = "".join(ch for ch in str(ticker or "") if ch.isdigit()).zfill(6) if ticker else ""
    if name and code:
        return f"{name} {code}"
    return name or code


def _ncp_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }


def _legacy_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def _normalize_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    items = []
    for raw in payload.get("items") or []:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "title": strip_html(raw.get("title")),
                "description": strip_html(raw.get("description")),
                "link": raw.get("link") or raw.get("originallink") or "",
                "originallink": raw.get("originallink") or "",
                "pubDate": raw.get("pubDate") or "",
            }
        )
    return items


def _request(
    kind: str,
    client_id: str,
    client_secret: str,
    query: str,
    *,
    display: int,
    start: int,
    sort: str | None,
    timeout: int,
) -> dict[str, Any]:
    import requests

    if not client_id or not client_secret:
        raise RuntimeError("네이버 Client ID/Secret이 없습니다.")
    hub_path, legacy_file = ENDPOINTS[kind]
    params: dict[str, Any] = {
        "query": query,
        "display": max(1, min(display, 100)),
        "start": max(1, min(start, 1000)),
        "format": "json",
    }
    if sort and kind in {"news"}:
        params["sort"] = sort
    attempts = (
        (HUB_BASE + hub_path, _ncp_headers(client_id, client_secret)),
        (f"{LEGACY_BASE}/{legacy_file}", _legacy_headers(client_id, client_secret)),
    )
    last_error = "네이버 검색 실패"
    for url, headers in attempts:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        if resp.status_code < 400:
            payload = resp.json()
            return {
                "query": query,
                "kind": kind,
                "total": payload.get("total"),
                "items": _normalize_items(payload),
                "source": "ncp" if "ntruss.com" in url else "legacy",
            }
        last_error = f"네이버 {kind} HTTP {resp.status_code}: {resp.text[:180]}"
    raise RuntimeError(last_error)


def search_news(
    client_id: str,
    client_secret: str,
    query: str,
    *,
    display: int = 8,
    sort: str = "date",
    timeout: int = 12,
) -> dict[str, Any]:
    return _request("news", client_id, client_secret, query, display=display, start=1, sort=sort, timeout=timeout)


def search_web(
    client_id: str,
    client_secret: str,
    query: str,
    *,
    display: int = 5,
    timeout: int = 12,
) -> dict[str, Any]:
    return _request("webkr", client_id, client_secret, query, display=display, start=1, sort=None, timeout=timeout)


def search_encyc(
    client_id: str,
    client_secret: str,
    query: str,
    *,
    display: int = 3,
    timeout: int = 12,
) -> list[dict[str, str]]:
    try:
        return _request("encyc", client_id, client_secret, query, display=display, start=1, sort=None, timeout=timeout).get("items") or []
    except RuntimeError:
        return []


NEWS_QUERIES = [
    {"id": "kr_market", "query": "코스피 증시", "label": "국내 증시"},
    {"id": "kr_rate", "query": "한국은행 기준금리", "label": "국내 금리"},
    {"id": "fx", "query": "원달러 환율", "label": "환율"},
    {"id": "fed", "query": "연준 금리", "label": "연준"},
    {"id": "us_market", "query": "미국 증시 나스닥", "label": "미국 증시"},
]
ENCYC_QUERIES = ("기준금리", "장단기 금리차", "원달러")

_news_cache: tuple[float, dict[str, Any]] | None = None
_NEWS_TTL = 10 * 60


def market_news_bundle(
    client_id: str,
    client_secret: str,
    *,
    refresh: bool = False,
    display: int = 5,
) -> dict[str, Any]:
    """Macro headlines via Naver Search. Overlay only."""
    global _news_cache
    now = time.time()
    if not refresh and _news_cache and now - _news_cache[0] < _NEWS_TTL:
        return _news_cache[1]
    groups: list[dict[str, Any]] = []
    error = None
    for spec in NEWS_QUERIES:
        try:
            payload = search_news(client_id, client_secret, spec["query"], display=display, sort="date")
            groups.append(
                {
                    "id": spec["id"],
                    "label": spec["label"],
                    "query": spec["query"],
                    "total": payload.get("total"),
                    "items": (payload.get("items") or [])[:display],
                    "source": payload.get("source"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:180]
            groups.append({"id": spec["id"], "label": spec["label"], "query": spec["query"], "items": [], "error": error})
    encyc: list[dict[str, str]] = []
    for query in ENCYC_QUERIES:
        try:
            encyc.extend(search_encyc(client_id, client_secret, query, display=1))
        except Exception:  # noqa: BLE001
            continue
    out = {
        "configured": True,
        "used_in_quant": False,
        "fetched_at": now,
        "error": error,
        "groups": groups,
        "encyc": encyc[:6],
        "disclaimer": "네이버 검색 API 헤드라인입니다. 매수 지시가 아닙니다.",
    }
    _news_cache = (now, out)
    return out


def company_bundle(client_id: str, client_secret: str, company: str | None, ticker: str | None) -> dict[str, Any]:
    query = company_query(company, ticker)
    news = search_news(client_id, client_secret, query)
    web_items: list[dict[str, str]] = []
    try:
        web_items = search_web(client_id, client_secret, query, display=5).get("items") or []
    except RuntimeError:
        web_items = []
    encyc = search_encyc(client_id, client_secret, company or query)
    return {
        "query": query,
        "news": news.get("items") or [],
        "web": web_items,
        "total": news.get("total"),
        "encyc": encyc,
        "source": news.get("source"),
    }
