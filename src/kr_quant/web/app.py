from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kr_quant.settings import load_settings
from kr_quant.web.envfile import apply_env_to_process, mask_secret, upsert_env_file
from kr_quant.web.jobs import RUNNER, job_demo, job_krx_history, job_krx_prices, job_live, job_screen

STATIC_DIR = Path(__file__).resolve().parent / "static"

def _grok_auth_public() -> dict[str, Any]:
    from kr_quant.research.grok_auth import session_status

    return session_status()


app = FastAPI(title="KR Quant Research", version="3.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
def api_status() -> dict[str, Any]:
    from kr_quant.freshness import freshness_snapshot
    from kr_quant.web.scheduler import scheduler_status

    from kr_quant.web.guide import explain_run_status

    s = load_settings()
    quality = _quality(s)
    live_prices = s.staged_dir / "live" / "prices.parquet"
    fresh = freshness_snapshot(s, screen_as_of=(quality or {}).get("as_of_date"))
    status_explain = explain_run_status(quality, status_csv_exists=s.status_csv.exists())
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
        "keys": {
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
def api_settings_get() -> dict[str, Any]:
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
def api_settings_put(body: SettingsIn) -> dict[str, Any]:
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
    return api_settings_get()


@app.post("/api/settings/test")
def api_settings_test() -> dict[str, Any]:
    s = load_settings()
    out: dict[str, Any] = {}
    if s.opendart_api_key:
        try:
            import requests

            r = requests.get(
                "https://opendart.fss.or.kr/api/company.json",
                params={"crtfc_key": s.opendart_api_key, "corp_code": "00126380"},
                timeout=20,
            )
            js = r.json()
            out["opendart"] = {"ok": str(js.get("status")) == "000", "detail": js.get("corp_name") or js.get("message")}
        except Exception as exc:  # noqa: BLE001
            out["opendart"] = {"ok": False, "detail": str(exc)}
    else:
        out["opendart"] = {"ok": False, "detail": "키 없음"}

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
                    found = f"{cur.isoformat()} {len(rows)}종목"
                    break
                cur -= timedelta(days=1)
            out["krx"] = {"ok": found is not None, "detail": found or "최근 시세 없음"}
        except Exception as exc:  # noqa: BLE001
            out["krx"] = {"ok": False, "detail": str(exc)}
    else:
        out["krx"] = {"ok": False, "detail": "키 없음"}

    if s.kis_app_key and s.kis_app_secret:
        try:
            import requests

            r = requests.post(
                f"{s.kis_base_url.rstrip('/')}/oauth2/tokenP",
                headers={"content-type": "application/json"},
                json={"grant_type": "client_credentials", "appkey": s.kis_app_key, "appsecret": s.kis_app_secret},
                timeout=20,
            )
            js = r.json()
            out["kis"] = {"ok": "access_token" in js, "detail": "토큰 발급" if "access_token" in js else str(js)[:120]}
        except Exception as exc:  # noqa: BLE001
            out["kis"] = {"ok": False, "detail": str(exc)}
    else:
        out["kis"] = {"ok": False, "detail": "키 없음"}

    if s.naver_client_id and s.naver_client_secret:
        try:
            from kr_quant.ingest.naver_search import search_news

            news = search_news(s.naver_client_id, s.naver_client_secret, "코스피", display=1)
            out["naver"] = {"ok": True, "detail": f"뉴스 검색 정상 · 총 {news.get('total')}건"}
        except Exception as exc:  # noqa: BLE001
            out["naver"] = {"ok": False, "detail": str(exc)[:160]}
    else:
        out["naver"] = {"ok": False, "detail": "Client ID/Secret 없음"}

    if s.naver_map_client_id and s.naver_map_client_secret:
        try:
            from kr_quant.ingest.naver_maps import geocode

            geo = geocode(s.naver_map_client_id, s.naver_map_client_secret, "서울특별시 중구 세종대로 110")
            out["naver_map"] = {
                "ok": geo is not None,
                "detail": "Geocoding 정상" if geo else "주소 결과 없음",
            }
        except Exception as exc:  # noqa: BLE001
            out["naver_map"] = {"ok": False, "detail": str(exc)[:160]}
    else:
        out["naver_map"] = {"ok": False, "detail": "지도 Client ID/Secret 없음"}

    if s.toss_client_id and s.toss_client_secret:
        try:
            from kr_quant.ingest.tossinvest import get_prices, issue_token

            issue_token(s.toss_client_id, s.toss_client_secret)
            rows = get_prices(s.toss_client_id, s.toss_client_secret, ["005930"])
            out["toss"] = {"ok": True, "detail": f"시세 조회 정상 · {len(rows)}건"}
        except Exception as exc:  # noqa: BLE001
            out["toss"] = {"ok": False, "detail": str(exc)[:180]}
    else:
        out["toss"] = {"ok": False, "detail": "Client ID/Secret 없음"}

    if s.fred_api_key:
        try:
            from kr_quant.ingest.fred import fetch_series

            obs = fetch_series(s.fred_api_key, "DGS10")
            last = obs[0] if obs else None
            out["fred"] = {
                "ok": bool(last),
                "detail": f"DGS10 {last.get('date')} {last.get('value')}" if last else "관측치 없음",
            }
        except Exception as exc:  # noqa: BLE001
            out["fred"] = {"ok": False, "detail": str(exc)[:180]}
    else:
        out["fred"] = {"ok": False, "detail": "FRED_API_KEY 없음"}

    try:
        from kr_quant.ingest.ecos import latest_point

        point = latest_point(s.bok_ecos_api_key, "기준금리")
        out["ecos"] = {
            "ok": bool(point),
            "detail": f"{point.get('alias')} {point.get('time')} {point.get('value')}" if point else "관측치 없음",
        }
    except Exception as exc:  # noqa: BLE001
        out["ecos"] = {"ok": False, "detail": str(exc)[:180]}

    try:
        from kr_quant.ingest.yahoo import snapshot_from_chart

        ks = snapshot_from_chart("^KS11", "KOSPI")
        out["yahoo"] = {
            "ok": ks.get("last") is not None,
            "detail": f"KOSPI {ks.get('as_of')} {ks.get('last')} · {ks.get('source')}",
        }
    except Exception as exc:  # noqa: BLE001
        out["yahoo"] = {"ok": False, "detail": str(exc)[:180]}

    if s.telegram_bot_token:
        try:
            from kr_quant.ingest.telegram import configured, get_me

            me = get_me(s.telegram_bot_token)
            ready = configured(s.telegram_bot_token, s.telegram_chat_id)
            out["telegram"] = {
                "ok": True,
                "detail": f"@{me.get('username')}" + (" · 채팅 ID 설정됨" if ready else " · 채팅 ID 없음"),
            }
        except Exception as exc:  # noqa: BLE001
            out["telegram"] = {"ok": False, "detail": str(exc)[:180]}
    else:
        out["telegram"] = {"ok": False, "detail": "봇 토큰 없음"}

    from kr_quant.research.providers import PROVIDERS, resolve_provider

    for name in PROVIDERS:
        try:
            ep = resolve_provider(s, name)
        except ValueError:
            continue
        if not ep.api_key:
            out[name] = {"ok": False, "detail": "키 없음"}
            continue
        try:
            import requests

            r = requests.get(
                f"{ep.base_url}/models",
                headers={"Authorization": f"Bearer {ep.api_key}"},
                timeout=20,
            )
            out[name] = {
                "ok": r.status_code == 200,
                "detail": f"{ep.label} {ep.model} HTTP {r.status_code}",
            }
        except Exception as exc:  # noqa: BLE001
            out[name] = {"ok": False, "detail": str(exc)}
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
            timeout=15,
        )
        js = r.json()
        if str(js.get("status")) != "000":
            return {}
        return {
            "corp_name": js.get("corp_name"),
            "ceo": js.get("ceo_nm"),
            "address": js.get("adres"),
            "homepage": js.get("hm_url"),
            "phone": js.get("phn_no"),
            "founded": js.get("est_dt"),
        }
    except Exception:  # noqa: BLE001
        return {}


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
def api_sunzi(n: int = 40) -> dict[str, Any]:
    from kr_quant.sunzi.five import build_sunzi_board

    return build_sunzi_board(load_settings(), n=max(10, min(int(n), 80)))


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


@app.get("/api/stocks/search")
def api_stocks_search(q: str = "", limit: int = 15) -> dict[str, Any]:
    query = str(q or "").strip()
    if not query:
        return {"items": []}

    s = load_settings()
    # Try loading latest_all_stocks.parquet
    df = None
    for p in (s.output_dir / "latest_all_stocks.parquet", s.output_dir / "all_stocks.parquet"):
        if p.exists():
            try:
                df = pd.read_parquet(p)
                break
            except Exception:
                pass

    if df is None or df.empty:
        from kr_quant.strategy.run import _prices
        df = _prices(s)

    if df is None or df.empty:
        return {"items": []}

    q_lower = query.lower()
    q_is_digit = query.isdigit()
    q_is_chosung = all(ch in _CHOSUNG_LIST for ch in query)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for rec in df.to_dict("records"):
        ticker = str(rec.get("ticker") or "").zfill(6)
        if not ticker or ticker in seen:
            continue
        company = str(rec.get("company") or "")
        company_lower = company.lower()

        matched = False
        if q_is_digit and query in ticker:
            matched = True
        elif not q_is_digit:
            if query in company or q_lower in company_lower:
                matched = True
            elif q_is_chosung and query in _to_chosung(company):
                matched = True

        if matched:
            seen.add(ticker)
            r_score = rec.get("quant_score")
            r_rank = rec.get("quant_rank")
            score_num = round(float(r_score), 1) if pd.notna(r_score) and r_score else None
            rank_num = int(r_rank) if pd.notna(r_rank) and r_rank else None

            items.append({
                "ticker": ticker,
                "company": company or ticker,
                "market": str(rec.get("market") or "KOSPI"),
                "sector": str(rec.get("sector") or ""),
                "quant_score": score_num,
                "quant_rank": rank_num,
            })
            if len(items) >= limit:
                break

    return {"items": items}


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
def api_seasonality_events_get(horizon_days: int = 90) -> dict[str, Any]:
    from kr_quant.strategy.event_calendar import get_upcoming_events

    events = get_upcoming_events(horizon_days=horizon_days)
    return {"ok": True, "horizon_days": horizon_days, "count": len(events), "events": events}


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
    from kr_quant.strategy.seasonality import scan_seasonality, EVENT_PRESETS

    s = load_settings()
    rows = scan_seasonality(
        s,
        target_month=month,
        min_win_rate=min_win_rate,
        min_avg_return=min_avg_return,
        preset=preset,
        query=query,
    )
    return {
        "ok": True,
        "target_month": month or pd.Timestamp.now().month,
        "count": len(rows),
        "presets": EVENT_PRESETS,
        "rows": rows,
    }


@app.get("/api/seasonality/ticker/{ticker}")
def api_seasonality_ticker_get(ticker: str) -> dict[str, Any]:
    from kr_quant.strategy.seasonality import build_seasonality_database

    s = load_settings()
    db = build_seasonality_database(s)
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

    return backtest_single_stock(load_settings(), ticker)


@app.post("/api/strategy/ticker")
def api_strategy_ticker_post(body: StrategyTickerIn) -> dict[str, Any]:
    from kr_quant.strategy.run import backtest_single_stock

    return backtest_single_stock(load_settings(), body.ticker)

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

    s = load_settings()
    code = str(ticker).zfill(6)
    path = find_report_file(s.output_dir, code, as_of)
    if not path or not path.exists():
        row, day = _load_stock_row(code, as_of)
        record = {"ticker": code, "company": row.get("company") or code, "as_of_date": day or as_of}
        html = generate_infographic_html(record, stock_row=row)
        return HTMLResponse(content=html)

    record = json.loads(path.read_text(encoding="utf-8"))
    html = record.get("infographic_html")
    if not html:
        row, day = _load_stock_row(code, as_of)
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

    uvicorn.run(
        "kr_quant.web.app:app",
        host=host,
        port=chosen,
        reload=False,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    serve()
