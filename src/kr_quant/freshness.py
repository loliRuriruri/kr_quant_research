from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
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
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        if "trade_date" in pf.schema.names:
            idx = pf.schema.names.index("trade_date")
            max_vals = []
            for i in range(pf.metadata.num_row_groups):
                rg_col = pf.metadata.row_group(i).column(idx)
                if rg_col.statistics and rg_col.statistics.has_min_max:
                    max_vals.append(rg_col.statistics.max)
            if max_vals:
                raw_max = max(max_vals)
                if hasattr(raw_max, "date"):
                    return raw_max.date()
                return date.fromisoformat(str(raw_max)[:10])
    except Exception:  # noqa: BLE001
        pass
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
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        avail = [c for c in ("available_date", "rcept_dt", "period_end") if c in pf.schema.names]
        if avail:
            df = pd.read_parquet(path, columns=avail)
        else:
            return None
    except Exception:  # noqa: BLE001
        try:
            df = pd.read_parquet(path)
        except Exception:  # noqa: BLE001
            return None
    for col in ("available_date", "rcept_dt", "period_end"):
        if col in df.columns:
            hit = _max_date(df[col])
            if hit:
                return hit
    return None


def trading_session_lag(observed: date | None, expected: date) -> int | None:
    """Count missing default KRX sessions, not calendar days."""
    if observed is None:
        return None
    if observed >= expected:
        return 0
    lag = 0
    cursor = observed + timedelta(days=1)
    while cursor <= expected:
        if is_default_trading_day(cursor):
            lag += 1
        cursor += timedelta(days=1)
    return lag


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=KST).isoformat()


def _financial_coverage(facts_path: Path, master_path: Path, backfill_path: Path | None = None) -> dict[str, Any]:
    from kr_quant.ingest.live import dart_coverage_report

    facts = None
    master = None
    if facts_path.exists():
        try:
            facts = pd.read_parquet(facts_path, columns=["ticker"])
        except Exception:  # noqa: BLE001
            facts = None
    if master_path.exists():
        try:
            master = pd.read_parquet(master_path)
        except Exception:  # noqa: BLE001
            master = None
    outcomes: dict[str, Any] = {}
    if backfill_path and backfill_path.exists():
        try:
            payload = json.loads(backfill_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("ticker_outcomes"), dict):
                outcomes = payload["ticker_outcomes"]
        except (OSError, json.JSONDecodeError):
            outcomes = {}
    report = dart_coverage_report(master, facts, outcomes)
    report['meaning'] = 'stored_ticker_presence_not_latest_filing_completeness'
    report['latest_filing_verified'] = False
    return report


def _official_flow_freshness(settings: Settings, expected: date) -> dict[str, Any]:
    """Observe existing storage only; no DB creation, token issue or collector calls."""
    base = {'label': 'KIS 공식 수급', 'expected_date': expected.isoformat(),
            'observed_date': None, 'state': 'missing', 'used_in_quant': False,
            'scope': 'stored_tickers_not_all_listed_stocks'}
    if not settings.db_path.exists():
        return base
    try:
        import duckdb
        with duckdb.connect(str(settings.db_path), read_only=True) as con:
            rows = con.execute("SELECT ticker, max(CASE WHEN is_final AND trade_date <= ? THEN trade_date END) FROM investor_flows_daily WHERE source = 'KIS' GROUP BY ticker", [expected]).fetchall()
    except Exception:  # DB busy/unreadable must not be reported as fresh.
        return {**base, 'state': 'unavailable'}
    if not rows:
        return base
    dates = [day for _, day in rows if day is not None]
    observed = max(dates) if dates else None
    current = sum(day == expected for _, day in rows)
    future = sum(day is not None and day > expected for _, day in rows)
    return {**base, 'observed_date': observed.isoformat() if observed else None,
            'state': 'future' if future else ('fresh' if current == len(rows) else ('partial' if current else 'stale')),
            'lag_trading_days': trading_session_lag(observed, expected),
            'coverage': {'stored_tickers': len(rows), 'current_tickers': current,
                         'not_current_tickers': len(rows) - current}}


def _strategy_cache_date(path: Path) -> date | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    direct = payload.get("source_price_as_of")
    candidates = [direct, *[row.get("to") for row in payload.get("rows") or [] if isinstance(row, dict)]]
    parsed = pd.to_datetime(pd.Series([value for value in candidates if value]), errors="coerce").dropna()
    return None if parsed.empty else parsed.max().date()


def _backfill_progress(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        key: payload.get(key)
        for key in (
            "status",
            "cursor",
            "batch_end",
            "total_targets",
            "processed_this_run",
            "covered_tickers",
            "coverage_pct",
            "completed_cycles",
            "completed_at",
            "started_at",
            "error",
            "remaining_tickers",
            "remaining_batches",
            "eta_days",
            "has_retryable",
            "cycle_complete",
            "coverage",
        )
    }


def latest_price_date(settings: Settings) -> date | None:
    live = settings.staged_dir / "live" / "prices.parquet"
    demo = settings.staged_dir / "demo" / "prices.parquet"
    return _read_price_max(live if live.exists() else demo)


def freshness_snapshot(settings: Settings, *, now: datetime | None = None, screen_as_of: str | None = None) -> dict[str, Any]:
    from kr_quant.run_generation import current_output_path, is_updating
    expected = expected_price_date(now)
    live = settings.staged_dir / "live"
    demo = settings.staged_dir / "demo"
    price_path = live / "prices.parquet" if (live / "prices.parquet").exists() else demo / "prices.parquet"
    facts_path = live / "financial_facts.parquet" if (live / "financial_facts.parquet").exists() else demo / "financial_facts.parquet"
    price_max = _read_price_max(price_path)
    price_days = _read_price_days(price_path)
    financial_max = _read_financial_max(facts_path)
    screen_day = None
    quality_path = current_output_path(settings, "data_quality_report.json")
    if not screen_as_of and quality_path.exists():
        try:
            screen_as_of = json.loads(quality_path.read_text(encoding="utf-8")).get("as_of_date")
        except (OSError, json.JSONDecodeError, TypeError):
            screen_as_of = None
    if screen_as_of:
        try:
            screen_day = date.fromisoformat(str(screen_as_of)[:10])
        except ValueError:
            screen_day = None
    lag = None if price_max is None else (expected - price_max).days
    session_lag = trading_session_lag(price_max, expected)
    stale_price = price_max is None or price_max < expected
    stale_screen = screen_day is None or price_max is None or screen_day != price_max
    if stale_price:
        status = "stale"
        label = "시세 지연" if price_max else "시세 없음"
    elif stale_screen:
        status = "screen_lag"
        label = "시세는 최신, 점수 미재계산"
    else:
        status = "fresh"
        label = "시세 최신"
    master_path = live / "master.parquet" if (live / "master.parquet").exists() else demo / "master.parquet"
    backfill_path = live / "dart_backfill_state.json"
    financial_coverage = _financial_coverage(facts_path, master_path, backfill_path)
    backfill_progress = _backfill_progress(backfill_path)
    strategy_path = settings.root / "data" / "cache" / "strategy_lab.json"
    strategy_day = _strategy_cache_date(strategy_path)
    strategy_lag = trading_session_lag(strategy_day, price_max or expected)
    strategy_state = "missing" if strategy_day is None else ("stale" if strategy_lag else "fresh")
    screen_lag = trading_session_lag(screen_day, price_max or expected)
    sources = {
        "krx_prices": {
            "label": "KRX 일봉 시세",
            "expected_date": expected.isoformat(),
            "observed_date": None if price_max is None else price_max.isoformat(),
            "lag_trading_days": session_lag,
            "state": "missing" if price_max is None else ("stale" if stale_price else "fresh"),
            "coverage": {"trading_days": price_days},
            "last_updated_at": _mtime_iso(price_path),
        },
        "financial_facts": {
            "label": "OpenDART 재무공시",
            "expected_date": None,
            "observed_date": None if financial_max is None else financial_max.isoformat(),
            "lag_trading_days": None,
            "state": "missing" if financial_max is None else ("partial" if (financial_coverage.get("coverage_pct") or 0) < 90 else "available"),
            "cadence": "공시 발생 기준",
            "freshness_verified": False,
            "coverage": financial_coverage,
            "backfill": backfill_progress,
            "last_updated_at": _mtime_iso(facts_path),
        },
        "quant_ranking": {
            "label": "퀀트 점수·랭킹",
            "expected_date": None if price_max is None else price_max.isoformat(),
            "observed_date": None if screen_day is None else screen_day.isoformat(),
            "lag_trading_days": screen_lag,
            "state": "missing" if screen_day is None else ("stale" if stale_screen or stale_price else "fresh"),
            "aligned_with_stored_prices": not stale_screen,
            "last_updated_at": _mtime_iso(quality_path),
        },
        "strategy_cache": {
            "label": "전략·백테스트 캐시",
            "expected_date": None if price_max is None else price_max.isoformat(),
            "observed_date": None if strategy_day is None else strategy_day.isoformat(),
            "lag_trading_days": strategy_lag,
            "state": strategy_state,
            "last_updated_at": _mtime_iso(strategy_path),
            "used_in_quant": False,
        },
        "official_flow": _official_flow_freshness(settings, expected),
    }
    required_stale = [name for name in ("krx_prices", "quant_ranking") if sources[name]["state"] != "fresh"]
    derived_stale = [name for name in ("strategy_cache",) if sources[name]["state"] != "fresh"]
    return {
        "timezone": "Asia/Seoul",
        "expected_price_date": expected.isoformat(),
        "price_max_date": None if price_max is None else price_max.isoformat(),
        "price_days": price_days,
        "financial_max_available_date": None if financial_max is None else financial_max.isoformat(),
        "screen_as_of": None if screen_day is None else screen_day.isoformat(),
        "lag_days": lag,
        "lag_trading_days": session_lag,
        "stale_price": stale_price,
        "stale_screen": stale_screen,
        "status": status,
        "label": label,
        "source": str(price_path) if price_path.exists() else None,
        "contract_status": "blocked" if stale_price else ("partial" if required_stale or derived_stale else "ready"),
        "required_stale": required_stale,
        "derived_stale": derived_stale,
        "sources": sources,
        "used_in_quant": False,
        "updating": is_updating(settings),
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
