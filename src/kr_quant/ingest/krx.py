from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests

from kr_quant.exceptions import SourceNotReady
from kr_quant.ingest.base import MarketDataAdapter

logger = logging.getLogger("kr_quant.ingest.krx")

MARKET_ENDPOINT = {
    "KOSPI": "sto/stk_bydd_trd",
    "KOSDAQ": "sto/ksq_bydd_trd",
}
MASTER_ENDPOINT = {
    "KOSPI": "sto/stk_isu_base_info",
    "KOSDAQ": "sto/ksq_isu_base_info",
}
INDEX_ENDPOINT = {
    "KOSPI": "sto/stk_bydd_idx",
    "KOSDAQ": "sto/ksq_bydd_idx",
}


class KrxOpenApiAdapter(MarketDataAdapter):
    """Official KRX Open API adapter.

    Requires KRX_API_KEY and a subscribed service for each endpoint.
    AUTH_KEY is sent as a request header.
    """

    def __init__(self, api_key: str, base_url: str, timeout: int = 30) -> None:
        if not api_key:
            raise SourceNotReady("KRX_API_KEY is not set")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        from kr_quant.ingest.http_retry import request_with_retry

        url = f"{self.base_url}/{endpoint}"
        headers = {"AUTH_KEY": self.api_key, "Accept": "application/json"}
        resp = request_with_retry(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
            retries=2,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_daily(self, as_of: date, market: str) -> list[dict[str, Any]]:
        endpoint = MARKET_ENDPOINT[market]
        bas = as_of.strftime("%Y%m%d")
        payload = self._get(endpoint, {"basDd": bas})
        rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
        if not rows:
            raise SourceNotReady(f"KRX {market} empty for {bas}")
        first = rows[0]
        bas_dd = str(first.get("BAS_DD") or first.get("basDd") or "")
        if bas_dd and bas_dd != bas:
            raise SourceNotReady(f"KRX {market} returned BAS_DD={bas_dd}, expected {bas}")
        return list(rows)

    def fetch_daily_maybe(self, as_of: date, market: str) -> list[dict[str, Any]]:
        endpoint = MARKET_ENDPOINT[market]
        bas = as_of.strftime("%Y%m%d")
        payload = self._get(endpoint, {"basDd": bas})
        rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
        return list(rows or [])

    def fetch_master(self, as_of: date, market: str) -> list[dict[str, Any]]:
        endpoint = MASTER_ENDPOINT[market]
        payload = self._get(endpoint, {"basDd": as_of.strftime("%Y%m%d")})
        return list(payload.get("OutBlock_1") or [])

    def fetch_index(self, as_of: date, market: str) -> dict[str, Any] | None:
        endpoint = INDEX_ENDPOINT.get(market)
        if not endpoint:
            return None
        try:
            payload = self._get(endpoint, {"basDd": as_of.strftime("%Y%m%d")})
        except Exception as exc:  # noqa: BLE001
            logger.warning("KRX index fetch failed for %s: %s", market, exc)
            return None
        rows = payload.get("OutBlock_1") or payload.get("output") or []
        return rows[0] if rows else None


def parse_krx_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace(" ", "")
    if text in {"", "-", "null", "None"}:
        return None
    return float(text)
