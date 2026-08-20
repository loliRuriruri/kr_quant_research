from __future__ import annotations

import html
import re
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
