from __future__ import annotations

from types import SimpleNamespace

from kr_quant.research.tier1_contract import (
    tier1_deterministic_fallback,
    tier1_success,
    tier1_unavailable,
)


ENDPOINT = SimpleNamespace(provider="openrouter", model="free/test-model")


def test_tier1_unavailable_never_pretends_generation_succeeded():
    result = tier1_unavailable(
        ENDPOINT,
        sources=["sector_ranking"],
        missing=["sector_rows"],
        prompt_version="sector_test_v1",
    )

    assert result["ok"] is False
    assert result["status"] == "UNAVAILABLE"
    assert result["ai_generated"] is False
    assert result["used_in_quant"] is False
    assert result["evidence"]["coverage"] == "NONE"
    assert result["evidence"]["missing"] == ["sector_rows"]


def test_tier1_success_carries_provenance_and_quant_isolation():
    result = tier1_success(
        ENDPOINT,
        {"headline": "실제 자료 기반 요약"},
        as_of="2026-08-26",
        sources=["all_stocks", "all_stocks"],
        evidence_count=5,
        prompt_version="dashboard_test_v1",
    )

    assert result["ok"] is True
    assert result["status"] == "GENERATED"
    assert result["ai_generated"] is True
    assert result["used_in_quant"] is False
    assert result["evidence"]["as_of"] == "2026-08-26"
    assert result["evidence"]["sources"] == ["all_stocks"]
    assert result["evidence"]["coverage"] == "SUFFICIENT"


def test_deterministic_fallback_is_not_labeled_as_ai_generated():
    result = tier1_deterministic_fallback(
        ENDPOINT,
        {"diagnosis": "검증 3회, 최종검증 2회"},
        sources=["custom_strategy_backtest"],
        evidence_count=2,
        prompt_version="backtest_test_v1",
    )

    assert result["ok"] is True
    assert result["status"] == "DETERMINISTIC_FALLBACK"
    assert result["ai_generated"] is False
    assert result["used_in_quant"] is False
