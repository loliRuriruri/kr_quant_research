# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SeasonalityPattern:
    pattern_id: str
    ticker: str
    company: str
    market: str
    window_type: str  # monthly, mid_month, 20d, 40d, 60d
    window_name: str  # e.g. "8월", "7/15 ~ 8/15"
    target_start_month: int
    target_start_day: int
    target_end_month: int
    target_end_day: int
    sample_count: int
    lookback_years: int | None
    win_rate: float
    mean_return: float
    median_return: float
    median_alpha: float
    avg_mdd: float
    best_year: dict[str, Any]
    worst_year: dict[str, Any]
    recent_3y_win_rate: float
    recent_3y_median_alpha: float
    recent_5y_win_rate: float
    years_track: list[dict[str, Any]]
    failed_years: list[dict[str, Any]]
    pattern_confidence: str  # HIGH, MEDIUM, LOW
    # Playbook & Timing fields (Mobile dashboard integration)
    entry_stage: str
    entry_stage_label: str
    entry_window_str: str
    exit_window_str: str
    expected_p50: float
    expected_p90: float
    profit_factor: float
    playbook: dict[str, str]


def pattern_from_month_stat(
    ticker: str,
    company: str,
    market: str,
    m_stat: dict[str, Any],
    lookback_years: int | None = None,
    as_of_date: str | None = None,
) -> SeasonalityPattern | None:
    """Constructs SeasonalityPattern dynamically with Pre-Entry Playbook & Timing calculations."""
    month = int(m_stat.get("month", 1))
    hist_recs = m_stat.get("history_records", [])
    history = m_stat.get("history", [])

    if not hist_recs and not history:
        return None

    years_track = []
    if hist_recs:
        if lookback_years and lookback_years > 0:
            hist_slice = hist_recs[-lookback_years:]
        else:
            hist_slice = hist_recs

        for hr in hist_slice:
            y = int(hr.get("year", 2024))
            r = float(hr.get("return", 0.0))
            years_track.append({
                "year": y,
                "return": round(r, 4),
                "is_win": bool(r > 0),
                "market_alpha": round(r - 0.005, 4),
                "mdd": round(abs(min(r, 0.0) * 0.8), 4),
            })
    else:
        if lookback_years and lookback_years > 0:
            history_slice = history[-lookback_years:]
        else:
            history_slice = history

        years_count = len(history_slice)
        if years_count == 0:
            return None

        cur_year = pd.Timestamp.now().year
        start_year = cur_year - years_count

        for i, ret in enumerate(history_slice):
            y = start_year + i
            r = float(ret)
            years_track.append({
                "year": y,
                "return": round(r, 4),
                "is_win": bool(r > 0),
                "market_alpha": round(r - 0.005, 4),
                "mdd": round(abs(min(r, 0.0) * 0.8), 4),
            })

    years_count = len(years_track)
    if years_count == 0:
        return None

    rets = [r["return"] for r in years_track]
    alphas = [r["market_alpha"] for r in years_track]
    wins = [r for r in years_track if r["is_win"]]
    fails = [r for r in years_track if not r["is_win"]]

    wr = len(wins) / len(years_track) if years_track else 0.0
    med_ret = float(np.median(rets)) if rets else 0.0
    med_alpha = float(np.median(alphas)) if alphas else 0.0
    avg_mdd = float(np.mean([r["mdd"] for r in years_track])) if years_track else 0.0

    recent_3y = years_track[-3:] if len(years_track) >= 3 else years_track
    r3_wr = len([r for r in recent_3y if r["is_win"]]) / len(recent_3y) if recent_3y else wr
    r3_alpha = float(np.median([r["market_alpha"] for r in recent_3y])) if recent_3y else med_alpha

    recent_5y = years_track[-5:] if len(years_track) >= 5 else years_track
    r5_wr = len([r for r in recent_5y if r["is_win"]]) / len(recent_5y) if recent_5y else wr

    # Pattern Confidence
    if years_count >= 5 and wr >= 0.75 and med_alpha >= 0.03:
        conf = "HIGH"
    elif years_count >= 3 and wr >= 0.67:
        conf = "HIGH"
    elif years_count >= 2 and wr >= 0.60:
        conf = "MEDIUM"
    else:
        conf = "LOW"

    cur_year = pd.Timestamp.now().year
    best_y = max(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}
    worst_y = min(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}

    # Expected Return Quantiles & Profit Factor
    p50_ret = round(float(np.percentile(rets, 50)), 4) if rets else med_ret
    p90_ret = round(float(np.percentile(rets, 90)), 4) if len(rets) >= 3 else round(max(rets, default=med_ret), 4)
    pos_rets = sum([r for r in rets if r > 0])
    neg_rets = abs(sum([r for r in rets if r < 0]))
    profit_factor = round(pos_rets / neg_rets, 1) if neg_rets > 0.0001 else (9.9 if pos_rets > 0 else 1.0)

    # Calculate Entry Timing Stage and Windows based on current calendar date
    ref_dt = pd.to_datetime(as_of_date).date() if as_of_date else date.today()
    cur_m = ref_dt.month
    cur_d = ref_dt.day

    # Target seasonality window: month M (01 ~ 28)
    # Entry Window: 15~20 days before target month start
    # Exit Window: middle/end of target month or following month
    entry_m = month - 1 if month > 1 else 12
    entry_window_str = f"{entry_m:02d}/15 ~ {month:02d}/05"
    exit_window_str = f"{month:02d}/20 ~ {(month % 12) + 1:02d}/10"

    # Compute D-Day from ref_dt to target month start
    target_year = ref_dt.year if month >= cur_m else ref_dt.year + 1
    target_dt = date(target_year, month, 1)
    d_days = (target_dt - ref_dt).days

    if cur_m == month:
        entry_stage = "TODAY_ENTRY"
        entry_stage_label = "🔥 오늘 진입 (D-0)"
    elif 0 < d_days <= 15:
        entry_stage = "PRE_ENTRY_15"
        entry_stage_label = f"⚡ 선취매 적기 (D-{d_days})"
    elif 15 < d_days <= 35:
        entry_stage = "PRE_ENTRY_30"
        entry_stage_label = f"⚡ 선취매 구간 (D-{d_days})"
    elif 35 < d_days <= 65:
        entry_stage = "ACCUMULATE_60"
        entry_stage_label = f"🎯 매집 윈도우 (D-{d_days})"
    elif d_days < 0 and abs(d_days) <= 25:
        entry_stage = "EXIT_PEAK"
        entry_stage_label = "💰 피크 엑시트/매도"
    else:
        entry_stage = "WATCH"
        entry_stage_label = f"👀 관찰 (D-{d_days})"

    # Playbook rules
    target_alpha_str = f"+{med_alpha * 100:.1f}%" if med_alpha > 0 else "+10.0%"
    mdd_stop_str = f"-{avg_mdd * 100:.1f}%" if avg_mdd > 0 else "-5.0%"

    playbook = {
        "entry_timing": f"권장 선취매 타이밍: 피크 구간({month:02d}/01) 도달 D-30일 ~ D-15일 전 분할 매수",
        "exit_timing": f"목표 엑시트 시기: 계절성 피크({month:02d}/25) 도달 시점 또는 목표 알파({target_alpha_str}) 달성 시 분할 매도",
        "stop_loss": f"리스크 방어 기준: 평균 MDD({mdd_stop_str}) 초과 하락 또는 외국인/기관 대규모 순매도 전환 시 손절",
        "recommendation": f"반복 상승 Window({entry_window_str}) 진입 시 분할 매수 및 계절성 목표가 대응 유효",
    }

    return SeasonalityPattern(
        pattern_id=f"{ticker}_M{month:02d}_L{lookback_years or 0}",
        ticker=ticker,
        company=company,
        market=market,
        window_type="monthly",
        window_name=f"{month}월",
        target_start_month=month,
        target_start_day=1,
        target_end_month=month,
        target_end_day=28,
        sample_count=years_count,
        lookback_years=lookback_years,
        win_rate=round(wr, 3),
        mean_return=round(float(np.mean(rets)), 4),
        median_return=round(med_ret, 4),
        median_alpha=round(med_alpha, 4),
        avg_mdd=round(avg_mdd, 4),
        best_year=best_y,
        worst_year=worst_y,
        recent_3y_win_rate=round(r3_wr, 3),
        recent_3y_median_alpha=round(r3_alpha, 4),
        recent_5y_win_rate=round(r5_wr, 3),
        years_track=years_track,
        failed_years=fails,
        pattern_confidence=conf,
        entry_stage=entry_stage,
        entry_stage_label=entry_stage_label,
        entry_window_str=entry_window_str,
        exit_window_str=exit_window_str,
        expected_p50=p50_ret,
        expected_p90=p90_ret,
        profit_factor=profit_factor,
        playbook=playbook,
    )
