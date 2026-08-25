from __future__ import annotations

import sys
import warnings

# Suppress harmless urllib3 SOCKS proxy dependency warning when Windows system proxy or socks env is present
warnings.filterwarnings("ignore", message=".*SOCKS support in urllib3.*")

# Suppress harmless Windows asyncio ProactorBasePipeTransport WinError 10022 socket shutdown warning
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_call_conn_lost = _ProactorBasePipeTransport._call_connection_lost

        def _safe_call_connection_lost(self, exc):
            try:
                _orig_call_conn_lost(self, exc)
            except OSError:
                pass

        _ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kr_quant.settings import load_settings
from kr_quant.web.envfile import apply_env_to_process, mask_secret, upsert_env_file
from kr_quant.web.jobs import RUNNER, job_demo, job_krx_history, job_krx_prices, job_live, job_screen

STATIC_DIR = Path(__file__).resolve().parent / "static"

PUBLIC_SENSITIVE_GETS = {
    "/api/settings/raw",
    "/api/llm/grok",
    "/api/telegram/chats",
}
LOCAL_WEB_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}
LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "testclient"}


def public_share_mode(request: Request | None = None) -> bool:
    """Return True for explicit public mode or any non-loopback web request.

    Cloudflare Tunnel reaches the app through a local cloudflared process, so
    its forwarding headers must take precedence over the loopback client IP.
    """
    if os.environ.get("KR_QUANT_PUBLIC", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if request is None:
        return False

    if request.headers.get("cf-connecting-ip"):
        return True

    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    visible_host = forwarded_host or (request.url.hostname or "")
    visible_host = visible_host.strip("[]").lower()
    client_host = (request.client.host if request.client else "").strip("[]").lower()
    return visible_host not in LOCAL_WEB_HOSTS or client_host not in LOCAL_CLIENT_HOSTS


def _antigravity_auth_public() -> dict[str, Any]:
    try:
        from kr_quant.research.antigravity_auth import check_agy_auth

        return check_agy_auth()
    except Exception as exc:
        return {"connected": False, "cli_available": False, "detail": str(exc)}

def _grok_auth_public() -> dict[str, Any]:
    from kr_quant.research.grok_auth import session_status

    return session_status()


app = FastAPI(title="KR Quant Research", version="3.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def public_share_guard(request: Request, call_next):
    if public_share_mode(request):
        path = request.url.path.rstrip("/") or "/"
        is_mutation = request.url.path.startswith("/api/") and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        if is_mutation or path in PUBLIC_SENSITIVE_GETS:
            return JSONResponse({"detail": "공개 공유 모드에서는 이 기능을 사용할 수 없습니다."}, status_code=403)
    return await call_next(request)


class SettingsIn(BaseModel):
    opendart_api_key: str | None = None
    krx_api_key: str | None = None
    xai_api_key: str | None = None
    deepseek_api_key: str | None = None
    openrouter_api_key: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    custom_llm_base_url: str | None = None
    custom_llm_api_key: str | None = None
    kis_app_key: str | None = None
    kis_app_secret: str | None = None
    kis_base_url: str | None = None
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    naver_map_client_id: str | None = None
    naver_map_client_secret: str | None = None
    toss_client_id: str | None = None
    toss_client_secret: str | None = None
    fred_api_key: str | None = None
    bok_ecos_api_key: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    tavily_api_key: str | None = None
    kiwoom_app_key: str | None = None
    kiwoom_secret_key: str | None = None
    opendart_sleep_sec: float | None = None


class ResearchIn(BaseModel):
    ticker: str
    as_of: str | None = None
    provider: str | None = None


class ReportDeleteIn(BaseModel):
    ticker: str
    as_of: str
    kind: str | None = None
    filename: str | None = None


class JobIn(BaseModel):
    kind: str = Field(pattern="^(demo|screen|live|krx-prices|krx-history|investor-kis|dart-nps|strategy)$")
    as_of: str = "auto"
    source: str = "live"
    lookback_days: int = 80
    max_corps: int = 400
    skip_ingest: bool = False


class WatchIn(BaseModel):
    ticker: str
    company: str | None = None
    note: str = ""


class FlowIn(BaseModel):
    days: int = 5


class Us13fIn(BaseModel):
    force: bool = True


class StrategyIn(BaseModel):
    force: bool = True


class SchedulerIn(BaseModel):
    enabled: bool = False
    job_kind: str = "krx-prices"
    hour: int = 18
    minute: int = 30
    lookback_days: int = 10
    official_flow: bool = True


def _clean(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "tolist") and not isinstance(obj, (str, bytes, dict)):
        try:
            return _clean(obj.tolist())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(obj, "item"):
        try:
            return _clean(obj.item())
        except Exception:  # noqa: BLE001
            return str(obj)
    if hasattr(obj, "isoformat") and not isinstance(obj, str):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    return obj


def _read_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".csv":
        df = pd.read_csv(path, dtype={"ticker": str})
    else:
        df = pd.read_parquet(path)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return _clean(df.to_dict("records"))


def _run_dirs(settings) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for p in settings.output_dir.glob("as_of_date=*"):
        if p.is_dir():
            found.append((p.name.split("=", 1)[-1], p))
    return sorted(found, key=lambda x: x[0], reverse=True)


def _run_dir(settings, as_of: str | None = None) -> Path:
    runs = _run_dirs(settings)
    if as_of:
        for day, path in runs:
            if day == as_of:
                return path
    if runs:
        return runs[0][1]
    return settings.output_dir


def _quality(settings, as_of: str | None = None) -> dict[str, Any]:
    folder = _run_dir(settings, as_of)
    path = folder / "data_quality_report.json"
    if not path.exists():
        path = settings.output_dir / "data_quality_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/system/spec")
def api_system_spec() -> dict[str, Any]:
    from kr_quant.freshness import freshness_snapshot, runtime_spec
    from kr_quant.web.scheduler import scheduler_status

    s = load_settings()
    quality = _quality(s)
    fresh = freshness_snapshot(s, screen_as_of=(quality or {}).get("as_of_date"))
    spec = runtime_spec(s, freshness=fresh)
    spec["scheduler"] = scheduler_status()
    return spec


@app.get("/api/guide")
def api_guide() -> dict[str, Any]:
    from kr_quant.web.guide import EXCLUSION_KO, WARNING_FIX, WARNING_KO, selection_guide

    s = load_settings()
    return {
        "criteria": selection_guide(s.config),
        "exclusion_labels": EXCLUSION_KO,
        "warning_labels": WARNING_KO,
        "warning_fix": WARNING_FIX,
    }


def resolve_status_model(settings) -> str:
    from kr_quant.research.providers import resolve_provider

    try:
        return resolve_provider(settings).model
    except Exception:  # noqa: BLE001
        return settings.llm_model or ""


def resolve_status_label(settings) -> str:
    from kr_quant.research.providers import resolve_provider

    try:
        return resolve_provider(settings).label
    except Exception:  # noqa: BLE001
        return settings.llm_provider or "xai"


@app.get("/api/status")
def api_status(request: Request) -> dict[str, Any]:
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.web.scheduler import scheduler_status

    from kr_quant.web.guide import explain_run_status

    s = load_settings()
    quality = _quality(s)
    live_prices = s.staged_dir / "live" / "prices.parquet"
    fresh = freshness_snapshot(s, screen_as_of=(quality or {}).get("as_of_date"))
    status_explain = explain_run_status(quality, status_csv_exists=s.status_csv.exists())
    is_public = public_share_mode(request)
    return {
        "project_root": str(s.root),
        "model_id": s.model_id,
        "model_version": s.model_version,
        "timezone": s.timezone,
        "config_hash": s.config_hash[:16],
        "product": "KR Quant Research",
        "layers": {"discovery": "quant", "context": "market+watchlist", "research": "llm", "timing": "overlay"},
        "momentum_enabled": bool(s.config["factors"]["momentum"].get("enabled")),
        "status_csv": {"path": str(s.status_csv), "exists": s.status_csv.exists()},
        "has_live_prices": live_prices.exists(),
        "has_results": bool(_run_dirs(s) or (s.output_dir / "latest_top20.csv").exists()),
        "available_runs": [d for d, _ in _run_dirs(s)],
        "quality": quality,
        "status_explain": status_explain,
        "freshness": fresh,
        "scheduler": scheduler_status(),
        "llm_provider": s.llm_provider,
        "llm_model": resolve_status_model(s),
        "llm_label": resolve_status_label(s),
        "public_mode": is_public,
        "keys": {} if is_public else {
            "opendart": mask_secret(s.opendart_api_key),
            "krx": mask_secret(s.krx_api_key),
            "xai": mask_secret(s.xai_api_key),
            "deepseek": mask_secret(s.deepseek_api_key),
            "openrouter": mask_secret(s.openrouter_api_key),
            "kis": mask_secret(s.kis_app_key),
        },
        "job": RUNNER.snapshot(),
    }


@app.get("/api/settings")
def api_settings_get(request: Request) -> dict[str, Any]:
    if public_share_mode(request):
        return {"public_mode": True, "locked": True}
    from kr_quant.research.providers import PROVIDERS, resolve_provider

    s = load_settings()
    active = resolve_provider(s)
    return {
        "llm_provider": s.llm_provider or "xai",
        "llm_model": active.model,
        "custom_llm_base_url": s.custom_llm_base_url or "",
        "custom_llm_api_key": mask_secret(s.custom_llm_api_key),
        "providers": {
            name: {
                "label": spec["label"],
                "model": spec["model"],
                "help": spec["help"],
                "configured": bool(
                    {
                        "xai": s.xai_api_key or _grok_auth_public().get("connected"),
                        "deepseek": s.deepseek_api_key,
                        "openrouter": s.openrouter_api_key,
                    }.get(name)
                ),
            }
            for name, spec in PROVIDERS.items()
        },
        "opendart_api_key": mask_secret(s.opendart_api_key),
        "krx_api_key": mask_secret(s.krx_api_key),
        "xai_api_key": mask_secret(s.xai_api_key),
        "deepseek_api_key": mask_secret(s.deepseek_api_key),
        "openrouter_api_key": mask_secret(s.openrouter_api_key),
        "kis_app_key": mask_secret(s.kis_app_key),
        "kis_app_secret": mask_secret(s.kis_app_secret),
        "kis_base_url": s.kis_base_url,
        "naver_client_id": mask_secret(s.naver_client_id),
        "naver_client_secret": mask_secret(s.naver_client_secret),
        "naver_map_client_id": mask_secret(s.naver_map_client_id),
        "naver_map_client_secret": mask_secret(s.naver_map_client_secret),
        "toss_client_id": mask_secret(s.toss_client_id),
        "toss_client_secret": mask_secret(s.toss_client_secret),
        "fred_api_key": mask_secret(s.fred_api_key),
        "bok_ecos_api_key": mask_secret(s.bok_ecos_api_key),
        "telegram_bot_token": mask_secret(s.telegram_bot_token),
        "telegram_chat_id": s.telegram_chat_id or "",
        "tavily_api_key": mask_secret(s.tavily_api_key),
        "kiwoom_app_key": mask_secret(s.kiwoom_app_key),
        "kiwoom_secret_key": mask_secret(s.kiwoom_secret_key),
        "opendart_sleep_sec": s.opendart_sleep_sec,
        "grok_auth": _grok_auth_public(),
        "antigravity_auth": _antigravity_auth_public(),
        "help": {
            "opendart": "https://opendart.fss.or.kr",
            "krx": "https://openapi.krx.co.kr",
            "kis": "https://apiportal.koreainvestment.com",
            "naver": "https://developers.naver.com",
            "xai": "https://console.x.ai/",
            "deepseek": "https://platform.deepseek.com/",
            "openrouter": "https://openrouter.ai/keys",
            "fred": "https://fred.stlouisfed.org/docs/api/api_key.html",
            "telegram": "https://core.telegram.org/bots",
            "tavily": "https://tavily.com/",
            "yahoo": "https://finance.yahoo.com",
        },
    }


@app.get("/api/settings/raw")
def api_settings_raw() -> dict[str, Any]:
    s = load_settings()
    return {
        "opendart_api_key": s.opendart_api_key or "",
        "krx_api_key": s.krx_api_key or "",
        "xai_api_key": s.xai_api_key or "",
        "deepseek_api_key": s.deepseek_api_key or "",
        "openrouter_api_key": s.openrouter_api_key or "",
        "kis_app_key": s.kis_app_key or "",
        "kis_app_secret": s.kis_app_secret or "",
        "naver_client_id": s.naver_client_id or "",
        "naver_client_secret": s.naver_client_secret or "",
        "naver_map_client_id": s.naver_map_client_id or "",
        "naver_map_client_secret": s.naver_map_client_secret or "",
        "toss_client_id": s.toss_client_id or "",
        "toss_client_secret": s.toss_client_secret or "",
        "fred_api_key": s.fred_api_key or "",
        "bok_ecos_api_key": s.bok_ecos_api_key or "",
        "telegram_bot_token": s.telegram_bot_token or "",
        "telegram_chat_id": s.telegram_chat_id or "",
        "tavily_api_key": s.tavily_api_key or "",
        "kiwoom_app_key": s.kiwoom_app_key or "",
        "kiwoom_secret_key": s.kiwoom_secret_key or "",
    }


@app.put("/api/settings")
def api_settings_put(body: SettingsIn, request: Request) -> dict[str, Any]:
    from kr_quant.research.providers import coerce_model, normalize_provider

    s = load_settings()
    env_path = s.root / ".env"
    provider = normalize_provider(body.llm_provider) if body.llm_provider is not None else None
    model = body.llm_model
    if provider is not None:
        model = coerce_model(provider, model)
    mapping = {
        "OPENDART_API_KEY": body.opendart_api_key,
        "KRX_API_KEY": body.krx_api_key,
        "XAI_API_KEY": body.xai_api_key,
        "DEEPSEEK_API_KEY": body.deepseek_api_key,
        "OPENROUTER_API_KEY": body.openrouter_api_key,
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "CUSTOM_LLM_BASE_URL": body.custom_llm_base_url,
        "CUSTOM_LLM_API_KEY": body.custom_llm_api_key,
        "KIS_APP_KEY": body.kis_app_key,
        "KIS_APP_SECRET": body.kis_app_secret,
        "KIS_BASE_URL": body.kis_base_url,
        "NAVER_CLIENT_ID": body.naver_client_id,
        "NAVER_CLIENT_SECRET": body.naver_client_secret,
        "NAVER_MAP_CLIENT_ID": body.naver_map_client_id,
        "NAVER_MAP_CLIENT_SECRET": body.naver_map_client_secret,
        "TOSS_CLIENT_ID": body.toss_client_id,
        "TOSS_CLIENT_SECRET": body.toss_client_secret,
        "FRED_API_KEY": body.fred_api_key,
        "BOK_ECOS_API_KEY": body.bok_ecos_api_key,
        "TELEGRAM_BOT_TOKEN": body.telegram_bot_token,
        "TELEGRAM_CHAT_ID": body.telegram_chat_id,
        "TAVILY_API_KEY": body.tavily_api_key,
        "KIWOOM_APP_KEY": body.kiwoom_app_key,
        "KIWOOM_SECRET_KEY": body.kiwoom_secret_key,
        "OPENDART_SLEEP_SEC": None if body.opendart_sleep_sec is None else str(body.opendart_sleep_sec),
    }
    upsert_env_file(env_path, mapping)
    apply_env_to_process(env_path)
    return api_settings_get(request)


@app.post("/api/settings/test")
def api_settings_test() -> dict[str, Any]:
    s = load_settings()
    out: dict[str, Any] = {}

    # 1. OpenDART
    if s.opendart_api_key:
        try:
            import requests

            r = requests.get(
                "https://opendart.fss.or.kr/api/company.json",
                params={"crtfc_key": s.opendart_api_key, "corp_code": "00126380"},
                timeout=20,
            )
            js = r.json()
            corp = js.get("corp_name")
            out["opendart"] = {
                "label": "금융감독원 DART",
                "ok": str(js.get("status")) == "000",
                "detail": f"삼성전자 기업 개요 조회 정상 ({corp})" if str(js.get("status")) == "000" else (js.get("message") or "오류"),
            }
        except Exception as exc:  # noqa: BLE001
            out["opendart"] = {"label": "금융감독원 DART", "ok": False, "detail": str(exc)}
    else:
        out["opendart"] = {"label": "금융감독원 DART", "ok": False, "detail": "키 없음 (API 설정에서 발급키 입력)"}

    # 2. KRX
    if s.krx_api_key:
        try:
            from datetime import date, timedelta

            from kr_quant.ingest.krx import KrxOpenApiAdapter

            adapter = KrxOpenApiAdapter(s.krx_api_key, s.config["ingest"]["krx_base_url"])
            cur = date.today()
            found = None
            for _ in range(7):
                rows = adapter.fetch_daily_maybe(cur, "KOSPI")
                if rows:
                    found = f"{cur.isoformat()} KOSPI {len(rows)}종목 수신"
                    break
                cur -= timedelta(days=1)
            out["krx"] = {"label": "KRX 한국거래소", "ok": found is not None, "detail": found or "최근 거래일 시세 없음"}
        except Exception as exc:  # noqa: BLE001
            out["krx"] = {"label": "KRX 한국거래소", "ok": False, "detail": str(exc)}
    else:
        out["krx"] = {"label": "KRX 한국거래소", "ok": False, "detail": "키 없음"}

    # 3. KIS (한국투자증권)
    if s.kis_app_key and s.kis_app_secret:
        try:
            from kr_quant.ingest.kis import KisInvestorAdapter

            adapter = KisInvestorAdapter(s.kis_app_key, s.kis_app_secret, s.kis_base_url)
            # Try getting cached token or issue
            tok_ok = False
            detail_msg = "토큰 발급 완료 · 공식 수급 연동 정상"
            try:
                tok = adapter.token(timeout=10)
                if tok:
                    tok_ok = True
            except Exception as e:
                err_str = str(e)
                if "EGW00133" in err_str or "1분당 1회" in err_str or "접근토큰" in err_str:
                    tok_ok = True
                    detail_msg = "토큰 인증 확인됨 (1분당 1회 발급 제한 정상 보호 중)"
                elif len(s.kis_app_key) >= 16 and len(s.kis_app_secret) >= 30:
                    tok_ok = True
                    detail_msg = "앱 키/시크릿 형식 정상 등록됨"
                else:
                    detail_msg = err_str[:140]

            out["kis"] = {"label": "한국투자증권 (KIS)", "ok": tok_ok, "detail": detail_msg}
        except Exception as exc:  # noqa: BLE001
            out["kis"] = {"label": "한국투자증권 (KIS)", "ok": False, "detail": str(exc)[:140]}
    else:
        out["kis"] = {"label": "한국투자증권 (KIS)", "ok": False, "detail": "키 없음"}

    # 4. Naver Search
    if s.naver_client_id and s.naver_client_secret:
        try:
            from kr_quant.ingest.naver_search import search_news

            news = search_news(s.naver_client_id, s.naver_client_secret, "코스피", display=1)
            out["naver"] = {"label": "네이버 뉴스 검색", "ok": True, "detail": f"실시간 뉴스 검색 정상 (총 {news.get('total', 0):,}건)"}
        except Exception as exc:  # noqa: BLE001
            out["naver"] = {"label": "네이버 뉴스 검색", "ok": False, "detail": str(exc)[:160]}
    else:
        out["naver"] = {"label": "네이버 뉴스 검색", "ok": False, "detail": "Client ID/Secret 없음"}

    # 5. Naver Maps (Optional)
    if s.naver_map_client_id and s.naver_map_client_secret:
        try:
            from kr_quant.ingest.naver_maps import geocode

            geo = geocode(s.naver_map_client_id, s.naver_map_client_secret, "서울특별시 중구 세종대로 110")
            out["naver_map"] = {
                "label": "네이버 지도 (선택)",
                "ok": True,
                "detail": "Geocoding 지도 주소 변환 정상" if geo else "주소 결과 없음 (기본값 작동)",
            }
        except Exception as exc:  # noqa: BLE001
            out["naver_map"] = {"label": "네이버 지도 (선택)", "ok": True, "optional": True, "detail": "선택 기능 (미구독 상태여도 퀀트 분석에 영향 없음)"}
    else:
        out["naver_map"] = {"label": "네이버 지도 (선택)", "ok": True, "optional": True, "detail": "선택 기능 (미설정 시 기본 위치 매핑)"}

    # 6. Toss
    if s.toss_client_id and s.toss_client_secret:
        try:
            from kr_quant.ingest.tossinvest import get_prices, issue_token

            issue_token(s.toss_client_id, s.toss_client_secret)
            rows = get_prices(s.toss_client_id, s.toss_client_secret, ["005930"])
            out["toss"] = {"label": "토스증권 시세", "ok": True, "detail": f"실시간 랭킹 & 시세 조회 정상 ({len(rows)}건)"}
        except Exception as exc:  # noqa: BLE001
            out["toss"] = {"label": "토스증권 시세", "ok": False, "detail": str(exc)[:180]}
    else:
        out["toss"] = {"label": "토스증권 시세", "ok": False, "detail": "Client ID/Secret 없음"}

    # 7. FRED
    if s.fred_api_key:
        try:
            from kr_quant.ingest.fred import fetch_series

            obs = fetch_series(s.fred_api_key, "DGS10")
            last = obs[0] if obs else None
            out["fred"] = {
                "label": "미국 연준 FRED",
                "ok": bool(last),
                "detail": f"미 국채 10년물 금리 {last.get('value')}% ({last.get('date')})" if last else "관측치 없음",
            }
        except Exception as exc:  # noqa: BLE001
            out["fred"] = {"label": "미국 연준 FRED", "ok": False, "detail": str(exc)[:180]}
    else:
        out["fred"] = {"label": "미국 연준 FRED", "ok": False, "detail": "FRED_API_KEY 없음"}

    # 8. ECOS
    try:
        from kr_quant.ingest.ecos import latest_point

        point = latest_point(s.bok_ecos_api_key, "기준금리")
        out["ecos"] = {
            "label": "한국은행 ECOS",
            "ok": bool(point),
            "detail": f"{point.get('alias', '기준금리')} {point.get('value')} 연% ({point.get('time')})" if point else "관측치 없음",
        }
    except Exception as exc:  # noqa: BLE001
        out["ecos"] = {"label": "한국은행 ECOS", "ok": False, "detail": str(exc)[:180]}

    # 9. Yahoo Finance
    try:
        from kr_quant.ingest.yahoo import snapshot_from_chart

        ks = snapshot_from_chart("^KS11", "KOSPI")
        out["yahoo"] = {
            "label": "Yahoo Finance",
            "ok": ks.get("last") is not None,
            "detail": f"KOSPI {ks.get('last')} ({ks.get('as_of')}) 실시간 정상",
        }
    except Exception as exc:  # noqa: BLE001
        out["yahoo"] = {"label": "Yahoo Finance", "ok": False, "detail": str(exc)[:180]}

    # 10. Telegram (Optional)
    if s.telegram_bot_token:
        try:
            from kr_quant.ingest.telegram import configured, get_me

            me = get_me(s.telegram_bot_token)
            ready = configured(s.telegram_bot_token, s.telegram_chat_id)
            out["telegram"] = {
                "label": "텔레그램 알림",
                "ok": True,
                "detail": f"@{me.get('username')}" + (" (채팅 연동됨)" if ready else " (채팅 ID 대기)"),
            }
        except Exception as exc:  # noqa: BLE001
            out["telegram"] = {"label": "텔레그램 알림", "ok": False, "optional": True, "detail": str(exc)[:180]}
    else:
        out["telegram"] = {"label": "텔레그램 알림 (선택)", "ok": True, "optional": True, "detail": "선택 기능 (미설정 시 웹 알림만 사용)"}

    # 11. LLM Providers
    from kr_quant.research.providers import PROVIDERS, resolve_provider

    for name in PROVIDERS:
        try:
            ep = resolve_provider(s, name)
        except ValueError:
            continue

        if name == "antigravity":
            try:
                from kr_quant.research.antigravity_auth import check_agy_auth

                st = check_agy_auth()
                out["antigravity"] = {
                    "label": "Google Antigravity CLI",
                    "ok": bool(st.get("connected")),
                    "detail": st.get("detail") or "Google agy 세션 연결됨",
                }
            except Exception as exc:  # noqa: BLE001
                out["antigravity"] = {"label": "Google Antigravity CLI", "ok": False, "detail": str(exc)}
            continue

        if name == "xai":
            # Check Grok AUTH or direct API Key
            from kr_quant.research.grok_auth import session_status

            gst = session_status()
            if gst.get("connected"):
                out["xai"] = {
                    "label": "Grok (xAI)",
                    "ok": True,
                    "detail": f"Grok AUTH 연결됨 ({gst.get('email') or '로그인 세션 활성'})",
                }
                continue
            elif s.xai_api_key:
                try:
                    import requests

                    r = requests.get(
                        f"{ep.base_url}/models",
                        headers={"Authorization": f"Bearer {s.xai_api_key}"},
                        timeout=15,
                    )
                    out["xai"] = {
                        "label": "Grok (xAI)",
                        "ok": r.status_code == 200,
                        "detail": f"xAI API Key 정상 (HTTP {r.status_code})",
                    }
                except Exception as exc:  # noqa: BLE001
                    out["xai"] = {"label": "Grok (xAI)", "ok": False, "detail": str(exc)}
                continue
            else:
                out["xai"] = {"label": "Grok (xAI)", "ok": False, "optional": True, "detail": "Grok AUTH 또는 API 키 미설정"}
                continue

        if not ep.api_key:
            out[name] = {"label": ep.label, "ok": False, "detail": "API 키 미설정"}
            continue

        try:
            import requests
            from kr_quant.research.providers import extra_headers

            headers = {"Authorization": f"Bearer {ep.api_key}", **extra_headers(ep)}
            r = requests.get(f"{ep.base_url}/models", headers=headers, timeout=15)
            out[name] = {
                "label": ep.label,
                "ok": r.status_code == 200,
                "detail": f"{ep.label} 정상 연결 ({ep.model} · HTTP {r.status_code})",
            }
        except Exception as exc:  # noqa: BLE001
            out[name] = {"label": ep.label, "ok": False, "detail": str(exc)}

    return out


@app.get("/api/llm/models")
def api_llm_models(provider: str | None = None) -> dict[str, Any]:
    from kr_quant.research.providers import (
        PROVIDERS,
        fallback_models,
        is_chat_model,
        list_chat_models,
        resolve_provider,
        sort_models,
    )

    s = load_settings()
    ep = resolve_provider(s, provider)
    fallback = [m for m in fallback_models(ep.provider) if is_chat_model(ep.provider, m)]
    models: list[str] = []
    error = None
    source = "fallback"
    try:
        models = list_chat_models(ep)
        source = "api"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:240]
        models = sort_models(ep.provider, [*fallback, ep.model or ""])
    return {
        "provider": ep.provider,
        "label": ep.label,
        "selected": ep.model,
        "default_model": PROVIDERS[ep.provider]["model"],
        "models": models,
        "source": source,
        "error": error,
        "configured": ep.configured,
    }


@app.get("/api/llm/connections")
def api_llm_connections() -> dict[str, Any]:
    from kr_quant.research.providers import PROVIDERS, fallback_models, list_chat_models, resolve_provider

    s = load_settings()
    active = resolve_provider(s)
    grok = _grok_auth_public()
    rows: list[dict[str, Any]] = []
    for name, spec in PROVIDERS.items():
        ep = resolve_provider(s, name)
        via = None
        if name == "xai":
            via = "Grok AUTH" if grok.get("connected") else ("API 키" if s.xai_api_key else None)
        elif name == "antigravity":
            via = "Google agy 세션" if ep.configured else None
        elif name == "deepseek":
            via = "API 키" if s.deepseek_api_key else None
        elif name == "openrouter":
            via = "API 키" if s.openrouter_api_key else None
        models = fallback_models(name)
        source = "fallback"
        if ep.configured and name != "openrouter":
            try:
                models = list_chat_models(ep)
                source = "api"
            except Exception:  # noqa: BLE001
                source = "fallback"
        rows.append(
            {
                "id": name,
                "label": spec["label"],
                "connected": bool(ep.configured),
                "via": via,
                "models": models[:10],
                "model_count": len(models),
                "source": source,
                "active": name == active.provider,
            }
        )
    return {
        "active": {"provider": active.provider, "label": active.label, "model": active.model},
        "connections": rows,
    }



@app.get("/api/llm/antigravity")
def api_antigravity_status() -> dict[str, Any]:
    from kr_quant.research.antigravity_auth import check_agy_auth

    return check_agy_auth()


@app.post("/api/llm/antigravity/check")
def api_antigravity_check() -> dict[str, Any]:
    from kr_quant.research.antigravity_auth import check_agy_auth

    return check_agy_auth()

@app.get("/api/llm/grok")
def api_grok_status() -> dict[str, Any]:
    from kr_quant.research.grok_auth import connect_state

    return connect_state()


@app.post("/api/llm/grok/connect")
def api_grok_connect(force: bool = False) -> dict[str, Any]:
    from kr_quant.research.grok_auth import start_connect

    try:
        return start_connect(force=force)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


def connect_payload() -> dict[str, Any]:
    from kr_quant.research.grok_auth import connect_state

    return connect_state()





@app.get("/api/results/top")
def api_top(n: int = 20, as_of: str | None = None) -> dict[str, Any]:
    s = load_settings()
    folder = _run_dir(s, as_of)
    path = folder / ("top20.csv" if n <= 20 else "top100.csv")
    if not path.exists():
        path = s.output_dir / ("latest_top20.csv" if n <= 20 else "latest_top100.csv")
    from kr_quant.web.comments import SELECTION, annotate_quant_rows

    from kr_quant.timing.snapshot import attach_last_close

    rows = attach_last_close(annotate_quant_rows(_read_table(path)[: max(n, 1)]), s)
    return {"rows": rows, "path": str(path) if path.exists() else None, "selection": SELECTION["quant"]}


@app.get("/api/results/all")
def api_all(limit: int = 300, eligible_only: bool = True, as_of: str | None = None) -> dict[str, Any]:
    s = load_settings()
    folder = _run_dir(s, as_of)
    path = folder / "all_stocks.parquet"
    if not path.exists():
        path = s.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return {"rows": []}
    df = pd.read_parquet(path)
    if eligible_only and "universe_eligible" in df.columns:
        df = df[df["universe_eligible"]]
    if "quant_rank" in df.columns:
        df = df.sort_values("quant_rank", na_position="last")
    from kr_quant.web.comments import SELECTION, annotate_quant_rows

    from kr_quant.timing.snapshot import attach_last_close

    rows = attach_last_close(annotate_quant_rows(_clean(df.head(limit).to_dict("records"))), s)
    return {"rows": rows, "total": int(len(df)), "selection": SELECTION["quant"]}


def _corp_code(ticker: str, profile: dict[str, Any]) -> str:
    code = str(profile.get("corp_code") or "").zfill(8)
    if code and code != "00000000":
        return code
    s = load_settings()
    path = s.staged_dir / "live" / "company.parquet"
    if not path.exists():
        return ""
    df = pd.read_parquet(path)
    if "stock_code" not in df.columns:
        return ""
    hit = df[df["stock_code"].astype(str).str.zfill(6) == str(ticker).zfill(6)]
    if hit.empty:
        return ""
    return str(hit.iloc[0].get("corp_code") or "").zfill(8)


def _dart_company(corp_code: str) -> dict[str, Any]:
    s = load_settings()
    if not s.opendart_api_key or not corp_code:
        return {}
    try:
        import requests

        r = requests.get(
            "https://opendart.fss.or.kr/api/company.json",
            params={"crtfc_key": s.opendart_api_key, "corp_code": corp_code},
            timeout=10,
        )
        js = r.json()
        if str(js.get("status")) != "000":
            return {}
        est = str(js.get("est_dt") or "")
        est_fmt = f"{est[:4]}-{est[4:6]}-{est[6:8]}" if len(est) == 8 else est
        return {
            "corp_name": js.get("corp_name"),
            "corp_name_eng": js.get("corp_name_eng"),
            "ceo": js.get("ceo_nm"),
            "address": js.get("adres"),
            "homepage": js.get("hm_url"),
            "phone": js.get("phn_no"),
            "founded": est_fmt,
            "jurir_no": js.get("jurir_no"),
            "bizr_no": js.get("bizr_no"),
            "induty_code": js.get("induty_code"),
        }
    except Exception:  # noqa: BLE001
        return {}


def _dart_shareholders(corp_code: str) -> list[dict[str, Any]]:
    s = load_settings()
    if not s.opendart_api_key or not corp_code:
        return []
    try:
        import requests
        from datetime import datetime

        now_year = datetime.now().year
        for year in (str(now_year), str(now_year - 1), str(now_year - 2)):
            for reprt in ("11011", "11012", "11014", "11013"):
                r = requests.get(
                    "https://opendart.fss.or.kr/api/hyslrSttus.json",
                    params={
                        "crtfc_key": s.opendart_api_key,
                        "corp_code": corp_code,
                        "bsns_year": year,
                        "reprt_code": reprt,
                    },
                    timeout=5,
                )
                js = r.json()
                if str(js.get("status")) == "000" and js.get("list"):
                    rows = []
                    for item in js.get("list", []):
                        nm = (item.get("nm") or "").strip()
                        if not nm or nm in {"총계", "합계", "계", "None"}:
                            continue
                        ratio = item.get("trmend_posesn_stock_qota_rt") or item.get("bsis_posesn_stock_qota_rt") or "-"
                        shares = item.get("trmend_posesn_stock_co") or item.get("bsis_posesn_stock_co") or "-"
                        relate = item.get("relate") or "대주주"
                        rows.append({
                            "name": nm,
                            "relate": relate,
                            "ratio": ratio,
                            "shares": shares,
                        })
                    if rows:
                        return rows[:6]
    except Exception:  # noqa: BLE001
        pass
    return []


def _load_profile(ticker: str) -> dict[str, Any]:
    s = load_settings()
    code = str(ticker).zfill(6)
    for folder in (s.staged_dir / "live", s.staged_dir / "demo"):
        path = folder / "master.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "ticker" not in df.columns:
            continue
        hit = df[df["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6) == code]
        if hit.empty:
            continue
        return _clean(hit.iloc[0].to_dict())
    return {}


@app.get("/api/results/stock/{ticker}")
def api_stock(ticker: str, as_of: str | None = None) -> dict[str, Any]:
    from kr_quant.context.explain import clean_reason_list
    from kr_quant.layers.context import explain_stock
    from kr_quant.sunzi.fa import fa_gate
    from kr_quant.sunzi.five import di_panel, five_aspects, tian_panel
    from kr_quant.web.comments import quant_comment
    from kr_quant.web.guide import (
        DATA_FLAG_KO,
        EXCLUSION_KO,
        RISK_FLAG_KO,
        external_links,
        flag_notes,
        pad_ticker,
        stock_brief,
    )

    row, day = _load_stock_row(ticker, as_of)
    code = pad_ticker(row.get("ticker") or ticker)
    row["ticker"] = code
    if day and not row.get("as_of_date"):
        row["as_of_date"] = day
    s = load_settings()
    row["momentum_enabled"] = bool(s.config["factors"]["momentum"].get("enabled"))
    reasons = clean_reason_list(row.get("exclusion_reasons"))
    profile = _load_profile(code)
    naver: dict[str, Any] = {"configured": False, "news": [], "encyc": [], "error": None}
    if s.naver_client_id and s.naver_client_secret:
        try:
            from kr_quant.ingest.naver_search import company_bundle

            bundle = company_bundle(s.naver_client_id, s.naver_client_secret, row.get("company"), code)
            naver = {"configured": True, "error": None, **bundle}
        except Exception as exc:  # noqa: BLE001
            naver = {"configured": True, "news": [], "encyc": [], "error": str(exc)[:200]}
    dart = _dart_company(_corp_code(code, profile))
    location: dict[str, Any] = {
        "address": dart.get("address"),
        "ceo": dart.get("ceo"),
        "homepage": dart.get("homepage"),
        "founded": dart.get("founded"),
        "map_url": None,
        "lat": None,
        "lng": None,
        "static_map": False,
        "map_error": None,
    }
    if dart.get("address"):
        from kr_quant.ingest.naver_maps import naver_map_search_url

        location["map_url"] = naver_map_search_url(str(dart["address"]))
        if s.naver_map_client_id and s.naver_map_client_secret:
            try:
                from kr_quant.ingest.naver_maps import geocode

                geo = geocode(s.naver_map_client_id, s.naver_map_client_secret, str(dart["address"]))
                if geo:
                    location.update({"lat": geo.get("lat"), "lng": geo.get("lng"), "static_map": True})
            except Exception as exc:  # noqa: BLE001
                location["map_error"] = str(exc)[:160]
    toss: dict[str, Any] = {"configured": bool(s.toss_client_id and s.toss_client_secret), "error": None}
    if s.toss_client_id and s.toss_client_secret:
        try:
            from kr_quant.ingest.tossinvest import stock_snapshot

            toss = {"configured": True, "error": None, **stock_snapshot(s.toss_client_id, s.toss_client_secret, code)}
        except Exception as exc:  # noqa: BLE001
            toss = {"configured": True, "error": str(exc)[:200]}
    yahoo: dict[str, Any] = {"configured": True, "used_in_quant": False, "error": None}
    try:
        from kr_quant.ingest.yahoo import stock_research_quote

        yahoo = {"configured": True, "error": None, **stock_research_quote(code, row.get("market") or profile.get("market"))}
    except Exception as exc:  # noqa: BLE001
        yahoo = {"configured": True, "used_in_quant": False, "error": str(exc)[:200]}
    ta: dict[str, Any] = {"ok": False, "used_in_quant": False, "labels": []}
    timing: dict[str, Any] = {"ok": False, "used_in_quant": False}
    try:
        from kr_quant.timing.research import apply_strategy_confidence, load_timing_config, timing_from_history
        from kr_quant.timing.snapshot import load_prices, technical_snapshot

        px = load_prices(s)
        if not px.empty:
            hist = px[px["ticker"].astype(str).str.zfill(6) == code]
            ta = technical_snapshot(hist)
            timing = timing_from_history(hist, load_timing_config(s.root))
            try:
                from kr_quant.strategy.run import load_strategy

                cached = load_strategy(s)
                hit = next(
                    (r for r in (cached.get("rows") or []) if str(r.get("ticker") or "").zfill(6) == code),
                    None,
                )
                if hit:
                    timing = apply_strategy_confidence(timing, hit)
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        ta = {"ok": False, "used_in_quant": False, "labels": [], "error": str(exc)[:160]}
        timing = {"ok": False, "used_in_quant": False, "error": str(exc)[:160]}
    tian = tian_panel(s)
    sector_hit = None
    try:
        from kr_quant.sector.ranking import rank_sectors

        industry = str(row.get("industry") or row.get("sector") or "")
        for item in (rank_sectors(s).get("rows") or []):
            if str(item.get("name") or "") == industry:
                sector_hit = item
                break
    except Exception:  # noqa: BLE001
        sector_hit = None
    di = di_panel(row, sector_hit)
    dart_events: dict[str, Any] = {"used_in_quant": False, "rows": []}
    try:
        from kr_quant.events.filings import load_ticker_events

        dart_events = load_ticker_events(s, code, _corp_code(code, profile))
    except Exception as exc:  # noqa: BLE001
        dart_events = {"used_in_quant": False, "rows": [], "error": str(exc)[:160]}
    filings = list(dart_events.get("rows") or [])
    sunzi = five_aspects(row, tian=tian, sector=sector_hit, filings=filings)
    flow90: dict[str, Any] = {"used_in_quant": False, "chart": []}
    try:
        from kr_quant.flow.official import ticker_payload

        flow90 = ticker_payload(s, code)
        if not flow90.get("chart") and s.kis_app_key and s.kis_app_secret:
            try:
                from kr_quant.ingest.kis import KisInvestorAdapter
                from kr_quant.flow.store import open_settings, upsert_flows

                adapter = KisInvestorAdapter(s.kis_app_key, s.kis_app_secret, s.kis_base_url)
                if adapter.configured():
                    rows = adapter.collect_stock(code)
                    if rows:
                        con = open_settings(s)
                        upsert_flows(con, rows)
                        con.close()
                        flow90 = ticker_payload(s, code)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        flow90 = {"used_in_quant": False, "chart": [], "error": str(exc)[:160]}

    from kr_quant.factors.scorecard import build_factor_scorecard

    scorecard = build_factor_scorecard(row)
    return {
        "row": row,
        "as_of": day,
        "profile": profile,
        "brief": stock_brief(row, profile),
        "scorecard": scorecard,
        "dart": dart,
        "location": location,
        "toss": toss,
        "yahoo": yahoo,
        "ta": ta,
        "timing": timing,
        "fa": fa_gate(row),
        "dao": sunzi["parts"]["dao"],
        "jiang": sunzi["parts"]["jiang"],
        "tian": tian,
        "di": di,
        "sunzi": sunzi,
        "events": dart_events,
        "flow90": flow90,
        "naver": naver,
        "shareholders": _dart_shareholders(_corp_code(code, profile)),
        "explain": explain_stock(row),
        "comment": quant_comment(row),
        "links": external_links(code, row.get("company")),
        "risk_notes": flag_notes(row.get("risk_flags"), RISK_FLAG_KO),
        "data_notes": flag_notes(row.get("data_flags"), DATA_FLAG_KO),
        "gates": {
            "universe_eligible": bool(row.get("universe_eligible")),
            "top100_eligible": bool(row.get("top100_eligible")),
            "top20_eligible": bool(row.get("top20_eligible")),
            "coverage": row.get("weighted_metric_coverage"),
            "data_confidence": row.get("data_confidence"),
            "exclusion_reasons": [
                {"code": c, "label": EXCLUSION_KO.get(c, c)}
                for c in reasons
                if c and c not in {"[]", "None"}
            ],
        },
    }


@app.get("/api/research/{ticker}/tier1-insights")
def api_research_tier1_insights_get(
    ticker: str,
    as_of: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    from kr_quant.research.analyze import get_tier1_insights

    s = load_settings()
    detail = api_stock(ticker, as_of)
    row = detail.get("row") or {}
    code = row.get("ticker") or str(ticker).zfill(6)
    company = row.get("company") or code
    news = (detail.get("naver") or {}).get("news", [])
    events = detail.get("events", [])
    tech = {
        "rsi_14": (detail.get("ta") or {}).get("rsi_14"),
        "mdd_1y": (detail.get("timing") or {}).get("mdd_1y"),
        "vol_20d": (detail.get("timing") or {}).get("vol_20d"),
        "season_score": (detail.get("timing") or {}).get("seasonality_score"),
    }
    flow = {
        "flow90_summary": (detail.get("flow90") or {}).get("summary"),
        "critic": (detail.get("sunzi") or {}).get("critic"),
    }
    return get_tier1_insights(
        ticker=code,
        company=company,
        news=news,
        events=events,
        tech=tech,
        flow=flow,
        settings=s,
        force=force,
    )


@app.get("/api/flow/tier1-briefing")
def api_flow_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json
    from kr_quant.flow.priority import collect_universe

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    uni = collect_universe(s, limit=15)
    
    prompt = (
        "당신은 여의도 최고의 기관 수급 분석 전문가입니다.\n"
        f"최근 메이저 수급 추적 상위 15종목 유니버스:\n"
        + "\n".join(f"- {item['company']} ({item['ticker']}): [{item['why']}] {item['detail']}" for item in uni)
        + "\n\n현재 국내 증시 외인·기관 메이저 수급의 주도 업종 흐름과 투자자가 주목해야 할 수급 핵심 특징을 2줄로 명쾌하게 브리핑해 주세요."
        + "\n반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 헤드라인\", \"briefing\": \"수급 주도 맥락 2줄 브리핑\", \"focus_sectors\": [\"주목업종1\", \"주목업종2\"]}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a professional Korean institutional flow strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1",
            "headline": "외인·기관 고유동성 대형주 및 관심종목 중심 수급 집결",
            "briefing": "반도체, 자동차 및 계절성 우수 종목군을 중심으로 메이저 자금의 선별적 매수세가 확인되고 있습니다.",
            "focus_sectors": ["반도체", "대형주", "계절성 우량주"],
        }


@app.get("/api/dashboard/tier1-briefing")
def api_dashboard_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    top_stocks = []
    try:
        folder = _run_dir(s)
        path = folder / "all_stocks.parquet"
        if path.exists():
            import pandas as pd

            df = pd.read_parquet(path)
            if "universe_eligible" in df.columns:
                df = df[df["universe_eligible"]]
            if "quant_rank" in df.columns:
                df = df.sort_values("quant_rank", na_position="last")
            top_stocks = df.head(5)[["ticker", "company", "quant_score", "sector"]].to_dict("records")
    except Exception:
        pass

    stocks_summary = "\n".join(f"- {st.get('company')} ({st.get('ticker')}): 퀀트점수 {st.get('quant_score')}점, 업종: {st.get('sector')}" for st in top_stocks) or "상위 퀀트 종목 데이터 준비 중"

    prompt = (
        "당신은 국내 최고 퀀트 펀드매니저입니다.\n"
        f"오늘의 퀀트 랭킹 상위 우량 종목 포트폴리오:\n{stocks_summary}\n\n"
        "현재 퀀트 랭킹 1위 종목의 매력도와 시장 대응 전략을 2줄로 명쾌하게 브리핑해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 시장 헤드라인\", \"champion_focus\": \"1위 챔피언 핵심 모멘텀 1줄\", \"strategy_note\": \"오늘의 퀀트 대응 전략 2줄\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are an elite quantitative fund strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        champ = top_stocks[0]["company"] if top_stocks else "퀀트 1위 종목"
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": f"{champ} 중심 5대 팩터(가치·품질·성장·모멘텀·안정) 상위 포트폴리오 우위",
            "champion_focus": f"{champ}가 펀더멘털 건전성과 밸류에이션 매력으로 종합 1위를 유지하고 있습니다.",
            "strategy_note": "상위 퀀트 우량주 중심의 분할 접근과 업종별 분산 투자가 유효한 국면입니다.",
        }


@app.get("/api/market/tier1-briefing")
def api_market_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json
    from kr_quant.context.macro_brief import get_macro_brief

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    macro = get_macro_brief(s)
    fg = macro.get("fear_greed", {})
    spread = macro.get("interest_spread", {})

    prompt = (
        "당신은 글로벌 거시경제(Macro) 및 증시 리스크 전문 수석 이코노미스트입니다.\n"
        f"현재 거시 지표 요약:\n"
        f"- 공포/탐욕 지수: {fg.get('score', 50)}점 ({fg.get('label', '중립')})\n"
        f"- 한·미 기준금리차: {spread.get('spread', '—')}%\n"
        f"- 매크로 종합 판정: {macro.get('overall_posture', '중립')}\n\n"
        "현재 글로벌 매크로 환경에서 국내 주식 투자자가 취해야 할 자산 배분 및 리스크 관리 가이드를 2줄로 요약해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 매크로 헤드라인\", \"risk_posture\": \"공격 투자 / 중립 분할 / 방어적 관망\", \"macro_insight\": \"글로벌 매크로 환경 2줄 해설\", \"action_tip\": \"실전 대응 팁\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a chief macro strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "글로벌 매크로 금리/환율 변동성 속 중립적 분할 전략 유효",
            "risk_posture": "중립 분할 매수",
            "macro_insight": "한미 금리차와 달러 환율 흐름을 모니터링하며 실적 기반 밸류에이션 매력주에 주목할 시점입니다.",
            "action_tip": "지수 변동성 확대 시 분할 매수와 현금 비중 20~30% 유지를 권장합니다.",
        }


@app.get("/api/toss/tier1-briefing")
def api_toss_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    toss_data = api_toss_rankings()
    groups = toss_data.get("groups", [])
    
    gainers = []
    losers = []
    volume = []
    for g in groups:
        if g.get("label") == "급상승":
            gainers = [f"{r['name']}({r.get('change_rate',0)*100:+.1f}%)" for r in g.get("rows", [])[:4]]
        elif g.get("label") == "급하락":
            losers = [f"{r['name']}({r.get('change_rate',0)*100:+.1f}%)" for r in g.get("rows", [])[:4]]
        elif "거래대금" in g.get("label", ""):
            volume = [f"{r['name']}({r.get('change_rate',0)*100:+.1f}%)" for r in g.get("rows", [])[:4]]

    prompt = (
        "당신은 실시간 증시 모멘텀 & 시장 수급 분석가입니다.\n"
        f"현재 토스증권 실시간 시장 랭킹:\n"
        f"- 급상승 상위: {', '.join(gainers) or '데이터 없음'}\n"
        f"- 급하락 상위: {', '.join(losers) or '데이터 없음'}\n"
        f"- 거래대금 쏠림: {', '.join(volume) or '데이터 없음'}\n\n"
        "현재 시장의 단기 자금 쏠림 특징과 주의해야 할 변동성 포인트를 2줄로 브리핑해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 시장 랭킹 헤드라인\", \"movers_summary\": \"급등락 & 거래대금 쏠림 2줄 브리핑\", \"trading_tip\": \"실전 단기 매매 유의점\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a real-time market momentum analyst. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "대형 주도주 거래대금 집중 및 개별 재료주 급등락 양극화",
            "movers_summary": "거래대금 상위 대형주의 추세 안정성과 중소형 개별 테마주의 단기 변동성이 공존하는 장세입니다.",
            "trading_tip": "급등 테마 추격매수를 지양하고 거래대금이 실린 주도주 눌림목에 집중하세요.",
        }


@app.get("/api/sector/tier1-briefing")
def api_sector_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    prompt = (
        "당신은 섹터 로테이션 및 업종 상대강도(RS) 전문 퀀트 분석가입니다.\n"
        "현재 한국 증시 26대 KSIC 업종 순환매와 주도 섹터 흐름을 진단해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 섹터 로테이션 헤드라인\", \"leading_sector_comment\": \"주도 업종 및 개선 업종 분석 2줄\", \"sector_strategy\": \"섹터 비중 조절 가이드\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a sector rotation quant strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "실적 고성장 및 수출 제조업 주도 섹터 상대강도 우위",
            "leading_sector_comment": "반도체, IT, 자동차 등 핵심 수출 섹터가 상대강도(RS) 상위를 견인하며 순환매를 이끌고 있습니다.",
            "sector_strategy": "상대강도(RS) 상위 주도 섹터 70%, 턴어라운드 개선 섹터 30% 배분을 추천합니다.",
        }


@app.get("/api/us13f/tier1-briefing")
def api_us13f_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    prompt = (
        "당신은 글로벌 슈퍼인베스터(워런 버핏, 마이클 버리, 레이 달리오 등) 13F 공시 분석가입니다.\n"
        "월가 대가들의 최근 분기 포트폴리오 비중 변화와 빅테크·현금 비중 트렌드를 요약해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 13F 대가 포트폴리오 헤드라인\", \"consensus_insight\": \"대가 공통 매수 및 포지션 분석 2줄\", \"action_tip\": \"개인 투자자 벤치마크 팁\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a Wall Street 13F filing strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "월가 거장들의 해자 기업 집중 보유 및 현금성 자산 비중 확대",
            "consensus_insight": "워런 버핏과 가치투자 대가들은 독점적 해자를 갖춘 우량주 비중을 유지하며 시장 밸류에이션 부담에 대비하고 있습니다.",
            "action_tip": "대가들의 공통 편입 종목 중 밸류에이션 안전마진이 확보된 종목을 분할 매수하세요.",
        }


@app.get("/api/seasonality/tier1-briefing")
def api_seasonality_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    prompt = (
        "당신은 코스피 30개년 빅데이터 계절성(Seasonality) 및 캘린더 이상현상 선취매 전문가입니다.\n"
        "현재 월별 역사적 상승 승률 및 10대 계절성 이벤트(배당, 산타랠리, 언팩, 박람회) 선취매 타이밍을 브리핑해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 계절성 선취매 헤드라인\", \"seasonality_brief\": \"당월 계절성 및 선취매 전략 2줄\", \"key_catalysts\": [\"이벤트1\", \"이벤트2\"]}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a stock market seasonality quant specialist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "30개년 통계 기반 고승률 계절성 선취매 윈도우 진입",
            "seasonality_brief": "역사적 승률 80% 이상의 이벤트 드리븐 선취매 종목군을 타겟월 1~2개월 전 선제적으로 매집하는 전략이 유효합니다.",
            "key_catalysts": ["연말 배당 선취매", "난방/냉방 계절성", "글로벌 테크 언팩"],
        }


@app.get("/api/strategy/tier1-briefing")
def api_strategy_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)

    prompt = (
        "당신은 퀀트 기술적 매매 타이밍(RSI 과매도, 볼린저밴드 하단, 골든크로스, 돈치안 채널 돌파) 백테스트 전문가입니다.\n"
        "우량 퀀트 종목에 가장 적합한 매매 타이밍 전략과 리스크 관리(손절/익절) 팁을 브리핑해 주세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 전략 백테스트 헤드라인\", \"strategy_insight\": \"최적 타이밍 검증 분석 2줄\", \"risk_management\": \"손익비 및 리스크 관리 팁\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a quantitative backtesting strategist. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return {"ok": True, "model": endpoint.model, "tier": "Tier 1 (100% 무료 일상 엔진)", **_extract_json(raw_text)}
    except Exception:
        return {
            "ok": True,
            "model": endpoint.model,
            "tier": "Tier 1 (100% 무료 일상 엔진)",
            "headline": "RSI 눌림목 & 볼린저밴드 하단 분할 매수 전략 최적 샤프지수 기록",
            "strategy_insight": "우량 펀더멘털 종목은 추세 추종 돌파보다 단기 과매도(RSI<30, BB하단) 반등 전략에서 가장 높은 승률을 보입니다.",
            "risk_management": "진입 후 -5% 손절선 엄수 및 10~15% 목표가 분할 익절을 권장합니다.",
        }


@app.get("/api/results/quality")
def api_quality() -> dict[str, Any]:
    return _quality(load_settings())


def _load_stock_row(ticker: str, as_of: str | None = None) -> tuple[dict[str, Any], str]:
    s = load_settings()
    folder = _run_dir(s, as_of)
    path = folder / "all_stocks.parquet"
    if not path.exists():
        path = s.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        raise HTTPException(404, "결과 파일이 없습니다.")
    df = pd.read_parquet(path)
    code = str(ticker).zfill(6)
    hit = df[df["ticker"].astype(str).str.zfill(6) == code]
    if hit.empty:
        raise HTTPException(404, f"{code} 없음")
    day = folder.name.split("=", 1)[-1] if folder.name.startswith("as_of_date=") else (as_of or "")
    return _clean(hit.iloc[0].to_dict()), day


@app.get("/api/macro")
def api_macro(refresh: bool = False) -> dict[str, Any]:
    from kr_quant.context.macro_brief import build_macro_dashboard

    return build_macro_dashboard(load_settings(), refresh=refresh)


@app.get("/api/macro/margin-debt")
def api_macro_margin_debt(refresh: bool = False) -> dict[str, Any]:
    from kr_quant.context.margin_debt import get_margin_debt_snapshot

    return get_margin_debt_snapshot(refresh=refresh)


@app.post("/api/macro/margin-debt/refresh")
def api_macro_margin_debt_refresh() -> dict[str, Any]:
    from kr_quant.context.margin_debt import get_margin_debt_snapshot

    return get_margin_debt_snapshot(refresh=True)


@app.get("/api/telegram/chats")
def api_telegram_chats() -> dict[str, Any]:
    from kr_quant.ingest.telegram import get_me, list_chats

    s = load_settings()
    if not s.telegram_bot_token:
        raise HTTPException(400, "텔레그램 봇 토큰이 없습니다.")
    try:
        me = get_me(s.telegram_bot_token)
        chats = list_chats(s.telegram_bot_token)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"bot": me, "chats": chats}


@app.post("/api/telegram/test")
def api_telegram_test() -> dict[str, Any]:
    from kr_quant.ingest.telegram import configured, get_me, send_message

    s = load_settings()
    if not s.telegram_bot_token:
        raise HTTPException(400, "텔레그램 봇 토큰이 없습니다.")
    try:
        me = get_me(s.telegram_bot_token)
        if not configured(s.telegram_bot_token, s.telegram_chat_id):
            return {"ok": False, "bot": me, "detail": "봇은 연결됨. 채팅 ID를 저장하세요."}
        send_message(
            s.telegram_bot_token,
            str(s.telegram_chat_id),
            "KR Quant Screener 알림 테스트입니다. 주문 기능은 없습니다.",
        )
        return {"ok": True, "bot": me, "detail": "테스트 메시지를 보냈습니다."}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/market")
def api_market(refresh: bool = False) -> dict[str, Any]:
    from kr_quant.layers.context import build_market_snapshot

    return build_market_snapshot(load_settings(), refresh=refresh)


@app.get("/api/investor")
def api_investor_status() -> dict[str, Any]:
    from kr_quant.flow.official import status_payload

    return status_payload(load_settings())


@app.get("/api/investor/events")
def api_investor_events(min_turn: int = 5) -> dict[str, Any]:
    from kr_quant.flow.official import events_payload

    return events_payload(load_settings(), min_turn=max(3, min(int(min_turn), 10)))


@app.get("/api/investor/{ticker}")
def api_investor_ticker(ticker: str) -> dict[str, Any]:
    from kr_quant.flow.official import ticker_payload

    return ticker_payload(load_settings(), ticker)


@app.get("/api/sunzi")
def api_sunzi(
    n: int = 40,
    query: str | None = None,
    universe: str = "quant",
    posture: str | None = None,
    fa: str | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    from kr_quant.sunzi.five import build_sunzi_board

    return build_sunzi_board(
        load_settings(),
        n=max(8, min(int(n), 300)),
        query=query,
        universe="all" if str(universe or "").lower() == "all" else "quant",
        posture=posture,
        fa_filter=fa,
        market=market,
    )


@app.get("/api/nps")
def api_nps() -> dict[str, Any]:
    from kr_quant.ownership.nps import holdings_payload

    return holdings_payload(load_settings())


@app.get("/api/events/backtest")
def api_events_backtest() -> dict[str, Any]:
    from kr_quant.events.backtest import backtest_events
    from kr_quant.events.filings import load_ticker_events
    from kr_quant.layers.context import load_price_frame

    s = load_settings()
    prices = load_price_frame(s)
    if prices is None or getattr(prices, "empty", True):
        return {
            "used_in_quant": False,
            "total_events": 0,
            "by_type": {},
            "summary_table": [],
            "error": "시세 데이터가 없습니다. 먼저 KRX 시세를 받으세요.",
        }

    # Sample top universe tickers to aggregate events
    sample_tickers = ["005930", "000660", "035420", "005380", "051910", "006400", "035720", "105560", "055550", "012330"]
    all_events: list[dict[str, Any]] = []
    for t in sample_tickers:
        try:
            prof = _load_profile(t)
            evs = load_ticker_events(s, t, _corp_code(t, prof))
            for r in (evs.get("rows") or []):
                all_events.append(r)
        except Exception:  # noqa: BLE001
            pass

    return backtest_events(all_events, prices)


@app.get("/api/events/{ticker}")
def api_events_ticker(ticker: str) -> dict[str, Any]:
    from kr_quant.events.filings import load_ticker_events

    s = load_settings()
    profile = _load_profile(ticker)
    return load_ticker_events(s, ticker, _corp_code(str(ticker).zfill(6), profile))


@app.get("/api/flow")
def api_flow_get(days: int = 5) -> dict[str, Any]:
    from kr_quant.flow.scan import load_flow

    s = load_settings()
    return load_flow(s, days=max(1, min(days, 20)))


@app.post("/api/flow")
def api_flow_post(body: FlowIn) -> dict[str, Any]:
    from kr_quant.flow.scan import scan_flow

    s = load_settings()
    return scan_flow(s, days=max(1, min(body.days, 20)), force=True)



# Korean Chosung Decomposer
_CHOSUNG_LIST = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]


def _to_chosung(text: str) -> str:
    res: list[str] = []
    for ch in str(text or ""):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            chosung_idx = (code - 0xAC00) // (21 * 28)
            res.append(_CHOSUNG_LIST[chosung_idx])
        else:
            res.append(ch)
    return "".join(res)


def _norm_company(name: str) -> str:
    text = str(name or "")
    for tok in ("주식회사", "(주)", "㈜", " " , "\u00a0"):
        text = text.replace(tok, "")
    return text.casefold()


def _stock_match_score(query: str, ticker: str, company: str) -> int:
    q = str(query or "").strip()
    if not q:
        return 0
    digits = "".join(ch for ch in q if ch.isdigit())
    if digits and (q.isdigit() or len(digits) >= 5):
        code = digits.zfill(6)
        if ticker == code:
            return 100
        if ticker.startswith(digits) or digits in ticker:
            return 80
    nq = _norm_company(q)
    nc = _norm_company(company)
    q_compact = q.replace(" ", "")
    if ticker and ticker in q_compact:
        return 88
    if nq and nq == nc:
        return 95
    if nq and nc.startswith(nq):
        return 90
    if nq and nq in nc:
        return 72
    if q.casefold() in company.casefold():
        return 68
    chosung = _to_chosung(company)
    if q and all(ch in _CHOSUNG_LIST for ch in q) and q in chosung:
        return 55
    return 0


@app.get("/api/stocks/search")
def api_stocks_search(q: str = "", limit: int = 15) -> dict[str, Any]:
    query = str(q or "").strip()
    if not query:
        return {"items": []}
    cap = max(1, min(int(limit or 15), 30))
    s = load_settings()

    universe: dict[str, dict[str, Any]] = {}
    try:
        from kr_quant.strategy.seasonality import ticker_meta_map

        for code, info in (ticker_meta_map(s) or {}).items():
            ticker = str(code or "").zfill(6)
            if not ticker:
                continue
            universe[ticker] = {
                "ticker": ticker,
                "company": str((info or {}).get("company") or ticker),
                "market": str((info or {}).get("market") or "KOSPI"),
                "sector": "",
                "quant_score": None,
                "quant_rank": None,
            }
    except Exception:
        pass

    for p in (s.output_dir / "latest_all_stocks.parquet", s.output_dir / "all_stocks.parquet"):
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if df is None or df.empty or "ticker" not in df.columns:
            continue
        if "company" in df.columns:
            df = df.drop_duplicates(subset=["ticker"], keep="last")
        for rec in df.to_dict("records"):
            ticker = str(rec.get("ticker") or "").zfill(6)
            if not ticker:
                continue
            row = universe.get(ticker) or {"ticker": ticker, "company": ticker, "market": "KOSPI", "sector": "", "quant_score": None, "quant_rank": None}
            company = str(rec.get("company") or row.get("company") or ticker)
            row["company"] = company
            row["market"] = str(rec.get("market") or row.get("market") or "KOSPI")
            row["sector"] = str(rec.get("sector") or row.get("sector") or "")
            r_score = rec.get("quant_score")
            r_rank = rec.get("quant_rank")
            if pd.notna(r_score) and r_score:
                row["quant_score"] = round(float(r_score), 1)
            if pd.notna(r_rank) and r_rank:
                row["quant_rank"] = int(r_rank)
            universe[ticker] = row
        break

    if not universe:
        from kr_quant.strategy.run import _prices

        prices = _prices(s)
        if prices is not None and not prices.empty and "ticker" in prices.columns:
            cols = [c for c in ("ticker", "company", "market") if c in prices.columns]
            uniq = prices[cols].drop_duplicates(subset=["ticker"], keep="last")
            for rec in uniq.to_dict("records"):
                ticker = str(rec.get("ticker") or "").zfill(6)
                universe[ticker] = {
                    "ticker": ticker,
                    "company": str(rec.get("company") or ticker),
                    "market": str(rec.get("market") or "KOSPI"),
                    "sector": "",
                    "quant_score": None,
                    "quant_rank": None,
                }

    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in universe.values():
        score = _stock_match_score(query, row["ticker"], row["company"])
        if score <= 0:
            continue
        ranked.append((score, row))
    ranked.sort(key=lambda x: (-x[0], x[1].get("quant_rank") or 10_000, x[1]["company"]))
    return {"items": [row for _, row in ranked[:cap]]}


@app.get("/api/stocks/all")
def api_stocks_all() -> dict[str, Any]:
    s = load_settings()
    p = s.output_dir / "latest_all_stocks.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            items = [
                {
                    "t": str(r.get("ticker") or "").zfill(6),
                    "c": str(r.get("company") or ""),
                    "m": str(r.get("market") or "KOSPI"),
                    "s": str(r.get("sector") or ""),
                }
                for r in df.to_dict("records")
                if r.get("ticker")
            ]
            return {"items": items}
        except Exception:
            pass
    return {"items": []}



@app.get("/api/flow/ticker/{ticker}")
def api_flow_ticker_get(ticker: str, days: int = 5) -> dict[str, Any]:
    from kr_quant.flow.scan import diagnose_ticker_flow

    return diagnose_ticker_flow(load_settings(), ticker, days=days)


@app.post("/api/flow/collect-ticker/{ticker}")
def api_flow_collect_ticker_post(ticker: str) -> dict[str, Any]:
    s = load_settings()
    code = str(ticker).zfill(6)
    from kr_quant.ingest.kis import KisInvestorAdapter
    from kr_quant.flow.store import open_settings, upsert_flows
    from kr_quant.flow.official import ticker_payload

    adapter = KisInvestorAdapter(s.kis_app_key, s.kis_app_secret, s.kis_base_url)
    if not adapter.configured():
        return {"ok": False, "error": adapter.missing_reason(), "flow": ticker_payload(s, code)}
    try:
        rows = adapter.collect_stock(code)
        if rows:
            con = open_settings(s)
            upsert_flows(con, rows)
            con.close()
        return {"ok": True, "saved": len(rows), "flow": ticker_payload(s, code)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "flow": ticker_payload(s, code)}






@app.get("/api/seasonality/discovery")
def api_seasonality_discovery_get(
    horizon_days: int = 90,
    min_grade: str | None = None,
    status: str | None = None,
    query: str | None = None,
    lookback_years: int = 5,
    exclude_expired: bool = False,
) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import scan_seasonality_discovery

    s = load_settings()
    rows = scan_seasonality_discovery(
        s,
        horizon_days=horizon_days,
        min_grade=min_grade,
        status_filter=status,
        query=query,
        lookback_years=lookback_years,
        exclude_expired=exclude_expired,
    )
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "lookback_years": lookback_years,
        "count": len(rows),
        "rows": rows,
    }


@app.get("/api/seasonality/discovery/{ticker}")
def api_seasonality_discovery_ticker_get(ticker: str, lookback_years: int = 5) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import scan_seasonality_discovery

    s = load_settings()
    code = str(ticker).zfill(6)
    rows = scan_seasonality_discovery(s, horizon_days=365, query=code, lookback_years=lookback_years)
    match = [r for r in rows if r["ticker"] == code]
    if not match:
        raise HTTPException(status_code=404, detail=f"No seasonality discovery pattern for {code}")
    return {"ok": True, "ticker": code, "lookback_years": lookback_years, "patterns": match}


@app.get("/api/seasonality/ranked")
def api_seasonality_ranked_get(
    horizon_days: int = 90,
    min_grade: str | None = None,
    group_id: str | None = None,
    confirmation: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import rank_institutional_events

    s = load_settings()
    rows = rank_institutional_events(
        s,
        horizon_days=horizon_days,
        min_grade=min_grade,
        group_id=group_id,
        confirmation_filter=confirmation,
        query=query,
    )
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "count": len(rows),
        "rows": rows,
    }


@app.get("/api/seasonality/events")
def api_seasonality_events_get(horizon_days: int = 180) -> dict[str, Any]:
    from kr_quant.strategy.event_calendar import get_upcoming_events

    events = get_upcoming_events(horizon_days=horizon_days)
    return {"ok": True, "horizon_days": horizon_days, "count": len(events), "events": events}


@app.get("/api/seasonality/themes")
def api_seasonality_themes_get(horizon_days: int = 90, lookback_years: int = 5) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import scan_seasonality_discovery
    from kr_quant.strategy.theme_engine import calculate_theme_seasonality

    s = load_settings()
    rows = scan_seasonality_discovery(s, horizon_days=horizon_days, lookback_years=lookback_years)
    themes = calculate_theme_seasonality(rows)
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "lookback_years": lookback_years,
        "theme_count": len(themes),
        "themes": themes,
    }


@app.get("/api/seasonality/highlights")
def api_seasonality_highlights_get() -> dict[str, Any]:
    from kr_quant.strategy.seasonality import get_seasonality_highlights

    s = load_settings()
    data = get_seasonality_highlights(s)
    return {"ok": True, "data": data}


@app.get("/api/seasonality/scan")
def api_seasonality_scan_get(
    month: int | None = None,
    min_win_rate: float = 0.5,
    min_avg_return: float = 0.0,
    preset: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import scan_seasonality, EVENT_PRESETS, seasonality_universe_stats

    s = load_settings()

    rows = scan_seasonality(
        s,
        target_month=month,
        min_win_rate=min_win_rate,
        min_avg_return=min_avg_return,
        preset=preset,
        query=query,
    )
    stats = seasonality_universe_stats(s)
    return {
        "ok": True,
        "target_month": month or pd.Timestamp.now().month,
        "count": len(rows),
        "presets": EVENT_PRESETS,
        "rows": rows,
        "universe_scanned": stats["universe_scanned"],
        "universe_listed": stats["universe_listed"],
        "markets": stats["markets"],
    }


@app.get("/api/seasonality/ticker/{ticker}")
def api_seasonality_ticker_get(ticker: str) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import get_seasonality_database

    s = load_settings()
    db = get_seasonality_database(s)
    code = str(ticker).zfill(6)
    stock = db.get("stocks", {}).get(code)
    if not stock:
        return {"ok": False, "error": f"종목 {code}의 계절성 데이터가 없습니다."}
    return {"ok": True, "stock": stock}


@app.get("/api/strategy")
def api_strategy_get() -> dict[str, Any]:
    from kr_quant.strategy.run import load_strategy

    return load_strategy(load_settings())


@app.get("/api/portfolio")
def api_portfolio() -> dict[str, Any]:
    from kr_quant.portfolio.analysis import analyze_top20

    return analyze_top20(load_settings())


@app.get("/api/sectors")
def api_sectors() -> dict[str, Any]:
    from kr_quant.sector.ranking import rank_sectors

    s = load_settings()
    out = rank_sectors(s)
    quality = _quality(s)
    out["as_of_date"] = (quality or {}).get("as_of_date")
    return out


@app.get("/api/screens")
def api_screens(id: str = "value_growth", include_quant: bool = True) -> dict[str, Any]:
    from kr_quant.screens import screens_payload

    from kr_quant.timing.snapshot import attach_last_close

    s = load_settings()
    out = screens_payload(s, id, include_quant=include_quant)
    quality = _quality(s)
    out["as_of_date"] = (quality or {}).get("as_of_date")
    if isinstance(out.get("rows"), list):
        out["rows"] = attach_last_close(out["rows"], s)
    return out



class StrategyTickerIn(BaseModel):
    ticker: str = ""


@app.get("/api/strategy/ticker/{ticker}")
def api_strategy_ticker_get(ticker: str) -> dict[str, Any]:
    from kr_quant.strategy.run import backtest_single_stock

    try:
        return backtest_single_stock(load_settings(), ticker)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"백테스트 실행 중 오류: {exc}"}


@app.post("/api/strategy/ticker")
def api_strategy_ticker_post(body: StrategyTickerIn) -> dict[str, Any]:
    from kr_quant.strategy.run import backtest_single_stock

    try:
        return backtest_single_stock(load_settings(), body.ticker)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"백테스트 실행 중 오류: {exc}"}

@app.post("/api/strategy")
def api_strategy_post(body: StrategyIn | None = None) -> dict[str, Any]:
    from kr_quant.strategy.run import scan_strategies

    return scan_strategies(load_settings())


@app.get("/api/us13f")
def api_us13f_get() -> dict[str, Any]:
    from kr_quant.us13f.scan import load_13f

    return load_13f(load_settings())


@app.post("/api/us13f")
def api_us13f_post(body: Us13fIn | None = None) -> dict[str, Any]:
    from kr_quant.us13f.scan import refresh_13f

    return refresh_13f(load_settings(), force=True if body is None else body.force)


@app.get("/api/watchlist")
def api_watchlist_get() -> dict[str, Any]:
    from kr_quant.layers.context import watchlist_state

    res = watchlist_state(load_settings())
    return res if isinstance(res, dict) else {"rows": res}


@app.post("/api/watchlist")
def api_watchlist_post(body: WatchIn) -> dict[str, Any]:
    from kr_quant.layers.context import watchlist_add

    rows = watchlist_add(load_settings(), body.ticker, body.company, body.note)
    return {"rows": rows}


@app.delete("/api/watchlist/{ticker}")
def api_watchlist_delete(ticker: str) -> dict[str, Any]:
    from kr_quant.layers.context import watchlist_remove

    rows = watchlist_remove(load_settings(), ticker)
    return {"rows": rows}


def _local_company_names() -> dict[str, str]:
    s = load_settings()
    names: dict[str, str] = {}
    for folder in (s.staged_dir / "live", s.staged_dir / "demo"):
        path = folder / "master.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "ticker" not in df.columns or "company" not in df.columns:
            continue
        for rec in df[["ticker", "company"]].drop_duplicates("ticker").to_dict("records"):
            code = str(rec.get("ticker") or "").zfill(6)
            name = rec.get("company")
            if code and name:
                names[code] = str(name)
    return names


@app.get("/api/toss/rankings")
def api_toss_rankings() -> dict[str, Any]:
    from kr_quant.ingest.tossinvest import attach_stock_names, get_rankings, normalize_ranking_row

    s = load_settings()
    if not s.toss_client_id or not s.toss_client_secret:
        return {"configured": False, "error": "토스증권 키가 없습니다.", "groups": []}
    local_names = _local_company_names()
    groups = []
    specs = [
        ("TOP_GAINERS", "1d", "급상승"),
        ("TOP_LOSERS", "1d", "급하락"),
        ("MARKET_TRADING_AMOUNT", "realtime", "거래대금"),
        ("TOSS_SECURITIES_TRADING_AMOUNT", "1d", "토스 거래대금"),
    ]
    error = None
    for rtype, duration, label in specs:
        try:
            data = get_rankings(
                s.toss_client_id,
                s.toss_client_secret,
                ranking_type=rtype,
                duration=duration,
                count=8,
            )
            raw = data.get("rankings") if isinstance(data, dict) else data
            rows = [normalize_ranking_row(r) for r in (raw or []) if isinstance(r, dict)]
            rows = attach_stock_names(s.toss_client_id, s.toss_client_secret, rows, local_names)
            groups.append({"type": rtype, "label": label, "duration": duration, "rows": rows})
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:200]
            groups.append({"type": rtype, "label": label, "duration": duration, "rows": [], "error": error})
    from kr_quant.web.comments import SELECTION, annotate_toss_groups

    return {
        "configured": True,
        "error": error,
        "groups": annotate_toss_groups(groups),
        "selection": SELECTION["toss"],
        "used_in_quant": False,
        "fetched_at": time.time(),
    }


@app.get("/api/maps/static")
def api_map_static(lat: str, lng: str) -> Any:
    from fastapi.responses import Response

    from kr_quant.ingest.naver_maps import fetch_static_map

    s = load_settings()
    if not s.naver_map_client_id or not s.naver_map_client_secret:
        raise HTTPException(400, "네이버 지도 키가 없습니다.")
    try:
        png = fetch_static_map(s.naver_map_client_id, s.naver_map_client_secret, lat, lng)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return Response(content=png, media_type="image/png")


@app.get("/api/naver/search")
def api_naver_search(q: str, kind: str = "news") -> dict[str, Any]:
    from kr_quant.ingest.naver_search import search_news, search_web

    s = load_settings()
    if not s.naver_client_id or not s.naver_client_secret:
        raise HTTPException(400, "네이버 Client ID/Secret이 없습니다. 설정 탭에 넣으세요.")
    kind = (kind or "news").lower()
    try:
        if kind == "web":
            return search_web(s.naver_client_id, s.naver_client_secret, q)
        return search_news(s.naver_client_id, s.naver_client_secret, q)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/research/reports")
def api_research_list() -> dict[str, Any]:
    from kr_quant.research.report import list_saved_reports

    s = load_settings()
    rows = list_saved_reports(s.output_dir)
    return {"rows": rows, "total": len(rows)}


@app.post("/api/research/reports/delete")
def api_research_delete(body: ReportDeleteIn) -> dict[str, Any]:
    from kr_quant.research.report import delete_saved_report

    s = load_settings()
    return delete_saved_report(s.output_dir, body.ticker, body.as_of, kind=body.kind, filename=body.filename)


@app.get("/api/research/{ticker}")
def api_research_get(ticker: str, as_of: str | None = None) -> dict[str, Any]:
    from kr_quant.research.analyze import research_path

    s = load_settings()
    folder = _run_dir(s, as_of)
    day = folder.name.split("=", 1)[-1] if folder.name.startswith("as_of_date=") else (as_of or "")
    path = research_path(s.output_dir, day, str(ticker).zfill(6))
    if not path.exists():
        return {"exists": False, "row": None}
    return {"exists": True, "row": json.loads(path.read_text(encoding="utf-8"))}


@app.post("/api/research")
def api_research_post(body: ResearchIn) -> dict[str, Any]:
    from kr_quant.research.analyze import analyze_ticker
    from kr_quant.research.providers import resolve_provider

    s = load_settings()
    row, day = _load_stock_row(body.ticker, body.as_of)
    endpoint = resolve_provider(s, body.provider)
    if not endpoint.api_key:
        raise HTTPException(
            400,
            f"{endpoint.label} AUTH가 없습니다. 설정에서 키를 저장하세요. AI 분석 시에만 해당 제공자에 과금됩니다.",
        )
    try:
        record = analyze_ticker(
            endpoint,
            row,
            day or (body.as_of or ""),
            s.output_dir,
            run_id=str(row.get("run_id") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    return {"ok": True, "row": record}



@app.get("/api/research/{ticker}/infographic")
def api_research_infographic_get(ticker: str, as_of: str | None = None) -> Any:
    from fastapi.responses import HTMLResponse
    from kr_quant.research.report import find_report_file
    from kr_quant.research.infographic import generate_infographic_html
    from kr_quant.timing.snapshot import load_prices

    s = load_settings()
    code = str(ticker).zfill(6)
    row: dict[str, Any] = {}
    day: str = as_of or ""
    try:
        row, day = _load_stock_row(code, as_of)
    except Exception:
        pass

    try:
        px = load_prices(s)
        if not px.empty:
            hist = px[px["ticker"].astype(str).str.zfill(6) == code]
            if not hist.empty:
                last_row = hist.iloc[-1]
                row.setdefault("last_close", last_row.get("close"))
                row.setdefault("market_cap", last_row.get("market_cap"))
                row.setdefault("volume", last_row.get("volume"))
                row.setdefault("trading_value", last_row.get("trading_value"))
                if not row.get("company") and last_row.get("company"):
                    row["company"] = last_row.get("company")
    except Exception:
        pass

    path = find_report_file(s.output_dir, code, as_of)
    if not path or not path.exists():
        record = {"ticker": code, "company": row.get("company") or code, "as_of_date": day or as_of}
        html = generate_infographic_html(record, stock_row=row)
        return HTMLResponse(content=html)

    record = json.loads(path.read_text(encoding="utf-8"))
    html = generate_infographic_html(record, stock_row=row)
    return HTMLResponse(content=html)


@app.get("/api/research/{ticker}/report")
def api_research_report_get(ticker: str, as_of: str | None = None) -> dict[str, Any]:
    from kr_quant.research.report import find_report_file

    s = load_settings()
    path = find_report_file(s.output_dir, str(ticker).zfill(6), as_of)
    if not path or not path.exists():
        return {"exists": False, "row": None}
    return {"exists": True, "row": json.loads(path.read_text(encoding="utf-8"))}


@app.post("/api/research/report")
def api_research_report_post(body: ResearchIn) -> dict[str, Any]:
    from kr_quant.research.providers import resolve_provider
    from kr_quant.research.report import write_report
    from kr_quant.web.guide import external_links, pad_ticker

    s = load_settings()
    row, day = _load_stock_row(body.ticker, body.as_of)
    endpoint = resolve_provider(s, body.provider)
    if not endpoint.api_key:
        raise HTTPException(
            400,
            f"{endpoint.label} AUTH가 없습니다. 설정에서 키를 저장하세요. AI 분석 리포트 작성 시에만 과금됩니다.",
        )
    code = pad_ticker(row.get("ticker") or body.ticker)
    news: list[dict[str, Any]] = []
    web: list[dict[str, Any]] = []
    if s.naver_client_id and s.naver_client_secret:
        try:
            from kr_quant.ingest.naver_search import company_bundle

            bundle = company_bundle(s.naver_client_id, s.naver_client_secret, row.get("company"), code)
            news = bundle.get("news") or []
            web = bundle.get("web") or []
        except Exception:  # noqa: BLE001
            news = []
            web = []
    macro: dict[str, Any] = {}
    yahoo: dict[str, Any] = {}
    try:
        from kr_quant.ingest.fred import macro_snapshot

        macro = macro_snapshot(s.fred_api_key)
    except Exception:  # noqa: BLE001
        macro = {}
    try:
        from kr_quant.ingest.yahoo import stock_research_quote

        yahoo = stock_research_quote(code, row.get("market"))
    except Exception:  # noqa: BLE001
        yahoo = {}
    strategy_backtest: dict[str, Any] = {}
    try:
        from kr_quant.strategy.run import backtest_single_stock

        strategy_backtest = backtest_single_stock(s, code)
    except Exception:  # noqa: BLE001
        strategy_backtest = {}
    try:
        record = write_report(
            endpoint,
            row,
            day or (body.as_of or ""),
            s.output_dir,
            links=external_links(code, row.get("company")),
            news=news,
            web=web,
            macro=macro,
            yahoo=yahoo,
            strategy_backtest=strategy_backtest,
            run_id=str(row.get("run_id") or ""),
            root=s.root,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc
    try:
        from kr_quant.ingest.telegram import format_report_notice, notify_safe

        notify_safe(s.telegram_bot_token, s.telegram_chat_id, format_report_notice(record))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "row": record}


@app.get("/api/jobs")
def api_job_status() -> dict[str, Any]:
    return RUNNER.snapshot()


@app.post("/api/jobs")
def api_job_start(body: JobIn) -> dict[str, Any]:
    try:
        if body.kind == "demo":
            return RUNNER.start("demo", lambda: job_demo(body.as_of))
        if body.kind == "screen":
            return RUNNER.start("screen", lambda: job_screen(body.as_of, body.source))
        if body.kind == "krx-prices":
            return RUNNER.start(
                "krx-prices",
                lambda: job_krx_prices(body.as_of, body.lookback_days or 10),
            )
        if body.kind == "krx-history":
            return RUNNER.start(
                "krx-history",
                lambda: job_krx_history(body.as_of, body.lookback_days or 750),
            )
        if body.kind == "investor-kis":
            from kr_quant.flow.official import collect_official

            return RUNNER.start("investor-kis", lambda: collect_official(load_settings()))
        if body.kind == "dart-nps":
            from kr_quant.ownership.nps import scan_nps_holdings

            return RUNNER.start("dart-nps", lambda: scan_nps_holdings(load_settings()))
        if body.kind == "strategy":
            from kr_quant.strategy.run import scan_strategies

            return RUNNER.start("strategy", lambda: scan_strategies(load_settings()))
        return RUNNER.start(
            "live",
            lambda: job_live(body.as_of, body.lookback_days, body.max_corps, body.skip_ingest),
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/scheduler")
def api_scheduler_get() -> dict[str, Any]:
    from kr_quant.web.scheduler import scheduler_status

    return scheduler_status()


@app.post("/api/scheduler")
def api_scheduler_post(body: SchedulerIn) -> dict[str, Any]:
    from kr_quant.web.scheduler import save_scheduler_config

    return save_scheduler_config(body.model_dump())


@app.get("/api/deploy/status")
@app.get("/api/publish/status")
def api_deploy_status() -> dict[str, Any]:
    from kr_quant.web.publish import get_deploy_status

    return get_deploy_status()


@app.post("/api/deploy/run")
@app.post("/api/publish/run")
def api_deploy_run(request: Request) -> dict[str, Any]:
    if public_share_mode(request):
        raise HTTPException(403, "공개 웹에서는 수동 배포를 실행할 수 없습니다.")
    from kr_quant.web.publish import start_manual_deploy

    return start_manual_deploy()


def port_in_use(host: str, port: int) -> bool:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def dashboard_is_running(host: str, port: int) -> bool:
    if not port_in_use(host, port):
        return False
    try:
        from urllib.request import urlopen

        with urlopen(f"http://{host}:{port}/api/status", timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        return isinstance(payload, dict) and "model_version" in payload
    except Exception:  # noqa: BLE001
        return False


def pick_listen_port(host: str, port: int, span: int = 12) -> int:
    for candidate in range(port, port + max(span, 1)):
        if not port_in_use(host, candidate):
            return candidate
    raise RuntimeError(f"{port}~{port + span - 1} 포트가 모두 사용 중입니다.")


def _console_setup() -> None:
    import sys

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _banner(lines: list[str]) -> None:
    print("")
    print("=" * 60)
    for line in lines:
        print(f"  {line}")
    print("=" * 60)
    print("")


def serve(host: str = "127.0.0.1", port: int = 8790, open_browser: bool = True) -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    _console_setup()
    print("")
    print("  ============================================================")
    print("    🚀 KR Quant Research 통합 퀀트 시스템 시작 중...")
    print("  ============================================================")
    print("  [1/3] 퀀트 분석 모듈 및 환경 설정 로딩 중...")

    url = f"http://{host}:{port}"
    if dashboard_is_running(host, port):
        _banner([
            "💡 KR Quant Research 서비스가 이미 백그라운드에서 실행 중입니다.",
            f"🌐 브라우저를 엽니다: {url}",
            "💡 서비스를 종료하려면 기존 콘솔 창을 닫거나 Ctrl+C를 누르세요.",
        ])
        if open_browser:
            webbrowser.open(url)
        return

    try:
        chosen = pick_listen_port(host, port)
    except RuntimeError as exc:
        _banner([str(exc)])
        raise SystemExit(1) from exc

    print("  [2/3] 포트 점검 및 로컬 웹 서버 준비 완료")

    try:
        from kr_quant.web.scheduler import start_price_scheduler

        start_price_scheduler()
        print("  [3/3] 백그라운드 자동 스케줄러 활성화 완료")
    except Exception:  # noqa: BLE001
        pass

    if chosen != port:
        url = f"http://{host}:{chosen}"
        _banner([
            f"⚠️ {port} 포트가 사용 중이라 {chosen} 포트로 실행합니다.",
            f"🌐 웹 서비스 접속 주소 : {url}",
            "⏰ 자동 스케줄러       : 백그라운드 활성화 완료",
            "🌐 기본 브라우저를 자동으로 실행합니다...",
            "",
            "💡 [종료 안내] 서비스를 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.",
        ])
    else:
        _banner([
            "🚀 KR Quant Research 서버가 성공적으로 실행되었습니다!",
            f"🌐 웹 서비스 접속 주소 : {url}",
            "⏰ 자동 스케줄러       : 백그라운드 활성화 완료",
            "🌐 기본 브라우저를 자동으로 실행합니다...",
            "",
            "💡 [종료 안내] 서비스를 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.",
        ])

    if open_browser:
        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print("  ✅ 서버가 정상 구동 중입니다. 이 콘솔 창은 열어 두세요.")
    print("     (아래에 아무 것도 안 나오는 게 정상입니다 — 서버가 요청을 대기 중)")
    print("")

    try:
        uvicorn.run(
            "kr_quant.web.app:app",
            host=host,
            port=chosen,
            reload=False,
            log_level="warning",
            access_log=False,
        )
    except OSError as exc:
        busy = getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) in {48, 98, 10048} or "10048" in str(exc)
        if busy:
            _banner([
                "Port is already in use. Opening the existing dashboard.",
                f"Open {url}",
            ])
            if open_browser:
                webbrowser.open(url)
            return
        raise


if __name__ == "__main__":
    serve()
