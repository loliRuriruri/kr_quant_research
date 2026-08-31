"""KIS read-only investor-flow adapter. Never places orders. Overlay only."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_quant.flow.types import display_name, normalize_investor_type
from kr_quant.universe.identifiers import UNSUPPORTED_TICKER_FORMAT, canonical_ticker, provider_symbol

logger = logging.getLogger("kr_quant.ingest.kis")

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

_token: dict[str, Any] = {
    "access_token": None,
    "expires_at": 0.0,
    "issued_at": None,
    "reason": None,
    "source": None,
    "retry_at": 0.0,
    "fingerprint": None,
}
_token_lock = threading.Lock()
_token_cv = threading.Condition(_token_lock)
_issuing = False
CACHE_NAME = "kis_token.dpapi"
RATE_LIMIT_SECONDS = 60.0


class KisTokenError(RuntimeError):
    """Token issue or refresh failed. Message must never include the token."""


class KisTokenRateLimited(KisTokenError):
    def __init__(self, retry_at: float, message: str) -> None:
        super().__init__(message)
        self.retry_at = retry_at


def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def _fingerprint(app_key: str) -> str:
    return hashlib.sha256(app_key.encode("utf-8")).hexdigest()[:16]


def default_token_cache_path() -> Path:
    from kr_quant.settings import find_project_root

    return find_project_root() / "data" / "cache" / CACHE_NAME


def clear_token_cache(*, persist: bool = False, cache_path: Path | None = None) -> None:
    """Drop the in-memory token. persist=True also deletes the local blob."""
    global _issuing
    with _token_lock:
        _token.update(
            {
                "access_token": None,
                "expires_at": 0.0,
                "issued_at": None,
                "reason": None,
                "source": None,
                "retry_at": 0.0,
                "fingerprint": None,
            }
        )
        _issuing = False
    if persist:
        path = cache_path or default_token_cache_path()
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def protect_bytes(data: bytes) -> bytes | None:
    """Encrypt with Windows DPAPI. Returns None when persistence is unsafe."""
    if os.name != "nt" or not data:
        return None
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def unprotect_bytes(blob: bytes) -> bytes | None:
    if os.name != "nt" or not blob:
        return None
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(blob)
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def token_meta() -> dict[str, Any]:
    """Secret-free view of the current token cache."""
    now = time.time()
    cached = bool(_token.get("access_token") and float(_token.get("expires_at") or 0) > now)
    retry_at = float(_token.get("retry_at") or 0)
    return {
        "cached": cached,
        "expires_at": _iso(float(_token["expires_at"])) if cached else None,
        "issued_at": _token.get("issued_at"),
        "last_reason": _token.get("reason"),
        "source": _token.get("source") if cached else None,
        "retry_at": _iso(retry_at) if retry_at > now else None,
        "can_issue": retry_at <= now,
    }


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

    def __init__(
        self,
        app_key: str | None,
        app_secret: str | None,
        base_url: str,
        *,
        cache_path: Path | None = None,
    ) -> None:
        self.app_key = (app_key or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.base_url = (base_url or "https://openapi.koreainvestment.com:9443").rstrip("/")
        self.cache_path = Path(cache_path) if cache_path else default_token_cache_path()

    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def missing_reason(self) -> str:
        if not self.configured():
            return "KIS 앱 키/시크릿이 없습니다. API 설정에서 한국투자증권 키를 저장하세요."
        return ""

    def token_status(self) -> dict[str, Any]:
        if not self.configured():
            return {"configured": False, "cached": False, "can_issue": False}
        self._load_persistent()
        return {"configured": True, **token_meta()}

    def _load_persistent(self) -> None:
        if _token.get("access_token"):
            return
        path = self.cache_path
        if not path.exists():
            return
        try:
            raw = unprotect_bytes(path.read_bytes())
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("fingerprint") != _fingerprint(self.app_key):
            return
        expires_at = float(payload.get("expires_at") or 0)
        if expires_at <= time.time() or not payload.get("access_token"):
            return
        _token.update(
            {
                "access_token": payload.get("access_token"),
                "expires_at": expires_at,
                "issued_at": payload.get("issued_at"),
                "reason": "persistent_cache",
                "source": "dpapi",
                "fingerprint": payload.get("fingerprint"),
            }
        )
        logger.info(
            "KIS token cache hit source=dpapi expires_at=%s reason=persistent_cache",
            _iso(expires_at),
        )

    def _save_persistent(self) -> None:
        token = _token.get("access_token")
        if not token:
            return
        payload = {
            "access_token": token,
            "expires_at": _token.get("expires_at"),
            "issued_at": _token.get("issued_at"),
            "fingerprint": _fingerprint(self.app_key),
        }
        blob = protect_bytes(json.dumps(payload).encode("utf-8"))
        if not blob:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_bytes(blob)
        except OSError as exc:
            logger.warning("KIS token persist skipped: %s", type(exc).__name__)

    def _cached_token(self) -> str | None:
        now = time.time()
        if _token.get("access_token") and float(_token.get("expires_at") or 0) > now:
            if _token.get("fingerprint") in {None, _fingerprint(self.app_key)}:
                return str(_token["access_token"])
        return None

    def token(self, timeout: int = 20, *, reason: str = "collect", force: bool = False) -> str:
        if not self.configured():
            raise KisTokenError(self.missing_reason())
        global _issuing
        with _token_cv:
            self._load_persistent()
            if not force:
                cached = self._cached_token()
                if cached:
                    return cached
            retry_at = float(_token.get("retry_at") or 0)
            now = time.time()
            if retry_at > now:
                when = _iso(retry_at)
                raise KisTokenRateLimited(retry_at, f"KIS 토큰 발급 제한 · 다음 가능 {when}")
            while _issuing:
                _token_cv.wait(timeout=1.0)
                if not force:
                    cached = self._cached_token()
                    if cached:
                        return cached
            _issuing = True
        try:
            return self._issue_token(timeout=timeout, reason=reason)
        finally:
            with _token_cv:
                _issuing = False
                _token_cv.notify_all()

    def _issue_token(self, *, timeout: int, reason: str) -> str:
        import requests

        now = time.time()
        logger.info("KIS token issue start reason=%s", reason)
        resp = requests.post(
            self.base_url + TOKEN_PATH,
            headers={"content-type": "application/json"},
            json={"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret},
            timeout=timeout,
        )
        body_text = resp.text or ""
        if resp.status_code >= 400 or "EGW00133" in body_text or "1분당 1회" in body_text:
            if "EGW00133" in body_text or "1분당 1회" in body_text or resp.status_code == 403:
                retry_at = now + RATE_LIMIT_SECONDS
                with _token_lock:
                    _token["retry_at"] = retry_at
                logger.info("KIS token rate-limited reason=%s retry_at=%s", reason, _iso(retry_at))
                raise KisTokenRateLimited(retry_at, f"KIS 토큰 발급 제한 · 다음 가능 {_iso(retry_at)}")
            raise KisTokenError(f"KIS 토큰 HTTP {resp.status_code}")
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise KisTokenError("KIS 토큰 응답에 access_token이 없습니다.")
        expires_at = now + max(60, int(body.get("expires_in") or 86400) - 60)
        issued_at = _iso(now)
        with _token_lock:
            _token.update(
                {
                    "access_token": token,
                    "expires_at": expires_at,
                    "issued_at": issued_at,
                    "reason": reason,
                    "source": "issued",
                    "retry_at": 0.0,
                    "fingerprint": _fingerprint(self.app_key),
                }
            )
        self._save_persistent()
        logger.info("KIS token issued reason=%s expires_at=%s", reason, _iso(expires_at))
        return str(token)

    def fetch_stock_investor(self, ticker: str, timeout: int = 20) -> dict[str, Any]:
        """Single-stock KIS inquire-investor. Not for the full universe."""
        import requests

        code, err = provider_symbol("kis", ticker)
        if err:
            raise RuntimeError(err)
        token = self.token(reason="collect")
        resp = self._investor_get(code, token, timeout)
        if resp.status_code == 401:
            logger.info("KIS investor 401, refreshing token once")
            token = self.token(reason="refresh_401", force=True)
            resp = self._investor_get(code, token, timeout)
            if resp.status_code == 401:
                raise KisTokenError("KIS 수급 401이 반복되어 중단했습니다.")
        if resp.status_code >= 400:
            raise RuntimeError(f"KIS 수급 HTTP {resp.status_code}")
        return resp.json()

    def _investor_get(self, code: str, token: str, timeout: int):
        import requests

        return requests.get(
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

    def collect_stock(self, ticker: str) -> list[dict[str, Any]]:
        _code, err = provider_symbol("kis", ticker)
        if err:
            return []
        payload = self.fetch_stock_investor(ticker)
        return parse_investor_payload(payload, ticker, source="KIS")
