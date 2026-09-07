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
    lookback_years: int | None
    win_rate: float
    mean_return: float
    median_return: float
    median_alpha: float | None
    avg_mdd: float | None
    best_year: dict[str, Any]
    worst_year: dict[str, Any]
    recent_3y_win_rate: float
    recent_3y_median_alpha: float | None
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

    # Explicit historical callers must not depend on the machine's current year.
    # The default legacy path is preserved for existing production callers.
    cutoff = None
    if as_of_date is not None:
        cutoff = pd.Timestamp(as_of_date)
        if pd.isna(cutoff):
            raise ValueError("Invalid as_of_date")
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_convert("Asia/Seoul").tz_localize(None)
        cutoff = cutoff.normalize()
        if not 1 <= month <= 12:
            raise ValueError("Invalid month")
        if not hist_recs:
            raise ValueError("Historical replay requires explicit history_records years")
    cur_year = cutoff.year if cutoff is not None else pd.Timestamp.now().year
    years_track = []
    if hist_recs:
        sorted_recs = sorted(
            [hr for hr in hist_recs if int(hr.get("year", 0)) <= cur_year],
            key=lambda x: int(x.get("year", 0))
        )
        if cutoff is not None:
            # Conservative whole-calendar-month rule, including month-end day:
            # same-day release timing is unknown, so only earlier months qualify.
            sorted_recs = [hr for hr in sorted_recs
                           if pd.Timestamp(year=int(hr["year"]), month=month, day=1)
                           + pd.offsets.MonthEnd(0) < cutoff]
            years = [int(hr["year"]) for hr in sorted_recs]
            if len(years) != len(set(years)):
                raise ValueError("Duplicate historical year")
            for hr in sorted_recs:
                value = hr.get("return")
                if isinstance(value, bool) or value is None or not np.isfinite(float(value)):
                    raise ValueError("Historical return must be finite")
        if lookback_years and lookback_years > 0:
            valid_recs = sorted_recs[-lookback_years:]
        else:
            valid_recs = sorted_recs

        for hr in valid_recs:
            y = int(hr.get("year", 2024))
            r = float(hr.get("return", 0.0))
            years_track.append({
                "year": y,
                "return": round(r, 4),
                "is_win": bool(r > 0),
                "market_alpha": None,
                "mdd": None,
            })
    else:
        if lookback_years and lookback_years > 0:
            history_slice = history[-lookback_years:]
        else:
            history_slice = history

        years_count = len(history_slice)
        if years_count == 0:
            return None

        start_year = cur_year - years_count
        for i, ret in enumerate(history_slice):
            y = start_year + i
            r = float(ret)
            years_track.append({
                "year": y,
                "return": round(r, 4),
                "is_win": bool(r > 0),
                "market_alpha": None,
                "mdd": None,
            })

    years_count = len(years_track)
    if years_count < 2:
        return None

    rets = [r["return"] for r in years_track]
    wins = [r for r in years_track if r["is_win"]]
    fails = [r for r in years_track if not r["is_win"]]

    wr = len(wins) / len(years_track) if years_track else 0.0
    med_ret = float(np.median(rets)) if rets else 0.0
    # Benchmark and intramonth daily-path series are not part of the monthly
    # statistic input.  Do not manufacture excess return or drawdown proxies.
    med_alpha = None
    avg_mdd = None

    recent_3y = years_track[-3:] if len(years_track) >= 3 else years_track
    r3_wr = len([r for r in recent_3y if r["is_win"]]) / len(recent_3y) if recent_3y else wr
    r3_alpha = None

    recent_5y = years_track[-5:] if len(years_track) >= 5 else years_track
    r5_wr = len([r for r in recent_5y if r["is_win"]]) / len(recent_5y) if recent_5y else wr

    # Pattern Confidence
    if years_count >= 5 and wr >= 0.75 and med_ret >= 0.03:
        conf = "HIGH"
    elif years_count >= 3 and wr >= 0.67:
        conf = "HIGH"
    elif years_count >= 2 and wr >= 0.60:
        conf = "MEDIUM"
    else:
        conf = "LOW"

    best_y = max(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}
    worst_y = min(years_track, key=lambda x: x["return"]) if years_track else {"year": cur_year, "return": 0.0}

    # Expected Return Quantiles & Profit Factor
    p50_ret = round(float(np.percentile(rets, 50)), 4) if rets else med_ret
    p90_ret = round(float(np.percentile(rets, 90)), 4) if len(rets) >= 3 else round(max(rets, default=med_ret), 4)
    pos_rets = sum([r for r in rets if r > 0])
    neg_rets = abs(sum([r for r in rets if r < 0]))
    profit_factor = round(pos_rets / neg_rets, 1) if neg_rets > 0.0001 else (9.9 if pos_rets > 0 else 1.0)

    # Exact entry/peak timing requires daily paths.  It is attached later by
    # remaining_peak.py only when enough fresh observations exist.
    entry_stage = "WATCH"
    entry_stage_label = "실측 피크 산출 대기"
    entry_window_str = ""
    exit_window_str = ""
    playbook = {
        "entry_timing": "월간 수익률만으로는 진입일을 산출하지 않습니다. 신선한 일봉 경로와 3개년 이상 피크 표본이 필요합니다.",
        "exit_timing": "역사적 피크 감시 구간은 일봉 경로 검증을 통과한 경우에만 별도로 표시합니다.",
        "stop_loss": "월간 집계에는 경로상 최대낙폭이 없으므로 MDD 기반 손절선을 제시하지 않습니다.",
        "recommendation": "월별 반복 수익률은 탐색 근거이며 주문·추천 신호가 아닙니다.",
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
        median_alpha=med_alpha,
        avg_mdd=avg_mdd,
        best_year=best_y,
        worst_year=worst_y,
        recent_3y_win_rate=round(r3_wr, 3),
        recent_3y_median_alpha=r3_alpha,
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
