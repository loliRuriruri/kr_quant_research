# -*- coding: utf-8 -*-
"""Export read-only API responses for the full local dashboard UI.

The public site uses the same HTML/CSS/JS as localhost, but reads these
precomputed responses instead of calling the local FastAPI process.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402
from kr_quant.web.app import app  # noqa: E402
from kr_quant.settings import load_settings  # noqa: E402

SENSITIVE_KEY = re.compile(r"(api[_-]?key|secret|token|password|authorization|bearer|cookie)", re.I)

ROUTES: dict[str, str] = {
    "/api/status": "/api/status",
    "/api/guide": "/api/guide",
    "/api/results/top": "/api/results/top?n=100",
    "/api/results/all": "/api/results/all?limit=300",
    "/api/dashboard/tier1-briefing": "/api/dashboard/tier1-briefing?deterministic=true",
    "/api/rank/tier1-briefing": "/api/rank/tier1-briefing?deterministic=true",
    "/api/research/reports": "/api/research/reports",
    "/api/market": "/api/market",
    "/api/macro": "/api/macro",
    "/api/investor": "/api/investor",
    "/api/investor/events": "/api/investor/events?min_turn=5",
    "/api/sunzi": "/api/sunzi?n=300&universe=all",
    "/api/nps": "/api/nps",
    "/api/flow": "/api/flow?days=5",
    "/api/sectors": "/api/sectors",
    "/api/screens": "/api/screens",
    "/api/portfolio": "/api/portfolio",
    "/api/strategy": "/api/strategy",
    "/api/us13f": "/api/us13f",
    "/api/watchlist": "/api/watchlist",
    "/api/toss/rankings": "/api/toss/rankings",
    "/api/stocks/all": "/api/stocks/all",
    "/api/seasonality/highlights": "/api/seasonality/highlights",
    "/api/seasonality/discovery": "/api/seasonality/discovery?lookback_years=5&horizon_days=90",
    "/api/seasonality/themes": "/api/seasonality/themes?lookback_years=5&horizon_days=90",
    "/api/seasonality/ranked": "/api/seasonality/ranked?lookback_years=5&horizon_days=90",
    "/api/seasonality/events": "/api/seasonality/events?horizon_days=90",
    # Export the complete tradable universe once. The public read-only client
    # derives the selected month or event preset from each row's 12-month
    # statistics, matching the local API without needing multiple snapshots.
    "/api/seasonality/scan": "/api/seasonality/scan?month=1&min_win_rate=0&min_avg_return=-1",
}


PATH_PATTERN = re.compile(
    r"([A-Za-z]:\\[^\s\"'>{}]+|[A-Za-z]:/[^\s\"'>{}]+|/(?:home|Users)/[^\s\"'>{}]+)",
    re.IGNORECASE,
)


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not SENSITIVE_KEY.search(str(k))}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return clean(value.item())
        except Exception:
            pass
    if isinstance(value, str):
        value = PATH_PATTERN.sub("[local path omitted]", value)
        root_variants = {str(ROOT), str(ROOT).replace("\\", "/")}
        if any(root.lower() in value.lower() for root in root_variants):
            return "[local path omitted]"
    return value


def slug(route: str) -> str:
    return route.strip("/").replace("/", "-").replace("_", "-") or "root"


def public_ticker(value: Any) -> str:
    raw = str(value or "").replace(".0", "").strip().upper()
    if re.fullmatch(r"[0-9A-Z]{5,6}", raw) and re.search(r"[A-Z]", raw):
        return raw.zfill(6)
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.zfill(6) if digits else raw


def get_json(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path)
    if response.status_code != 200:
        return {"ok": False, "error": "공개 스냅샷 미수집", "status": response.status_code}
    data = response.json()
    return clean(data if isinstance(data, dict) else {"data": data})


def _profile_map() -> dict[str, dict[str, Any]]:
    """Load local company metadata once without external API calls."""
    import pandas as pd

    settings = load_settings()
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "master.parquet"
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        if "ticker" not in frame.columns:
            continue
        profiles: dict[str, dict[str, Any]] = {}
        for rec in frame.to_dict("records"):
            code = public_ticker(rec.get("ticker"))
            if code and code != "000000":
                profiles[code] = clean(rec)
        return profiles
    return {}


def build_public_stock_detail(
    row: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    tian: dict[str, Any] | None = None,
    sector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build rich read-only detail using only precomputed local data."""
    from kr_quant.context.explain import clean_reason_list
    from kr_quant.factors.scorecard import build_factor_scorecard
    from kr_quant.layers.context import explain_stock
    from kr_quant.sunzi.fa import fa_gate
    from kr_quant.sunzi.five import five_aspects
    from kr_quant.web.comments import quant_comment
    from kr_quant.web.guide import (
        DATA_FLAG_KO,
        EXCLUSION_KO,
        RISK_FLAG_KO,
        external_links,
        flag_notes,
        stock_brief,
    )

    stock = clean(dict(row or {}))
    code = public_ticker(stock.get("ticker"))
    stock["ticker"] = code
    prof = clean(dict(profile or {}))
    reasons = clean_reason_list(stock.get("exclusion_reasons"))
    five = five_aspects(stock, tian=tian, sector=sector, filings=[])
    fa = fa_gate(stock)
    return clean({
        "row": stock,
        "as_of": stock.get("as_of_date"),
        "profile": prof,
        "brief": stock_brief(stock, prof),
        "scorecard": build_factor_scorecard(stock),
        "dart": {},
        "location": {},
        "toss": {"configured": False, "error": None},
        "yahoo": {"configured": False, "used_in_quant": False, "error": None},
        "ta": {"ok": False, "used_in_quant": False, "labels": []},
        "timing": {"ok": False, "used_in_quant": False},
        "fa": fa,
        "dao": five["parts"]["dao"],
        "jiang": five["parts"]["jiang"],
        "tian": five["parts"]["tian"],
        "di": five["parts"]["di"],
        "sunzi": five,
        "events": {"used_in_quant": False, "rows": [], "n": 0},
        "flow90": {"used_in_quant": False, "rows": [], "chart": [], "n": 0},
        "naver": {"configured": False, "news": [], "web": [], "encyc": [], "error": None},
        "explain": explain_stock(stock),
        "comment": quant_comment(stock),
        "links": external_links(code, stock.get("company")),
        "risk_notes": flag_notes(stock.get("risk_flags"), RISK_FLAG_KO),
        "data_notes": flag_notes(stock.get("data_flags"), DATA_FLAG_KO),
        "gates": {
            "universe_eligible": bool(stock.get("universe_eligible")),
            "top100_eligible": bool(stock.get("top100_eligible")),
            "top20_eligible": bool(stock.get("top20_eligible")),
            "coverage": stock.get("weighted_metric_coverage"),
            "data_confidence": stock.get("data_confidence"),
            "exclusion_reasons": [
                {"code": item, "label": EXCLUSION_KO.get(item, item)}
                for item in reasons
                if item and item not in {"[]", "None"}
            ],
        },
        "public_snapshot": True,
    })


def export_stock_details(
    client: TestClient,
    out_dir: Path,
    *,
    tian: dict[str, Any] | None,
    sectors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write one lazy-loaded detail JSON file per scored stock."""
    full = get_json(client, "/api/results/all?limit=5000&eligible_only=false")
    rows = list(full.get("rows") or [])
    profiles = _profile_map()
    sector_map = {
        str(item.get("name") or ""): item
        for item in sectors
        if isinstance(item, dict) and item.get("name")
    }
    detail_dir = out_dir / "stocks"
    detail_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in rows:
        code = public_ticker(row.get("ticker"))
        if not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        industry = str(row.get("industry") or row.get("sector") or "")
        payload = build_public_stock_detail(
            row,
            profile=profiles.get(code),
            tian=tian,
            sector=sector_map.get(industry),
        )
        (detail_dir / f"{code}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
    return {"base": "stocks", "count": written}


def export_research_details(
    client: TestClient,
    out_dir: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Export saved read-only AI/validation records, never create new ones."""
    result: dict[str, Any] = {
        "analysis": {},
        "analysis_latest": {},
        "reports": {},
        "reports_latest": {},
    }
    for item in rows:
        code = str(item.get("ticker") or "").zfill(6)
        as_of = str(item.get("as_of_date") or "").strip()
        if not re.fullmatch(r"\d{6}", code) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
            continue
        is_analysis = str(item.get("kind") or "") == "간단 검증"
        bucket = "analysis" if is_analysis else "reports"
        endpoint = f"/api/research/{code}?as_of={as_of}" if is_analysis else f"/api/research/{code}/report?as_of={as_of}"
        payload = get_json(client, endpoint)
        if not payload.get("exists"):
            continue
        rel = f"research/{bucket}/{code}--{as_of}.json"
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        result[bucket][f"{code}|{as_of}"] = rel
        result[f"{bucket}_latest"].setdefault(code, rel)
    result["count"] = len(result["analysis"]) + len(result["reports"])
    return result


def export(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "full-ui-readonly-snapshot",
        "schema_version": "1.1.0",
        "routes": {},
        "screens": {},
    }

    route_data: dict[str, dict[str, Any]] = {}
    with TestClient(app) as client:
        for route, request_path in ROUTES.items():
            data = get_json(client, request_path)
            if route == "/api/status":
                data["public_mode"] = True
                data["keys"] = {}
                data.pop("project_root", None)
                ((data.get("evidence_registry") or {}).get("menus") or {}).pop("settings", None)
            filename = f"{slug(route)}.json"
            (out_dir / filename).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            manifest["routes"][route] = filename
            route_data[route] = data

        screen_default = get_json(client, "/api/screens")
        for item in screen_default.get("catalog") or []:
            screen_id = str(item.get("id") or "").strip()
            if not screen_id:
                continue
            data = get_json(client, f"/api/screens?id={screen_id}&include_quant=true")
            filename = f"screen-{re.sub(r'[^a-zA-Z0-9_-]+', '-', screen_id)}.json"
            (out_dir / filename).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            manifest["screens"][screen_id] = filename

        manifest["stock_details"] = export_stock_details(
            client,
            out_dir,
            tian=(route_data.get("/api/sunzi") or {}).get("tian"),
            sectors=list((route_data.get("/api/sectors") or {}).get("rows") or []),
        )
        manifest["research_details"] = export_research_details(
            client,
            out_dir,
            list((route_data.get("/api/research/reports") or {}).get("rows") or []),
        )

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return {
        "routes": len(manifest["routes"]),
        "screens": len(manifest["screens"]),
        "stock_details": manifest["stock_details"]["count"],
        "research_details": manifest["research_details"]["count"],
        "generated_at": manifest["generated_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist-public/data/api")
    args = parser.parse_args()
    print(json.dumps(export(Path(args.out)), ensure_ascii=False))


if __name__ == "__main__":
    main()
