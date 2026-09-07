from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd


def _as_date(value: date | datetime | str | pd.Timestamp | None) -> date | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _safe_date(year: int, month: int, day: int) -> date:
    day = max(1, min(int(day), 28))
    return date(int(year), int(month), day)


def _pctile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(values, percentile)), 4)


def _stage_for(as_of: date, peak_date: date) -> tuple[str, str]:
    entry_start = peak_date - timedelta(days=30)
    entry_end = peak_date - timedelta(days=15)
    exit_start = peak_date - timedelta(days=3)
    exit_end = peak_date + timedelta(days=4)
    d_day = (peak_date - as_of).days

    if as_of < entry_start:
        if d_day <= 60:
            return "ACCUMULATE_60", f"🎯 사전 준비구간 (피크 D-{d_day})"
        return "WATCH", f"👀 계절성 관찰 (피크 D-{d_day})"
    if as_of <= entry_end:
        return "TODAY_ENTRY", f"🔥 사전 진입 유효 (피크 D-{d_day})"
    if as_of < exit_start:
        return "RALLY_ACTIVE", f"📈 랠리 확인구간 (피크 D-{d_day})"
    if as_of <= exit_end:
        sign = "-" if d_day >= 0 else "+"
        return "EXIT_PEAK", f"💰 역사적 피크 감시 (D{sign}{abs(d_day)})"
    return "SEASON_END", "🏁 계절성 구간 종료"


def _empty_result(reason: str, *, ticker: str, target_month: int) -> dict[str, Any]:
    return {
        "available": False,
        "status": reason,
        "ticker": ticker,
        "target_month": int(target_month),
        "sample_count": 0,
        "warnings": [],
    }


def calculate_remaining_peak_upside(
    prices: pd.DataFrame,
    ticker: str,
    target_month: int,
    *,
    as_of_date: date | datetime | str | pd.Timestamp | None = None,
    lookback_years: int = 5,
    min_samples: int = 3,
) -> dict[str, Any]:
    """Estimate today's remaining upside to a seasonal peak from actual daily OHLC paths.

    The reference date for each historical year is aligned by the same calendar
    offset to the historical median peak date.  The default estimate uses the
    close because it is reproducible; the intraday-high estimate is returned as
    a separately labelled diagnostic.
    """
    code = str(ticker or "").zfill(6)
    month = int(target_month)
    if isinstance(lookback_years, bool) or int(lookback_years) != lookback_years or lookback_years < 0:
        raise ValueError("기간은 0(전체) 이상의 정수여야 합니다.")
    if prices is None or prices.empty or month < 1 or month > 12:
        return _empty_result("NO_PRICE_DATA", ticker=code, target_month=month)

    frame = prices.copy()
    if "ticker" in frame.columns:
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
        frame = frame[frame["ticker"] == code]
    if frame.empty:
        return _empty_result("NO_TICKER_PRICE_DATA", ticker=code, target_month=month)

    date_col = "trade_date" if "trade_date" in frame.columns else "date"
    if date_col not in frame.columns or "close" not in frame.columns:
        return _empty_result("MISSING_OHLC_COLUMNS", ticker=code, target_month=month)

    frame["date"] = pd.to_datetime(frame[date_col], errors="coerce")
    for col in ("close", "high", "low", "volume", "adj_close"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    frame = frame[(frame["close"] > 0) & np.isfinite(frame["close"])].sort_values("date").drop_duplicates("date", keep="last")
    if frame.empty:
        return _empty_result("NO_VALID_PRICE_ROWS", ticker=code, target_month=month)

    requested_as_of = _as_date(as_of_date)
    if requested_as_of is not None:
        frame = frame[frame["date"].dt.date <= requested_as_of]
    if frame.empty:
        return _empty_result("NO_PRICE_AT_AS_OF", ticker=code, target_month=month)

    price_as_of = frame.iloc[-1]["date"].date()

    adj_coverage = 0.0
    if "adj_close" in frame.columns:
        valid_adj = frame["adj_close"].notna() & np.isfinite(frame["adj_close"]) & (frame["adj_close"] > 0)
        adj_coverage = float(valid_adj.mean())
    use_adjusted = adj_coverage == 1.0
    if use_adjusted:
        frame["basis_close"] = frame["adj_close"]
        ratio = frame["adj_close"] / frame["close"]
        frame["basis_high"] = frame.get("high", frame["close"]) * ratio
        frame["basis_low"] = frame.get("low", frame["close"]) * ratio
    else:
        frame["basis_close"] = frame["close"]
        frame["basis_high"] = frame.get("high", frame["close"]).fillna(frame["close"])
        frame["basis_low"] = frame.get("low", frame["close"]).fillna(frame["close"])

    latest = frame.iloc[-1]
    current_close = float(latest["close"])
    current_volume = float(latest.get("volume") or 0.0) if pd.notna(latest.get("volume")) else 0.0

    # Completed historical target months determine the recurring peak day.
    completed = frame[(frame["date"].dt.month == month) & (frame["date"].dt.date < price_as_of)].copy()
    completed["year"] = completed["date"].dt.year
    historical_months: list[tuple[int, pd.DataFrame]] = []
    for year, group in completed.groupby("year"):
        month_end = _safe_date(int(year), month, 28)
        if month == price_as_of.month and int(year) == price_as_of.year:
            continue
        if price_as_of <= month_end and int(year) == price_as_of.year:
            continue
        group = group.sort_values("date")
        if len(group) < 8:
            continue
        # Korean daily limits are normally 30%; larger one-day jumps usually
        # indicate an unadjusted corporate action or corrupted history.
        if group["basis_close"].pct_change().abs().max(skipna=True) > 0.35:
            continue
        historical_months.append((int(year), group))

    if not historical_months:
        result = _empty_result("NO_COMPLETED_SEASONAL_MONTHS", ticker=code, target_month=month)
        result.update({"price_as_of": str(price_as_of), "current_price": round(current_close, 2)})
        return result

    historical_months = sorted(historical_months, key=lambda item: item[0])
    if lookback_years:
        historical_months = historical_months[-int(lookback_years):]

    peak_days = [int(group.loc[group["basis_close"].idxmax(), "date"].day) for _, group in historical_months]
    median_peak_day = int(round(float(np.median(peak_days))))
    median_peak_day = max(1, min(median_peak_day, 28))

    target_year = price_as_of.year
    target_peak_date = _safe_date(target_year, month, median_peak_day)
    if price_as_of > target_peak_date + timedelta(days=4):
        target_year += 1
        target_peak_date = _safe_date(target_year, month, median_peak_day)

    entry_start = target_peak_date - timedelta(days=30)
    entry_end = target_peak_date - timedelta(days=15)
    exit_start = target_peak_date - timedelta(days=3)
    exit_end = target_peak_date + timedelta(days=4)
    offset_days = (price_as_of - target_peak_date).days

    paths: list[dict[str, Any]] = []
    for year, _ in historical_months:
        hist_peak_anchor = _safe_date(year, month, median_peak_day)
        hist_reference = hist_peak_anchor + timedelta(days=offset_days)
        hist_end = hist_peak_anchor + timedelta(days=4)
        path = frame[
            (frame["date"].dt.date >= hist_reference)
            & (frame["date"].dt.date <= hist_end)
        ].copy()
        if len(path) < 3:
            continue
        baseline_row = path.iloc[0]
        baseline = float(baseline_row["basis_close"])
        if baseline <= 0:
            continue
        # Reject historical windows with split-like discontinuities when only
        # raw KRX prices are available.
        if path["basis_close"].pct_change().abs().max(skipna=True) > 0.35:
            continue
        close_peak_idx = path["basis_close"].idxmax()
        close_peak_row = path.loc[close_peak_idx]
        close_peak = float(close_peak_row["basis_close"])
        intraday_peak = float(path["basis_high"].max())
        through_peak = path[path["date"] <= close_peak_row["date"]]
        downside = float(through_peak["basis_low"].min() / baseline - 1.0)
        trading_days = int(path.index.get_loc(close_peak_idx)) if close_peak_idx in path.index else 0
        paths.append({
            "year": year,
            "reference_date": str(baseline_row["date"].date()),
            "peak_date": str(close_peak_row["date"].date()),
            "remaining_return": round(close_peak / baseline - 1.0, 4),
            "window_end_return": round(float(path.iloc[-1]["basis_close"]) / baseline - 1.0, 4),
            "intraday_peak_return": round(intraday_peak / baseline - 1.0, 4),
            "downside_before_peak": round(downside, 4),
            "trading_days_to_peak": trading_days,
        })

    returns = [float(row["remaining_return"]) for row in paths]
    end_returns = [float(row["window_end_return"]) for row in paths]
    intraday_returns = [float(row["intraday_peak_return"]) for row in paths]
    downsides = [float(row["downside_before_peak"]) for row in paths]
    days_to_peak = [int(row["trading_days_to_peak"]) for row in paths]
    sample_count = len(paths)
    warnings: list[str] = []
    warnings.append("피크 수익률은 사후 최고 종가 기준으로 음수가 되지 않을 수 있습니다. 실현 수익률·미래 성공 확률이 아닙니다.")
    warnings.append("같은 과거 표본에서 피크일을 찾고 평가한 기술통계입니다. 독립 OOS·거래비용 검증은 미완료입니다.")
    if not use_adjusted:
        warnings.append("수정주가가 없어 35% 초과 단절 구간을 제외한 원시 종가 기준입니다.")
    freshness_clock = requested_as_of or date.today()
    stale_days = max(0, (freshness_clock - price_as_of).days)
    if stale_days > 5:
        warnings.append(f"최근 시세가 {stale_days}일 지연되었습니다.")
    if current_volume <= 0:
        warnings.append("최근 거래량이 0이어서 실제 진입 가능 여부를 별도 확인해야 합니다.")
    if sample_count < min_samples:
        warnings.append(f"유효 표본이 {sample_count}개년으로 최소 {min_samples}개년보다 적습니다.")

    stage, stage_label = _stage_for(price_as_of, target_peak_date)
    status = "READY" if sample_count >= min_samples else "LOW_SAMPLE"
    if stale_days > 5:
        status = "STALE_PRICE"
    available = sample_count >= min_samples and stale_days <= 5 and current_volume > 0

    p25 = _pctile(returns, 25)
    p50 = _pctile(returns, 50)
    p75 = _pctile(returns, 75)
    p90 = _pctile(returns, 90)
    intraday_p50 = _pctile(intraday_returns, 50)
    downside_p50 = _pctile(downsides, 50)

    entry_rows = frame[frame["date"].dt.date >= entry_start]
    entry_rows = entry_rows[entry_rows["date"].dt.date <= price_as_of]
    realized_since_entry = None
    if not entry_rows.empty:
        entry_price = float(entry_rows.iloc[0]["basis_close"])
        current_basis = float(latest["basis_close"])
        if entry_price > 0:
            realized_since_entry = round(current_basis / entry_price - 1.0, 4)

    confidence = "MEDIUM" if sample_count >= 5 else "LOW"
    return {
        "available": available,
        "status": status,
        "ticker": code,
        "target_month": month,
        "price_as_of": str(price_as_of),
        "current_price": round(current_close, 2),
        "price_basis": "ADJUSTED_CLOSE" if use_adjusted else "RAW_CLOSE_FILTERED",
        "sample_count": sample_count,
        "confidence": confidence,
        "validation_status": "IN_SAMPLE_DESCRIPTIVE_NOT_OOS",
        "window_end_p50": _pctile(end_returns, 50),
        "window_end_positive_rate": round(float(np.mean(np.asarray(end_returns) > 0)), 3) if end_returns else None,
        "costs_included": False,
        "historical_peak_day": median_peak_day,
        "target_peak_date": str(target_peak_date),
        "entry_window_str": f"{entry_start:%m/%d} ~ {entry_end:%m/%d}",
        "exit_window_str": f"{exit_start:%m/%d} ~ {exit_end:%m/%d}",
        "entry_stage": stage,
        "entry_stage_label": stage_label,
        "remaining_p25": p25,
        "remaining_p50": p50,
        "remaining_p75": p75,
        "remaining_p90": p90,
        "intraday_peak_p50": intraday_p50,
        "positive_peak_rate": round(float(np.mean(np.asarray(returns) > 0)), 3) if returns else None,
        "downside_before_peak_p50": downside_p50,
        "median_trading_days_to_peak": int(round(float(np.median(days_to_peak)))) if days_to_peak else None,
        "realized_since_entry_start": realized_since_entry,
        "peak_price_p25": round(current_close * (1.0 + p25), 2) if p25 is not None else None,
        "peak_price_p50": round(current_close * (1.0 + p50), 2) if p50 is not None else None,
        "peak_price_p75": round(current_close * (1.0 + p75), 2) if p75 is not None else None,
        "paths": paths,
        "warnings": warnings,
        "methodology": "동일 계절 진행시점의 종가부터 역사적 피크 구간 최고 종가까지의 수익률 분포",
    }
