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


def load_prices(settings: Settings) -> pd.DataFrame:
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
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
    note = " 스토캐스틱(5,3,3)·일목(9-26-52)은 KRX OHLC이며 Quant 점수에 넣지 않습니다."
    disc = str(payload.get("disclaimer") or "")
    if "스토캐스틱" not in disc:
        payload["disclaimer"] = (disc + note).strip()
    payload["ta_attached"] = True
    return payload
