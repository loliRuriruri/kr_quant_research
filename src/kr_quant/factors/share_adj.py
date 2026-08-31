from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def share_adjusted_level(close: Any, shares: Any, mcap: Any) -> float | None:
    """Split-safe level from official KRX fields. Not a dividend total-return series."""
    try:
        if mcap is not None and not pd.isna(mcap) and float(mcap) > 0:
            return float(mcap)
    except (TypeError, ValueError):
        pass
    try:
        px = float(close)
        sh = float(shares)
    except (TypeError, ValueError):
        return None
    if px > 0 and sh > 0:
        return px * sh
    return None


def _levels(hist: pd.DataFrame) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    if hist is None or hist.empty:
        return rows
    work = hist.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work.sort_values("trade_date")
    for rec in work.itertuples(index=False):
        level = share_adjusted_level(
            getattr(rec, "close", None),
            getattr(rec, "listed_shares", None) if hasattr(rec, "listed_shares") else None,
            getattr(rec, "market_cap", None) if hasattr(rec, "market_cap") else None,
        )
        if level is None:
            continue
        rows.append((rec.trade_date, level))
    return rows


def lookback_return(levels: list[tuple[date, float]], lookback: int) -> float | None:
    if lookback <= 0 or len(levels) <= lookback:
        return None
    start = levels[-(lookback + 1)][1]
    end = levels[-1][1]
    if start <= 0:
        return None
    return end / start - 1.0


def high_52w(levels: list[tuple[date, float]], window: int = 252) -> float | None:
    if not levels:
        return None
    window_lv = [lv for _, lv in levels[-window:]]
    return max(window_lv) if window_lv else None


def ticker_momentum(
    hist: pd.DataFrame,
    specs: dict[str, int],
    *,
    validate_integrity: bool = True,
) -> dict[str, float | None]:
    # A market-cap proxy is split-safe, but it is not a complete adjusted-price
    # feed. Do not bridge share-count changes or unexplained price jumps.
    if validate_integrity:
        from kr_quant.quality.price_integrity import latest_clean_price_segments

        clean, _, _ = latest_clean_price_segments(hist)
    else:
        clean = hist
    levels = _levels(clean)
    last = levels[-1][1] if levels else None
    high = high_52w(levels, specs.get("high_52w_distance", 252))
    return {
        "return_3m": lookback_return(levels, specs.get("return_3m", 63)),
        "return_6m": lookback_return(levels, specs.get("return_6m", 126)),
        "return_12m": lookback_return(levels, specs.get("return_12m", 252)),
        "high_52w": high,
        "adj_close": last,
    }


def market_median_return(by_ticker: dict[str, dict[str, float | None]], key: str = "return_6m") -> float | None:
    vals = [row[key] for row in by_ticker.values() if row.get(key) is not None]
    if not vals:
        return None
    vals.sort()
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def compute_share_adj_momentum(
    prices: pd.DataFrame,
    as_of: date,
    cfg: dict[str, Any],
    *,
    validate_integrity: bool = True,
) -> dict[str, dict[str, float | None]]:
    specs = {
        name: int(mspec.get("lookback", 63))
        for name, mspec in (cfg.get("factors", {}).get("momentum", {}).get("metrics") or {}).items()
        if "lookback" in mspec
    }
    work = prices.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work[work["trade_date"] <= as_of]
    out: dict[str, dict[str, float | None]] = {}
    markets: dict[str, list[str]] = {}
    for ticker, grp in work.groupby("ticker"):
        mom = ticker_momentum(grp, specs, validate_integrity=validate_integrity)
        out[str(ticker)] = mom
        mkt = str(grp["market"].iloc[-1]) if "market" in grp.columns and not grp.empty else ""
        markets.setdefault(mkt, []).append(str(ticker))
    for _mkt, tickers in markets.items():
        subset = {t: out[t] for t in tickers if t in out}
        med = market_median_return(subset, "return_6m")
        for t in tickers:
            out[t]["market_return_6m"] = med
    return out
