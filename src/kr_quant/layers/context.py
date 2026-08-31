from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    krx_as_of = str((components.get("_meta") or {}).get("as_of") or "") or None
    fred_compact: dict[str, Any] = {"configured": False, "used_in_quant": False, "series": []}
    if settings.fred_api_key:
        try:
            from kr_quant.ingest.fred import macro_snapshot

            fred = macro_snapshot(settings.fred_api_key, refresh=refresh)
            components = attach_macro(components, fred.get("series") or [], krx_as_of=krx_as_of)
            fred_compact = components.get("_macro") or {
                "configured": True,
                "source": "FRED",
                "used_in_quant": False,
                "series": [],
            }
            fred_compact["configured"] = True
        except Exception as exc:  # noqa: BLE001
            fred_compact = {"configured": False, "used_in_quant": False, "error": str(exc)[:180], "series": []}
    from kr_quant.context.market_sentiment import compute_kr_market_sentiment
    from kr_quant.freshness import freshness_snapshot

    kr_sent = compute_kr_market_sentiment(prices)
    regime = market_regime(components, cfg)
    fresh = freshness_snapshot(settings)
    details = regime.get("details") or {}
    rows = []
    for key, label in COMPONENT_KO.items():
        detail = dict(details.get(key) or {})
        val = regime.get(key)
        if val is None:
            tone = "미관측"
        elif float(val) >= 60:
            tone = "우호"
        elif float(val) <= 40:
            tone = "부담"
        else:
            tone = "중립"
        rows.append(
            {
                "id": key,
                "label": label,
                "value": val,
                "tone": tone,
                "as_of": detail.get("as_of"),
                "source": detail.get("source"),
                "sample_count": detail.get("sample_count"),
                "sample_unit": detail.get("sample_unit"),
                "configured_weight": detail.get("configured_weight"),
                "effective_weight": detail.get("effective_weight"),
                "contribution": detail.get("contribution"),
                "change_1d": detail.get("change_1d"),
                "change_1m": detail.get("change_1m"),
                "observed_value": detail.get("observed_value"),
                "observed_unit": detail.get("observed_unit"),
                "lag_days": detail.get("lag_days"),
                "stale": detail.get("stale"),
                "formula": detail.get("formula"),
                "observation": detail.get("observation"),
                "opinion": detail.get("opinion"),
                "falsification": detail.get("falsification"),
                "available": detail.get("available", val is not None),
                "missing_reason": detail.get("missing_reason"),
                "related": detail.get("related") or [],
            }
        )
    ecos_as_of = None
    for item in ecos.get("series") or []:
        if isinstance(item, dict) and item.get("time"):
            ecos_as_of = str(item.get("time"))
    fred_as_of = None
    for item in fred_compact.get("series") or []:
        if isinstance(item, dict) and item.get("as_of"):
            fred_as_of = str(item.get("as_of"))
    payload = {
        "configured": True,
        "used_in_quant": False,
        "regime": regime.get("regime"),
        "label": regime.get("label"),
        "regime_score": regime.get("regime_score"),
        "confidence": regime.get("confidence"),
        "confidence_label": regime.get("confidence_label"),
        "weight_policy": regime.get("weight_policy"),
        "formula": regime.get("formula"),
        "score_check": regime.get("score_check"),
        "contributions": regime.get("contributions") or [],
        "missing": regime.get("missing") or [],
        "opinion": regime.get("opinion"),
        "falsification": regime.get("falsification"),
        "kr_sentiment": kr_sent,
        "disclaimer": "시장 국면은 조사 맥락입니다. Quant 순위와 합산하지 않습니다. 빠진 지표는 0점이 아니라 가중치에서 제외합니다.",
        "components": rows,
        "ecos": ecos,
        "macro": fred_compact,
        "fear_greed": fear,
        "freshness": fresh,
    }
    _store_market_cache(
        settings,
        {
            "as_of": krx_as_of,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "regime_score": regime.get("regime_score"),
            "available_count": len([row for row in rows if row.get("available")]),
            "component_count": len(rows),
            "missing": regime.get("missing") or [],
            "confidence": regime.get("confidence"),
            "fred_as_of": fred_as_of,
            "ecos_as_of": ecos_as_of,
            "used_in_quant": False,
        },
    )
    return payload


def _store_market_cache(settings: Settings, payload: dict[str, Any]) -> None:
    path = settings.root / "data" / "cache" / "market_regime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


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

        def _safe_float(v, default=0.0):
            try:
                if v is None or pd.isna(v):
                    return default
                return float(v)
            except Exception:
                return default

        def _safe_int(v, default=None):
            try:
                if v is None or pd.isna(v):
                    return default
                return int(float(v))
            except Exception:
                return default

        # Attach Quant scores
        s_info = scored_map.get(code) or {}
        if s_info:
            item["quant_score"] = round(_safe_float(s_info.get("quant_score")), 1)
            item["quant_rank"] = _safe_int(s_info.get("quant_rank"))
            item["value_score"] = round(_safe_float(s_info.get("value_score")), 1)
            item["quality_score"] = round(_safe_float(s_info.get("quality_score")), 1)
            item["growth_score"] = round(_safe_float(s_info.get("growth_score")), 1)
            item["momentum_score"] = round(_safe_float(s_info.get("momentum_score")), 1)
            item["financial_score"] = round(_safe_float(s_info.get("financial_score")), 1)
            if s_info.get("sector") and not pd.isna(s_info.get("sector")):
                item["sector"] = str(s_info.get("sector"))
            if s_info.get("company") and not pd.isna(s_info.get("company")):
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
