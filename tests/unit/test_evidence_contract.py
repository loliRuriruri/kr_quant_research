import json
from dataclasses import replace

import pandas as pd

from kr_quant.settings import load_settings
from kr_quant.web.evidence import build_evidence_registry, validate_evidence_registry


def test_evidence_registry_covers_every_visible_research_menu(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    settings.output_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "000001", "universe_eligible": True},
            {"ticker": "000002", "universe_eligible": False},
        ]
    ).to_parquet(settings.output_dir / "latest_all_stocks.parquet", index=False)
    cache = settings.root / "data" / "cache"
    cache.mkdir(parents=True)
    (cache / "strategy_lab.json").write_text(
        json.dumps({"source_price_as_of": "2026-08-28", "rows": [{"ticker": "000001"}]}),
        encoding="utf-8",
    )
    quality = {"as_of_date": "2026-08-28", "status": "success", "warnings": []}
    freshness = {
        "price_max_date": "2026-08-28",
        "financial_max_available_date": "2026-08-19",
        "sources": {
            "krx_prices": {"state": "fresh"},
            "financial_facts": {"state": "partial"},
            "quant_ranking": {"state": "fresh", "last_updated_at": "2026-08-28T20:00:00+09:00"},
            "strategy_cache": {"state": "fresh"},
        },
    }

    registry = build_evidence_registry(settings, quality=quality, freshness=freshness)

    assert validate_evidence_registry(registry)["valid"] is True
    assert registry["menus"]["rank"]["sample"]["count"] == 1
    assert registry["menus"]["rank"]["used_in_quant"] is True
    assert registry["menus"]["strategy"]["used_in_quant"] is False
    assert registry["menus"]["market"]["sample"]["count"] == 7
    assert registry["menus"]["market"]["sources"][0]["name"] == "KRX"
    assert "0점" in " ".join(registry["menus"]["market"]["limitations"])
    assert set(registry["menus"]) >= {
        "dash",
        "rank",
        "strategy",
        "screens",
        "market",
        "sector",
        "investor",
        "trade",
        "seasonality",
        "watch",
        "us13f",
        "sunzi",
        "run",
        "settings",
    }


def test_evidence_registry_validation_fails_closed_for_missing_core_menu():
    result = validate_evidence_registry({"contract_version": "1.0", "menus": {}})

    assert result["valid"] is False
    assert "EVIDENCE_MENU_MISSING:dash" in result["errors"]
