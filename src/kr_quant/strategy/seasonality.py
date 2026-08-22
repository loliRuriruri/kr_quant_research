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

    names_map: dict[str, dict[str, str]] = {}
    if "company" in df.columns:
        for _, row in df[["ticker", "company"]].drop_duplicates(subset=["ticker"]).iterrows():
            names_map[str(row["ticker"]).zfill(6)] = {
                "company": str(row.get("company") or ""),
                "market": "KOSPI",
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

    return {
        "current_month": now_m,
        "next_month": next_m,
        "current_champions": _trim(cur_rows, 3),
        "upcoming_champions": _trim(next_rows, 3),
        "active_presets": active_presets,
    }
