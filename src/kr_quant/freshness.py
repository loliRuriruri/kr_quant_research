from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from kr_quant.calendar import is_default_trading_day, previous_trading_day
from kr_quant.settings import Settings

KST = ZoneInfo("Asia/Seoul")
SESSION_DONE = time(18, 0)


def now_kst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def expected_price_date(now: datetime | None = None) -> date:
    """Last KRX session that should already be in prices.parquet."""
    current = now_kst(now)
    today = current.date()
    clock = current.hour * 60 + current.minute
    done = SESSION_DONE.hour * 60 + SESSION_DONE.minute
    if is_default_trading_day(today) and clock >= done:
        return today
    return previous_trading_day(today)


def _max_date(series: pd.Series | None) -> date | None:
    if series is None or series.empty:
        return None
    converted = pd.to_datetime(series, errors="coerce").dropna()
    if converted.empty:
        return None
    value = converted.max()
    return value.date() if hasattr(value, "date") else date.fromisoformat(str(value)[:10])


def _read_price_max(path: Path) -> date | None:
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path, columns=["trade_date"])
    except Exception:  # noqa: BLE001
        return None
    return _max_date(df["trade_date"])


def _read_price_days(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        df = pd.read_parquet(path, columns=["trade_date"])
    except Exception:  # noqa: BLE001
        return 0
    converted = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    return int(converted.dt.normalize().nunique()) if not converted.empty else 0


def _read_financial_max(path: Path) -> date | None:
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    for col in ("available_date", "rcept_dt", "period_end"):
        if col in df.columns:
            hit = _max_date(df[col])
            if hit:
                return hit
    return None


def freshness_snapshot(settings: Settings, *, now: datetime | None = None, screen_as_of: str | None = None) -> dict[str, Any]:
    expected = expected_price_date(now)
    live = settings.staged_dir / "live"
    demo = settings.staged_dir / "demo"
    price_path = live / "prices.parquet" if (live / "prices.parquet").exists() else demo / "prices.parquet"
    facts_path = live / "financial_facts.parquet" if (live / "financial_facts.parquet").exists() else demo / "financial_facts.parquet"
    price_max = _read_price_max(price_path)
    price_days = _read_price_days(price_path)
    financial_max = _read_financial_max(facts_path)
    screen_day = None
    if screen_as_of:
        try:
            screen_day = date.fromisoformat(str(screen_as_of)[:10])
        except ValueError:
            screen_day = None
    lag = None if price_max is None else (expected - price_max).days
    stale_price = price_max is None or price_max < expected
    stale_screen = bool(screen_day and price_max and screen_day < price_max)
    if stale_price:
        status = "stale"
        label = "시세 지연" if price_max else "시세 없음"
    elif stale_screen:
        status = "screen_lag"
        label = "시세는 최신, 점수 미재계산"
    else:
        status = "fresh"
        label = "시세 최신"
    return {
        "timezone": "Asia/Seoul",
        "expected_price_date": expected.isoformat(),
        "price_max_date": None if price_max is None else price_max.isoformat(),
        "price_days": price_days,
        "financial_max_available_date": None if financial_max is None else financial_max.isoformat(),
        "screen_as_of": None if screen_day is None else screen_day.isoformat(),
        "lag_days": lag,
        "stale_price": stale_price,
        "stale_screen": stale_screen,
        "status": status,
        "label": label,
        "source": str(price_path) if price_path.exists() else None,
        "used_in_quant": False,
    }


def runtime_spec(settings: Settings, *, freshness: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings.config
    factors = cfg.get("factors") or {}
    uni = cfg.get("universe") or {}
    return {
        "product": "KR Quant Research",
        "model_id": settings.model_id,
        "model_version": settings.model_version,
        "timezone": settings.timezone,
        "config_hash": settings.config_hash[:16],
        "orders": False,
        "momentum_enabled": bool((factors.get("momentum") or {}).get("enabled")),
        "listed_shares_adjustment": bool((cfg.get("corporate_actions") or {}).get("listed_shares_adjustment")),
        "quant_weights": {
            "value": (factors.get("value") or {}).get("max_points"),
            "quality": (factors.get("quality") or {}).get("max_points"),
            "growth": (factors.get("growth") or {}).get("max_points"),
            "momentum": (factors.get("momentum") or {}).get("max_points"),
            "stability": (factors.get("financial_stability") or {}).get("max_points"),
            "risk_penalty_cap": cfg.get("risk_penalty_cap") or (cfg.get("risk") or {}).get("soft_penalty_cap"),
        },
        "universe": {
            "markets": uni.get("markets"),
            "min_market_cap_krw": uni.get("min_market_cap_krw"),
            "min_median_trading_value_krw": (uni.get("liquidity") or {}).get("min_median_trading_value_krw"),
        },
        "overlays": {
            "market_regime": False,
            "flow": False,
            "timing": False,
            "us13f": False,
            "strategy": False,
            "portfolio": False,
            "sector": False,
            "screens": False,
            "macro": False,
            "news": False,
            "fa_gate": False,
            "dao": False,
            "jiang": False,
            "tian": False,
            "di": False,
            "sunzi": False,
            "official_flow": False,
            "nps_holdings": False,
            "dart_events": False,
            "llm_research": False,
        },
        "freshness": freshness,
        "note": "overlays used_in_quant=false. LLM does not write quant_score.",
    }
