"""KIS read-only investor-flow adapter. Never places orders. Overlay only."""

from __future__ import annotations

import time
from typing import Any

from kr_quant.flow.types import display_name, normalize_investor_type
from kr_quant.universe.identifiers import UNSUPPORTED_TICKER_FORMAT, canonical_ticker, provider_symbol

TOKEN_PATH = "/oauth2/tokenP"
INVESTOR_PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor"
INVESTOR_TR_ID = "FHKST01010900"

# Map KIS field stems to canonical types. FUND stays 기금, not 연기금.
FIELD_MAP = {
    "prsn_ntby_qty": ("INDIVIDUAL", "qty"),
    "frgn_ntby_qty": ("FOREIGN", "qty"),
    "orgn_ntby_qty": ("INSTITUTION_TOTAL", "qty"),
    "fund_ntby_qty": ("FUND", "qty"),
    "prsn_ntby_tr_pbmn": ("INDIVIDUAL", "value"),
    "frgn_ntby_tr_pbmn": ("FOREIGN", "value"),
    "orgn_ntby_tr_pbmn": ("INSTITUTION_TOTAL", "value"),
    "fund_ntby_tr_pbmn": ("FUND", "value"),
}

_token: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_investor_payload(payload: dict[str, Any], ticker: str, *, source: str = "KIS") -> list[dict[str, Any]]:
    """Turn a KIS-like JSON blob into investor_flows_daily rows. No HTTP."""
    code = canonical_ticker(ticker)
    blocks: list[dict[str, Any]] = []
    output = payload.get("output") or payload.get("output1") or payload.get("output2")
    if isinstance(output, dict):
        blocks = [output]
    elif isinstance(output, list):
        blocks = [b for b in output if isinstance(b, dict)]
    elif isinstance(payload.get("rows"), list):
        blocks = [b for b in payload["rows"] if isinstance(b, dict)]
    out: list[dict[str, Any]] = []
    for block in blocks:
        day = str(block.get("stck_bsop_date") or block.get("date") or block.get("trade_date") or "")
        if len(day) == 8 and day.isdigit():
            day = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        if not day:
            continue
        buckets: dict[str, dict[str, Any]] = {}
        for key, val in block.items():
            stem = str(key).lower()
            mapped = FIELD_MAP.get(stem)
            if not mapped:
                canon = normalize_investor_type(stem)
                if not canon:
                    continue
                kind = "qty" if "qty" in stem or "ntby" in stem else "value"
                mapped = (canon, kind)
            canon, kind = mapped
            bucket = buckets.setdefault(
                canon,
                {
                    "trade_date": day,
                    "ticker": code,
                    "investor_type": canon,
                    "investor_type_raw": stem,
                    "buy_value": None,
                    "sell_value": None,
                    "net_value": None,
                    "buy_qty": None,
                    "sell_qty": None,
                    "net_qty": None,
                    "is_final": True,
                    "source": source,
                    "used_in_quant": False,
                    "label_ko": display_name(canon),
                },
            )
            num = _num(val)
            if kind == "qty":
                bucket["net_qty"] = num
            else:
                bucket["net_value"] = num
        out.extend(buckets.values())
    return out


class KisInvestorAdapter:
    """Read-only. Collects per-ticker investor days. Not a bulk ranking API."""

    def __init__(self, app_key: str | None, app_secret: str | None, base_url: str) -> None:
        self.app_key = (app_key or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.base_url = (base_url or "https://openapi.koreainvestment.com:9443").rstrip("/")

    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def missing_reason(self) -> str:
        if not self.configured():
            return "KIS 앱 키/시크릿이 없습니다. API 설정에서 한국투자증권 키를 저장하세요."
        return ""

    def token(self, timeout: int = 20) -> str:
        if not self.configured():
            raise RuntimeError(self.missing_reason())
        now = time.time()
        if _token.get("access_token") and float(_token.get("expires_at") or 0) > now:
            return str(_token["access_token"])
        import requests

        resp = requests.post(
            self.base_url + TOKEN_PATH,
            headers={"content-type": "application/json"},
            json={"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"KIS 토큰 HTTP {resp.status_code}")
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise RuntimeError("KIS 토큰 응답에 access_token이 없습니다.")
        _token["access_token"] = token
        _token["expires_at"] = now + max(60, int(body.get("expires_in") or 86400) - 60)
        return str(token)

    def fetch_stock_investor(self, ticker: str, timeout: int = 20) -> dict[str, Any]:
        """Single-stock KIS inquire-investor. Not for the full universe."""
        import requests

        code, err = provider_symbol("kis", ticker)
        if err:
            raise RuntimeError(err)
        token = self.token()
        resp = requests.get(
            self.base_url + INVESTOR_PATH,
            headers={
                "authorization": f"Bearer {token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": INVESTOR_TR_ID,
                "custtype": "P",
            },
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"KIS 수급 HTTP {resp.status_code}: {resp.text[:160]}")
        return resp.json()

    def collect_stock(self, ticker: str) -> list[dict[str, Any]]:
        _code, err = provider_symbol("kis", ticker)
        if err:
            return []
        payload = self.fetch_stock_investor(ticker)
        return parse_investor_payload(payload, ticker, source="KIS")
