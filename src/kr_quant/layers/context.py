from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from kr_quant.context.explain import interpret_row
from kr_quant.context.market import COMPONENT_KO, attach_macro, derive_market_components, market_regime
from kr_quant.context.watchlist import add_ticker, load_watchlist, remove_ticker
from kr_quant.settings import Settings


def _market_config(settings: Settings) -> dict[str, Any]:
    path = settings.root / "config" / "market.yaml"
    if not path.exists():
        return {"market_regime": {"weights": {"trend": 20, "breadth": 20}, "risk_on_min": 70, "neutral_min": 40}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_price_frame(settings: Settings) -> pd.DataFrame:
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        path = folder / "prices.parquet"
        if path.exists():
            return pd.read_parquet(path)
    return pd.DataFrame()


def build_market_snapshot(settings: Settings, *, refresh: bool = False) -> dict[str, Any]:
    cfg = _market_config(settings)
    prices = load_price_frame(settings)
    ecos: dict[str, Any] = {"configured": False, "used_in_quant": False, "series": []}
    try:
        from kr_quant.ingest.ecos import ecos_snapshot

        ecos = ecos_snapshot(settings.bok_ecos_api_key)
    except Exception as exc:  # noqa: BLE001
        ecos = {"configured": False, "used_in_quant": False, "error": str(exc)[:180], "series": []}
    try:
        from kr_quant.ingest.fear_greed import fear_greed_snapshot

        fear = fear_greed_snapshot(refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        fear = {"configured": False, "used_in_quant": False, "error": str(exc)[:180]}
    if prices.empty:
        from kr_quant.freshness import freshness_snapshot

        return {
            "configured": False,
            "used_in_quant": False,
            "error": "시세가 없습니다. 데모 또는 실데이터 수집을 먼저 실행하세요.",
            "components": [],
            "ecos": ecos,
            "fear_greed": fear,
            "freshness": freshness_snapshot(settings),
        }
    components = derive_market_components(prices)
    if settings.fred_api_key:
        try:
            from kr_quant.ingest.fred import macro_snapshot

            fred = macro_snapshot(settings.fred_api_key)
            components = attach_macro(components, fred.get("series") or [])
        except Exception:  # noqa: BLE001
            pass
    from kr_quant.context.market_sentiment import compute_kr_market_sentiment
    from kr_quant.freshness import freshness_snapshot

    kr_sent = compute_kr_market_sentiment(prices)
    regime = market_regime(components, cfg)
    fresh = freshness_snapshot(settings)
    rows = []
    for key, label in COMPONENT_KO.items():
        val = regime.get(key)
        if val is None:
            tone = "미연결"
        elif float(val) >= 60:
            tone = "우호"
        elif float(val) <= 40:
            tone = "부담"
        else:
            tone = "중립"
        rows.append({"id": key, "label": label, "value": val, "tone": tone})
    return {
        "configured": True,
        "used_in_quant": False,
        "regime": regime.get("regime"),
        "label": regime.get("label"),
        "regime_score": regime.get("regime_score"),
        "kr_sentiment": kr_sent,
        "disclaimer": "시장 국면은 조사 맥락입니다. Quant 순위와 합산하지 않습니다.",
        "components": rows,
        "ecos": ecos,
        "fear_greed": fear,
        "freshness": fresh,
    }


def watchlist_state(settings: Settings) -> dict[str, Any]:
    raw_rows = load_watchlist(settings.root)
    if not raw_rows:
        return {"rows": [], "summary": {}, "sector_distribution": {}}

    # Load all_stocks for Quant scores
    scored_map: dict[str, dict[str, Any]] = {}
    for p in (settings.output_dir / "latest_all_stocks.parquet", settings.output_dir / "all_stocks.parquet"):
        if p.exists():
            try:
                df = pd.read_parquet(p)
                for rec in df.to_dict("records"):
                    t = str(rec.get("ticker") or "").zfill(6)
                    scored_map[t] = rec
                break
            except Exception:
                pass

    # Load prices for latest close
    from kr_quant.strategy.run import _prices
    prices = _prices(settings)
    prices_map: dict[str, dict[str, Any]] = {}
    if not prices.empty:
        for t, g in prices.groupby("ticker"):
            code = str(t).zfill(6)
            last_row = g.sort_values("trade_date").iloc[-1]
            prices_map[code] = {
                "close_price": float(last_row.get("close") or 0),
                "company": str(last_row.get("company") or ""),
                "market": str(last_row.get("market") or ""),
                "sector": str(last_row.get("sector") or ""),
            }

    enriched_rows: list[dict[str, Any]] = []
    total_quant = 0.0
    total_val = 0.0
    total_qual = 0.0
    total_growth = 0.0
    total_mom = 0.0
    total_fin = 0.0
    valid_count = 0
    sector_dist: dict[str, int] = {}

    for r in raw_rows:
        code = str(r.get("ticker") or "").zfill(6)
        item = dict(r)
        item["ticker"] = code

        # Attach prices
        p_info = prices_map.get(code) or {}
        if p_info:
            item["close_price"] = p_info.get("close_price")
            item["company"] = item.get("company") or p_info.get("company") or code
            item["market"] = item.get("market") or p_info.get("market") or "KOSPI"
            if p_info.get("sector"):
                item["sector"] = p_info.get("sector")

        # Attach Quant scores
        s_info = scored_map.get(code) or {}
        if s_info:
            item["quant_score"] = round(float(s_info.get("quant_score") or 0), 1)
            item["quant_rank"] = int(s_info.get("quant_rank") or 0) if s_info.get("quant_rank") else None
            item["value_score"] = round(float(s_info.get("value_score") or 0), 1)
            item["quality_score"] = round(float(s_info.get("quality_score") or 0), 1)
            item["growth_score"] = round(float(s_info.get("growth_score") or 0), 1)
            item["momentum_score"] = round(float(s_info.get("momentum_score") or 0), 1)
            item["financial_score"] = round(float(s_info.get("financial_score") or 0), 1)
            if s_info.get("sector"):
                item["sector"] = str(s_info.get("sector"))
            if s_info.get("company"):
                item["company"] = str(s_info.get("company"))

            total_quant += item["quant_score"]
            total_val += item["value_score"]
            total_qual += item["quality_score"]
            total_growth += item["growth_score"]
            total_mom += item["momentum_score"]
            total_fin += item["financial_score"]
            valid_count += 1

        sec = str(item.get("sector") or item.get("market") or "기타").strip()
        sector_dist[sec] = sector_dist.get(sec, 0) + 1
        enriched_rows.append(item)

    n = max(1, valid_count)
    summary = {
        "total_count": len(enriched_rows),
        "scored_count": valid_count,
        "avg_quant_score": round(total_quant / n, 1) if valid_count else None,
        "avg_value_score": round(total_val / n, 1) if valid_count else None,
        "avg_quality_score": round(total_qual / n, 1) if valid_count else None,
        "avg_growth_score": round(total_growth / n, 1) if valid_count else None,
        "avg_momentum_score": round(total_mom / n, 1) if valid_count else None,
        "avg_financial_score": round(total_fin / n, 1) if valid_count else None,
    }

    return {
        "rows": enriched_rows,
        "summary": summary,
        "sector_distribution": sector_dist,
    }



def watchlist_add(settings: Settings, ticker: str, company: str | None = None, note: str = "") -> list[dict[str, Any]]:
    return add_ticker(settings.root, ticker, company, note)


def watchlist_remove(settings: Settings, ticker: str) -> list[dict[str, Any]]:
    return remove_ticker(settings.root, ticker)


def explain_stock(row: dict[str, Any]) -> dict[str, Any]:
    return interpret_row(row)
