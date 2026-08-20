from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

REPRT_Q1 = "11013"
REPRT_H1 = "11012"
REPRT_Q3 = "11014"
REPRT_FY = "11011"

CUMULATIVE_CODES = {REPRT_Q1: 1, REPRT_H1: 2, REPRT_Q3: 3, REPRT_FY: 4}


@dataclass
class DiscreteQuarter:
    security_id: str
    account: str
    fs_div: str
    currency: str
    fiscal_year: int
    quarter: int  # 1-4
    period_start: date | None
    period_end: date | None
    amount: float
    available_date: date
    rcept_no: str
    derived: bool = False


def _to_date(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, date) and not isinstance(v, pd.Timestamp):
        return v
    return pd.to_datetime(v).date()


def select_latest_valid_facts(
    facts: pd.DataFrame,
    as_of: date,
    cutoff_date: date | None = None,
) -> pd.DataFrame:
    """Keep the latest non-withdrawn revision with available_date <= as_of."""
    if facts.empty:
        return facts
    df = facts.copy()
    df["available_date"] = pd.to_datetime(df["available_date"]).dt.date
    df = df[df["available_date"] <= as_of]
    if cutoff_date is not None:
        df = df[df["available_date"] <= cutoff_date]
    if "is_withdrawn" in df.columns:
        df = df[~df["is_withdrawn"].fillna(False).astype(bool)]
    sort_cols = [c for c in ["available_date", "revision_id", "rcept_no"] if c in df.columns]
    df = df.sort_values(sort_cols)
    key = [c for c in ["security_id", "canonical_account", "fs_div", "reprt_code", "bsns_year", "period_end"] if c in df.columns]
    return df.drop_duplicates(key, keep="last")


def derive_discrete_quarters(facts: pd.DataFrame, account: str) -> tuple[list[DiscreteQuarter], list[str]]:
    flags: list[str] = []
    rows: list[DiscreteQuarter] = []
    if facts.empty:
        return rows, flags
    acc = facts[facts["canonical_account"] == account].copy()
    if acc.empty:
        return rows, flags

    group_cols = ["security_id", "fs_div", "currency", "bsns_year"]
    for gkey, g in acc.groupby(group_cols, dropna=False):
        security_id, fs_div, currency, year = gkey
        by_code: dict[str, pd.Series] = {}
        for _, row in g.iterrows():
            code = str(row["reprt_code"])
            prev = by_code.get(code)
            if prev is None or _to_date(row["available_date"]) >= _to_date(prev["available_date"]):
                by_code[code] = row

        amounts: dict[int, tuple[float, pd.Series]] = {}
        for code, qn in ((REPRT_Q1, 1), (REPRT_H1, 2), (REPRT_Q3, 3), (REPRT_FY, 4)):
            if code in by_code:
                amounts[qn] = (float(by_code[code]["normalized_value"]), by_code[code])

        q1 = amounts.get(1)
        h1 = amounts.get(2)
        q3c = amounts.get(3)
        fy = amounts.get(4)

        def push(qtr: int, amount: float, src: pd.Series, derived: bool, start: date | None, end: date | None) -> None:
            rows.append(
                DiscreteQuarter(
                    security_id=str(security_id),
                    account=account,
                    fs_div=str(fs_div),
                    currency=str(currency),
                    fiscal_year=int(year),
                    quarter=qtr,
                    period_start=start,
                    period_end=end,
                    amount=amount,
                    available_date=_to_date(src.get("available_date")) or date.min,
                    rcept_no=str(src.get("rcept_no", "")),
                    derived=derived,
                )
            )

        from datetime import timedelta

        q1_end = _to_date(q1[1].get("period_end")) if q1 else None
        h1_end = _to_date(h1[1].get("period_end")) if h1 else None
        q3_end = _to_date(q3c[1].get("period_end")) if q3c else None
        fy_end = _to_date(fy[1].get("period_end")) if fy else None
        q1_start = _to_date(q1[1].get("period_start")) if q1 else None

        if q1:
            push(1, q1[0], q1[1], False, q1_start, q1_end)
        if h1 and q1:
            start = (q1_end + timedelta(days=1)) if q1_end else None
            push(2, h1[0] - q1[0], h1[1], True, start, h1_end)
        elif h1:
            flags.append("INCOMPLETE_CUMULATIVE")
        if q3c and h1:
            start = (h1_end + timedelta(days=1)) if h1_end else None
            push(3, q3c[0] - h1[0], q3c[1], True, start, q3_end)
        elif q3c:
            flags.append("INCOMPLETE_CUMULATIVE")
        if fy and q3c:
            q4 = fy[0] - q3c[0]
            if fy[0] != 0 and abs(q4) > abs(fy[0]) * 1.5:
                flags.append("Q4_DERIVATION_ANOMALY")
            start = (q3_end + timedelta(days=1)) if q3_end else None
            push(4, q4, fy[1], True, start, fy_end)
        elif fy:
            flags.append("INCOMPLETE_CUMULATIVE")

    return rows, flags


def ttm_from_discrete(
    quarters: list[DiscreteQuarter],
    min_days: int = 330,
    max_days: int = 400,
) -> tuple[float | None, list[DiscreteQuarter], str | None]:
    if len(quarters) < 4:
        return None, [], "INSUFFICIENT_TTM"
    ordered = sorted(quarters, key=lambda q: (q.fiscal_year, q.quarter, q.period_end or date.min))
    window = ordered[-4:]
    fs = {q.fs_div for q in window}
    cur = {q.currency for q in window}
    if len(fs) > 1:
        return None, window, "SCOPE_MISMATCH"
    if len(cur) > 1:
        return None, window, "CURRENCY_MISMATCH"
    starts = [q.period_start for q in window if q.period_start]
    ends = [q.period_end for q in window if q.period_end]
    if starts and ends:
        span = (max(ends) - min(starts)).days
        if span < min_days or span > max_days:
            return None, window, "INSUFFICIENT_TTM"
    seq = [(q.fiscal_year, q.quarter) for q in window]
    if not _consecutive(seq):
        return None, window, "INSUFFICIENT_TTM"
    return sum(q.amount for q in window), window, None


def _consecutive(seq: list[tuple[int, int]]) -> bool:
    if len(seq) < 2:
        return True
    for (y0, q0), (y1, q1) in zip(seq, seq[1:]):
        if q0 < 4:
            if not (y1 == y0 and q1 == q0 + 1):
                return False
        else:
            if not (y1 == y0 + 1 and q1 == 1):
                return False
    return True


def lag_ttm(quarters: list[DiscreteQuarter], lag: int = 4, **kwargs: Any) -> tuple[float | None, str | None]:
    if len(quarters) < 4 + lag:
        return None, "INSUFFICIENT_TTM"
    ordered = sorted(quarters, key=lambda q: (q.fiscal_year, q.quarter, q.period_end or date.min))
    val, _, err = ttm_from_discrete(ordered[:-lag], **kwargs)
    return val, err
