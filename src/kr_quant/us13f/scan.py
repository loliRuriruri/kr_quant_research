from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from kr_quant.settings import Settings
from kr_quant.us13f.edgar import load_period_holdings, recent_13f, submissions
from kr_quant.us13f.enrich import enrich_payload
from kr_quant.us13f.parse import common_holdings, compare_holdings, trend_rows


def cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "us13f.json"


def filers_path(root: Path) -> Path:
    return root / "config" / "us_13f_filers.yaml"


def load_filers(root: Path) -> dict[str, Any]:
    path = filers_path(root)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return data or {"filers": [], "used_in_quant": False}


def _load_cache(root: Path) -> dict[str, Any] | None:
    path = cache_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_cache(root: Path, payload: dict[str, Any]) -> None:
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _public_holdings(book: dict[str, dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = sorted(book.values(), key=lambda r: int(r.get("value") or 0), reverse=True)
    return [
        {
            "cusip": r["cusip"],
            "issuer": r.get("issuer"),
            "value": r.get("value"),
            "shares": r.get("shares"),
            "weight": r.get("weight"),
        }
        for r in rows[:limit]
    ]


def _with_comments(payload: dict[str, Any]) -> dict[str, Any]:
    from kr_quant.web.comments import annotate_13f

    return annotate_13f(payload)


def load_13f(settings: Settings) -> dict[str, Any]:
    cached = _load_cache(settings.root)
    if cached and cached.get("filers"):
        return _with_comments(enrich_payload(cached, settings))
    cfg = load_filers(settings.root)
    return {
        "configured": True,
        "used_in_quant": False,
        "need_refresh": True,
        "filers": [],
        "new": [],
        "exits": [],
        "increases": [],
        "common": [],
        "trend": [],
        "disclaimer": cfg.get("disclaimer") or "13F는 SEC EDGAR 원문.",
    }


def refresh_13f(settings: Settings, *, force: bool = False) -> dict[str, Any]:
    cached = None if force else _load_cache(settings.root)
    if cached and (time.time() - float(cached.get("fetched_at") or 0)) < 6 * 3600:
        return _with_comments(enrich_payload(cached, settings))
    cfg = load_filers(settings.root)
    filer_cfg = [f for f in (cfg.get("filers") or []) if isinstance(f, dict)]
    filer_rows: list[dict[str, Any]] = []
    changes_by: dict[str, list[dict[str, Any]]] = {}
    current_books: dict[str, dict[str, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    periods: set[str] = set()

    for spec in filer_cfg:
        cik = str(spec.get("cik") or "")
        name = str(spec.get("name") or cik)
        try:
            sub = submissions(settings, cik)
            filings = recent_13f(sub, limit=2)
            if not filings:
                errors.append({"filer": name, "error": "13F-HR 없음"})
                continue
            current = load_period_holdings(settings, cik, filings[0])
            previous = load_period_holdings(settings, cik, filings[1]) if len(filings) > 1 else None
            book = current["holdings"]
            prev_book = previous["holdings"] if previous else {}
            changes = compare_holdings(prev_book, book)
            current_books[name] = book
            changes_by[name] = changes
            periods.add(str(current.get("report_date") or ""))
            new_n = sum(1 for c in changes if c["action"] == "new")
            exit_n = sum(1 for c in changes if c["action"] == "exit")
            filer_rows.append(
                {
                    "id": spec.get("id"),
                    "name": name,
                    "cik": cik.zfill(10),
                    "manager": sub.get("name") or name,
                    "report_date": current.get("report_date"),
                    "prev_report_date": (previous or {}).get("report_date"),
                    "filing_date": current.get("filing_date"),
                    "page": current.get("page"),
                    "whale": spec.get("whale"),
                    "n": current.get("n"),
                    "total_value": current.get("total_value"),
                    "new": new_n,
                    "exits": exit_n,
                    "top": _public_holdings(book, 8),
                    "used_in_quant": False,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"filer": name, "error": str(exc)[:220]})

    new_rows: list[dict[str, Any]] = []
    exit_rows: list[dict[str, Any]] = []
    inc_rows: list[dict[str, Any]] = []
    for filer, changes in changes_by.items():
        for row in changes:
            item = {**row, "filer": filer}
            if row["action"] == "new":
                new_rows.append(item)
            elif row["action"] == "exit":
                exit_rows.append(item)
            elif row["action"] == "increase":
                inc_rows.append(item)
    new_rows.sort(key=lambda r: int(r.get("value") or 0), reverse=True)
    exit_rows.sort(key=lambda r: int(r.get("prev_value") or 0), reverse=True)
    inc_rows.sort(key=lambda r: int(r.get("value_delta") or 0), reverse=True)
    common = common_holdings(current_books, min_filers=2)
    trend = trend_rows(changes_by)
    out = {
        "configured": True,
        "used_in_quant": False,
        "fetched_at": time.time(),
        "source": "SEC EDGAR",
        "source_page": "https://www.sec.gov/edgar/search/",
        "whale_page": "https://whalewisdom.com/",
        "periods": sorted(p for p in periods if p),
        "scanned": len(filer_rows),
        "errors": errors,
        "disclaimer": cfg.get("disclaimer")
        or "13F는 분기 말 스냅샷이며 45일 시차입니다. SEC EDGAR 원문입니다.",
        "filers": filer_rows,
        "new": new_rows[:80],
        "exits": exit_rows[:80],
        "increases": inc_rows[:80],
        "common": common[:80],
        "trend": trend[:80],
    }
    out = enrich_payload(out, settings)
    _save_cache(settings.root, out)
    return _with_comments(out)
