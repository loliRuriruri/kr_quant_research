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

from kr_quant.research.tier1_contract import (
    tier1_cached_chat_json,
    tier1_deterministic_fallback,
    tier1_success,
    tier1_unavailable,
)
from kr_quant.settings import load_settings
from kr_quant.web.envfile import apply_env_to_process, mask_secret, upsert_env_file
from kr_quant.web.jobs import RUNNER, job_dart_backfill, job_demo, job_history_summary, job_krx_history, job_krx_prices, job_live, job_screen, job_smart_sync

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
    kind: str = Field(pattern="^(smart-sync|demo|screen|live|krx-prices|krx-history|dart-backfill|investor-kis|dart-nps|strategy)$")
    as_of: str = "auto"
    source: str = "live"
    lookback_days: int = 80
    max_corps: int = 400
    dart_batch_size: int = 50
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
    job_kind: str = "smart-sync"
    hour: int = 19
    minute: int = 10
    lookback_days: int = 80
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


def _has_usable_rank_rows(path: Path) -> bool:
    """Return True only when a ranking artifact contains at least one usable row.

    A failed screen can still leave a correctly shaped, zero-row top CSV or an
    all-stocks parquet where every security is ineligible.  Existence alone is
    therefore not a success signal.
    """
    if not path.exists():
        return False
    try:
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path, dtype={"ticker": str})
        else:
            try:
                frame = pd.read_parquet(path, columns=["quant_rank", "universe_eligible"])
            except Exception:
                frame = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return False
    if frame.empty or "quant_rank" not in frame.columns:
        return False
    usable = pd.to_numeric(frame["quant_rank"], errors="coerce").notna()
    if "universe_eligible" in frame.columns:
        usable &= frame["universe_eligible"].fillna(False).astype(bool)
    return bool(usable.any())


def _resolve_rank_output(
    settings: Any,
    dated_name: str,
    latest_name: str,
    *,
    as_of: str | None = None,
) -> Path | None:
    """Resolve the newest *successful* rank artifact, not merely newest file.

    An explicit historical date remains strict.  Default dashboard requests
    walk dated runs newest-first and then the latest-success pointer, skipping
    incomplete runs that contain no eligible ranked securities.
    """
    if as_of:
        exact = _run_dir(settings, as_of) / dated_name
        return exact if exact.exists() else None

    from kr_quant.run_generation import current_output_path

    candidates = [current_output_path(settings, latest_name)]
    candidates.extend(folder / dated_name for _, folder in _run_dirs(settings))
    candidates.append(settings.output_dir / latest_name)
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _has_usable_rank_rows(path):
            return path
    return None


def _rank_source_as_of(frame: pd.DataFrame, path: Path | None = None) -> str | None:
    if "as_of_date" in frame.columns:
        values = frame["as_of_date"].dropna().astype(str)
        if not values.empty:
            return str(values.iloc[0])[:10]
    if path is not None and path.parent.name.startswith("as_of_date="):
        return path.parent.name.split("=", 1)[-1]
    return None


def _quality(settings, as_of: str | None = None) -> dict[str, Any]:
    from kr_quant.run_generation import current_output_path

    folder = _run_dir(settings, as_of)
    path = folder / "data_quality_report.json"
    if not as_of:
        committed = current_output_path(settings, "data_quality_report.json")
        if committed.exists():
            path = committed
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
    from kr_quant.web.evidence import build_evidence_registry
    from kr_quant.web.scheduler import scheduler_status

    from kr_quant.web.guide import explain_run_status

    s = load_settings()
    quality = _quality(s)
    live_prices = s.staged_dir / "live" / "prices.parquet"
    fresh = freshness_snapshot(s, screen_as_of=(quality or {}).get("as_of_date"))
    evidence_registry = build_evidence_registry(s, quality=quality, freshness=fresh)
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
        "evidence_registry": evidence_registry,
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

    # 3. KIS (한국투자증권) — user-clicked test may issue a token; status/GET must not.
    if s.kis_app_key and s.kis_app_secret:
        try:
            from kr_quant.ingest.kis import KisInvestorAdapter, KisTokenRateLimited

            adapter = KisInvestorAdapter(s.kis_app_key, s.kis_app_secret, s.kis_base_url)
            status = adapter.token_status()
            if status.get("cached"):
                out["kis"] = {
                    "label": "한국투자증권 (KIS)",
                    "ok": True,
                    "detail": f"캐시된 토큰 유효 · 재발급 없음 · 만료 {status.get('expires_at') or '—'}",
                }
            elif not status.get("can_issue"):
                out["kis"] = {
                    "label": "한국투자증권 (KIS)",
                    "ok": True,
                    "detail": f"발급 제한 보호 중 · 다음 가능 {status.get('retry_at') or '1분 후'}",
                }
            else:
                adapter.token(timeout=10, reason="connection_test")
                out["kis"] = {
                    "label": "한국투자증권 (KIS)",
                    "ok": True,
                    "detail": "토큰 발급 완료 · 공식 수급 연동 정상",
                }
        except KisTokenRateLimited as exc:
            out["kis"] = {"label": "한국투자증권 (KIS)", "ok": True, "detail": str(exc)[:160]}
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
    dated_name = "top20.csv" if n <= 20 else "top100.csv"
    latest_name = "latest_top20.csv" if n <= 20 else "latest_top100.csv"
    path = _resolve_rank_output(s, dated_name, latest_name, as_of=as_of)
    from kr_quant.web.comments import SELECTION, annotate_quant_rows

    from kr_quant.timing.snapshot import attach_last_close

    rows = attach_last_close(annotate_quant_rows(_read_table(path)[: max(n, 1)] if path else []), s)
    source_as_of = str(rows[0].get("as_of_date") or "")[:10] if rows else None
    return {
        "rows": rows,
        "path": str(path) if path and path.exists() else None,
        "source_as_of": source_as_of,
        "selection": SELECTION["quant"],
    }


@app.get("/api/results/all")
def api_all(limit: int = 300, eligible_only: bool = True, as_of: str | None = None) -> dict[str, Any]:
    s = load_settings()
    path = _resolve_rank_output(s, "all_stocks.parquet", "latest_all_stocks.parquet", as_of=as_of)
    if path is None:
        return {"rows": [], "total": 0, "source_as_of": None}
    df = pd.read_parquet(path)
    source_as_of = _rank_source_as_of(df, path)
    if eligible_only and "universe_eligible" in df.columns:
        df = df[df["universe_eligible"].fillna(False).astype(bool)]
    if "quant_rank" in df.columns:
        df = df.sort_values("quant_rank", na_position="last")
    from kr_quant.web.comments import SELECTION, annotate_quant_rows

    from kr_quant.timing.snapshot import attach_last_close

    rows = attach_last_close(annotate_quant_rows(_clean(df.head(limit).to_dict("records"))), s)
    return {
        "rows": rows,
        "total": int(len(df)),
        "source_as_of": source_as_of,
        "selection": SELECTION["quant"],
    }


_CORP_CODE_CACHE: dict[str, str] = {}


def _corp_code(ticker: str, profile: dict[str, Any]) -> str:
    code = str(profile.get("corp_code") or "").zfill(8)
    if code and code != "00000000":
        return code
    t_code = str(ticker).zfill(6)
    if t_code in _CORP_CODE_CACHE:
        return _CORP_CODE_CACHE[t_code]
    s = load_settings()
    path = s.staged_dir / "live" / "company.parquet"
    if not path.exists():
        return ""
    try:
        df = pd.read_parquet(path, columns=["stock_code", "corp_code"])
    except Exception:
        try:
            df = pd.read_parquet(path)
        except Exception:
            return ""
    if "stock_code" not in df.columns or "corp_code" not in df.columns:
        return ""
    for sc, cc in zip(df["stock_code"].astype(str).str.zfill(6), df["corp_code"].astype(str).str.zfill(8)):
        if sc and cc and cc != "00000000":
            _CORP_CODE_CACHE[sc] = cc
    return _CORP_CODE_CACHE.get(t_code, "")


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


TIER1_FACTOR_LABELS = {
    "value_score": "가치",
    "quality_score": "품질",
    "growth_score": "성장",
    "momentum_score": "모멘텀",
    "financial_score": "재무안정",
}


def _ranking_tier1_snapshot(settings: Any, *, limit: int = 10) -> dict[str, Any]:
    path = _resolve_rank_output(settings, "all_stocks.parquet", "latest_all_stocks.parquet")
    if path is None:
        return {"as_of": None, "top_rows": [], "movers": [], "universe_count": 0, "missing": ["all_stocks"]}

    df = pd.read_parquet(path)
    source_as_of = _rank_source_as_of(df, path)
    if "universe_eligible" in df.columns:
        eligible = df[df["universe_eligible"].fillna(False).astype(bool)].copy()
    else:
        eligible = df.copy()
    if "quant_rank" in eligible.columns:
        eligible = eligible.sort_values("quant_rank", na_position="last")

    def compact_row(rec: dict[str, Any]) -> dict[str, Any]:
        factors = []
        for column, label in TIER1_FACTOR_LABELS.items():
            value = rec.get(column)
            if value is not None and not pd.isna(value):
                factors.append({"factor": label, "score": round(float(value), 1)})
        factors.sort(key=lambda item: item["score"], reverse=True)
        return {
            "ticker": str(rec.get("ticker") or "").zfill(6),
            "company": rec.get("company"),
            "sector": rec.get("sector"),
            "rank": rec.get("quant_rank"),
            "previous_rank": rec.get("previous_rank"),
            "rank_change": rec.get("rank_change"),
            "score": rec.get("quant_score"),
            "previous_score": rec.get("previous_score"),
            "score_change": rec.get("score_change"),
            "dominant_factors": factors[:2],
            "weak_factors": list(reversed(factors[-2:])),
            "data_confidence": rec.get("data_confidence"),
            "coverage": rec.get("weighted_metric_coverage"),
            "risk_flags": _clean(rec.get("risk_flags")) if rec.get("risk_flags") is not None else [],
        }

    top_rows = [compact_row(rec) for rec in eligible.head(max(1, limit)).to_dict("records")]
    movers: list[dict[str, Any]] = []
    if "rank_change" in eligible.columns:
        changed = eligible[eligible["rank_change"].notna()].copy()
        if not changed.empty:
            changed["abs_rank_change"] = changed["rank_change"].abs()
            movers = [compact_row(rec) for rec in changed.sort_values("abs_rank_change", ascending=False).head(8).to_dict("records")]

    low_confidence_count = 0
    if "data_confidence" in eligible.columns:
        low_confidence_count = int((pd.to_numeric(eligible["data_confidence"], errors="coerce") < 60).sum())
    return {
        "as_of": source_as_of,
        "source_path": str(path),
        "top_rows": _clean(top_rows),
        "movers": _clean(movers),
        "universe_count": int(len(eligible)),
        "low_confidence_count": low_confidence_count,
        "missing": [] if top_rows else ["eligible_rank_rows"],
    }


def _factor_names(row: dict[str, Any], key: str) -> str:
    names = [str(item.get("factor")) for item in (row.get(key) or []) if item.get("factor")]
    return "·".join(names) if names else "확인 가능한 팩터 없음"


def _dashboard_rank_fallback_payload(context: dict[str, Any]) -> dict[str, Any]:
    top_rows = context.get("top_rows") or []
    champion = top_rows[0]
    movers = context.get("movers") or []
    mover = movers[0] if movers else None
    as_of = context.get("as_of") or "최근 성공 기준일"
    headline = f"{as_of} 적격 {context.get('universe_count', 0)}종목 기준 퀀트 1위: {champion.get('company') or champion.get('ticker')}"
    champion_focus = (
        f"현재 점수 {float(champion.get('score') or 0):.1f}, 우세 팩터는 {_factor_names(champion, 'dominant_factors')}, "
        f"취약 팩터는 {_factor_names(champion, 'weak_factors')}입니다."
    )
    if mover:
        change = float(mover.get("rank_change") or 0)
        direction = "상승" if change > 0 else "하락" if change < 0 else "변동 없음"
        strategy_note = (
            f"가장 큰 전회 대비 순위 변화는 {mover.get('company') or mover.get('ticker')}의 {abs(change):.0f}계단 {direction}입니다. "
            f"신뢰도 60 미만 종목은 {context.get('low_confidence_count', 0)}개이며, 이 설명은 점수 계산에 반영되지 않습니다."
        )
    else:
        strategy_note = "비교 가능한 전회 순위 변화가 없습니다. 현재 팩터와 데이터 신뢰도만 확인해야 합니다."
    return {"headline": headline, "champion_focus": champion_focus, "strategy_note": strategy_note}


def _rank_fallback_payload(context: dict[str, Any]) -> dict[str, Any]:
    top_rows = context.get("top_rows") or []
    movers = context.get("movers") or []
    changes = []
    for row in movers[:4]:
        change = float(row.get("rank_change") or 0)
        if change == 0:
            continue
        direction = "상승" if change > 0 else "하락"
        changes.append(f"{row.get('company') or row.get('ticker')}: 전회 대비 {abs(change):.0f}계단 {direction}")
    explanations = [
        {
            "ticker": row.get("ticker"),
            "summary": (
                f"현재 {float(row.get('score') or 0):.1f}점, 우세 {_factor_names(row, 'dominant_factors')}, "
                f"취약 {_factor_names(row, 'weak_factors')}, 데이터 신뢰도 {float(row.get('data_confidence') or 0):.1f}"
            ),
        }
        for row in top_rows[:4]
    ]
    champion = top_rows[0]
    return {
        "headline": f"{context.get('as_of') or '최근 성공 기준일'} 퀀트 1위: {champion.get('company') or champion.get('ticker')}",
        "changes": changes or ["비교 가능한 전회 순위 변화가 없습니다."],
        "top_explanations": explanations,
        "cautions": [
            "실패한 최신 계산본은 제외하고 적격 랭킹이 존재하는 마지막 성공본을 사용했습니다.",
            "현재 팩터만으로 점수 변화의 원인을 단정할 수 없습니다.",
        ],
    }


@app.get("/api/flow/tier1-briefing")
def api_flow_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.flow.official import events_payload

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    flow = events_payload(s, min_turn=5)
    active_key = str(flow.get("active") or "official")
    active = flow.get(active_key) if isinstance(flow.get(active_key), dict) else {}
    source_name = "kis_investor_flow" if active_key == "official" else "toss_flow_cache"
    by_ticker: dict[str, dict[str, Any]] = {}
    for table_name in ("cum5", "consecutive", "paired", "turns"):
        for row in (active.get(table_name) or [])[:15]:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").zfill(6)
            if not ticker.strip("0"):
                continue
            item = by_ticker.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "company": row.get("company"),
                    "source": row.get("source") or active.get("source"),
                    "party": row.get("party_ko"),
                    "last_date": row.get("last_date"),
                    "today_primary": row.get("today_a"),
                    "today_foreign": row.get("today_b"),
                    "w5": row.get("w5"),
                    "w20": row.get("w20"),
                    "streak_days": row.get("days"),
                    "direction": row.get("direction"),
                    "paired": row.get("paired"),
                    "paired_direction": row.get("paired_direction"),
                    "turn": row.get("turn"),
                    "event_types": [],
                },
            )
            if table_name not in item["event_types"]:
                item["event_types"].append(table_name)
    evidence = list(by_ticker.values())[:15]
    prompt_version = "flow_tier1_v3"
    if not evidence:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="수급 브리핑에 사용할 실제 종목 데이터가 없습니다.",
            sources=[source_name],
            missing=["investor_flow_events"],
            prompt_version=prompt_version,
        )

    evidence_json = json.dumps(evidence, ensure_ascii=False, default=str)
    prompt = (
        "당신은 기관 수급 데이터 감사자입니다.\n"
        f"실제 투자자별 순매수 관측치(수량 단위, 금액 아님):\n{evidence_json}\n\n"
        "w5/w20은 저장된 거래일 순매수 수량 합계이고 today_primary/today_foreign도 주수입니다. "
        "제공된 수치와 이벤트 유형만 요약하세요. 업종·원인·지지선·매집 의도를 추정하지 말고, 표본 범위와 기준일을 밝히며 주문·비중 지시는 하지 마세요."
        + "\n반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 헤드라인\", \"briefing\": \"관찰된 수급 공통점과 한계 2줄\", \"focus_sectors\": [\"실제 후보에서 확인된 업종\"]}"
    )
    sample_lines = [
        f"{row.get('company') or row['ticker']}: 5일 {float(row.get('w5') or 0):+,.0f}주, {row.get('direction') or 'FLAT'} {int(row.get('streak_days') or 0)}일"
        for row in evidence[:3]
    ]
    fallback_payload = {
        "headline": f"{active.get('source') or active_key.upper()} 실제 수급 이벤트 {len(evidence)}종목",
        "briefing": " · ".join(sample_lines) + ". 수량 기반 제한 표본이며 전시장 업종 순위나 매수 의도를 뜻하지 않습니다.",
        "focus_sectors": [],
    }
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="flow",
        prompt_version=prompt_version,
        evidence=evidence,
        messages=[
            {"role": "system", "content": "You are a professional Korean institutional flow strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        as_of=max((str(row.get("last_date") or "") for row in evidence), default=None) or None,
        sources=[source_name],
        evidence_count=len(evidence),
    )
    if result.get("ok"):
        return result
    return tier1_deterministic_fallback(
        endpoint,
        fallback_payload,
        as_of=max((str(row.get("last_date") or "") for row in evidence), default=None) or None,
        sources=[source_name],
        evidence_count=len(evidence),
        prompt_version=prompt_version,
    )


@app.get("/api/dashboard/tier1-briefing")
def api_dashboard_tier1_briefing_get(deterministic: bool = False) -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "dashboard_tier1_v2"

    rank_context = _ranking_tier1_snapshot(s, limit=8)
    top_stocks = rank_context.get("top_rows") or []
    stocks_summary = json.dumps(rank_context, ensure_ascii=False, default=str)
    if not top_stocks:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="대시보드 브리핑에 사용할 적격 상위 종목 데이터가 없습니다.",
            sources=["all_stocks"],
            missing=["top_ranked_stocks"],
            prompt_version=prompt_version,
        )

    fallback_payload = _dashboard_rank_fallback_payload(rank_context)
    if deterministic:
        return tier1_deterministic_fallback(
            endpoint,
            fallback_payload,
            as_of=rank_context.get("as_of"),
            sources=["all_stocks", "daily_rank_change"],
            evidence_count=len(top_stocks),
            missing=rank_context.get("missing") or [],
            prompt_version=prompt_version,
        )

    prompt = (
        "당신은 국내 최고 퀀트 펀드매니저입니다.\n"
        f"오늘의 퀀트 랭킹 및 전회 대비 변화 데이터:\n{stocks_summary}\n\n"
        "현재 순위·점수·전회 대비 변화·우세/취약 팩터·데이터 신뢰도만 사용하세요. 점수 변화가 특정 팩터 때문에 발생했다고 단정하지 말고, 제공되지 않은 재무 사실이나 주문·비중 지시는 하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 랭킹 변화 헤드라인\", \"champion_focus\": \"1위 종목의 현재 우세/취약 팩터와 변화 1줄\", \"strategy_note\": \"가장 큰 순위 변화와 데이터 주의점 2줄\"}"
    )
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="dashboard",
        prompt_version=prompt_version,
        evidence=rank_context,
        messages=[
            {"role": "system", "content": "You are an elite quantitative fund strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        as_of=rank_context.get("as_of"),
        sources=["all_stocks", "daily_rank_change"],
        evidence_count=len(top_stocks),
        missing=rank_context.get("missing") or [],
    )
    if result.get("ok"):
        return result
    fallback = tier1_deterministic_fallback(
        endpoint,
        fallback_payload,
        as_of=rank_context.get("as_of"),
        sources=["all_stocks", "daily_rank_change"],
        evidence_count=len(top_stocks),
        missing=rank_context.get("missing") or [],
        prompt_version=prompt_version,
    )
    fallback["ai_error_code"] = result.get("error_code")
    return fallback


@app.get("/api/rank/tier1-briefing")
def api_rank_tier1_briefing_get(deterministic: bool = False) -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "rank_tier1_v1"
    context = _ranking_tier1_snapshot(s, limit=12)
    top_rows = context.get("top_rows") or []
    movers = context.get("movers") or []
    if not top_rows:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="점수 랭킹 해설에 사용할 적격 종목 데이터가 없습니다.",
            as_of=context.get("as_of"),
            sources=["all_stocks", "daily_rank_change"],
            missing=context.get("missing") or ["rank_rows"],
            prompt_version=prompt_version,
        )

    fallback_payload = _rank_fallback_payload(context)
    if deterministic:
        return tier1_deterministic_fallback(
            endpoint,
            fallback_payload,
            as_of=context.get("as_of"),
            sources=["all_stocks", "daily_rank_change", "factor_scores"],
            evidence_count=len(top_rows) + len(movers),
            missing=context.get("missing") or [],
            prompt_version=prompt_version,
        )

    prompt = (
        "당신은 한국 주식 퀀트 랭킹 결과를 검수하는 연구원입니다.\n"
        f"실제 랭킹 스냅샷:\n{json.dumps(context, ensure_ascii=False, default=str)}\n\n"
        "현재 점수, 전회 대비 순위·점수 변화, 현재 우세/취약 팩터, 신뢰도만 해설하세요. 이전 팩터 점수가 없으므로 특정 팩터가 점수 변화를 일으켰다고 단정하지 마세요. 매수·매도·비중·목표가를 제시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 랭킹 변화 요약\", \"changes\": [\"실제 순위 상승·하락 관측\"], \"top_explanations\": [{\"ticker\": \"6자리 코드\", \"summary\": \"현재 우세/취약 팩터와 신뢰도 해설\"}], \"cautions\": [\"데이터 또는 해석 주의점\"]}"
    )
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="rank",
        prompt_version=prompt_version,
        evidence=context,
        messages=[
            {"role": "system", "content": "You are a Korean equity ranking auditor. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        as_of=context.get("as_of"),
        sources=["all_stocks", "daily_rank_change", "factor_scores"],
        evidence_count=len(top_rows) + len(movers),
        missing=context.get("missing") or [],
    )
    if result.get("ok"):
        return result
    fallback = tier1_deterministic_fallback(
        endpoint,
        fallback_payload,
        as_of=context.get("as_of"),
        sources=["all_stocks", "daily_rank_change", "factor_scores"],
        evidence_count=len(top_rows) + len(movers),
        missing=context.get("missing") or [],
        prompt_version=prompt_version,
    )
    fallback["ai_error_code"] = result.get("error_code")
    return fallback


@app.get("/api/market/tier1-briefing")
def api_market_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.context.macro_brief import build_macro_dashboard

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "market_tier1_v2"

    macro = build_macro_dashboard(s, refresh=False)
    brief = macro.get("brief") or {}
    selected_ids = {"bok_rate", "kr_us_diff", "ktb3y", "usdkrw_bok", "FEDFUNDS", "DGS10", "DGS2", "T10Y2Y", "CPIAUCSL", "UNRATE", "DEXKOUS"}
    indicator_rows = []
    for group_name in ("domestic", "international"):
        for row in ((brief.get(group_name) or {}).get("items") or []):
            if row.get("id") in selected_ids:
                indicator_rows.append(
                    {
                        "id": row.get("id"),
                        "value": row.get("value"),
                        "unit": row.get("unit"),
                        "delta": row.get("delta"),
                        "tone": row.get("tone"),
                        "as_of": row.get("as_of"),
                    }
                )
    yahoo_symbols = {"^VIX", "^KS11", "^KQ11", "^GSPC", "^IXIC", "KRW=X"}
    market_rows = [
        {
            "symbol": row.get("symbol"),
            "last": row.get("last"),
            "ret_1d": row.get("ret_1d"),
            "ret_1m": row.get("ret_1m"),
            "ret_1y": row.get("ret_1y"),
            "as_of": row.get("as_of"),
        }
        for row in ((macro.get("yahoo") or {}).get("indexes") or [])
        if row.get("symbol") in yahoo_symbols and not row.get("error")
    ]
    macro_context = {
        "overall": brief.get("overall"),
        "domestic_stance": (brief.get("domestic") or {}).get("stance"),
        "international_stance": (brief.get("international") or {}).get("stance"),
        "yield_comparison": brief.get("yield_comparison"),
        "indicators": indicator_rows,
        "market_indexes": market_rows,
        "yen_carry": macro.get("yencarry"),
        "margin_debt": macro.get("margin_debt"),
        "source_as_of": brief.get("as_of"),
    }
    evidence_count = sum(row.get("value") is not None for row in indicator_rows) + sum(row.get("last") is not None for row in market_rows)
    missing = []
    available_ids = {row.get("id") for row in indicator_rows if row.get("value") is not None}
    available_symbols = {row.get("symbol") for row in market_rows if row.get("last") is not None}
    for required in ("DGS10", "DGS2", "T10Y2Y", "DEXKOUS"):
        if required not in available_ids:
            missing.append(required)
    if "^VIX" not in available_symbols:
        missing.append("VIX")
    if evidence_count <= 0:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="시장 브리핑에 사용할 금리·환율·지수 관측값이 없습니다.",
            as_of=macro.get("fetched_at"),
            sources=["FRED", "BOK_ECOS", "Yahoo_comparison"],
            missing=missing or ["macro_indicators"],
            prompt_version=prompt_version,
        )

    prompt = (
        "당신은 글로벌 거시경제(Macro) 및 증시 리스크 전문 수석 이코노미스트입니다.\n"
        f"실제 거시·시장 관측 데이터:\n{json.dumps(macro_context, ensure_ascii=False, default=str)}\n\n"
        "금리·장단기 스프레드·환율·VIX·주가지수 중 실제 제공된 지표만 사용해 같은 방향과 충돌을 설명하세요. 누락 지표를 추정하거나 자산 배분·주문·비중을 지시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 매크로 헤드라인\", \"risk_posture\": \"위험선호 / 중립 / 위험회피 / 판단불가\", \"macro_insight\": \"지표별 방향과 상충 관계 2~3줄\", \"action_tip\": \"누락되거나 추가 확인할 지표\", \"drivers\": [{\"id\": \"실제 지표 id\", \"direction\": \"우호/부담/중립\", \"reason\": \"수치 근거\"}]}"
    )
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="market",
        prompt_version=prompt_version,
        evidence=macro_context,
        messages=[
            {"role": "system", "content": "You are a chief macro strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        as_of=macro.get("fetched_at"),
        sources=["FRED", "BOK_ECOS", "Yahoo_comparison"],
        evidence_count=evidence_count,
        missing=missing,
    )


@app.get("/api/toss/tier1-briefing")
def api_toss_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "toss_tier1_v2"

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

    evidence_count = len(gainers) + len(losers) + len(volume)
    if evidence_count <= 0:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="토스 랭킹 브리핑에 사용할 실시간 순위 데이터가 없습니다.",
            sources=["toss_rankings"],
            missing=["gainers", "losers", "trading_amount"],
            prompt_version=prompt_version,
        )

    prompt = (
        "당신은 실시간 증시 모멘텀 & 시장 수급 분석가입니다.\n"
        f"현재 토스증권 실시간 시장 랭킹:\n"
        f"- 급상승 상위: {', '.join(gainers) or '데이터 없음'}\n"
        f"- 급하락 상위: {', '.join(losers) or '데이터 없음'}\n"
        f"- 거래대금 쏠림: {', '.join(volume) or '데이터 없음'}\n\n"
        "제공된 순위에서 확인되는 단기 자금 쏠림과 급등락의 공통점을 설명하세요. 원인을 단정하거나 매수·매도·추격 여부를 지시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 시장 랭킹 헤드라인\", \"movers_summary\": \"급등락 및 거래대금 쏠림 2줄\", \"trading_tip\": \"자료 해석상 주의점\"}"
    )
    toss_context = {"gainers": gainers, "losers": losers, "trading_amount": volume}
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="toss",
        prompt_version=prompt_version,
        evidence=toss_context,
        messages=[
            {"role": "system", "content": "You are a real-time market momentum analyst. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["toss_rankings"],
        evidence_count=evidence_count,
    )


@app.get("/api/sector/tier1-briefing")
def api_sector_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "sector_tier1_v2"
    sector_data = api_sectors()
    sector_rows = (sector_data.get("rows") or [])[:8]
    if not sector_rows:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="업종 브리핑에 사용할 업종 순위 데이터가 없습니다.",
            as_of=sector_data.get("as_of_date"),
            sources=["sector_ranking"],
            missing=["sector_rows"],
            prompt_version=prompt_version,
        )

    sector_summary = "\n".join(
        f"- {row.get('rank')}위 {row.get('name')}: 종합 {row.get('score')}, RS {row.get('rs')}, "
        f"확산 {row.get('breadth')}, 실적확산 {row.get('earnings')}, 전회대비 {row.get('delta')}"
        for row in sector_rows
    )

    prompt = (
        "당신은 섹터 로테이션 및 업종 상대강도(RS) 전문 퀀트 분석가입니다.\n"
        f"실제 업종 순위 상위 데이터:\n{sector_summary}\n\n"
        "제공된 수치만 사용해 주도 업종, 개선 업종, 한 종목 쏠림 가능성을 설명하세요. 비중·매수·매도 지시는 하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 섹터 로테이션 헤드라인\", \"leading_sector_comment\": \"주도 업종 및 개선 업종 분석 2줄\", \"sector_strategy\": \"수치를 읽을 때의 주의점\"}"
    )
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="sector",
        prompt_version=prompt_version,
        evidence={"as_of": sector_data.get("as_of_date"), "rows": sector_rows},
        messages=[
            {"role": "system", "content": "You are a sector rotation quant strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        as_of=sector_data.get("as_of_date"),
        sources=["sector_ranking"],
        evidence_count=len(sector_rows),
    )


@app.get("/api/us13f/tier1-briefing")
def api_us13f_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "us13f_tier1_v2"

    # Load 13F context
    cache_path = s.root / "data" / "cache" / "us13f.json"
    top_new: list[str] = []
    top_common: list[str] = []
    top_exits: list[str] = []
    if cache_path.exists():
        try:
            cdata = json.loads(cache_path.read_text(encoding="utf-8"))
            top_new = [r.get("issuer_ko") or r.get("issuer") for r in (cdata.get("new") or [])[:5]]
            top_common = [r.get("issuer_ko") or r.get("issuer") for r in (cdata.get("common") or [])[:5]]
            top_exits = [r.get("issuer_ko") or r.get("issuer") for r in (cdata.get("exits") or [])[:5]]
        except Exception:
            pass

    evidence_count = len(top_new) + len(top_common) + len(top_exits)
    if evidence_count <= 0:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="13F 브리핑에 사용할 공시 집계 데이터가 없습니다.",
            sources=["sec_13f_cache"],
            missing=["new_positions", "common_holdings", "exits"],
            prompt_version=prompt_version,
        )

    ctx_str = (
        f"최근 13F 주요 신규편입: {', '.join(filter(None, top_new)) or '데이터 없음'}\n"
        f"대가 공통 집중보유: {', '.join(filter(None, top_common)) or '데이터 없음'}\n"
        f"전량청산: {', '.join(filter(None, top_exits)) or '데이터 없음'}"
    )

    prompt = (
        "당신은 글로벌 슈퍼인베스터(워런 버핏, 마이클 버리, 켄 그리핀, 론 바론 등) SEC 13F 포트폴리오 수석 전략가입니다.\n"
        f"{ctx_str}\n\n"
        "위 월가 대가들의 13F 공시 실전 데이터를 분석하여 한국 투자자들에게 명쾌한 투자 브리핑을 작성하세요.\n"
        "제공된 공시 집계에 존재하는 종목만 언급하고, 분기말 보유 정보라는 시차를 명시하세요. 매수·매도 지시는 하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 13F 포트폴리오 핵심 헤드라인\", \"consensus_insight\": \"공통 보유와 변화 분석 2~3줄\", \"action_tip\": \"13F 자료 해석상 한계\"}"
    )
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="us13f",
        prompt_version=prompt_version,
        evidence={"new": top_new, "common": top_common, "exits": top_exits},
        messages=[
            {"role": "system", "content": "You are a Wall Street 13F filing strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["sec_13f_cache"],
        evidence_count=evidence_count,
    )


@app.get("/api/seasonality/tier1-briefing")
def api_seasonality_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "seasonality_tier1_v2"
    highlights_payload = api_seasonality_highlights_get()
    highlights = highlights_payload.get("data") or {}
    current_rows = highlights.get("current_champions") or []
    upcoming_rows = highlights.get("upcoming_champions") or []
    active_presets = highlights.get("active_presets") or []
    evidence_count = len(current_rows) + len(upcoming_rows) + len(active_presets)
    if evidence_count <= 0:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="계절성 브리핑에 사용할 통계 표본이 없습니다.",
            sources=["seasonality_highlights"],
            missing=["current_champions", "upcoming_champions", "active_events"],
            prompt_version=prompt_version,
        )

    seasonality_summary = json.dumps(
        {
            "current_month": highlights.get("current_month"),
            "next_month": highlights.get("next_month"),
            "current_champions": current_rows,
            "upcoming_champions": upcoming_rows,
            "active_presets": active_presets,
        },
        ensure_ascii=False,
        default=str,
    )

    prompt = (
        "당신은 주식시장 계절성 통계 검증 연구원입니다.\n"
        f"실제 계절성 집계:\n{seasonality_summary}\n\n"
        "제공된 승률·평균수익률·연도 표본 수만 사용하고 표본 부족과 특정 연도 쏠림 가능성을 설명하세요. 선취매·매집·주문 지시는 하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 계절성 통계 헤드라인\", \"seasonality_brief\": \"당월 및 익월 통계 해설 2줄\", \"key_catalysts\": [\"실제 활성 이벤트\"], \"sample_caution\": \"표본과 재현성 주의점\"}"
    )
    seasonality_context = {
        "current_month": highlights.get("current_month"),
        "next_month": highlights.get("next_month"),
        "current_champions": current_rows,
        "upcoming_champions": upcoming_rows,
        "active_presets": active_presets,
    }
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="seasonality",
        prompt_version=prompt_version,
        evidence=seasonality_context,
        messages=[
            {"role": "system", "content": "You are a stock market seasonality quant specialist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["seasonality_highlights"],
        evidence_count=evidence_count,
    )


@app.get("/api/strategy/tier1-briefing")
def api_strategy_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "strategy_tier1_v2"

    # Load strategy cache context
    cache_path = s.root / "data" / "cache" / "strategy_lab.json"
    high_stocks: list[str] = []
    med_stocks: list[str] = []
    best_strats: list[str] = []
    rows: list[dict[str, Any]] = []
    avg_sharpe: float | None = None
    avg_mdd: float | None = None
    if cache_path.exists():
        try:
            sdata = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = sdata.get("rows") or []
            high_stocks = [r.get("company") for r in rows if r.get("stability_label") == "HIGH"]
            med_stocks = [r.get("company") for r in rows if r.get("stability_label") == "MEDIUM"]
            best_strats = list({r.get("best_name") for r in rows if r.get("best_name")})
            sharpes = [((r.get("strategies") or [{}])[0]).get("sharpe") for r in rows if ((r.get("strategies") or [{}])[0]).get("sharpe") is not None]
            if sharpes:
                avg_sharpe = round(sum(sharpes) / len(sharpes), 2)
            mdds = [((r.get("strategies") or [{}])[0]).get("max_drawdown") for r in rows if ((r.get("strategies") or [{}])[0]).get("max_drawdown") is not None]
            if mdds:
                avg_mdd = round((sum(mdds) / len(mdds)) * 100, 1)
        except Exception:
            pass

    ctx_str = (
        f"TOP20 백테스트 표본: 20개 우량주\n"
        f"최종/순환 검증 기준 충족(HIGH) 종목: {', '.join(filter(None, high_stocks)) or '없음'}\n"
        f"검증 구간 1위 전략 유형: {', '.join(filter(None, best_strats)) or '집계 결과 없음'}\n"
        f"전체기간 참고 평균 샤프: {avg_sharpe if avg_sharpe is not None else '집계 없음'}, "
        f"평균 최대낙폭: {f'{avg_mdd}%' if avg_mdd is not None else '집계 없음'}\n"
        "체결 가정: 신호 다음 거래일 시가, 설정된 수수료와 슬리피지 반영"
    )

    prompt = (
        "당신은 퀀트 기술적 매매 타이밍(RSI 과매도, 볼린저밴드 하단 반등, 이평선 골든크로스, 돈치안 채널 돌파) 및 Walk-Forward 과적합 방지 수석 연구원입니다.\n"
        f"{ctx_str}\n\n"
        "위 데이터에 실제로 포함된 내용만 사용해 학습·검증·최종검증의 차이와 표본 한계를 설명하세요. 종목 추천, 주문, 비중, 목표가를 제시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 백테스트 핵심\", \"strategy_insight\": \"검증 결과와 최종검증 일관성 분석 2~3줄\", \"action_guide\": \"HIGH/MED/LOW 등급을 읽는 방법\", \"risk_management\": \"표본·비용·최대낙폭 관련 한계\"}"
    )
    strategy_context = {
        "rows": rows,
        "high_stocks": high_stocks,
        "medium_stocks": med_stocks,
        "best_strategies": best_strats,
        "average_sharpe": avg_sharpe,
        "average_mdd": avg_mdd,
    }
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="strategy",
        prompt_version=prompt_version,
        evidence=strategy_context,
        messages=[
            {"role": "system", "content": "You are a quantitative trading strategy auditor. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["strategy_lab_cache"],
        evidence_count=len(rows),
        missing=[] if rows else ["strategy_rows"],
    )
    if result.get("status") == "UNAVAILABLE":
        return tier1_deterministic_fallback(
            endpoint,
            {
                "headline": "전략별 검증 구간과 최종검증 결과를 분리해 확인하세요",
                "strategy_insight": (
                    f"현재 HIGH 기준 충족 종목은 {len(high_stocks)}개입니다. "
                    f"전체기간 참고 평균 샤프는 {avg_sharpe if avg_sharpe is not None else '집계 없음'}, "
                    f"평균 최대낙폭은 {f'{avg_mdd}%' if avg_mdd is not None else '집계 없음'}이며 "
                    "개별 검증 거래 수를 함께 확인해야 합니다."
                ),
                "action_guide": "HIGH는 설정 기준 충족, MEDIUM은 구간 편차, LOW는 표본 부족 또는 검증 불일치를 뜻하며 매수·매도 지시가 아닙니다.",
                "risk_management": "수수료·슬리피지 가정, 적은 거래 수, 시장 구조 변화 때문에 과거 결과가 재현되지 않을 수 있습니다.",
            },
            sources=["strategy_lab_cache"],
            evidence_count=len(rows),
            missing=[] if rows else ["strategy_rows"],
            prompt_version=prompt_version,
        )
    return result


@app.get("/api/trade/tier1-briefing")
def api_trade_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.flow.scan import load_flow

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "trade_tier1_v3"

    flow_data = load_flow(s, days=5)
    rows = flow_data.get("trading") or flow_data.get("rows") or []
    evidence = []
    for row in rows[:8]:
        ta = row.get("ta") if isinstance(row.get("ta"), dict) else {}
        evidence.append({
            "ticker": row.get("ticker"),
            "company": row.get("company"),
            "flow_from": row.get("from"),
            "flow_to": row.get("to"),
            "last": row.get("last"),
            "change_rate": row.get("change_rate"),
            "foreign_net": row.get("foreign_net"),
            "institution_net": row.get("institution_net"),
            "pe_net": row.get("pe_net"),
            "setup_notional_krw": max(float(row.get("dual_krw") or 0), float(row.get("pe_krw") or 0), float(row.get("empty_krw") or 0)),
            "setups": row.get("setups") or [],
            "stoch_k": ta.get("stoch_k"),
            "stoch_d": ta.get("stoch_d"),
            "ichimoku_signal": ta.get("ichimoku_signal") or ta.get("signal"),
            "ret_5d": row.get("ret_5d"),
            "ret_5d_status": (row.get("ret_5d_meta") or {}).get("status") if isinstance(row.get("ret_5d_meta"), dict) else None,
        })
    if not evidence:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="트레이딩 랩 설명에 사용할 수급 후보가 없습니다.",
            sources=["flow_scan_5d"],
            missing=["trade_candidates"],
            prompt_version=prompt_version,
        )

    evidence_json = json.dumps(evidence, ensure_ascii=False, default=str)
    prompt = (
        "당신은 실전 데이트레이딩 및 3~5일 단기 스윙 전략 헤드 트레이더입니다.\n"
        f"현재 단기 트레이딩 랩 실제 근거:\n{evidence_json}\n"
        "수급 주수, 추정금액, 스토캐스틱, 일목 신호 중 제공된 값만 설명하세요. ret_5d_status가 COMPLETE가 아니면 성과로 인용하지 마세요. "
        "확인되지 않은 지지선·반등·수익률·원인을 만들지 말고 주문·목표가·손절가를 제시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 트레이딩 랩 헤드라인\", \"trading_brief\": \"단기 수급/기술 지표 해설 2줄\", \"execution_guide\": \"해석상 무효화 조건과 주의점\"}"
    )
    fallback_payload = {
        "headline": f"실제 수급·기술 근거가 연결된 단기 후보 {len(evidence)}종목",
        "trading_brief": " · ".join(
            f"{row.get('company') or row.get('ticker')}: 외인 {float(row.get('foreign_net') or 0):+,.0f}주, 기관 {float(row.get('institution_net') or 0):+,.0f}주, 스토K {row.get('stoch_k') if row.get('stoch_k') is not None else '미연결'}"
            for row in evidence[:3]
        ),
        "execution_guide": "D+5 관측이 끝난 성과만 검증값으로 읽고, 기술 지표·가격선이 누락된 종목에는 방향성을 부여하지 않습니다.",
    }
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="trade",
        prompt_version=prompt_version,
        evidence=evidence,
        messages=[
            {"role": "system", "content": "You are a professional quantitative swing trading strategist. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["flow_scan_5d"],
        as_of=str(flow_data.get("fetched_at") or "") or None,
        evidence_count=len(evidence),
    )
    if result.get("ok"):
        return result
    return tier1_deterministic_fallback(
        endpoint,
        fallback_payload,
        sources=["flow_scan_5d"],
        as_of=str(flow_data.get("fetched_at") or "") or None,
        evidence_count=len(evidence),
        prompt_version=prompt_version,
    )


def _empty_tier1_fallback_payload(comeback_rows: list[dict], empty_rows: list[dict]) -> dict[str, Any]:
    c_names = [str(r.get("company", "")) for r in comeback_rows[:3] if r.get("company")]
    e_names = [str(r.get("company", "")) for r in empty_rows[:3] if r.get("company")]
    
    if c_names and e_names:
        headline = f"외인·기관 수급 턴어라운드({', '.join(c_names[:2])}) 및 수급 공백 빈집({', '.join(e_names[:2])}) 포착"
        insight = f"외인·기관 매도세가 진정되고 순매수 재유입이 관찰되는 턴어라운드 후보와, 동반 순매도로 물량이 비워진 빈집 종목의 수급 변곡점을 분석합니다."
    elif c_names:
        headline = f"외인·기관 수급 재유입 턴어라운드 후보 {len(comeback_rows)}종목 관찰"
        insight = f"이탈했던 메이저 수급이 최근 5거래일 기준 순매수로 전환되기 시작한 {', '.join(c_names)} 등의 거래대금 연속성을 확인합니다."
    elif e_names:
        headline = f"외인·기관 동반 순매도 수급 공백 종목 {len(empty_rows)}개 탐색"
        insight = f"수급 이탈로 주가가 눌려있는 {', '.join(e_names)} 종목의 하방 지지력 및 매도세 진정 국면을 관찰합니다."
    else:
        headline = "최근 5거래일 메이저 수급 이탈 및 복귀 스캔 완료"
        insight = "외인·기관의 순매매 추이를 집계하여 수급 공백 및 턴어라운드 후보군을 추출했습니다."

    caution = "수급 전환 초기 종목은 호가 공백과 거래대금 변동성이 크므로 1회성 진입보다 분할 관찰이 안전합니다."
    return {
        "headline": headline,
        "empty_insight": insight,
        "entry_caution": caution,
    }


@app.get("/api/empty/tier1-briefing")
def api_empty_tier1_briefing_get() -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.flow.scan import load_flow

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "empty_tier1_v2"

    flow_data = load_flow(s, days=5)
    empty_rows = flow_data.get("empty") or []
    comeback_rows = flow_data.get("comeback") or []
    
    comebacks = [f"{r.get('company')}({r.get('ticker')})" for r in comeback_rows[:4] if r.get("company")]
    empties = [f"{r.get('company')}({r.get('ticker')})" for r in empty_rows[:4] if r.get("company")]
    evidence_count = len(comebacks) + len(empties)
    if evidence_count <= 0:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="빈집 분석에 사용할 수급 후보가 없습니다.",
            sources=["flow_scan_5d"],
            missing=["empty_candidates", "comeback_candidates"],
            prompt_version=prompt_version,
        )

    fallback_payload = _empty_tier1_fallback_payload(comeback_rows, empty_rows)
    prompt = (
        "당신은 기관 소외주 및 턴어라운드 빈집 발굴 전문 펀드매니저입니다.\n"
        f"현재 포착된 수급 복귀(턴어라운드) 종목: {', '.join(comebacks) or '데이터 집계 중'}\n"
        f"현재 외인·기관 쌍매도 빈집 종목: {', '.join(empties) or '데이터 집계 중'}\n\n"
        "제공된 수급 분류가 뜻하는 바와 유동성·거래 가능성 확인 필요성을 설명하세요. 선취매·매집·주문 지시는 하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"headline\": \"한 줄 빈집 발굴 헤드라인\", \"empty_insight\": \"수급 공백과 복귀 후보 해설 2줄\", \"entry_caution\": \"유동성·거래가능성·데이터 한계\"}"
    )
    result = tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace="empty",
        prompt_version=prompt_version,
        evidence={"empty": empty_rows[:4], "comeback": comeback_rows[:4]},
        messages=[
            {"role": "system", "content": "You are a turnaround and unowned stock quant analyst. Output strictly in JSON."},
            {"role": "user", "content": prompt},
        ],
        sources=["flow_scan_5d"],
        evidence_count=evidence_count,
    )
    if result.get("ok"):
        return result
    return tier1_deterministic_fallback(
        endpoint,
        fallback_payload,
        sources=["flow_scan_5d"],
        evidence_count=evidence_count,
        prompt_version=prompt_version,
    )


class CustomBacktestAiIn(BaseModel):
    ticker: str
    company: str | None = None
    strategy_name: str
    cagr: float | None = None
    mdd: float | None = None
    sharpe: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    total_return: float | None = None
    trades_count: int | None = None
    validation_return: float | None = None
    validation_trades: int | None = None
    oos_return: float | None = None
    oos_sharpe: float | None = None
    oos_trades: int | None = None
    stability_label: str | None = None


@app.post("/api/strategy/custom-ai-diagnosis")
def api_strategy_custom_ai_diagnosis_post(body: CustomBacktestAiIn) -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "custom_backtest_diagnosis_v2"
    evidence_count = sum(
        value is not None
        for value in (
            body.total_return,
            body.trades_count,
            body.validation_return,
            body.validation_trades,
            body.oos_return,
            body.oos_sharpe,
            body.oos_trades,
        )
    )

    cagr_str = f"{body.cagr*100:+.2f}%" if body.cagr is not None else "—"
    ret_str = f"{body.total_return*100:+.2f}%" if body.total_return is not None else "—"
    mdd_str = f"{body.mdd*100:.2f}%" if body.mdd is not None else "—"
    wr_str = f"{body.win_rate*100:.1f}%" if body.win_rate is not None else "—"
    pf_str = f"{body.profit_factor:.2f}" if body.profit_factor is not None else "—"
    sh_str = f"{body.sharpe:.2f}" if body.sharpe is not None else "—"
    validation_str = f"{body.validation_return*100:+.2f}%" if body.validation_return is not None else "—"
    oos_str = f"{body.oos_return*100:+.2f}%" if body.oos_return is not None else "—"
    oos_sharpe_str = f"{body.oos_sharpe:.2f}" if body.oos_sharpe is not None else "—"

    prompt = (
        "당신은 퀀트 기술적 전략 백테스트 검증 수석 연구원입니다.\n"
        f"종목: {body.company or body.ticker} ({body.ticker})\n"
        f"테스트 전략: {body.strategy_name}\n"
        f"백테스트 성과 지표:\n"
        f"- 총수익률: {ret_str}\n"
        f"- 연환산 수익률(CAGR): {cagr_str}\n"
        f"- 최대 낙폭(MDD): {mdd_str}\n"
        f"- 승률(Win Rate): {wr_str}\n"
        f"- 손익비(Profit Factor): {pf_str}\n"
        f"- 샤프 지수: {sh_str}\n"
        f"- 총 매매 횟수: {body.trades_count or 0}회\n\n"
        f"- 가운데 검증: {validation_str}, {body.validation_trades or 0}회\n"
        f"- 선택에 쓰지 않은 최종검증: {oos_str}, 샤프 {oos_sharpe_str}, {body.oos_trades or 0}회\n"
        f"- 안정성 등급: {body.stability_label or '—'}\n\n"
        "이 지표에서 확인되는 일관성·표본 부족·과적합 가능성을 설명하세요. 종목 추천, 주문, 목표가, 비중을 제시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"verdict\": \"근거 충분 / 제한적 / 표본 부족 / 구간 불일치\", \"diagnosis\": \"검증과 최종검증 비교 2줄\", \"tuning_tip\": \"추가 검증 또는 파라미터 개선점\", \"execution_risk\": \"해석상 한계와 비용 가정\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": "You are a quantitative trading strategy auditor. Output strictly in JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return tier1_success(
            endpoint,
            _extract_json(raw_text),
            sources=["custom_strategy_backtest"],
            evidence_count=evidence_count,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        print(f"Tier 1 custom backtest diagnosis fallback used: {exc}")
        enough_samples = (body.validation_trades or 0) >= 5 and (body.oos_trades or 0) >= 5
        same_direction = (body.validation_return or 0) * (body.oos_return or 0) > 0
        verdict = "근거 충분" if enough_samples and same_direction else "표본 부족" if not enough_samples else "구간 불일치"
        return tier1_deterministic_fallback(
            endpoint,
            {
                "verdict": verdict,
                "diagnosis": f"{body.strategy_name}의 검증 수익률은 {validation_str}, 최종검증 수익률은 {oos_str}이며 최종검증 거래는 {body.oos_trades or 0}회입니다.",
                "tuning_tip": "파라미터 수를 늘리기보다 더 긴 기간과 여러 시장 국면에서 같은 방향이 유지되는지 먼저 확인하세요.",
                "execution_risk": "적은 거래 수, 갭 체결, 수수료·슬리피지 변화로 결과가 크게 달라질 수 있으며 이 결과는 주문 신호가 아닙니다.",
            },
            sources=["custom_strategy_backtest"],
            evidence_count=evidence_count,
            prompt_version=prompt_version,
        )


@app.get("/api/results/quality")
def api_quality() -> dict[str, Any]:
    return _quality(load_settings())


def _load_stock_row(ticker: str, as_of: str | None = None) -> tuple[dict[str, Any], str]:
    s = load_settings()
    path = _resolve_rank_output(s, "all_stocks.parquet", "latest_all_stocks.parquet", as_of=as_of)
    if path is None:
        raise HTTPException(404, "결과 파일이 없습니다.")
    df = pd.read_parquet(path)
    code = str(ticker).zfill(6)
    hit = df[df["ticker"].astype(str).str.zfill(6) == code]
    if hit.empty:
        raise HTTPException(404, f"{code} 없음")
    day = _rank_source_as_of(df, path) or as_of or ""
    return _clean(hit.iloc[0].to_dict()), day


@app.get("/api/macro")
def api_macro(refresh: bool = False) -> dict[str, Any]:
    from kr_quant.context.macro_brief import build_macro_dashboard

    return build_macro_dashboard(load_settings(), refresh=refresh)


@app.get("/api/macro/live-ticker")
def api_macro_live_ticker(refresh: bool = False) -> dict[str, Any]:
    from kr_quant.ingest.yahoo import live_ticker_snapshot

    return live_ticker_snapshot(refresh=refresh)


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


class SunziTacticalAiIn(BaseModel):
    ticker: str
    company: str | None = None
    quant_score: float | None = None
    sector: str | None = None
    posture: str | None = None
    dao_score: float | None = None
    tian_score: float | None = None
    di_score: float | None = None
    jiang_score: float | None = None
    fa_pass: bool | None = None
    persona: str = "yang"


@app.get("/api/sunzi/tier1-briefing")
def api_sunzi_tier1_briefing_get(persona: str = "yang") -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "sunzi_briefing_v2"
    board = api_sunzi(n=8)
    board_rows = board.get("rows") or []
    if not board_rows:
        return tier1_unavailable(
            endpoint,
            code="TIER1_EVIDENCE_MISSING",
            message="은하퀀트전설 브리핑에 사용할 종목 판정 데이터가 없습니다.",
            sources=["sunzi_five_board"],
            missing=["sunzi_rows"],
            prompt_version=prompt_version,
        )
    board_context = json.dumps(
        {
            "candidate_count": board.get("n"),
            "fa_pass_count": board.get("fa_pass_n"),
            "market": board.get("tian"),
            "postures": board.get("postures"),
            "aspects": board.get("aspects"),
            "top_rows": board_rows[:8],
        },
        ensure_ascii=False,
        default=str,
    )

    persona_prompts = {
        "yang": (
            "당신은 《은하영웅전설》의 자유행성동맹 불패의 지략가 '양 웬리' 제독입니다.\n"
            "[말투 및 성격 절대 규칙]\n"
            "- 말투: 나긋나긋한 1인칭 구어체(~하네, ~이지, ~라고 봐, ~인 셈이야, ~겠지)로 말하세요.\n"
            "- 내용: 지독한 현실주의자이자 역사학도. 영웅적 돌격을 극도로 혐오하며, 보급선과 잉여현금(FCF), 안전마진을 최우선시합니다. 홍차에 브랜디 한 잔 타 마시며 지켜보는 여유를 보입니다.\n"
            "현재 증시 전황을 바탕으로 퀀트 투자자들에게 참모 당직 전술 브리핑을 해주세요.\n"
            "반드시 JSON 형식으로만 반환하세요: {\"commander\": \"양 웬리 제독\", \"title\": \"제13함대 당직 참모 브리핑\", \"headline\": \"한 줄 전황 요약\", \"briefing\": \"홍차 관망 및 전장 진단 2줄\", \"tactical_order\": \"오늘의 행동 지침\"}"
        ),
        "reinhard": (
            "당신은 《은하영웅전설》의 은하제국 황제 '라인하르트 폰 로엔그람'입니다.\n"
            "[말투 및 성격 절대 규칙]\n"
            "- 말투: 타오르는 패기와 위엄 넘치는 군주 어조(~하라, ~하겠다, ~이다, ~할 뿐이다, 전 함대 돌격하라!)로 말하세요.\n"
            "- 내용: 우유부단한 관망을 경멸하며, 압도적인 주도력과 성장 모멘텀, 신고가 주도주 정면 돌파를 명령합니다. 천재적 기동전으로 시장을 단숨에 장악하고자 합니다.\n"
            "현재 시장 주도 섹터와 상승 모멘텀을 바탕으로 전 함대 돌격 칙령을 내려주세요.\n"
            "반드시 JSON 형식으로만 반환하세요: {\"commander\": \"라인하르트 폰 로엔그람 황제\", \"title\": \"은하제국 황제 친정군 칙령\", \"headline\": \"한 줄 패도적 헤드라인\", \"briefing\": \"주도 섹터 장악 진단 2줄\", \"tactical_order\": \"제국 함대 출진 명령\"}"
        ),
        "oberstein": (
            "당신은 《은하영웅전설》의 은하제국 군무상서 '파울 폰 오베르슈타인'입니다.\n"
            "[말투 및 성격 절대 규칙]\n"
            "- 말투: 극도로 건조하고 서늘한 격식체(~입니다, ~하십시오, ~해야 합니다, 감정은 자본의 독입니다)로 말하세요.\n"
            "- 내용: 감상적 희망과 주관적 기대를 배제하고, 데이터 신뢰도와 팩터 감점, 판단 무효화 조건을 강조합니다.\n"
            "제공된 시스템 판정의 리스크 요인과 팩터 감점 근거를 냉정하게 브리핑해 주세요.\n"
            "반드시 JSON 형식으로만 반환하세요: {\"commander\": \"파울 폰 오베르슈타인 군무상서\", \"title\": \"군무상서 기밀 리스크 사정서\", \"headline\": \"한 줄 리스크 통제 헤드라인\", \"briefing\": \"수치와 기대치 기반 냉철 진단 2줄\", \"tactical_order\": \"리스크 도려내기 지침\"}"
        ),
        "julian": (
            "당신은 《은하영웅전설》의 성실하고 총명한 후계자 '율리안 민츠'입니다.\n"
            "[말투 및 성격 절대 규칙]\n"
            "- 말투: 예의 바르고 열정적인 청년 참모 어조(~합니다!, ~인 것 같습니다!, ~하겠습니다!)로 말하세요.\n"
            "- 내용: 양 웬리 제독님의 가르침을 깊이 새기며 제공된 5대 팩터와 수급 데이터를 꼼꼼하게 교차 검증합니다.\n"
            "현재 제공된 5대 팩터와 수급 판정을 정리하여 추가 확인이 필요한 항목을 브리핑해 주세요.\n"
            "반드시 JSON 형식으로만 반환하세요: {\"commander\": \"율리안 민츠 참모\", \"title\": \"후계자 율리안의 퀀트 정석 보고서\", \"headline\": \"한 줄 정석 헤드라인\", \"briefing\": \"데이터 교차 검증 2줄\", \"tactical_order\": \"추가 확인 지침\"}"
        ),
    }

    selected_prompt = (
        persona_prompts.get(persona, persona_prompts["yang"])
        + f"\n\n[실제 시스템 판정]\n{board_context}\n"
        + "제공된 시스템 판정에 없는 시장 사실이나 수치를 만들지 마세요. 캐릭터 말투는 표현에만 사용하고 주문·비중·목표가·손절가를 지시하지 마세요."
    )
    board_evidence = {
        "persona": persona,
        "candidate_count": board.get("n"),
        "fa_pass_count": board.get("fa_pass_n"),
        "market": board.get("tian"),
        "postures": board.get("postures"),
        "aspects": board.get("aspects"),
        "top_rows": board_rows[:8],
    }
    return tier1_cached_chat_json(
        s.root,
        endpoint,
        namespace=f"sunzi-{persona}",
        prompt_version=prompt_version,
        evidence=board_evidence,
        messages=[
            {
                "role": "system",
                "content": "You are a character from Legend of Galactic Heroes. Adhere strictly to the requested Korean speech style and persona. Output strictly in JSON.",
            },
            {"role": "user", "content": selected_prompt},
        ],
        sources=["sunzi_five_board"],
        evidence_count=len(board_rows),
        payload_prefix={"persona": persona},
    )


@app.post("/api/sunzi/tactical-ai")
def api_sunzi_tactical_ai_post(body: SunziTacticalAiIn) -> dict[str, Any]:
    from kr_quant.research.providers import resolve_tier1_endpoint
    from kr_quant.research.analyze import call_chat, _extract_json

    s = load_settings()
    endpoint = resolve_tier1_endpoint(s)
    prompt_version = "sunzi_tactical_v2"
    evidence_count = sum(
        value is not None
        for value in (
            body.quant_score,
            body.posture,
            body.dao_score,
            body.tian_score,
            body.di_score,
            body.jiang_score,
            body.fa_pass,
        )
    )

    persona_sys_rules = {
        "yang": (
            "You are Fleet Admiral Yang Wen-li (양 웬리 제독) from Legend of Galactic Heroes.\n"
            "MANDATORY KOREAN TONE RULES:\n"
            "- Speak in Korean using authentic 1st-person easygoing/cynical spoken tone (~하네, ~이지, ~라고 봐, ~인 셈이야, ~겠지).\n"
            "- Tone: Anti-heroic, values free cash flow (잉여현금), supply line (보급선), margin of safety (안전마진), likes tea with brandy (홍차와 브랜디). Hates reckless attacks."
        ),
        "reinhard": (
            "You are Emperor Reinhard von Lohengramm (라인하르트 폰 로엔그람 황제) from Legend of Galactic Heroes.\n"
            "MANDATORY KOREAN TONE RULES:\n"
            "- Speak in Korean using proud, majestic imperial commanding tone (~하라, ~하겠다, ~이다, ~할 뿐이다, 전 함대 돌격하라!).\n"
            "- Tone: Heroic, aggressive momentum breakthrough, concentrates capital on market leaders, despises cowardice and indecisiveness."
        ),
        "oberstein": (
            "You are Minister of Military Affairs Paul von Oberstein (파울 폰 오베르슈타인 군무상서) from Legend of Galactic Heroes.\n"
            "MANDATORY KOREAN TONE RULES:\n"
            "- Speak in Korean using chillingly cold, emotionless, formal honorifics (~입니다, ~하십시오, ~해야 합니다).\n"
            "- Tone: '감정은 자본을 갉아먹는 독입니다', strictly mathematical expectation, ruthless cut of penalty stocks, strict -3% stop-loss."
        ),
        "julian": (
            "You are Julian Mintz (율리안 민츠 참모) from Legend of Galactic Heroes.\n"
            "MANDATORY KOREAN TONE RULES:\n"
            "- Speak in Korean using polite, energetic, disciplined young researcher tone (~합니다!, ~인 것 같습니다!, ~하겠습니다!).\n"
            "- Tone: Follows Admiral Yang's principles, cross-validates 5 factors & financial statements diligently, textbook split accumulation."
        ),
    }

    selected_sys = persona_sys_rules.get(body.persona, persona_sys_rules["yang"])

    prompt = (
        f"분석 대상 종목: {body.company or body.ticker} ({body.ticker})\n"
        f"- 업종: {body.sector or '미분류'}\n"
        f"- 퀀트 종합점수: {body.quant_score or 50.0}점\n"
        f"- 5사 판정: 道(장부)={body.dao_score or 50}점, 天(시장)={body.tian_score or 50}점, 地(지형)={body.di_score or 50}점, 將(장수)={body.jiang_score or 50}점, 法(규율)={'통과' if body.fa_pass else '미달'}\n"
        f"- 작전 태세: {body.posture or 'WAIT'}\n\n"
        f"위 종목의 시스템 판정을 당신의 고유한 말투로 해설해 주세요. 제공되지 않은 재무·수급·가격 사실을 만들지 마세요. 주문·비중·목표가·손절가를 지시하지 마세요.\n"
        "반드시 JSON 형식으로만 반환하세요: {\"strategy_tag\": \"4자 사자성어 연구 태그\", \"tactical_briefing\": \"제공된 점수와 태세 해설 2줄\", \"maneuver_entry\": \"추가 확인할 조건\", \"escape_route\": \"현재 판단을 무효화할 위험\", \"one_line_verdict\": \"연구 우선순위 한 줄\"}"
    )
    try:
        raw_text, _ = call_chat(
            endpoint,
            [{"role": "system", "content": f"{selected_sys}\nOutput strictly valid JSON."},
             {"role": "user", "content": prompt}],
            timeout=15,
            json_mode=True,
        )
        return tier1_success(
            endpoint,
            {"persona": body.persona, **_extract_json(raw_text)},
            sources=["sunzi_tactical_input"],
            evidence_count=evidence_count,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        print(f"Tier 1 sunzi tactical analysis unavailable: {exc}")
        return tier1_unavailable(
            endpoint,
            sources=["sunzi_tactical_input"],
            evidence_count=evidence_count,
            prompt_version=prompt_version,
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
    from kr_quant.strategy.event_explainer import repeated_generic_catalysts
    from kr_quant.strategy.seasonality import scan_seasonality_discovery, seasonality_universe_stats

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
    stats = seasonality_universe_stats(s)
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "lookback_years": lookback_years,
        "count": len(rows),
        "rows": rows,
        "explanation_quality": repeated_generic_catalysts(rows),
        "data_context": stats["data_context"],
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
    from kr_quant.strategy.seasonality import rank_institutional_events, seasonality_universe_stats

    s = load_settings()
    rows = rank_institutional_events(
        s,
        horizon_days=horizon_days,
        min_grade=min_grade,
        group_id=group_id,
        confirmation_filter=confirmation,
        query=query,
    )
    stats = seasonality_universe_stats(s)
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "count": len(rows),
        "rows": rows,
        "data_context": stats["data_context"],
    }


@app.get("/api/seasonality/events")
def api_seasonality_events_get(horizon_days: int = 180) -> dict[str, Any]:
    from kr_quant.strategy.event_calendar import get_upcoming_events
    from kr_quant.strategy.seasonality import seasonality_universe_stats

    s = load_settings()
    events = get_upcoming_events(horizon_days=horizon_days)
    stats = seasonality_universe_stats(s)
    return {"ok": True, "horizon_days": horizon_days, "count": len(events), "events": events, "data_context": stats["data_context"]}


@app.get("/api/seasonality/themes")
def api_seasonality_themes_get(horizon_days: int = 90, lookback_years: int = 5) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import EVENT_PRESETS, scan_seasonality, seasonality_universe_stats
    from kr_quant.strategy.theme_engine import calculate_theme_seasonality

    s = load_settings()
    event_rows_by_preset = {
        preset_key: scan_seasonality(s, preset=preset_key)
        for preset_key in EVENT_PRESETS
    }
    themes = calculate_theme_seasonality([], event_rows_by_preset=event_rows_by_preset)
    stats = seasonality_universe_stats(s)
    return {
        "ok": True,
        "horizon_days": horizon_days,
        "lookback_years": lookback_years,
        "theme_count": len(themes),
        "theme_source": "seasonality_event_presets",
        "pre_entry_overlap_source": "seasonality_discovery_client",
        "themes": themes,
        "data_context": stats["data_context"],
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
    active_preset = EVENT_PRESETS.get(str(preset or ""))

    rows = scan_seasonality(
        s,
        target_month=month,
        min_win_rate=min_win_rate,
        min_avg_return=min_avg_return,
        preset=preset,
        query=query,
    )
    stats = seasonality_universe_stats(s)
    resolved_month = int(active_preset.get("analysis_month")) if active_preset else (month or pd.Timestamp.now().month)
    return {
        "ok": True,
        "filter_mode": "event" if active_preset else "month",
        "target_month": resolved_month,
        "requested_month": month,
        "active_preset_key": str(preset or "") if active_preset else None,
        "active_preset": active_preset,
        "event_mapped_count": len(active_preset.get("tickers", [])) if active_preset else None,
        "generic_thresholds_applied": active_preset is None,
        "count": len(rows),
        "presets": EVENT_PRESETS,
        "rows": rows,
        "universe_scanned": stats["universe_scanned"],
        "universe_listed": stats["universe_listed"],
        "markets": stats["markets"],
        "data_context": stats["data_context"],
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


DEFAULT_MOMENTUM_PORTFOLIO = [
    {
        "id": "stock-161580",
        "name": "필옵틱스",
        "code": "161580",
        "entry_date": "2026-08-27",
        "peak_date": "2026-09-10",
        "entry_price": 25400,
        "target_price": 31500,
        "catalyst": "9월 글로벌 SEMICON / IMID 학회 및 글래스 기판 레이저 장비 수주 모멘텀",
        "notes": "과거 학회 개막 3~5일 전 고점 형성. D-3(9/7)부터 50% 분할 익절, D-Day 전량 엑시트.",
        "exited": False,
        "trajectory_match": 89,
        "history_curve": [0, 1.2, 2.8, 4.5, 6.2, 8.8, 11.5, 14.8, 18.2, 22.0, 24.5, 23.0, 20.5, 17.0],
        "actual_curve": [0, 1.8],
    },
    {
        "id": "stock-204270",
        "name": "제이앤티씨",
        "code": "204270",
        "entry_date": "2026-08-27",
        "peak_date": "2026-09-12",
        "entry_price": 18200,
        "target_price": 22800,
        "catalyst": "9월 글로벌 스마트폰 신작(아이폰) 공개 전 커버글라스 / 기판 부품 공급 랠리",
        "notes": "신제품 공개 키노트 당일 '재료 소멸' 하락 주의. D-2 전량 엑시트 권장.",
        "exited": False,
        "trajectory_match": 92,
        "history_curve": [0, 0.9, 2.2, 3.8, 5.5, 7.8, 10.5, 13.6, 17.2, 21.0, 25.1, 23.5, 19.8, 15.2],
        "actual_curve": [0, 2.4],
    },
    {
        "id": "stock-178320",
        "name": "서진시스템",
        "code": "178320",
        "entry_date": "2026-08-27",
        "peak_date": "2026-09-28",
        "entry_price": 28500,
        "target_price": 35000,
        "catalyst": "하반기 글로벌 ESS 대형 수주 및 3Q 실적 턴어라운드 기관 선반영 랠리",
        "notes": "수주 공시 및 기관 매수세 유입 확인 시 분기말 목표일까지 추세 홀딩.",
        "exited": False,
        "trajectory_match": 84,
        "history_curve": [0, 0.6, 1.4, 2.5, 3.8, 5.4, 7.2, 9.5, 12.2, 15.5, 19.0, 23.2, 26.5, 25.0, 22.0],
        "actual_curve": [0, 0.8],
    },
    {
        "id": "stock-347850",
        "name": "디앤디파마텍",
        "code": "347850",
        "entry_date": "2026-08-27",
        "peak_date": "2026-10-05",
        "entry_price": 43200,
        "target_price": 56000,
        "catalyst": "9~10월 유럽당뇨학회(EASD) / 비만학회(ObesityWeek) 파이프라인 임상 모멘텀",
        "notes": "학회 초록(Abstract) 공개 시점 단기 급등 시 1차 50% 분할 익절.",
        "exited": False,
        "trajectory_match": 86,
        "history_curve": [0, 1.8, 3.9, 6.2, 8.8, 12.0, 15.8, 20.2, 25.5, 31.0, 35.8, 38.0, 34.2, 29.5],
        "actual_curve": [0, 3.2],
    }
]


@app.get("/api/seasonality/momentum-portfolio")
def api_seasonality_momentum_portfolio_get() -> dict[str, Any]:
    s = load_settings()
    file_path = s.root / "data" / "calendar_momentum_portfolio.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return {"ok": True, "items": data}
        except Exception:
            pass
    return {"ok": True, "items": DEFAULT_MOMENTUM_PORTFOLIO}


@app.post("/api/seasonality/momentum-portfolio")
def api_seasonality_momentum_portfolio_post(body: dict[str, Any]) -> dict[str, Any]:
    s = load_settings()
    items = body.get("items", [])
    file_path = s.root / "data" / "calendar_momentum_portfolio.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return {"ok": True, "saved_count": len(items)}


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
        try:
            df = pd.read_parquet(path, columns=["ticker", "company"])
        except Exception:
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
        if body.kind == "smart-sync":
            return RUNNER.start(
                "smart-sync",
                lambda: job_smart_sync(
                    body.as_of,
                    body.lookback_days or 80,
                    body.max_corps or 400,
                    body.dart_batch_size or 50,
                ),
            )
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
        if body.kind == "dart-backfill":
            return RUNNER.start(
                "dart-backfill",
                lambda: job_dart_backfill(body.as_of, body.max_corps or 50),
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


@app.post("/api/jobs/cancel")
def api_job_cancel() -> dict[str, Any]:
    return RUNNER.request_cancel()


@app.get("/api/jobs/history")
def api_job_history() -> dict[str, Any]:
    return job_history_summary()


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
def api_deploy_run(request: Request, force: bool = False, code_only: bool = False) -> dict[str, Any]:
    if public_share_mode(request):
        raise HTTPException(403, "공개 웹에서는 수동 배포를 실행할 수 없습니다.")
    from kr_quant.web.publish import start_manual_deploy

    return start_manual_deploy(allow_warnings=force, code_only=code_only)


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
