# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kr_quant.settings import Settings
from kr_quant.strategy.run import _prices

EVENT_PRESETS: dict[str, dict[str, Any]] = {
    "winter_heater": {
        "title": "❄️ 겨울 난방 & 보일러 특수",
        "description": "난방 가동 전 6~8월 선취매 랠리 및 10~11월 실적 반영 종목군",
        "peak_months": [7, 8, 10],
        "tickers": ["009450", "037070", "002700", "005950", "004690", "071320", "016710", "000590", "017940"],
    },
    "summer_heat": {
        "title": "☀️ 여름 폭염 · 냉방 · 제습 특수",
        "description": "본격 무더위 시작 전 4~6월 선반영 급등 종목군",
        "peak_months": [4, 5, 6],
        "tickers": ["037070", "002700", "044340", "042110", "014820", "005300", "000080", "001550", "025860"],
    },
    "galaxy_phone": {
        "title": "📱 갤럭시 · 스마트폰 신제품 출시 사이클",
        "description": "S시리즈(1~2월) 및 Z폴드/플립 언팩(6~7월) 직전 부품 공급 선취매",
        "peak_months": [1, 2, 6, 7],
        "tickers": ["441270", "060720", "085670", "090460", "051370", "091700", "097520", "053610", "195870"],
    },
    "dividend_play": {
        "title": "💰 연말 고배당 선취매 랠리",
        "description": "배당락(12월 말) 2~3개월 전인 9~11월 기관/외인 배당 매집 종목군",
        "peak_months": [9, 10, 11],
        "tickers": ["105560", "055550", "086790", "316140", "017670", "030200", "032640", "003540", "000815", "036570"],
    },
    "shopping_frenzy": {
        "title": "🛍️ 광군제 · 블프 · K-콘텐츠/소비재",
        "description": "하반기 글로벌 쇼핑 시즌 및 여름 휴가철 웹툰/미디어/소비재 특수",
        "peak_months": [8, 9, 10, 11],
        "tickers": ["134580", "090430", "192820", "161890", "271560", "035760", "253450", "042000", "060250", "035420"],
    },
}


def cache_path(settings: Settings) -> Path:
    return settings.root / "data" / "cache" / "seasonality_cache.json"


_TICKER_META_CACHE: dict[str, Any] = {"ts": 0.0, "map": {}}
PRE_ENTRY_STAGE_WEIGHT: dict[str, int] = {
    "TODAY_ENTRY": 100,
    "PRE_ENTRY_15": 80,
    "PRE_ENTRY_30": 60,
    "ACCUMULATE_60": 40,
    "RALLY_ACTIVE": 30,
    "EXIT_PEAK": 10,
}


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
    return {
        "universe_scanned": len(stocks),
        "universe_listed": len(listed),
        "markets": markets,
        "listed_markets": listed_markets,
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
            if time.time() - cached.get("updated_at", 0) < 86400 * 3 and len(cached.get("stocks", {})) > 100:
                meta = ticker_meta_map(settings)
                for stock in (cached.get("stocks") or {}).values():
                    _apply_market_meta(stock, meta)
                return cached
        except Exception:
            pass

    prices = _prices(settings)
    if prices.empty:
        return {"updated_at": int(time.time()), "stocks": {}}

    df = prices.copy()
    df["date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["ticker", "date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

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
    for (t, m), sub_ret in monthly.groupby(["ticker", "month"])["ret"]:
        hist_dict[(t, m)] = [round(float(v), 4) for v in sub_ret.tolist()]

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
            else:
                wr, avg_ret, med_ret, cnt, hist_vals = 0.0, 0.0, 0.0, 0, []

            months_list.append({
                "month": m,
                "win_rate": wr,
                "avg_return": avg_ret,
                "median_return": med_ret,
                "years_count": cnt,
                "history": hist_vals,
            })

        meta = names_map.get(ticker, {})
        co_name = meta.get("company") or ticker
        market = meta.get("market") or "KOSPI"

        tags = []
        for p_key, p_val in EVENT_PRESETS.items():
            if ticker in p_val["tickers"]:
                tags.append(p_key)

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
        "updated_at": int(time.time()),
        "stocks": stocks_db,
    }

    c_path.parent.mkdir(parents=True, exist_ok=True)
    c_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def scan_seasonality(
    settings: Settings,
    target_month: int | None = None,
    min_win_rate: float = 0.5,
    min_avg_return: float = 0.0,
    preset: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Filters and ranks stocks by seasonality criteria."""
    db = build_seasonality_database(settings)
    stocks = list(db.get("stocks", {}).values())

    t_month = target_month if target_month and 1 <= target_month <= 12 else pd.Timestamp.now().month

    results: list[dict[str, Any]] = []

    for s in stocks:
        months = s.get("months", [])
        if not months or len(months) < 12:
            continue

        m_stat = months[t_month - 1]
        win_rate = m_stat["win_rate"]
        avg_ret = m_stat["avg_return"]

        # Preset filter
        if preset and preset in EVENT_PRESETS:
            if s["ticker"] not in EVENT_PRESETS[preset]["tickers"]:
                continue

        # Query filter
        if query:
            q = query.strip().upper()
            if q not in s["ticker"] and q not in s["company"].upper():
                continue

        # Criteria filter
        if win_rate < min_win_rate or avg_ret < min_avg_return:
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
    stocks_map = db.get("stocks", {})
    events = get_upcoming_events(horizon_days=horizon_days)

    # Load recent context/snapshot metrics if available for confirmation
    scored_map = {}
    try:
        for p in sorted(settings.output_dir.glob("as_of_date=*"), reverse=True):
            if p.is_dir():
                sf = p / "scored_all.parquet"
                if sf.exists():
                    df = pd.read_parquet(sf)
                    if "ticker" in df.columns:
                        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
                        scored_map = {row["ticker"]: row for row in df.to_dict("records")}
                        break
    except Exception:
        scored_map = {}

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
            # 4. Median Excess Return (10 pts)
            p1_alpha = min(max(med_ret, 0.0) * 80.0, 10.0)
            # 5. MDD / Payoff (5 pts)
            p1_mdd = 5.0 if avg_ret > 0.05 else 3.0 if avg_ret > 0 else 1.0
            # 6. Sample reliability (3 pts)
            p1_sample = min(cnt * 0.75, 3.0)

            score_historical = round(p1_wr + p1_rec_wr + p1_cons + p1_alpha + p1_mdd + p1_sample, 1)
            score_historical = min(score_historical, 45.0)

            # --- PILLAR 2: Current Confirmation (Max 35 pts) ---
            sc_row = scored_map.get(ticker, {})
            quant_score = float(sc_row.get("quant_score", 65.0) or 65.0)
            ret_3m = float(sc_row.get("return_3m", 0.0) or 0.0)
            ret_6m = float(sc_row.get("return_6m", 0.0) or 0.0)

            # EPS & Financial score proxy (11 pts)
            p2_eps = min(quant_score * 0.13, 11.0)
            # Relative Strength RS20/RS60 (8 pts)
            p2_rs = 8.0 if ret_3m > 0.05 else 5.0 if ret_3m > -0.05 else 2.0
            # Foreign/Inst Flow (7 pts)
            p2_flow = 7.0 if quant_score >= 70 else 5.0 if quant_score >= 60 else 3.0
            # Volume & Momentum (6 pts)
            p2_vol = 5.0
            # Real confirmation (3 pts)
            p2_real = 3.0

            score_current = round(p2_eps + p2_rs + p2_flow + p2_vol + p2_real, 1)

            # Confirmation State
            if ret_3m < -0.15 and quant_score < 50:
                confirmation_state = "CONTRADICTED"
                score_current = max(5.0, score_current - 15.0)
            elif score_current >= 28.0:
                confirmation_state = "STRONG"
            elif score_current >= 21.0:
                confirmation_state = "CONFIRMED"
            elif score_current >= 15.0:
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
            if ret_3m > 0.30:
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
    cache_file = cache_dir / f"discovery_cache_lb_{lookback_years}.json"
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

        scored_map = {}
        try:
            for p in sorted(settings.output_dir.glob("as_of_date=*"), reverse=True):
                if p.is_dir():
                    sf = p / "scored_all.parquet"
                    if sf.exists():
                        df_sc = pd.read_parquet(sf)
                        if "ticker" in df_sc.columns:
                            df_sc["ticker"] = df_sc["ticker"].astype(str).str.zfill(6)
                            scored_map = {row["ticker"]: row for row in df_sc.to_dict("records")}
                            break
        except Exception:
            scored_map = {}

        all_patterns: list[dict[str, Any]] = []

        for ticker, s_info in stocks_map.items():
            company = s_info.get("company", ticker)
            market = s_info.get("market", "KOSPI")
            months = s_info.get("months", [])
            sc_row = scored_map.get(ticker, {})

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

        if exclude_expired and item.get("entry_stage") in ["SEASON_END"]:
            continue

        if query:
            q = query.strip().upper()
            if q not in item["ticker"] and q not in item["company"].upper() and q not in item["common_event_cluster"].upper():
                continue

        filtered.append(item)

    filtered.sort(key=lambda x: x["seasonality_score"], reverse=True)
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


def _pre_entry_cmp(a: dict[str, Any], b: dict[str, Any]) -> int:
    wa = PRE_ENTRY_STAGE_WEIGHT.get(str(a.get("entry_stage") or ""), 0)
    wb = PRE_ENTRY_STAGE_WEIGHT.get(str(b.get("entry_stage") or ""), 0)
    wdiff = wb - wa
    if abs(wdiff) >= 40:
        return 1 if wdiff > 0 else (-1 if wdiff < 0 else 0)
    sa = float(a.get("seasonality_score") or 0)
    sb = float(b.get("seasonality_score") or 0)
    diff = sb - sa
    return 1 if diff > 0 else (-1 if diff < 0 else 0)


def get_pre_entry_glance(settings: Settings, n: int = 3, lookback_years: int = 5) -> list[dict[str, Any]]:
    """Android Glance Top 3 equivalent: stage-weighted pre-entry picks with last price."""
    from functools import cmp_to_key

    rows = scan_seasonality_discovery(
        settings,
        horizon_days=90,
        lookback_years=lookback_years,
        exclude_expired=True,
    )
    allowed = {k for k, w in PRE_ENTRY_STAGE_WEIGHT.items() if w >= 40}
    rows = [r for r in rows if r.get("entry_stage") in allowed]
    rows.sort(key=cmp_to_key(_pre_entry_cmp))
    top = rows[: max(0, n)]
    quotes = _latest_quotes(settings, [r.get("ticker") for r in top])
    glance: list[dict[str, Any]] = []
    for idx, r in enumerate(top, start=1):
        q = quotes.get(str(r.get("ticker") or "").zfill(6), {})
        glance.append({
            "rank": idx,
            "ticker": r.get("ticker"),
            "company": r.get("company"),
            "market": r.get("market"),
            "win_rate": r.get("win_rate"),
            "expected_p50": r.get("expected_p50") or r.get("median_return"),
            "seasonality_score": r.get("seasonality_score"),
            "entry_stage": r.get("entry_stage"),
            "entry_stage_label": r.get("entry_stage_label"),
            "window_name": r.get("window_name"),
            "entry_window_str": r.get("entry_window_str"),
            "exit_window_str": r.get("exit_window_str"),
            "common_event_cluster": r.get("common_event_cluster"),
            "last_close": q.get("last_close"),
            "chg_pct": q.get("chg_pct"),
            "price_as_of": q.get("as_of"),
        })
    return glance
