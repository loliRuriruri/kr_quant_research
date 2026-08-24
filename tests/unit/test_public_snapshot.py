# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

from kr_quant.settings import load_settings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from export_public_snapshot import FORMULAS, export, fact  # noqa: E402
from export_public_ui_api import (  # noqa: E402
    ROUTES as UI_ROUTES,
    build_public_stock_detail,
    clean as clean_public_api,
)


def test_missing_is_not_zero():
    f = fact(None, as_of="2026-08-21", source="OpenDART", kind="official", formula="x")
    assert f["missing"] is True
    assert f["display"] == "미수집"
    assert f["value"] is None


def test_export_snapshot_has_no_settings_and_recomputes(tmp_path):
    s = load_settings()
    if not (s.output_dir / "latest_all_stocks.parquet").exists():
        return
    meta = export(tmp_path)
    snap = (tmp_path / "snapshot.json").read_text(encoding="utf-8")
    assert "sk-" not in snap
    assert "OPENDART_API_KEY=" not in snap
    assert "API 설정" not in snap
    assert meta["orders"] is False
    assert meta["ai_mutates_quant"] is False
    assert meta["public_ui"]["settings"] is False
    data = (tmp_path / "ranking.json").read_text(encoding="utf-8")
    assert "quant_score" in data
    assert "연기금" not in (tmp_path / "flow.json").read_text(encoding="utf-8") or "기금" in (tmp_path / "flow.json").read_text(encoding="utf-8")
    assert "quant_score" in FORMULAS


def test_full_public_ui_snapshot_allowlist_and_sanitizer():
    assert "/api/status" in UI_ROUTES
    assert "/api/results/all" in UI_ROUTES
    assert "/api/seasonality/discovery" in UI_ROUTES
    assert "/api/settings" not in UI_ROUTES
    assert "/api/settings/raw" not in UI_ROUTES

    cleaned = clean_public_api(
        {
            "api_key": "do-not-publish",
            "nested": {"client_secret": "do-not-publish", "score": 82.0},
            "path": str(ROOT / "data" / "private.json"),
        }
    )
    assert "api_key" not in cleaned
    assert "client_secret" not in cleaned["nested"]
    assert cleaned["nested"]["score"] == 82.0
    assert cleaned["path"] == "[local path omitted]"


def test_public_stock_detail_is_rich_and_read_only():
    payload = build_public_stock_detail(
        {
            "ticker": "005930",
            "company": "삼성전자",
            "market": "KOSPI",
            "sector": "전자부품반도체",
            "industry": "전자부품반도체",
            "as_of_date": "2026-08-21",
            "quant_score": 78.1,
            "value_score": 23.0,
            "quality_score": 22.0,
            "growth_score": 18.0,
            "momentum_score": 7.0,
            "financial_score": 8.0,
            "weighted_metric_coverage": 0.9,
            "data_confidence": 0.9,
            "risk_flags": [],
            "data_flags": [],
            "exclusion_reasons": [],
            "universe_eligible": True,
        },
        profile={"ticker": "005930", "company": "삼성전자"},
        tian={"id": "tian", "label": "天 시장", "score": 50, "regime_ko": "중립"},
    )
    assert payload["public_snapshot"] is True
    assert payload["row"]["company"] == "삼성전자"
    assert payload["scorecard"]["factors"]
    assert payload["sunzi"]["parts"]["dao"]
    assert payload["naver"]["configured"] is False
    assert "api_key" not in json.dumps(payload, ensure_ascii=False).lower()
