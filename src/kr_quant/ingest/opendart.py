from __future__ import annotations

import logging
import time
from typing import Any

import requests

from kr_quant.exceptions import SourceNotReady
from kr_quant.ingest.base import FilingAdapter

logger = logging.getLogger("kr_quant.ingest.opendart")


class OpenDartAdapter(FilingAdapter):
    def __init__(self, api_key: str, base_url: str, sleep_sec: float = 0.15, timeout: int = 30) -> None:
        if not api_key:
            raise SourceNotReady("OPENDART_API_KEY is not set")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.sleep_sec = sleep_sec
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str], raw: bool = False) -> Any:
        time.sleep(self.sleep_sec)
        q = {"crtfc_key": self.api_key, **params}
        url = f"{self.base_url}/{path}"
        resp = requests.get(url, params=q, timeout=self.timeout)
        resp.raise_for_status()
        if raw:
            return resp.content
        data = resp.json()
        status = str(data.get("status", "000"))
        if status not in {"000", "013"}:  # 013 = no data
            raise SourceNotReady(f"OpenDART {path} status={status} message={data.get('message')}")
        return data

    def fetch_corp_map(self) -> bytes:
        return self._get("corpCode.xml", {}, raw=True)

    def fetch_company(self, corp_code: str) -> dict[str, Any]:
        return self._get("company.json", {"corp_code": corp_code})

    def fetch_financials(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        fs_div: str,
    ) -> dict[str, Any]:
        return self._get(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )

    def fetch_list(self, corp_code: str, bgn_de: str, end_de: str) -> dict[str, Any]:
        params = {"bgn_de": bgn_de, "end_de": end_de, "page_count": "100"}
        if corp_code:
            params["corp_code"] = corp_code
        return self._get("list.json", params)

    def fetch_list_range(
        self,
        bgn_de: str,
        end_de: str,
        *,
        page_no: int = 1,
        page_count: int = 100,
        pblntf_detail_ty: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": str(page_no),
            "page_count": str(page_count),
        }
        if pblntf_detail_ty:
            params["pblntf_detail_ty"] = pblntf_detail_ty
        return self._get("list.json", params)

    def fetch_majorstock(self, corp_code: str) -> dict[str, Any]:
        return self._get("majorstock.json", {"corp_code": corp_code})
