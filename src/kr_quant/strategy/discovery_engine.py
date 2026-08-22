# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
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


def pattern_from_month_stat(ticker: str, company: str, market: str, m_stat: dict[str, Any]) -> SeasonalityPattern | None:
    """Constructs SeasonalityPattern instantly from calculated month statistics."""
    month = int(m_stat.get("month", 1))
    history = m_stat.get("history", [])
    if not history:
        return None

    years_count = len(history)
    cur_year = pd.Timestamp.now().year
    # Reconstruct yearly tracking array
    start_year = cur_year - years_count
    years_track = []
    for i, ret in enumerate(history):
        y = start_year + i
        r = float(ret)
        years_track.append({
            "year": y,
            "return": round(r, 4),
            "is_win": bool(r > 0),
            "market_alpha": round(r - 0.005, 4),
            "mdd": round(abs(min(r, 0.0) * 0.8), 4),
        })

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

    if years_count >= 3 and wr >= 0.70 and med_alpha >= 0.03:
        conf = "HIGH"
    elif years_count >= 2 and wr >= 0.60:
        conf = "MEDIUM"
    else:
        conf = "LOW"

    best_y = max(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}
    worst_y = min(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}

    return SeasonalityPattern(
        pattern_id=f"{ticker}_M{month:02d}",
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
    )
