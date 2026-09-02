from __future__ import annotations

from typing import Any

import pandas as pd

from kr_quant.settings import Settings
from kr_quant.timing.indicators import last_signals


def _ohlc_lists(hist: pd.DataFrame) -> tuple[list[float], list[float], list[float]] | None:
    if hist is None or hist.empty:
        return None
    work = hist.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
    work = work.dropna(subset=["trade_date"]).sort_values("trade_date")
    for col in ("high", "low", "close"):
        if col not in work.columns:
            return None
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["high", "low", "close"])
    if work.empty:
        return None
    return (
        [float(x) for x in work["high"].tolist()],
        [float(x) for x in work["low"].tolist()],
        [float(x) for x in work["close"].tolist()],
    )


def technical_snapshot(hist: pd.DataFrame | None) -> dict[str, Any]:
    ohlc = _ohlc_lists(hist) if hist is not None else None
    if ohlc is None:
        return {"ok": False, "used_in_quant": False, "labels": [], "bars": 0}
    high, low, close = ohlc
    return last_signals(high, low, close)


_last_close_cache: tuple[float, dict[str, float]] | None = None


def last_closes(settings: Settings) -> dict[str, float]:
    """Latest KRX close by ticker. Overlay helper, not a Quant input."""
    global _last_close_cache
    path_mtime = 0.0
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            path_mtime = max(path_mtime, path.stat().st_mtime)
    if _last_close_cache and _last_close_cache[0] == path_mtime:
        return _last_close_cache[1]
    frame = load_prices(settings, columns=["ticker", "trade_date", "close"])
    if frame is None or frame.empty:
        return {}
    work = frame.copy()
    work["ticker"] = work["ticker"].astype(str).str.zfill(6)
    work["trade_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.dropna(subset=["ticker", "trade_date", "close"]).sort_values("trade_date")
    series = work.groupby("ticker", sort=False)["close"].last()
    out = {str(k): float(v) for k, v in series.items()}
    _last_close_cache = (path_mtime, out)
    return out


def attach_last_close(rows: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    closes = last_closes(settings)
    if not closes:
        return rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("ticker") or "").zfill(6)
        if code in closes and row.get("last_close") is None:
            row["last_close"] = closes[code]
    return rows


def load_prices(settings: Settings, columns: list[str] | None = None) -> pd.DataFrame:
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            try:
                if columns:
                    return pd.read_parquet(path, columns=columns)
                return pd.read_parquet(path)
            except Exception:
                return pd.read_parquet(path)
    return pd.DataFrame()


def attach_technicals(
    payload: dict[str, Any],
    settings: Settings,
    prices: pd.DataFrame | None = None,
) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return payload
    frame = prices if prices is not None else load_prices(settings)
    if frame is None or frame.empty:
        for row in rows:
            if isinstance(row, dict):
                row["ta"] = {"ok": False, "used_in_quant": False, "labels": [], "bars": 0}
        return payload
    work = frame.copy()
    work["ticker"] = work["ticker"].astype(str).str.zfill(6)
    codes = {str(r.get("ticker") or "").zfill(6) for r in rows if isinstance(r, dict)}
    work = work[work["ticker"].isin(codes)]
    grouped = {code: grp for code, grp in work.groupby("ticker", sort=False)}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("ticker") or "").zfill(6)
        row["ta"] = technical_snapshot(grouped.get(code))
    note = " 스토캐스틱(5,3,3)·일목(9-26-52)은 KRX OHLC."
    disc = str(payload.get("disclaimer") or "")
    if "스토캐스틱" not in disc:
        payload["disclaimer"] = (disc + note).strip()
    payload["ta_attached"] = True
    return payload
