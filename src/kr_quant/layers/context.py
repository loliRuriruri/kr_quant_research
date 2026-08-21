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


def watchlist_state(settings: Settings) -> list[dict[str, Any]]:
    return load_watchlist(settings.root)


def watchlist_add(settings: Settings, ticker: str, company: str | None = None, note: str = "") -> list[dict[str, Any]]:
    return add_ticker(settings.root, ticker, company, note)


def watchlist_remove(settings: Settings, ticker: str) -> list[dict[str, Any]]:
    return remove_ticker(settings.root, ticker)


def explain_stock(row: dict[str, Any]) -> dict[str, Any]:
    return interpret_row(row)
