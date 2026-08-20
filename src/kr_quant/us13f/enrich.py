from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from kr_quant.settings import Settings
from kr_quant.us13f.names import fallback_note, korean_for_issuer, korean_for_ticker

OPENFIGI = "https://api.openfigi.com/v3/mapping"
EX_PREF = ("US", "UN", "UW", "UA", "UQ", "UR")


def _cusip_cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "cusip_map.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick_figi(rows: list[dict[str, Any]] | None) -> dict[str, str] | None:
    if not rows:
        return None
    ranked: list[dict[str, Any]] = []
    for item in rows:
        exch = str(item.get("exchCode") or "")
        score = 0
        if exch in EX_PREF:
            score += 10 - list(EX_PREF).index(exch)
        st = str(item.get("securityType") or "")
        if "Common" in st:
            score += 5
        if st in {"ETP", "ETF"}:
            score += 3
        ranked.append({**item, "_score": score})
    ranked.sort(key=lambda r: int(r.get("_score") or 0), reverse=True)
    best = ranked[0]
    ticker = str(best.get("ticker") or "").strip()
    if not ticker:
        return None
    return {
        "ticker": ticker,
        "name": str(best.get("name") or ""),
        "type": str(best.get("securityType") or ""),
        "exch": str(best.get("exchCode") or ""),
    }


def resolve_cusips(root: Path, cusips: list[str]) -> dict[str, dict[str, str]]:
    cache = _load_json(_cusip_cache_path(root))
    missing = [c for c in dict.fromkeys(cusips) if c and c not in cache]
    if missing:
        import requests

        for i in range(0, len(missing), 10):
            chunk = missing[i : i + 10]
            body = [{"idType": "ID_CUSIP", "idValue": c} for c in chunk]
            try:
                resp = requests.post(OPENFIGI, json=body, timeout=20, headers={"Content-Type": "application/json"})
                if resp.status_code >= 400:
                    continue
                payload = resp.json()
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(payload, list):
                continue
            for cusip, item in zip(chunk, payload, strict=False):
                picked = _pick_figi(item.get("data") if isinstance(item, dict) else None)
                cache[cusip] = picked or {}
            time.sleep(0.25)
        _save_json(_cusip_cache_path(root), cache)
    return cache


def filer_lookup(root: Path) -> dict[str, dict[str, str]]:
    path = root / "config" / "us_13f_filers.yaml"
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for spec in data.get("filers") or []:
        if not isinstance(spec, dict):
            continue
        en = str(spec.get("name") or "")
        rec = {
            "name_ko": str(spec.get("name_ko") or en),
            "who_ko": str(spec.get("who_ko") or ""),
            "name": en,
        }
        if en:
            out[en] = rec
        ident = str(spec.get("id") or "")
        if ident:
            out[ident] = rec
    return out


def _ko_filer(name: str, table: dict[str, dict[str, str]]) -> tuple[str, str]:
    rec = table.get(name) or {}
    return rec.get("name_ko") or name, rec.get("who_ko") or ""


def _annotate_security(row: dict[str, Any], cmap: dict[str, dict[str, str]]) -> None:
    cusip = str(row.get("cusip") or "").upper()
    issuer = str(row.get("issuer") or "")
    mapped = cmap.get(cusip) or {}
    ticker = str(mapped.get("ticker") or "").strip() or None
    hint = korean_for_issuer(issuer)
    if hint:
        if hint[0]:
            ticker = ticker or hint[0]
        else:
            ticker = None
    if ticker:
        row["ticker"] = ticker
    else:
        row.pop("ticker", None)
    ko = korean_for_ticker(ticker) if ticker else None
    if ko:
        row["issuer_ko"] = ko[0]
        row["note_ko"] = ko[1]
    elif hint:
        if hint[0]:
            row["ticker"] = row.get("ticker") or hint[0]
        row["issuer_ko"] = hint[1]
        row["note_ko"] = hint[2]
    else:
        row["issuer_ko"] = issuer.title() if issuer else (ticker or cusip)
        row["note_ko"] = fallback_note(issuer, mapped.get("type"))
    if ticker and not row.get("yahoo"):
        row["yahoo"] = f"https://finance.yahoo.com/quote/{ticker}"


def _map_filer_fields(row: dict[str, Any], funds: dict[str, dict[str, str]]) -> None:
    if row.get("filer"):
        ko, who = _ko_filer(str(row["filer"]), funds)
        row["filer_ko"] = ko
        row["filer_who"] = who
    if row.get("name"):
        ko, who = _ko_filer(str(row["name"]), funds)
        row["name_ko"] = ko
        row["who_ko"] = who or row.get("who_ko") or ""
    for key in ("filers", "buyers", "sellers"):
        names = row.get(key)
        if isinstance(names, list):
            row[f"{key}_ko"] = [_ko_filer(str(n), funds)[0] for n in names]


def collect_cusips(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in ("new", "exits", "increases", "common", "trend"):
        for row in payload.get(key) or []:
            if isinstance(row, dict) and row.get("cusip"):
                found.append(str(row["cusip"]).upper())
    for filer in payload.get("filers") or []:
        for row in (filer or {}).get("top") or []:
            if isinstance(row, dict) and row.get("cusip"):
                found.append(str(row["cusip"]).upper())
    return found


def enrich_payload(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    funds = filer_lookup(settings.root)
    cmap = resolve_cusips(settings.root, collect_cusips(payload))
    for key in ("new", "exits", "increases", "common", "trend"):
        for row in payload.get(key) or []:
            if isinstance(row, dict):
                _annotate_security(row, cmap)
                _map_filer_fields(row, funds)
    for filer in payload.get("filers") or []:
        if not isinstance(filer, dict):
            continue
        _map_filer_fields(filer, funds)
        for row in filer.get("top") or []:
            if isinstance(row, dict):
                _annotate_security(row, cmap)
                row["filer"] = filer.get("name")
                row["filer_ko"] = filer.get("name_ko")
    payload["localized"] = True
    return payload
