from __future__ import annotations

from datetime import date

import pandas as pd

from kr_quant.exceptions import PointInTimeLeak


def assert_no_future_rows(df: pd.DataFrame, as_of: date, col: str = "available_date") -> None:
    if df.empty:
        return
    if col not in df.columns:
        raise PointInTimeLeak(f"Missing availability column: {col}")
    timestamps = pd.to_datetime(df[col], errors='coerce')
    if timestamps.isna().any():
        raise PointInTimeLeak(f"Invalid or missing {col}")
    dates = timestamps.dt.date
    leaked = df[dates > as_of]
    if not leaked.empty:
        raise PointInTimeLeak(f"{len(leaked)} rows have {col} after {as_of}")


def as_of_prices(prices: pd.DataFrame, as_of: date) -> pd.DataFrame:
    df = prices.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    day = df[df["trade_date"] == as_of]
    if day.empty:
        return day
    assert_no_future_rows(day.rename(columns={"trade_date": "available_date"}), as_of)
    return day


def history_window(prices: pd.DataFrame, as_of: date, lookback: int = 400) -> pd.DataFrame:
    df = prices.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df[df["trade_date"] <= as_of].sort_values(["ticker", "trade_date"])
    if lookback <= 0:
        return df.iloc[0:0].copy()
    return df.groupby("ticker", sort=False, group_keys=False).tail(int(lookback)).reset_index(drop=True)
