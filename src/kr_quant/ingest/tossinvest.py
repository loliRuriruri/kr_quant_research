from __future__ import annotations

import threading
import time
from typing import Any

BASE = "https://openapi.tossinvest.com"

_lock = threading.Lock()
_token: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def issue_token(client_id: str, client_secret: str, timeout: int = 15) -> str:
    import requests

    if not client_id or not client_secret:
        raise RuntimeError("토스증권 Client ID/Secret이 없습니다.")
    resp = requests.post(
        f"{BASE}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"토스증권 토큰 HTTP {resp.status_code}: {resp.text[:180]}")
    body = resp.json()
    token = body.get("access_token")
    if not token:
        raise RuntimeError("토스증권 토큰 응답에 access_token이 없습니다.")
    expires = int(body.get("expires_in") or 1800)
    with _lock:
        _token["access_token"] = token
        _token["expires_at"] = time.time() + max(60, expires - 60)
    return str(token)


def _bearer(client_id: str, client_secret: str) -> str:
    with _lock:
        token = _token.get("access_token")
        exp = float(_token.get("expires_at") or 0)
    if token and exp > time.time():
        return str(token)
    return issue_token(client_id, client_secret)


def _get(client_id: str, client_secret: str, path: str, params: dict[str, Any] | None = None) -> Any:
    import requests

    token = _bearer(client_id, client_secret)
    resp = requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=15,
    )
    if resp.status_code == 401:
        token = issue_token(client_id, client_secret)
        resp = requests.get(
            f"{BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=15,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"토스증권 {path} HTTP {resp.status_code}: {resp.text[:200]}")
    return _unwrap(resp.json())


def get_prices(client_id: str, client_secret: str, symbols: list[str]) -> list[dict[str, Any]]:
    joined = ",".join(symbols)
    data = _get(client_id, client_secret, "/api/v1/prices", {"symbols": joined})
    if isinstance(data, dict):
        rows = data.get("prices") or data.get("items") or []
        return rows if isinstance(rows, list) else [data]
    return data if isinstance(data, list) else []


def get_stocks(client_id: str, client_secret: str, symbols: list[str]) -> list[dict[str, Any]]:
    joined = ",".join(symbols)
    data = _get(client_id, client_secret, "/api/v1/stocks", {"symbols": joined})
    if isinstance(data, dict):
        rows = data.get("stocks") or data.get("items") or []
        return rows if isinstance(rows, list) else [data]
    return data if isinstance(data, list) else []


def get_warnings(client_id: str, client_secret: str, symbol: str) -> list[Any]:
    data = _get(client_id, client_secret, f"/api/v1/stocks/{symbol}/warnings")
    if isinstance(data, dict):
        rows = data.get("warnings") or data.get("items") or []
        return rows if isinstance(rows, list) else [data]
    return data if isinstance(data, list) else []


def get_investor_trading(client_id: str, client_secret: str, symbol: str) -> dict[str, Any]:
    data = _get(client_id, client_secret, f"/api/v1/stocks/{symbol}/investor-trading")
    return data if isinstance(data, dict) else {"raw": data}


def _digits_code(symbol: Any) -> str:
    from kr_quant.universe.identifiers import canonical_ticker

    return canonical_ticker(symbol)


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def normalize_ranking_row(raw: dict[str, Any]) -> dict[str, Any]:
    price = raw.get("price") if isinstance(raw.get("price"), dict) else {}
    symbol = raw.get("symbol") or raw.get("code") or raw.get("productCode") or ""
    code = _digits_code(symbol)
    name = raw.get("name") or raw.get("stockName") or raw.get("koreanName") or raw.get("company")
    chg = _num(price.get("changeRate") if price else raw.get("changeRate"))
    last = _num(price.get("lastPrice") if price else raw.get("lastPrice") or raw.get("close"))
    return {
        "rank": raw.get("rank"),
        "code": code,
        "symbol": str(symbol),
        "name": name or code,
        "last": last,
        "change_rate": chg,
        "trading_amount": _num(raw.get("tradingAmount")),
        "page": f"https://www.tossinvest.com/stocks/A{code}" if code.isdigit() else f"https://www.tossinvest.com/stocks/{code}",
    }


def attach_stock_names(
    client_id: str,
    client_secret: str,
    rows: list[dict[str, Any]],
    local_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    names = {str(k).zfill(6) if str(k).isdigit() else str(k): str(v) for k, v in (local_names or {}).items() if v}
    missing = [r["code"] for r in rows if r.get("code") and r.get("name") in {None, "", r.get("code")}]
    uniq = list(dict.fromkeys(missing))
    if uniq:
        try:
            stocks = get_stocks(client_id, client_secret, uniq)
        except Exception:  # noqa: BLE001
            stocks = []
        for item in stocks:
            if not isinstance(item, dict):
                continue
            code = _digits_code(item.get("symbol"))
            if item.get("name"):
                names[code] = str(item["name"])
    for row in rows:
        code = row.get("code") or ""
        if names.get(code):
            row["name"] = names[code]
    return rows


def get_rankings(
    client_id: str,
    client_secret: str,
    *,
    ranking_type: str,
    market_country: str = "KR",
    duration: str = "1d",
    count: int = 10,
    exclude_caution: bool = True,
) -> dict[str, Any]:
    data = _get(
        client_id,
        client_secret,
        "/api/v1/rankings",
        {
            "type": ranking_type,
            "marketCountry": market_country,
            "duration": duration,
            "excludeInvestmentCaution": str(exclude_caution).lower(),
            "count": count,
        },
    )
    return data if isinstance(data, dict) else {"rankings": data}


def stock_snapshot(client_id: str, client_secret: str, symbol: str) -> dict[str, Any]:
    prices = get_prices(client_id, client_secret, [symbol])
    stocks = get_stocks(client_id, client_secret, [symbol])
    warnings = get_warnings(client_id, client_secret, symbol)
    investors = {}
    try:
        investors = get_investor_trading(client_id, client_secret, symbol)
    except RuntimeError:
        investors = {}
    quote = prices[0] if prices else {}
    info = stocks[0] if stocks else {}
    latest_inv = None
    records = investors.get("records") if isinstance(investors, dict) else None
    if isinstance(records, list) and records:
        latest_inv = records[0]
    return {
        "quote": quote,
        "info": info,
        "warnings": warnings,
        "investors": latest_inv,
        "page": f"https://www.tossinvest.com/stocks/A{symbol}" if symbol.isdigit() else f"https://www.tossinvest.com/stocks/{symbol}",
    }
