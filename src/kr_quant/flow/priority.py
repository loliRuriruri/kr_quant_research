"""Which names to collect first. Never the full listed universe in P0."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yaml

from kr_quant.context.watchlist import load_watchlist
from kr_quant.settings import Settings
from kr_quant.timing.snapshot import load_prices


def _cfg(settings: Settings) -> dict[str, Any]:
    path = settings.root / "config" / "investor_flow.yaml"
    if not path.exists():
        return {"max_tickers_per_run": 40, "priority": {"watchlist": True, "top_trading_value": 30}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collect_universe(settings: Settings, limit: int | None = None) -> list[dict[str, Any]]:
    cfg = _cfg(settings)
    cap = int(limit or cfg.get("max_tickers_per_run") or 40)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def add(ticker: str, company: str, why: str, detail: str, note: str = "", tag: str = "watch") -> None:
        code = "".join(ch for ch in str(ticker) if ch.isdigit()).zfill(6)
        if len(code) != 6 or code in seen:
            return
        seen.add(code)
        out.append({
            "ticker": code,
            "company": company or code,
            "why": why,
            "detail": detail,
            "note": note,
            "tag": tag,
        })

    if (cfg.get("priority") or {}).get("watchlist", True):
        for row in load_watchlist(settings.root):
            note = str(row.get("note") or "").strip()
            added_at = str(row.get("added_at") or "")[:10]
            detail = "⭐ 사용자가 직접 [관심종목]으로 등록하여 수급을 밀착 추적 중인 핵심 종목입니다."
            if note:
                detail += f" (메모: {note})"
            if added_at:
                detail += f" [등록일: {added_at}]"
            add(
                str(row.get("ticker") or ""),
                str(row.get("company") or ""),
                "관심종목",
                detail,
                note=note,
                tag="watch",
            )
    n_tv = int((cfg.get("priority") or {}).get("top_trading_value") or 30)
    prices = load_prices(settings)
    if prices is not None and not prices.empty and "trading_value" in prices.columns:
        work = prices.copy()
        work["ticker"] = work["ticker"].astype(str).str.zfill(6)
        work["trade_date"] = pd.to_datetime(work["trade_date"], errors="coerce")
        last_day = work["trade_date"].max()
        day = work[work["trade_date"] == last_day]
        top = day.sort_values("trading_value", ascending=False).head(n_tv)
        for rank, rec in enumerate(top.to_dict("records"), 1):
            tv = rec.get("trading_value")
            tv_str = f"{float(tv) / 1e8:.0f}억원" if tv and float(tv) > 0 else ""
            tv_text = f" ({tv_str})" if tv_str else ""
            detail = f"🔥 최근 거래대금#{rank}위{tv_text}를 기록한 고유동성 시장 주도주입니다. 외인·기관 메이저 수급 영향력이 가장 커 1순위 수집 대상입니다."
            add(
                str(rec.get("ticker")),
                str(rec.get("company") or rec.get("ticker")),
                "고유동성",
                detail,
                tag="liquidity",
            )
    return out[:cap]
