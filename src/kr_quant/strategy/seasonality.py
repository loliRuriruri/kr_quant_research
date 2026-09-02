# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kr_quant.settings import Settings
from kr_quant.strategy.remaining_peak import calculate_remaining_peak_upside
from kr_quant.strategy.run import _prices
from kr_quant.universe.tradability import evaluate_candidate_tradability, evaluate_event_universe_tradability

logger = logging.getLogger("kr_quant.strategy.seasonality")
SEASONALITY_CACHE_VERSION = 2
DISCOVERY_CACHE_VERSION = 5

EVENT_PRESETS: dict[str, dict[str, Any]] = {
    "winter_heater": {
        "label": "❄️ 겨울 난방/보일러",
        "title": "❄️ 겨울 난방 & 보일러 특수",
        "description": "난방 가동 전 6~8월 선취매 랠리 및 10~11월 실적 반영 종목군",
        "peak_months": [7, 8, 10],
        "analysis_month": 8,
        "tickers": ["009450", "037070", "002700", "005950", "004690", "071320", "016710", "000590", "017940"],
    },
    "summer_heat": {
        "label": "☀️ 여름 폭염/냉방",
        "title": "☀️ 여름 폭염 · 냉방 · 제습 특수",
        "description": "본격 무더위 시작 전 4~6월 선반영 급등 종목군",
        "peak_months": [4, 5, 6],
        "analysis_month": 5,
        "tickers": ["037070", "002700", "044340", "042110", "014820", "005300", "000080", "001550", "025860"],
    },
    "galaxy_phone": {
        "label": "📱 갤럭시 S/Z 언팩",
        "title": "📱 갤럭시 · 스마트폰 신제품 출시 사이클",
        "description": "S시리즈(1~2월) 및 Z폴드/플립 언팩(6~7월) 직전 부품 공급 선취매",
        "peak_months": [1, 2, 6, 7],
        "analysis_month": 7,
        "tickers": ["441270", "060720", "085670", "090460", "051370", "091700", "097520", "053610", "195870"],
    },
    "dividend_play": {
        "label": "💰 연말 고배당",
        "title": "💰 연말 고배당 선취매 랠리",
        "description": "배당락(12월 말) 2~3개월 전인 9~11월 기관/외인 배당 매집 종목군",
        "peak_months": [9, 10, 11],
        "analysis_month": 10,
        "tickers": ["105560", "055550", "086790", "316140", "017670", "030200", "032640", "003540", "000815", "036570"],
    },
    "shopping_frenzy": {
        "label": "🛍️ 광군제/블프/소비재",
        "title": "🛍️ 광군제 · 블프 · K-콘텐츠/소비재",
        "description": "하반기 글로벌 쇼핑 시즌 및 여름 휴가철 웹툰/미디어/소비재 특수",
        "peak_months": [8, 9, 10, 11],
        "analysis_month": 10,
        "tickers": ["134580", "090430", "192820", "161890", "271560", "035760", "253450", "042000", "060250", "035420"],
    },
    "index_rebalance": {
        "label": "📊 지수 편입/리밸런싱",
        "title": "📊 MSCI · KOSPI200 · KOSDAQ150 리밸런싱",
        "description": "지수 정기변경 전후 패시브 자금 유입·유출 후보 종목군",
        "peak_months": [5, 8, 11, 12],
        "analysis_month": 11,
        "tickers": ["105560", "000810", "267260", "192820", "259960", "053610", "086790"],
    },
    "earnings_pead": {
        "label": "📈 실적 시즌/PEAD",
        "title": "📈 실적 상향 · 어닝 서프라이즈 · PEAD",
        "description": "실적 발표 전 이익추정 상향과 발표 후 양의 드리프트 후보 종목군",
        "peak_months": [4, 7, 10, 11],
        "analysis_month": 10,
        "tickers": ["009450", "192820", "011070"],
    },
    "iphone_cycle": {
        "label": "🍎 아이폰 공급망",
        "title": "🍎 Apple iPhone 공개 · 양산 공급망 사이클",
        "description": "7~8월 초도 양산과 9월 공개 전 국내 카메라·OLED·FPCB·MLCC 공급망",
        "peak_months": [7, 8, 9],
        "analysis_month": 8,
        "tickers": ["011070", "090460", "034220", "009150"],
    },
    "ces_ai_robot": {
        "label": "🤖 CES/AI/로봇",
        "title": "🤖 CES · 온디바이스 AI · 로봇 · 자율주행",
        "description": "연말부터 CES 개막 전까지 신기술 공개 기대가 반영되는 국내 공급망",
        "peak_months": [11, 12, 1],
        "analysis_month": 12,
        "tickers": ["277810", "005930", "066570", "042700"],
    },
    "bio_conference": {
        "label": "🧬 바이오 학회",
        "title": "🧬 JPM · AACR · ASCO · ESMO 바이오 학회",
        "description": "초록 공개·임상 발표·기술수출 기대가 집중되는 고위험 바이오 이벤트 종목군",
        "peak_months": [1, 4, 5, 6, 9, 10, 11, 12],
        "analysis_month": 9,
        "tickers": ["000100", "196170", "141080", "206650", "310210"],
    },
    "game_show": {
        "label": "🎮 게임쇼/신작",
        "title": "🎮 G-STAR · 게임쇼 · 대형 신작 출시",
        "description": "게임쇼와 신작 공개 전 사전예약·쇼케이스 기대가 반영되는 게임·콘텐츠 종목군",
        "peak_months": [8, 9, 10, 11],
        "analysis_month": 10,
        "tickers": ["259960", "036570", "134580"],
    },
    "holiday_consumption": {
        "label": "✈️ 명절/여행/소비",
        "title": "✈️ 설 · 추석 · 연휴 여행/유통/콘텐츠",
        "description": "명절과 장기 연휴 전후 소비·여행·콘텐츠 수요 변화를 관찰하는 종목군",
        "peak_months": [1, 2, 9, 10],
        "analysis_month": 9,
        "tickers": ["001040", "097950", "028260", "035760"],
    },
    "year_end_calendar": {
        "label": "📅 연말/1월 효과",
        "title": "📅 대주주 양도세 · 산타랠리 · 1월 효과",
        "description": "연말 개인 매물 출회와 연초 신규 자금 유입을 함께 관찰하는 캘린더 종목군",
        "peak_months": [12, 1],
        "analysis_month": 12,
        "tickers": ["247540", "086520", "277810", "035420", "356680", "168360"],
    },
    "ipo_lockup": {
        "label": "🔓 IPO 락업/오버행",
        "title": "🔓 IPO 의무보유 해제 · 오버행 소화",
        "description": "락업 해제 전 매도압력과 해제 이후 수급 안정 여부를 구분해 관찰하는 종목군",
        "peak_months": [3, 6, 9, 12],
        "analysis_month": 9,
        "tickers": ["259960", "441270"],
    },
}


def cache_path(settings: Settings) -> Path:
    return settings.root / "data" / "cache" / "seasonality_cache.json"


_TICKER_META_CACHE: dict[str, Any] = {"ts": 0.0, "map": {}}
_SEASONALITY_DB_MEM: dict[str, Any] = {"ts": 0.0, "db": None}
_REMAINING_PEAK_CACHE: dict[str, Any] = {"signature": None, "values": {}}
_REMAINING_PEAK_LOCK = threading.RLock()
_CLEAN_TICKERS_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "signature": None,
    "tickers": set(),
    "ready": False,
    "errors": (),
}
_EVENT_TICKERS_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "signature": None,
    "tickers": set(),
    "ready": False,
    "errors": (),
}
PRE_ENTRY_STAGE_WEIGHT: dict[str, int] = {
    "TODAY_ENTRY": 100,
    "PRE_ENTRY_15": 80,
    "PRE_ENTRY_30": 60,
    "ACCUMULATE_60": 40,
    "RALLY_ACTIVE": 30,
    "EXIT_PEAK": 10,
}


def _load_scored_map(settings: Settings) -> dict[str, dict[str, Any]]:
    """Load the latest scored universe across current and legacy output names."""
    candidates: list[Path] = [settings.output_dir / "latest_all_stocks.parquet"]
    for dated in sorted(settings.output_dir.glob("as_of_date=*"), reverse=True):
        if not dated.is_dir():
            continue
        # all_stocks.parquet is the current orchestration output. Keep the
        # legacy name as a compatibility fallback for older saved runs.
        candidates.extend([dated / "all_stocks.parquet", dated / "scored_all.parquet"])

    for path in candidates:
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path)
            if "ticker" not in frame.columns:
                continue
            frame = frame.copy()
            frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
            return {row["ticker"]: row for row in frame.to_dict("records")}
        except Exception as exc:
            logger.debug("Scored output read failed for %s: %s", path, exc)
    return {}


def _load_flow_confirmation_map(settings: Settings) -> dict[str, dict[str, Any]]:
    """Load observed investor-flow fields without treating them as quant factors."""
    path = settings.data_dir / "cache" / "investor_flow.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("ticker"):
            continue
        ticker = str(row["ticker"]).zfill(6)
        out[ticker] = {
            "foreign_net": row.get("foreign_net"),
            "institution_net": row.get("institution_net"),
            "flow_as_of": row.get("to"),
        }
    return out


def _event_tags_for_ticker(ticker: Any) -> list[str]:
    code = str(ticker or "").zfill(6)
    return [key for key, preset in EVENT_PRESETS.items() if code in preset.get("tickers", [])]


def _clean_active_tickers(settings: Settings) -> set[str]:
    """Return a fail-closed candidate set from current official and scored sources."""
    now = time.time()

    price_path = next(
        (p for p in (settings.staged_dir / "live" / "prices.parquet", settings.staged_dir / "demo" / "prices.parquet") if p.exists()),
        None,
    )
    scored_path = settings.output_dir / "latest_all_stocks.parquet"
    if not scored_path.exists():
        scored_path = next(
            (
                p / "scored_all.parquet"
                for p in sorted(settings.output_dir.glob("as_of_date=*"), reverse=True)
                if (p / "scored_all.parquet").exists()
            ),
            scored_path,
        )
    master_path = settings.staged_dir / "live" / "krx_master.parquet"
    if not master_path.exists():
        master_path = settings.staged_dir / "live" / "master.parquet"

    paths = (price_path, scored_path, master_path)
    signature = tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size) if path is not None and path.exists() else None
        for path in paths
    )
    if (
        _CLEAN_TICKERS_CACHE.get("signature") == signature
        and now - float(_CLEAN_TICKERS_CACHE.get("ts") or 0) < 60
    ):
        return set(_CLEAN_TICKERS_CACHE.get("tickers") or set())

    result = None
    try:
        prices = pd.read_parquet(price_path) if price_path is not None and price_path.exists() else pd.DataFrame()
        scored = pd.read_parquet(scored_path) if scored_path.exists() else pd.DataFrame()
        master = pd.read_parquet(master_path) if master_path.exists() else pd.DataFrame()
        result = evaluate_candidate_tradability(prices, scored, master)
    except Exception as exc:  # fail closed on transient/corrupt source reads
        logger.error("Tradability gate source read failed: %s", exc)

    clean_tickers = set(result.allowed_tickers) if result is not None and result.ready else set()
    errors = result.errors if result is not None else ("TRADABILITY_SOURCE_READ_FAILED",)
    if errors:
        logger.warning("Tradability gate closed candidate output: %s", ",".join(errors))
    _CLEAN_TICKERS_CACHE.update(
        {
            "ts": now,
            "signature": signature,
            "tickers": clean_tickers,
            "ready": bool(result is not None and result.ready),
            "errors": errors,
        }
    )
    return clean_tickers


def _event_active_tickers(settings: Settings) -> set[str]:
    """Return the broad, current, safe-to-display event/theme universe."""
    now = time.time()
    price_path = next(
        (p for p in (settings.staged_dir / "live" / "prices.parquet", settings.staged_dir / "demo" / "prices.parquet") if p.exists()),
        None,
    )
    scored_path = settings.output_dir / "latest_all_stocks.parquet"
    if not scored_path.exists():
        scored_path = next(
            (
                p / "scored_all.parquet"
                for p in sorted(settings.output_dir.glob("as_of_date=*"), reverse=True)
                if (p / "scored_all.parquet").exists()
            ),
            scored_path,
        )
    master_path = settings.staged_dir / "live" / "krx_master.parquet"
    if not master_path.exists():
        master_path = settings.staged_dir / "live" / "master.parquet"

    paths = (price_path, scored_path, master_path)
    signature = tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size) if path is not None and path.exists() else None
        for path in paths
    )
    if (
        _EVENT_TICKERS_CACHE.get("signature") == signature
        and now - float(_EVENT_TICKERS_CACHE.get("ts") or 0) < 60
    ):
        return set(_EVENT_TICKERS_CACHE.get("tickers") or set())

    result = None
    try:
        prices = pd.read_parquet(price_path) if price_path is not None and price_path.exists() else pd.DataFrame()
        scored = pd.read_parquet(scored_path) if scored_path.exists() else pd.DataFrame()
        master = pd.read_parquet(master_path) if master_path.exists() else pd.DataFrame()
        result = evaluate_event_universe_tradability(prices, scored, master)
    except Exception as exc:  # fail closed on transient/corrupt source reads
        logger.error("Event universe source read failed: %s", exc)

    event_tickers = set(result.allowed_tickers) if result is not None and result.ready else set()
    errors = result.errors if result is not None else ("EVENT_UNIVERSE_SOURCE_READ_FAILED",)
    if errors:
        logger.warning("Event universe gate closed output: %s", ",".join(errors))
    _EVENT_TICKERS_CACHE.update(
        {
            "ts": now,
            "signature": signature,
            "tickers": event_tickers,
            "ready": bool(result is not None and result.ready),
            "errors": errors,
        }
    )
    return event_tickers


def ticker_meta_map(settings: Settings) -> dict[str, dict[str, str]]:
    """Unique ticker → {company, market} from staged prices. Cached 1 hour."""
    now = time.time()
    cached = _TICKER_META_CACHE.get("map") or {}
    if cached and now - float(_TICKER_META_CACHE.get("ts") or 0) < 3600:
        return cached

    prices = _prices(settings)
    out: dict[str, dict[str, str]] = {}
    if prices is None or prices.empty or "ticker" not in prices.columns:
        _TICKER_META_CACHE["ts"] = now
        _TICKER_META_CACHE["map"] = out
        return out

    cols = [c for c in ("ticker", "company", "market") if c in prices.columns]
    uniq = prices[cols].drop_duplicates(subset=["ticker"], keep="last")
    for row in uniq.itertuples(index=False):
        ticker = str(getattr(row, "ticker", "")).zfill(6)
        company = str(getattr(row, "company", "") or "") if "company" in cols else ""
        market = str(getattr(row, "market", "") or "KOSPI") if "market" in cols else "KOSPI"
        if not market or market == "nan":
            market = "KOSPI"
        out[ticker] = {"company": company, "market": market}

    _TICKER_META_CACHE["ts"] = now
    _TICKER_META_CACHE["map"] = out
    return out


def _apply_market_meta(stock: dict[str, Any], meta: dict[str, dict[str, str]]) -> None:
    info = meta.get(str(stock.get("ticker") or "").zfill(6))
    if not info:
        return
    if info.get("market"):
        stock["market"] = info["market"]
    if info.get("company") and (not stock.get("company") or stock.get("company") == stock.get("ticker")):
        stock["company"] = info["company"]


def seasonality_universe_stats(settings: Settings) -> dict[str, Any]:
    db = build_seasonality_database(settings)
    stocks = db.get("stocks") or {}
    markets: dict[str, int] = {}
    for s in stocks.values():
        m = str(s.get("market") or "UNKNOWN")
        markets[m] = markets.get(m, 0) + 1
    listed = ticker_meta_map(settings)
    listed_markets: dict[str, int] = {}
    for info in listed.values():
        m = str(info.get("market") or "UNKNOWN")
        listed_markets[m] = listed_markets.get(m, 0) + 1
    prices = _prices(settings)
    price_as_of = None
    if prices is not None and not prices.empty and "trade_date" in prices.columns:
        newest = pd.to_datetime(prices["trade_date"], errors="coerce").max()
        if not pd.isna(newest):
            price_as_of = newest.date().isoformat()
    updated_at = db.get("updated_at")
    calculated_at = None
    if updated_at:
        try:
            calculated_at = pd.to_datetime(float(updated_at), unit="s", utc=True).isoformat()
        except (TypeError, ValueError, OverflowError):
            calculated_at = None
    return {
        "universe_scanned": len(stocks),
        "universe_listed": len(listed),
        "markets": markets,
        "listed_markets": listed_markets,
        "data_context": {
            "price_as_of": price_as_of,
            "calculated_at": calculated_at,
            "source": "KRX 일봉 기반 월간 계절성",
        },
    }


def calculate_stock_seasonality(hist: pd.DataFrame) -> list[dict[str, Any]]:
    """Calculates 12 months win rate, avg return, median return, and years count for a single stock dataframe."""
    if hist.empty or len(hist) < 20:
        return []

    df = hist.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif "trade_date" in df.columns:
        df["date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    else:
        return []

    df = df.dropna(subset=["date"]).sort_values("date")
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    monthly = df.groupby(["year", "month"]).agg(
        start_close=("close", "first"),
        end_close=("close", "last")
    ).reset_index()

    monthly["ret"] = (monthly["end_close"] - monthly["start_close"]) / monthly["start_close"]

    month_stats: list[dict[str, Any]] = []
    for m in range(1, 13):
        m_data = monthly[monthly["month"] == m]["ret"]
        count = len(m_data)
        if count == 0:
            month_stats.append({
                "month": m,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "median_return": 0.0,
                "years_count": 0,
                "history": [],
            })
            continue

        win_rate = float((m_data > 0).mean())
        avg_ret = float(m_data.mean())
        med_ret = float(m_data.median())
        hist_list = [round(float(v), 4) for v in m_data.tolist()]

        month_stats.append({
            "month": m,
            "win_rate": round(win_rate, 3),
            "avg_return": round(avg_ret, 4),
            "median_return": round(med_ret, 4),
            "years_count": count,
            "history": hist_list,
        })

    return month_stats


def build_seasonality_database(settings: Settings) -> dict[str, Any]:
    """Scans all stocks using fast vectorized pandas groupby and caches to JSON."""
    c_path = cache_path(settings)
    if c_path.exists():
        try:
            cached = json.loads(c_path.read_text(encoding="utf-8"))
            if (
                cached.get("version") == SEASONALITY_CACHE_VERSION
                and time.time() - cached.get("updated_at", 0) < 86400 * 3
                and len(cached.get("stocks", {})) > 100
            ):
                meta = ticker_meta_map(settings)
                for stock in (cached.get("stocks") or {}).values():
                    _apply_market_meta(stock, meta)
                    stock["tags"] = _event_tags_for_ticker(stock.get("ticker"))
                return cached
        except Exception:
            pass

    prices = _prices(settings)
    if prices.empty:
        return {"version": SEASONALITY_CACHE_VERSION, "updated_at": int(time.time()), "stocks": {}}

    event_set = _event_active_tickers(settings)

    df = prices.copy()
    df["date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["ticker", "date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # Store the broader safe event universe. Monthly quant discovery applies
    # the stricter candidate gate at query time.
    df = df[df["ticker"].isin(event_set)]

    names_map: dict[str, dict[str, str]] = ticker_meta_map(settings)
    if not names_map and "company" in df.columns:
        cols = [c for c in ("ticker", "company", "market") if c in df.columns]
        for _, row in df[cols].drop_duplicates(subset=["ticker"]).iterrows():
            names_map[str(row["ticker"]).zfill(6)] = {
                "company": str(row.get("company") or ""),
                "market": str(row.get("market") or "KOSPI") if "market" in cols else "KOSPI",
            }

    monthly = df.groupby(["ticker", "year", "month"]).agg(
        start_close=("close", "first"),
        end_close=("close", "last")
    ).reset_index()

    monthly["ret"] = (monthly["end_close"] - monthly["start_close"]) / monthly["start_close"]

    grouped = monthly.groupby(["ticker", "month"])

    stats_df = grouped["ret"].agg(
        win_rate=lambda s: float((s > 0).mean()),
        avg_return="mean",
        median_return="median",
        years_count="count"
    ).reset_index()

    hist_dict: dict[tuple[str, int], list[float]] = {}
    hist_recs_dict: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for (t, m), sub_df in monthly.groupby(["ticker", "month"]):
        hist_dict[(t, m)] = [round(float(v), 4) for v in sub_df["ret"].tolist()]
        hist_recs_dict[(t, m)] = [
            {"year": int(r["year"]), "return": round(float(r["ret"]), 4)}
            for _, r in sub_df.sort_values("year").iterrows()
        ]

    stocks_db: dict[str, Any] = {}

    for ticker, sub in stats_df.groupby("ticker"):
        if len(sub) < 6:
            continue

        months_list: list[dict[str, Any]] = []
        month_map = {int(r["month"]): r for _, r in sub.iterrows()}

        for m in range(1, 13):
            r = month_map.get(m)
            if r is not None:
                wr = round(float(r["win_rate"]), 3)
                avg_ret = round(float(r["avg_return"]), 4)
                med_ret = round(float(r["median_return"]), 4)
                cnt = int(r["years_count"])
                hist_vals = hist_dict.get((ticker, m), [])
                hist_recs = hist_recs_dict.get((ticker, m), [])
            else:
                wr, avg_ret, med_ret, cnt, hist_vals, hist_recs = 0.0, 0.0, 0.0, 0, [], []

            months_list.append({
                "month": m,
                "win_rate": wr,
                "avg_return": avg_ret,
                "median_return": med_ret,
                "years_count": cnt,
                "history": hist_vals,
                "history_records": hist_recs,
            })

        meta = names_map.get(ticker, {})
        co_name = meta.get("company") or ticker
        market = meta.get("market") or "KOSPI"

        tags = _event_tags_for_ticker(ticker)

        best_m = max(months_list, key=lambda x: (x["win_rate"] * 0.6 + max(0, x["avg_return"]) * 0.4))

        stocks_db[ticker] = {
            "ticker": ticker,
            "company": co_name,
            "market": market,
            "months": months_list,
            "best_month": best_m["month"],
            "best_win_rate": best_m["win_rate"],
            "best_avg_return": best_m["avg_return"],
            "tags": tags,
        }

    payload = {
        "version": SEASONALITY_CACHE_VERSION,
        "updated_at": int(time.time()),
        "stocks": stocks_db,
    }

    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_seasonality_database(settings: Settings) -> dict[str, Any]:
    """In-process cache so ticker heatmap lookups do not re-parse the 40MB JSON."""
    now = time.time()
    cached = _SEASONALITY_DB_MEM.get("db")
    if cached and now - float(_SEASONALITY_DB_MEM.get("ts") or 0) < 3600:
        return cached
    db = build_seasonality_database(settings)
    _SEASONALITY_DB_MEM["db"] = db
    _SEASONALITY_DB_MEM["ts"] = now
    return db


def scan_seasonality(
    settings: Settings,
    target_month: int | None = None,
    min_win_rate: float = 0.5,
    min_avg_return: float = 0.0,
    preset: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Filter monthly seasonality or enumerate a special-event universe.

    A preset is an independent event-discovery mode. Its mapped, currently
    tradable stocks are not removed by the selected calendar month or the
    generic minimum win-rate/return controls. Historical statistics are shown
    on the preset's fixed analysis month so results remain comparable and do
    not change when the user had a different month selected beforehand.
    """
    db = get_seasonality_database(settings)
    preset_def = EVENT_PRESETS.get(str(preset or ""))
    event_mode = preset_def is not None
    allowed_set = _event_active_tickers(settings) if event_mode else _clean_active_tickers(settings)
    stocks = [
        stock
        for stock in db.get("stocks", {}).values()
        if str(stock.get("ticker") or "").zfill(6) in allowed_set
    ]

    requested_month = target_month if target_month and 1 <= target_month <= 12 else pd.Timestamp.now().month
    preset_month = int(preset_def.get("analysis_month") or requested_month) if preset_def else requested_month
    t_month = preset_month if 1 <= preset_month <= 12 else requested_month
    preset_tickers = set(preset_def.get("tickers", [])) if preset_def else set()

    results: list[dict[str, Any]] = []

    for s in stocks:
        months = s.get("months", [])
        if not months or len(months) < 12:
            continue

        month_map = {int(item.get("month") or 0): item for item in months}
        m_stat = month_map.get(t_month)
        if not m_stat:
            continue
        win_rate = m_stat["win_rate"]
        avg_ret = m_stat["avg_return"]

        if event_mode and s["ticker"] not in preset_tickers:
            continue

        # Query filter
        if query:
            q = query.strip().upper()
            if q not in s["ticker"] and q not in s["company"].upper():
                continue

        # Generic thresholds belong only to monthly discovery. Event mode must
        # show the complete mapped, tradable universe and communicate whether
        # each member is currently strong or weak through its metrics.
        if not event_mode and (win_rate < min_win_rate or avg_ret < min_avg_return):
            continue

        score = (win_rate * 50) + (min(avg_ret, 0.40) * 100) + (min(m_stat["years_count"], 4) * 2.5)

        results.append({
            "ticker": s["ticker"],
            "company": s["company"],
            "market": s["market"],
            "target_month": t_month,
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "median_return": m_stat["median_return"],
            "years_count": m_stat["years_count"],
            "history": m_stat["history"],
            "seasonality_score": round(score, 1),
            "all_months": months,
            "tags": s.get("tags", []),
            "event_mode": event_mode,
            "event_key": str(preset or "") if event_mode else None,
            "event_title": preset_def.get("title") if preset_def else None,
            "event_description": preset_def.get("description") if preset_def else None,
            "event_peak_months": preset_def.get("peak_months", []) if preset_def else [],
        })

    results.sort(key=lambda x: x["seasonality_score"], reverse=True)
    return results



def get_seasonality_highlights(settings: Settings) -> dict[str, Any]:
    """Extracts current month and next month top 3 champions + active events for dashboard widget."""
    now_m = pd.Timestamp.now().month
    next_m = 1 if now_m == 12 else now_m + 1

    cur_rows = scan_seasonality(settings, target_month=now_m, min_win_rate=0.67, min_avg_return=0.03)
    next_rows = scan_seasonality(settings, target_month=next_m, min_win_rate=0.67, min_avg_return=0.03)

    # Active presets for current or upcoming months
    active_presets = []
    for p_key, p_val in EVENT_PRESETS.items():
        if now_m in p_val["peak_months"] or next_m in p_val["peak_months"]:
            active_presets.append({
                "key": p_key,
                "title": p_val["title"],
                "description": p_val["description"],
                "peak_months": p_val["peak_months"],
                "tickers_count": len(p_val["tickers"]),
            })

    def _trim(rows, max_n=3):
        out = []
        for r in rows[:max_n]:
            out.append({
                "ticker": r["ticker"],
                "company": r["company"],
                "market": r["market"],
                "win_rate": r["win_rate"],
                "avg_return": r["avg_return"],
                "median_return": r["median_return"],
                "years_count": r["years_count"],
                "seasonality_score": r["seasonality_score"],
                "tags": r.get("tags", []),
            })
        return out

    stats = seasonality_universe_stats(settings)
    return {
        "current_month": now_m,
        "next_month": next_m,
        "current_champions": _trim(cur_rows, 3),
        "upcoming_champions": _trim(next_rows, 3),
        "active_presets": active_presets,
        "glance_top3": get_pre_entry_glance(settings, n=3, lookback_years=5),
        "universe_scanned": stats["universe_scanned"],
        "universe_listed": stats["universe_listed"],
        "markets": stats["markets"],
    }



from kr_quant.strategy.event_calendar import get_upcoming_events
from kr_quant.strategy.event_exposure import EVENT_EXPOSURES, get_stock_event_exposure


def rank_institutional_events(
    settings: Settings,
    horizon_days: int = 90,
    min_grade: str | None = None,
    group_id: str | None = None,
    confirmation_filter: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Institutional-grade 3-Pillar Event-Driven Screener (Specification v1.0)."""
    db = build_seasonality_database(settings)
    clean_set = _clean_active_tickers(settings)
    stocks_map = {
        ticker: stock
        for ticker, stock in db.get("stocks", {}).items()
        if str(ticker).zfill(6) in clean_set
    }
    events = get_upcoming_events(horizon_days=horizon_days)

    # Load recent context/snapshot metrics if available for confirmation.
    # Current runs write all_stocks.parquet; older runs used scored_all.parquet.
    scored_map = _load_scored_map(settings)
    flow_map = _load_flow_confirmation_map(settings)

    ranked_items: list[dict[str, Any]] = []

    for ev in events:
        ev_id = ev["event_id"]
        ev_group = ev["group_id"]
        if group_id and group_id != "all" and ev_group != group_id:
            continue

        target_month = pd.to_datetime(ev["target_date"]).month

        # Find target tickers: first from exposure map, or preset tickers, or top stocks
        target_tickers = []
        for t, exp_list in EVENT_EXPOSURES.items():
            if any(x["event_id"] == ev_id for x in exp_list):
                target_tickers.append(t)

        # Fallback to general universe if empty
        if not target_tickers:
            target_tickers = list(stocks_map.keys())[:50]

        for ticker in target_tickers:
            s_data = stocks_map.get(ticker)
            if not s_data:
                continue

            months = s_data.get("months", [])
            if not months or len(months) < 12:
                continue

            m_stat = months[target_month - 1]
            win_rate = float(m_stat.get("win_rate", 0))
            avg_ret = float(m_stat.get("avg_return", 0))
            med_ret = float(m_stat.get("median_return", 0))
            cnt = int(m_stat.get("years_count", 0))

            # --- PILLAR 1: Historical Edge (Max 45 pts) ---
            # 1. Win Rate (10 pts)
            p1_wr = min(win_rate * 10.0, 10.0)
            # 2. Recent Win Rate Proxy (10 pts)
            p1_rec_wr = min(win_rate * 10.0, 10.0)
            # 3. Consistency (7 pts)
            p1_cons = 7.0 if cnt >= 3 and win_rate >= 0.67 else 4.0 if cnt >= 2 else 2.0
            # 4. Median monthly return (10 pts); no benchmark alpha is inferred.
            p1_return = min(max(med_ret, 0.0) * 80.0, 10.0)
            # 5. Observed payoff (5 pts); no intramonth MDD is inferred.
            p1_payoff = 5.0 if med_ret > 0.05 else 3.0 if med_ret > 0 else 0.0
            # 6. Sample reliability (3 pts)
            p1_sample = min(cnt * 0.75, 3.0)

            score_historical = round(p1_wr + p1_rec_wr + p1_cons + p1_return + p1_payoff + p1_sample, 1)
            score_historical = min(score_historical, 45.0)

            # --- PILLAR 2: Current Confirmation (Max 35 pts) ---
            sc_row = {**scored_map.get(ticker, {}), **flow_map.get(ticker, {})}

            def _number(key: str) -> float | None:
                value = sc_row.get(key)
                if value is None:
                    return None
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None

            quant_score = _number("quant_score")
            ret_3m = _number("return_3m")
            foreign_net = _number("foreign_net")
            institution_net = _number("institution_net")
            confirmation_evidence: list[str] = []
            confirmation_missing: list[str] = []

            # EPS & Financial score proxy (11 pts)
            if quant_score is None:
                p2_eps = 0.0
                confirmation_missing.append("최신 퀀트 점수")
            else:
                p2_eps = min(max(quant_score, 0.0) * 0.13, 11.0)
                confirmation_evidence.append(f"퀀트 점수 {quant_score:.1f}")
            # Relative Strength RS20/RS60 (8 pts)
            if ret_3m is None:
                p2_rs = 0.0
                confirmation_missing.append("3개월 모멘텀")
            else:
                p2_rs = 8.0 if ret_3m > 0.05 else 5.0 if ret_3m > -0.05 else 2.0
                confirmation_evidence.append(f"3개월 수익률 {ret_3m * 100:+.1f}%")
            # Foreign/Inst Flow (7 pts)
            if foreign_net is None and institution_net is None:
                p2_flow = 0.0
                confirmation_missing.append("외국인·기관 수급")
            else:
                foreign = foreign_net or 0.0
                institution = institution_net or 0.0
                p2_flow = 7.0 if foreign > 0 and institution > 0 else 3.5 if foreign + institution > 0 else 0.0
                confirmation_evidence.append(f"외인 {foreign:+,.0f}주 · 기관 {institution:+,.0f}주")
            # No current volume/real-time confirmation source is attached here.
            p2_vol = 0.0
            p2_real = 0.0
            confirmation_missing.extend(["거래량 확인", "실시간 이벤트 확인"])

            score_current = round(p2_eps + p2_rs + p2_flow + p2_vol + p2_real, 1)

            # Confirmation State
            if not confirmation_evidence:
                confirmation_state = "WEAK"
            elif ret_3m is not None and quant_score is not None and ret_3m < -0.15 and quant_score < 50:
                confirmation_state = "CONTRADICTED"
                score_current = max(5.0, score_current - 15.0)
            elif score_current >= 20.0:
                confirmation_state = "STRONG"
            elif score_current >= 14.0:
                confirmation_state = "CONFIRMED"
            elif score_current >= 8.0:
                confirmation_state = "NEUTRAL"
            else:
                confirmation_state = "WEAK"

            score_current = min(score_current, 35.0)

            # --- PILLAR 3: Event Quality & Exposure (Max 20 pts) ---
            exp_info = get_stock_event_exposure(ticker, ev_id)
            exp_score = float(exp_info.get("exposure_score", 0.5))

            # Date Certainty (5 pts)
            p3_date = round(float(ev.get("date_certainty", 0.9)) * 5.0, 1)
            # Company Exposure (7 pts)
            p3_exp = round(exp_score * 7.0, 1)
            # Past Sensitivity (4 pts)
            p3_sens = 4.0 if exp_info.get("sensitivity") == "HIGH" else 2.5
            # Data Quality (2 pts)
            p3_qual = 2.0

            # Pre-pricing Penalty (-5 ~ -15 pts if stock already ran up > 25% in 3M without pullback)
            pre_pricing_flag = False
            pre_pricing_penalty = 0.0
            if ret_3m is not None and ret_3m > 0.30:
                pre_pricing_flag = True
                pre_pricing_penalty = 8.0

            score_event = round(p3_date + p3_exp + p3_sens + p3_qual - pre_pricing_penalty, 1)
            score_event = max(0.0, min(score_event, 20.0))

            # --- FINAL SEASONALITY SCORE (100 pts) ---
            final_score = round(score_historical + score_current + score_event, 1)
            final_score = max(0.0, min(100.0, final_score))

            # Grade Mapping
            if final_score >= 90.0:
                grade = "S+"
            elif final_score >= 85.0:
                grade = "S"
            elif final_score >= 80.0:
                grade = "A+"
            elif final_score >= 75.0:
                grade = "A"
            elif final_score >= 65.0:
                grade = "B"
            elif final_score >= 55.0:
                grade = "C"
            else:
                grade = "D"

            # Filters
            if min_grade:
                grade_order = {"S+": 6, "S": 5, "A+": 4, "A": 3, "B": 2, "C": 1, "D": 0}
                if grade_order.get(grade, 0) < grade_order.get(min_grade, 0):
                    continue

            if confirmation_filter and confirmation_filter != "all":
                if confirmation_state != confirmation_filter:
                    continue

            if query:
                q = query.strip().upper()
                if q not in ticker and q not in s_data["company"].upper() and q not in ev["title"].upper():
                    continue

            ranked_items.append({
                "ticker": ticker,
                "company": s_data["company"],
                "market": s_data["market"],
                "event_id": ev_id,
                "event_group": ev_group,
                "event_group_name": ev["group_name"],
                "event_title": ev["title"],
                "target_date": ev["target_date"],
                "d_day": ev["d_day"],
                "horizon_tag": ev["horizon_tag"],
                "seasonality_score": final_score,
                "grade": grade,
                "confirmation_state": confirmation_state,
                "score_breakdown": {
                    "historical_edge": score_historical,
                    "current_confirmation": score_current,
                    "event_quality": score_event,
                },
                "current_confirmation_evidence": confirmation_evidence,
                "current_confirmation_missing": confirmation_missing,
                "win_rate": win_rate,
                "avg_return": avg_ret,
                "median_return": med_ret,
                "years_count": cnt,
                "exposure_desc": exp_info.get("exposure_desc", ""),
                "pre_pricing_flag": pre_pricing_flag,
                "optimal_entry_window": ev["default_entry_window"],
                "optimal_exit_window": ev["default_exit_window"],
                "invalidating_rule": ev["invalidating_rule"],
                "binary_risk": ev["binary_risk"],
            })

    ranked_items.sort(key=lambda x: x["seasonality_score"], reverse=True)
    return ranked_items



from kr_quant.strategy.discovery_engine import pattern_from_month_stat, SeasonalityPattern
from kr_quant.strategy.event_explainer import explain_and_score_pattern


def _enrich_remaining_peak_rows(
    settings: Settings,
    rows: list[dict[str, Any]],
    *,
    lookback_years: int,
) -> list[dict[str, Any]]:
    """Attach current-price-to-peak estimates without persisting date-sensitive values."""
    if not rows:
        return []

    price_path = next(
        (path for path in (settings.staged_dir / "live" / "prices.parquet", settings.staged_dir / "demo" / "prices.parquet") if path.exists()),
        None,
    )
    signature = (
        str(price_path),
        price_path.stat().st_mtime_ns,
        price_path.stat().st_size,
        date.today().isoformat(),
    ) if price_path is not None else None
    requested: list[tuple[dict[str, Any], str, int, tuple[str, int, int]]] = []
    for source in rows:
        row = dict(source)
        ticker = str(row.get("ticker") or "").zfill(6)
        try:
            target_month = int(str(row.get("window_name") or "").replace("월", ""))
        except (TypeError, ValueError):
            target_month = int(row.get("target_start_month") or pd.Timestamp.now().month)
        requested.append((row, ticker, target_month, (ticker, target_month, int(lookback_years))))

    # The seasonality page requests highlights, discovery, themes and the Tier-1
    # briefing concurrently.  Without a lock each request can start the same
    # full-universe daily-path calculation before the shared cache is warm.
    # Serialize only the cache fill; subsequent readers reuse the completed
    # ticker/month metrics immediately.
    with _REMAINING_PEAK_LOCK:
        if _REMAINING_PEAK_CACHE.get("signature") != signature:
            _REMAINING_PEAK_CACHE["signature"] = signature
            _REMAINING_PEAK_CACHE["values"] = {}
        metric_cache: dict[tuple[str, int, int], dict[str, Any]] = _REMAINING_PEAK_CACHE["values"]

        missing_tickers = {ticker for _, ticker, _, key in requested if key not in metric_cache}
        by_ticker: dict[str, pd.DataFrame] = {}
        if missing_tickers:
            try:
                prices = _prices(settings, tickers=list(missing_tickers))
            except TypeError:
                prices = _prices(settings)
            if prices is not None and not prices.empty and "ticker" in prices.columns:
                ticker_values = prices["ticker"].astype(str).str.zfill(6)
                work = prices.loc[ticker_values.isin(missing_tickers)].copy()
                work["ticker"] = ticker_values.loc[work.index]
                by_ticker = {ticker: group.copy() for ticker, group in work.groupby("ticker", sort=False)}

        for _, ticker, target_month, cache_key in requested:
            if cache_key not in metric_cache:
                metric_cache[cache_key] = calculate_remaining_peak_upside(
                    by_ticker.get(ticker, pd.DataFrame()),
                    ticker,
                    target_month,
                    lookback_years=lookback_years,
                )

    enriched: list[dict[str, Any]] = []
    for row, ticker, target_month, cache_key in requested:
        metrics = metric_cache[cache_key]
        row["remaining_peak"] = metrics
        if metrics.get("available") is True and metrics.get("target_peak_date"):
            row["entry_window_str"] = metrics.get("entry_window_str")
            row["exit_window_str"] = metrics.get("exit_window_str")
            row["entry_stage"] = metrics.get("entry_stage")
            row["entry_stage_label"] = metrics.get("entry_stage_label")
            row["historical_peak_day"] = metrics.get("historical_peak_day")
            playbook = dict(row.get("playbook") or {})
            p50 = metrics.get("remaining_p50")
            downside = metrics.get("downside_before_peak_p50")
            peak_text = f", 오늘 기준 역사적 중앙값 상승여력 {p50 * 100:+.1f}%" if p50 is not None else ""
            risk_text = f"역사적 피크 전 중앙값 하방 {downside * 100:.1f}%" if downside is not None else "가격·거래량 무효화 조건"
            playbook.update({
                "entry_timing": f"실측 피크 역산 진입 관찰 구간: {metrics.get('entry_window_str')}",
                "exit_timing": f"역사적 피크 감시 구간: {metrics.get('exit_window_str')}{peak_text}",
                "stop_loss": f"리스크 참고: {risk_text}. 거래정지·거래량 0·가격 지연 시 산출값을 사용하지 않습니다.",
                "recommendation": "현재가 이후 남은 경로를 과거 동일 계절 진행시점과 비교합니다. 목표가가 아닌 역사적 분포 추정치입니다.",
            })
            row["playbook"] = playbook
        enriched.append(row)
    return enriched


def scan_seasonality_discovery(
    settings: Settings,
    horizon_days: int = 90,
    min_grade: str | None = None,
    status_filter: str | None = None,
    query: str | None = None,
    lookback_years: int = 5,
    exclude_expired: bool = False,
) -> list[dict[str, Any]]:
    """Price-First Seasonality Discovery & AI Explanation Engine (Specification v1.1) with Lookback selection."""
    cache_dir = settings.data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # The cache schema includes the explanation text. Bump the filename when
    # the fallback catalyst logic changes so stale generic comments cannot be
    # served after deployment.
    cache_file = cache_dir / f"discovery_cache_lb_{lookback_years}_v{DISCOVERY_CACHE_VERSION}.json"
    cached_list: list[dict[str, Any]] = []

    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                if isinstance(c_data, list) and len(c_data) > 0:
                    cached_list = c_data
        except Exception:
            cached_list = []

    if not cached_list:
        db = build_seasonality_database(settings)
        stocks_map = db.get("stocks", {})

        scored_map = _load_scored_map(settings)
        flow_map = _load_flow_confirmation_map(settings)

        all_patterns: list[dict[str, Any]] = []

        for ticker, s_info in stocks_map.items():
            company = s_info.get("company", ticker)
            market = s_info.get("market", "KOSPI")
            months = s_info.get("months", [])
            sc_row = {**scored_map.get(ticker, {}), **flow_map.get(ticker, {})}

            for m_stat in months:
                pat = pattern_from_month_stat(ticker, company, market, m_stat, lookback_years=lookback_years)
                if pat and pat.win_rate >= 0.50 and pat.sample_count >= 2:
                    exp_res = explain_and_score_pattern(pat, sc_row)
                    all_patterns.append(exp_res)

        all_patterns.sort(key=lambda x: x["seasonality_score"], reverse=True)
        cached_list = all_patterns

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cached_list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    meta = ticker_meta_map(settings)
    clean_set = _clean_active_tickers(settings)
    cached_list = [item for item in cached_list if str(item.get("ticker", "")).zfill(6) in clean_set]

    for item in cached_list:
        _apply_market_meta(item, meta)

    # Filter by horizon: target month within today + horizon_days
    now_m = pd.Timestamp.now().month
    target_months = []
    for d in range(0, horizon_days + 1, 15):
        m = (pd.Timestamp.now() + pd.Timedelta(days=d)).month
        if m not in target_months:
            target_months.append(m)

    filtered = []
    grade_order = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}

    for item in cached_list:
        w_name = item.get("window_name", "")
        try:
            item_m = int(w_name.replace("월", ""))
        except Exception:
            item_m = now_m

        if item_m not in target_months:
            continue

        if min_grade and grade_order.get(item.get("grade", "D"), 0) < grade_order.get(min_grade, 0):
            continue

        if status_filter and status_filter != "all" and item.get("current_status") != status_filter:
            continue

        if query:
            q = query.strip().upper()
            if q not in item["ticker"] and q not in item["company"].upper() and q not in item["common_event_cluster"].upper():
                continue

        filtered.append(dict(item))

    filtered = _enrich_remaining_peak_rows(settings, filtered, lookback_years=lookback_years)
    if exclude_expired:
        filtered = [item for item in filtered if item.get("entry_stage") != "SEASON_END"]

    filtered.sort(key=lambda x: x["seasonality_score"], reverse=True)
    ranked = rank_pre_entry_candidates(settings, filtered)
    rank_map = {
        (str(item.get("ticker") or "").zfill(6), str(item.get("pattern_id") or "")): item
        for item in ranked
    }
    for item in filtered:
        key = (str(item.get("ticker") or "").zfill(6), str(item.get("pattern_id") or ""))
        canonical = rank_map.get(key)
        item["pre_entry_rank"] = canonical.get("pre_entry_rank") if canonical else None
        item["last_close"] = canonical.get("last_close") if canonical else None
        item["chg_pct"] = canonical.get("chg_pct") if canonical else None
        item["price_as_of"] = canonical.get("price_as_of") if canonical else None
    return filtered


def _latest_quotes(settings: Settings, tickers: list[str]) -> dict[str, dict[str, Any]]:
    wanted = {str(t).zfill(6) for t in tickers if t}
    if not wanted:
        return {}
    prices = _prices(settings)
    if prices is None or prices.empty or "ticker" not in prices.columns:
        return {}
    df = prices.copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df[df["ticker"].isin(wanted)]
    if df.empty:
        return {}
    date_col = "trade_date" if "trade_date" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(["ticker", date_col])
    out: dict[str, dict[str, Any]] = {}
    for ticker, g in df.groupby("ticker"):
        last = g.iloc[-1]
        prev = g.iloc[-2] if len(g) >= 2 else last
        close = float(last["close"]) if pd.notna(last.get("close")) else None
        prev_close = float(prev["close"]) if pd.notna(prev.get("close")) else close
        chg = ((close - prev_close) / prev_close) if close and prev_close else 0.0
        as_of = last[date_col]
        out[str(ticker)] = {
            "last_close": round(close, 2) if close is not None else None,
            "chg_pct": round(float(chg), 4),
            "as_of": str(as_of.date()) if hasattr(as_of, "date") else str(as_of)[:10],
        }
    return out


def rank_pre_entry_candidates(settings: Settings, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the canonical pre-entry order used by dashboard and calendar.

    Entry urgency is the primary key, then the historical seasonality score and
    current-price-to-peak median.  Tradability and a valid remaining-peak model
    are required, so a card cannot appear on one screen but disappear on the
    other because of duplicated client-side rules.
    """
    allowed = {key for key, weight in PRE_ENTRY_STAGE_WEIGHT.items() if weight >= 40}
    clean_set = _clean_active_tickers(settings)
    candidates = [dict(row) for row in rows if row.get("entry_stage") in allowed]
    quotes = _latest_quotes(settings, [row.get("ticker") for row in candidates])
    valid_rows: list[dict[str, Any]] = []
    for row in candidates:
        ticker = str(row.get("ticker") or "").zfill(6)
        if ticker not in clean_set:
            continue
        remaining = row.get("remaining_peak") or {}
        if not bool(remaining.get("available")):
            continue
        quote = quotes.get(ticker, {})
        close = quote.get("last_close")
        if close is None or close < 1000.0:
            continue
        row["last_close"] = close
        row["chg_pct"] = quote.get("chg_pct")
        row["price_as_of"] = quote.get("as_of")
        valid_rows.append(row)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        remaining = row.get("remaining_peak") or {}
        remaining_p50 = remaining.get("remaining_p50")
        return (
            -PRE_ENTRY_STAGE_WEIGHT.get(str(row.get("entry_stage") or ""), 0),
            -float(row.get("seasonality_score") or 0),
            -float(remaining_p50 if remaining_p50 is not None else -99),
            str(row.get("ticker") or ""),
            str(row.get("pattern_id") or ""),
        )

    valid_rows.sort(key=sort_key)
    for index, row in enumerate(valid_rows, start=1):
        row["pre_entry_rank"] = index
    return valid_rows


def get_pre_entry_glance(settings: Settings, n: int = 3, lookback_years: int = 5) -> list[dict[str, Any]]:
    """Android Glance Top 3 equivalent: stage-weighted pre-entry picks with last price."""
    rows = scan_seasonality_discovery(
        settings,
        horizon_days=90,
        lookback_years=lookback_years,
        exclude_expired=True,
    )
    valid_rows = [row for row in rows if row.get("pre_entry_rank") is not None]
    valid_rows.sort(key=lambda row: int(row.get("pre_entry_rank") or 10**9))
    top = valid_rows[: max(0, n)]
    glance: list[dict[str, Any]] = []
    for idx, r in enumerate(top, start=1):
        glance.append({
            "rank": idx,
            "pattern_id": r.get("pattern_id"),
            "ticker": r.get("ticker"),
            "company": r.get("company"),
            "market": r.get("market"),
            "win_rate": r.get("win_rate"),
            "expected_p50": r.get("expected_p50") or r.get("median_return"),
            "remaining_peak": r.get("remaining_peak"),
            "seasonality_score": r.get("seasonality_score"),
            "entry_stage": r.get("entry_stage"),
            "entry_stage_label": r.get("entry_stage_label"),
            "window_name": r.get("window_name"),
            "entry_window_str": r.get("entry_window_str"),
            "exit_window_str": r.get("exit_window_str"),
            "common_event_cluster": r.get("common_event_cluster"),
            "last_close": r.get("last_close"),
            "chg_pct": r.get("chg_pct"),
            "price_as_of": r.get("price_as_of"),
        })
    return glance
