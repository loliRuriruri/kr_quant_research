from __future__ import annotations

import time
from typing import Any

import requests

from kr_quant.settings import Settings

DATA = "https://data.sec.gov"
ARCH = "https://www.sec.gov/Archives/edgar/data"


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, application/xml, text/xml, */*",
    }


def _cik_nolead(cik: str) -> str:
    return str(int(str(cik).strip()))


def _cik10(cik: str) -> str:
    return str(cik).strip().zfill(10)


def _adsh_nodash(adsh: str) -> str:
    return str(adsh).replace("-", "")


def _get(settings: Settings, url: str, *, json_mode: bool = False) -> Any:
    resp = requests.get(url, headers=_headers(settings), timeout=30)
    if resp.status_code == 403:
        raise RuntimeError(
            "SEC가 자동 접근을 막았습니다. .env에 SEC_USER_AGENT='이름 이메일' 형식으로 넣어 보세요."
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"SEC HTTP {resp.status_code}: {url}")
    return resp.json() if json_mode else resp.text


def submissions(settings: Settings, cik: str) -> dict[str, Any]:
    url = f"{DATA}/submissions/CIK{_cik10(cik)}.json"
    return _get(settings, url, json_mode=True)


def filing_index(settings: Settings, cik: str, adsh: str) -> dict[str, Any]:
    url = f"{ARCH}/{_cik_nolead(cik)}/{_adsh_nodash(adsh)}/index.json"
    return _get(settings, url, json_mode=True)


def filing_text(settings: Settings, cik: str, adsh: str, name: str) -> str:
    url = f"{ARCH}/{_cik_nolead(cik)}/{_adsh_nodash(adsh)}/{name}"
    return _get(settings, url, json_mode=False)


def filing_page(cik: str, adsh: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{_cik_nolead(cik)}/{_adsh_nodash(adsh)}/{adsh}-index.html"


def _index_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    directory = payload.get("directory") if isinstance(payload, dict) else None
    item = (directory or payload or {}).get("item") if isinstance(directory or payload, dict) else None
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return [x for x in item if isinstance(x, dict)]
    return []


def pick_infotable_name(index_payload: dict[str, Any]) -> str | None:
    items = _index_items(index_payload)
    xmls: list[dict[str, Any]] = []
    for it in items:
        name = str(it.get("name") or "")
        lower = name.lower()
        if not lower.endswith(".xml"):
            continue
        if "primary_doc" in lower or lower.startswith("xsl"):
            continue
        xmls.append(it)
    if not xmls:
        return None
    named = [
        it
        for it in xmls
        if "inftable" in str(it.get("name") or "").lower()
        or "informationtable" in str(it.get("name") or "").lower()
        or "13f" in str(it.get("name") or "").lower()
    ]
    pool = named or xmls

    def size_of(it: dict[str, Any]) -> int:
        try:
            return int(str(it.get("size") or "0") or 0)
        except ValueError:
            return 0

    return str(max(pool, key=size_of).get("name") or "") or None


def recent_13f(sub: dict[str, Any], limit: int = 2) -> list[dict[str, str]]:
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    rows: list[dict[str, str]] = []
    for i, form in enumerate(forms):
        if str(form) not in {"13F-HR", "13F-HR/A"}:
            continue
        acc = (recent.get("accessionNumber") or [None])[i] if i < len(recent.get("accessionNumber") or []) else None
        if not acc:
            continue
        rows.append(
            {
                "form": str(form),
                "accession": str(acc),
                "filing_date": str((recent.get("filingDate") or [""])[i] if i < len(recent.get("filingDate") or []) else ""),
                "report_date": str((recent.get("reportDate") or [""])[i] if i < len(recent.get("reportDate") or []) else ""),
                "primary": str((recent.get("primaryDocument") or [""])[i] if i < len(recent.get("primaryDocument") or []) else ""),
            }
        )
    best: dict[str, dict[str, str]] = {}
    for row in rows:
        period = row.get("report_date") or ""
        prev = best.get(period)
        if prev is None or (row.get("filing_date") or "") >= (prev.get("filing_date") or ""):
            best[period] = row
    ordered = sorted(best.values(), key=lambda r: r.get("report_date") or "", reverse=True)
    return ordered[:limit]


def load_period_holdings(settings: Settings, cik: str, filing: dict[str, str], pause: float = 0.2) -> dict[str, Any]:
    from kr_quant.us13f.parse import aggregate_holdings, parse_infotable

    time.sleep(pause)
    index = filing_index(settings, cik, filing["accession"])
    name = pick_infotable_name(index)
    if not name:
        raise RuntimeError("information table XML을 찾지 못했습니다.")
    time.sleep(pause)
    xml = filing_text(settings, cik, filing["accession"], name)
    rows = parse_infotable(xml)
    book = aggregate_holdings(rows)
    return {
        "form": filing.get("form"),
        "accession": filing.get("accession"),
        "filing_date": filing.get("filing_date"),
        "report_date": filing.get("report_date"),
        "file": name,
        "page": filing_page(cik, filing["accession"]),
        "n": len(book),
        "total_value": sum(int(v["value"]) for v in book.values()),
        "holdings": book,
    }
