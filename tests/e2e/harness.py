# -*- coding: utf-8 -*-
"""Local fixture app for browser E2E. No live market HTTP."""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parents[2] / "src" / "kr_quant" / "web" / "static"

HYUNDAI = {
    "ticker": "005380",
    "company": "현대차",
    "market": "KOSPI",
    "quant_rank": 1,
    "quant_score": 82.4,
    "last_close": 241000,
    "value_score": 24,
    "quality_score": 20,
    "growth_score": 18,
    "momentum_score": 8,
    "financial_score": 8,
    "risk_penalty": 2,
    "data_confidence": 88,
}
SAMSUNG = {**HYUNDAI, "ticker": "005930", "company": "삼성전자", "quant_rank": 2, "quant_score": 80.1, "last_close": 72000}
HYNIX = {**HYUNDAI, "ticker": "000660", "company": "SK하이닉스", "quant_rank": 3, "quant_score": 78.2, "last_close": 198000}
HEATER = {**HYUNDAI, "ticker": "009450", "company": "경동나비엔", "quant_rank": 11, "quant_score": 71.0, "last_close": 82000}

TOP_ROWS = [HYUNDAI, SAMSUNG, HYNIX] + [
    {
        **HYUNDAI,
        "ticker": f"{4000 + i:06d}",
        "company": f"픽스처종목{i:02d}",
        "quant_rank": i,
        "quant_score": 70 - i * 0.3,
        "last_close": 10000 + i,
    }
    for i in range(4, 31)
]
UNIVERSE = [HYUNDAI, SAMSUNG, HYNIX, HEATER]


def _season_row(stock: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "ticker": stock["ticker"],
        "company": stock["company"],
        "market": "KOSPI",
        "rank": rank,
        "pre_entry_rank": rank,
        "pattern_id": f"{stock['ticker']}-08",
        "window_name": "8월",
        "win_rate": 0.8,
        "sample_count": 5,
        "entry_stage": "PRE_ENTRY_15",
        "entry_stage_label": "D-15 사전진입",
        "price_as_of": "2026-08-28",
        "last_close": stock["last_close"],
        "chg_pct": 0.01,
        "common_event_cluster": "여름 실적·계절 관찰",
        "remaining_peak": {"available": True, "remaining_p50": 0.12, "positive_peak_rate": 0.8, "downside_before_peak_p50": 0.04},
    }


GLANCE = [_season_row(HYUNDAI, 1), _season_row(SAMSUNG, 2), _season_row(HYNIX, 3)]
WINTER_PRESET = {
    "label": "겨울 난방/보일러",
    "title": "겨울 난방",
    "analysis_month": 8,
    "tickers": ["009450"],
}

FLOW_ROW = {
    "ticker": "005380",
    "company": "현대차",
    "dual": True,
    "empty": True,
    "comeback": False,
    "in_quant": True,
    "last": 241000,
    "last_close": 241000,
    "change_rate": 0.01,
    "foreign_net": 120000,
    "institution_net": 80000,
    "individual_net": -200000,
    "pe_net": 10000,
    "dual_krw": 5_000_000_000,
    "empty_krw": 2_000_000_000,
    "days": 5,
    "ta": {
        "stoch_over_sold": True,
        "stoch_k": 18.2,
        "stoch_d": 22.0,
        "ichi_cloud": "above",
        "stoch_golden": False,
        "labels": ["과매도"],
    },
    "daily": [
        {"date": "2026-08-28", "close": 241000, "price_change_rate": 0.01, "foreign": 20000, "institution": 10000, "individual": -30000, "pe": 2000},
        {"date": "2026-08-27", "close": 238500, "price_change_rate": -0.005, "foreign": 15000, "institution": 8000, "individual": -22000, "pe": 1000},
        {"date": "2026-08-26", "close": 239700, "price_change_rate": 0.002, "foreign": 25000, "institution": 12000, "individual": -40000, "pe": 1500},
        {"date": "2026-08-25", "close": 239200, "price_change_rate": 0.0, "foreign": 30000, "institution": 20000, "individual": -50000, "pe": 2500},
        {"date": "2026-08-22", "close": 239200, "price_change_rate": 0.004, "foreign": 30000, "institution": 30000, "individual": -58000, "pe": 3000},
    ],
}

LONG_STRATEGY_NAME = "이동평균 교차 초장문전략이름검증용문구가잘리지않는지확인"
LONG_WARNING = "이 경고문은 아주 길어서도 표 셀에서 잘리면 안 되는 회귀 문구입니다. " * 3


def _status(*, public_mode: bool = False) -> dict[str, Any]:
    return {
        "public_mode": public_mode,
        "llm_label": "fixture",
        "llm_provider": "fixture",
        "llm_model": "fixture-model",
        "quality": {"as_of_date": "2026-08-28", "status": "success", "warnings": [], "run_id": "fixture-run"},
        "freshness": {"price_max_date": "2026-08-28", "contract_status": "ready"},
        "scheduler": {"enabled": False},
        "job": {"status": "idle", "logs": [], "history": {}},
        "keys": {"opendart": {"masked": "****", "configured": True}},
        "status_explain": {"status": "success", "label": "성공", "why": [], "improve": []},
    }


def _top(n: int = 30) -> dict[str, Any]:
    return {"rows": TOP_ROWS[: max(1, min(n, 100))], "source_as_of": "2026-08-28"}


def _all(limit: int = 300) -> dict[str, Any]:
    return {"rows": TOP_ROWS[:limit], "total": len(TOP_ROWS), "source_as_of": "2026-08-28"}


def _highlights() -> dict[str, Any]:
    return {
        "data": {
            "glance_top3": GLANCE,
            "universe_scanned": 2500,
            "universe_listed": 2500,
            "markets": {"KOSPI": 2, "KOSDAQ": 1},
        }
    }


def _discovery() -> dict[str, Any]:
    return {"rows": GLANCE, "source_as_of": "2026-08-28"}


def _scan(preset: str | None = None, month: int | None = None) -> dict[str, Any]:
    presets = {"winter_heater": WINTER_PRESET}
    if preset == "winter_heater":
        return {
            "ok": True,
            "filter_mode": "event",
            "generic_thresholds_applied": False,
            "event_mapped_count": 1,
            "active_preset": WINTER_PRESET,
            "presets": presets,
            "rows": [{"ticker": "009450", "company": "경동나비엔", "window_name": "8월", "win_rate": 0.8, "event_mode": True, "event_title": "겨울 난방"}],
        }
    return {
        "ok": True,
        "filter_mode": "month",
        "generic_thresholds_applied": True,
        "presets": presets,
        "rows": [{"ticker": "005930", "company": "삼성전자", "window_name": f"{month or 1}월", "win_rate": 0.7}],
    }


def _flow(days: int = 5) -> dict[str, Any]:
    row = {**FLOW_ROW, "days": days}
    return {
        "configured": True,
        "need_scan": False,
        "days": days,
        "fetched_at": "2026-08-28T15:30:00",
        "scanned": 1,
        "rows": [row],
        "trading": [row],
        "empty": [row],
        "dual": [row],
        "private_equity": [],
        "dual_pe": [],
        "dual_pe_retail": [],
        "other_corp": [],
        "pension": [],
    }


def _strategy() -> dict[str, Any]:
    return {
        "need_run": False,
        "rows": [
            {
                "ticker": "005380",
                "company": "현대자동차주식회사매우긴정식상호표시검증",
                "best_name": LONG_STRATEGY_NAME,
                "best_family": "ma_cross",
                "best_params_ko": f"단기 10일 · 장기 40일 · {LONG_WARNING.strip()}",
                "stability_label": "HIGH",
                "strategies": [
                    {
                        "strategy_id": "ma_cross",
                        "name": LONG_STRATEGY_NAME,
                        "sharpe": 1.2,
                        "sample": {"representative_sharpe": True},
                    }
                ],
                "warning": LONG_WARNING,
            }
        ],
    }


def _stock(ticker: str) -> dict[str, Any]:
    code = str(ticker).zfill(6)
    row = next((item for item in UNIVERSE if item["ticker"] == code), {**HYUNDAI, "ticker": code, "company": code})
    return {
        "row": row,
        "links": [
            {"label": "네이버", "url": f"https://finance.naver.com/item/main.naver?code={code}"},
            {"label": "토스", "url": f"https://tossinvest.com/stocks/{code}"},
        ],
        "gates": {},
        "naver": {},
    }


def _search(q: str = "", limit: int = 12) -> dict[str, Any]:
    needle = q.strip().lower()
    items = [row for row in UNIVERSE if needle in row["company"].lower() or needle in row["ticker"]]
    return {"items": items[:limit]}


def _slug(route: str) -> str:
    return route.strip("/").replace("/", "-").replace("_", "-") or "root"


def public_snapshot_files() -> dict[str, dict[str, Any]]:
    """Static JSON the public-preview client reads from /data/api/."""
    routes = {
        "/api/status": _status(public_mode=True),
        "/api/guide": {"ok": True},
        "/api/results/top": _top(100),
        "/api/results/all": _all(300),
        "/api/research/reports": {"rows": []},
        "/api/seasonality/highlights": _highlights(),
        "/api/seasonality/discovery": _discovery(),
        "/api/seasonality/themes": {"rows": [], "themes": []},
        "/api/seasonality/scan": _scan(),
        "/api/flow": _flow(),
        "/api/strategy": _strategy(),
        "/api/stocks/all": {"items": UNIVERSE},
        "/api/watchlist": {"rows": []},
        "/api/portfolio": {"rows": []},
        "/api/jobs": {"status": "idle", "logs": [], "history": {}},
    }
    files = {_slug(route) + ".json": payload for route, payload in routes.items()}
    files["manifest.json"] = {
        "generated_at": "2026-08-28T00:00:00+00:00",
        "mode": "e2e-fixture-readonly-snapshot",
        "routes": {route: _slug(route) + ".json" for route in routes},
        "screens": {},
        "stock_details": {"base": "stocks", "count": len(UNIVERSE)},
    }
    for row in UNIVERSE:
        files[f"stocks/{row['ticker']}.json"] = _stock(row["ticker"])
    return files


def create_app() -> FastAPI:
    app = FastAPI()
    snapshot = public_snapshot_files()

    @app.middleware("http")
    async def no_public_guard(request: Request, call_next):
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/data/api/{path:path}")
    def public_api_file(path: str):
        payload = snapshot.get(path)
        if payload is None:
            return JSONResponse({"ok": False, "error": path}, status_code=404)
        return payload

    @app.get("/api/status")
    def status():
        return _status()

    @app.get("/api/guide")
    def guide():
        return {"ok": True}

    @app.get("/api/results/top")
    def top(n: int = 30):
        return _top(n)

    @app.get("/api/results/all")
    def all_rows(limit: int = 300):
        return _all(limit)

    @app.get("/api/research/reports")
    def reports():
        return {"rows": []}

    @app.get("/api/seasonality/highlights")
    def highlights():
        return _highlights()

    @app.get("/api/seasonality/discovery")
    def discovery():
        return _discovery()

    @app.get("/api/seasonality/themes")
    def themes():
        return {"rows": [], "themes": []}

    @app.get("/api/seasonality/scan")
    def scan(preset: str | None = None, month: int | None = None):
        return _scan(preset, month)

    @app.get("/api/stocks/search")
    def search(q: str = "", limit: int = 12):
        return _search(q, limit)

    @app.get("/api/stocks/all")
    def stocks_all():
        return {"items": UNIVERSE}

    @app.get("/api/results/stock/{ticker}")
    def stock(ticker: str):
        return _stock(ticker)

    @app.get("/api/flow")
    def flow(days: int = 5):
        return _flow(days)

    @app.post("/api/flow")
    def flow_post():
        return _flow()

    @app.get("/api/strategy")
    def strategy():
        return _strategy()

    @app.post("/api/strategy")
    def strategy_post():
        return _strategy()

    @app.get("/api/jobs")
    def jobs():
        return {"status": "idle", "logs": [], "history": {}}

    @app.get("/api/watchlist")
    def watchlist():
        return {"rows": []}

    @app.get("/api/portfolio")
    def portfolio():
        return {"rows": []}

    @app.get("/api/settings")
    def settings():
        return {"llm_provider": "fixture", "llm_model": "fixture-model"}

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_fallback(rest: str):
        return JSONResponse({"ok": True, "rows": [], "items": []})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_server() -> tuple[str, Any]:
    import uvicorn

    port = free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 8
    while time.time() < deadline:
        if server.started:
            return f"http://127.0.0.1:{port}", server
        time.sleep(0.05)
    raise RuntimeError("fixture E2E server did not start")
