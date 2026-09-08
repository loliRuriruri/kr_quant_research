from __future__ import annotations

import json
from types import SimpleNamespace

from kr_quant.research.tier1_contract import (
    tier1_cached_chat_json,
    tier1_cache_identity,
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


def test_tier1_cache_identity_changes_with_evidence_model_and_prompt():
    endpoint = SimpleNamespace(provider="OPENROUTER", model="free-a")
    base = tier1_cache_identity(endpoint, namespace="rank", prompt_version="v1", evidence={"score": 70})
    same = tier1_cache_identity(endpoint, namespace="rank", prompt_version="v1", evidence={"score": 70})
    changed_data = tier1_cache_identity(endpoint, namespace="rank", prompt_version="v1", evidence={"score": 71})
    changed_prompt = tier1_cache_identity(endpoint, namespace="rank", prompt_version="v2", evidence={"score": 70})
    changed_model = tier1_cache_identity(
        SimpleNamespace(provider="OPENROUTER", model="free-b"),
        namespace="rank",
        prompt_version="v1",
        evidence={"score": 70},
    )

    assert base == same
    assert base["cache_key"] != changed_data["cache_key"]
    assert base["cache_key"] != changed_prompt["cache_key"]
    assert base["cache_key"] != changed_model["cache_key"]


def test_stock_insights_without_evidence_do_not_invent_catalysts(tmp_path, monkeypatch):
    from kr_quant.research.analyze import get_tier1_insights

    settings = SimpleNamespace(root=tmp_path, openrouter_api_key=None)
    monkeypatch.setattr(
        "kr_quant.research.providers.resolve_tier1_endpoint",
        lambda _settings: SimpleNamespace(provider="openrouter", model="paid/model", label="설정된 모델", api_key=None),
    )
    called = {"n": 0}

    def boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("LLM should not run without evidence")

    monkeypatch.setattr("kr_quant.research.analyze.call_chat", boom)
    result = get_tier1_insights("005930", "삼성전자", news=[], events=[], tech={}, flow={}, settings=settings)
    assert called["n"] == 0
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["ai_generated"] is False
    assert result["used_in_quant"] is False
    assert result["news_analysis"]["key_driver"] == "근거 부족"
    assert "100% 무료" not in str(result.get("tier") or "")
    assert "quant_score" not in result


def test_stock_insights_use_flash_when_free_hop_fails(tmp_path, monkeypatch):
    from kr_quant.research.analyze import get_tier1_insights

    free = SimpleNamespace(provider="openrouter", model="nvidia/nemotron-3-ultra-550b-a55b:free", label="Nemotron", configured=True)
    flash = SimpleNamespace(provider="openrouter", model="deepseek/deepseek-v4-flash-0731", label="Flash", configured=True)
    monkeypatch.setattr("kr_quant.research.providers.resolve_tier1_endpoint", lambda _s: free)
    monkeypatch.setattr("kr_quant.research.providers.resolve_tier1_routine_paid_endpoint", lambda _s: flash)
    calls = []

    def chat(endpoint, *_args, **_kwargs):
        calls.append(endpoint.model)
        if str(endpoint.model).endswith(":free"):
            raise TimeoutError("free hang")
        return json.dumps({
            "news_analysis": {"summary": "제목만 확인", "sentiment": "근거 부족", "key_driver": "공시"},
            "events_analysis": {"commentary": "공시 제목", "risk_level": "판단 불가", "key_point": "확인"},
            "tech_flow_analysis": {"action_guide": "지표 확인", "posture": "근거 부족", "timing_tip": "원본"},
        }, ensure_ascii=False), {}

    monkeypatch.setattr("kr_quant.research.analyze.call_chat", chat)
    result = get_tier1_insights(
        "005930", "삼성전자",
        news=[{"title": "실적", "source": "n", "snippet": "s"}],
        events=[{"title": "공시", "date": "2026-09-08"}],
        tech={"rsi": 50}, flow={"inst": 1},
        settings=SimpleNamespace(root=tmp_path, openrouter_api_key="test-key"),
    )
    assert calls == [free.model, flash.model]
    assert result["ai_generated"] is True
    assert result["model"] == flash.model
    assert result["used_in_quant"] is False


def test_tier1_cached_chat_reuses_only_successful_generation(tmp_path, monkeypatch):
    endpoint = SimpleNamespace(provider="OPENROUTER", model="free-model")
    calls = {"count": 0}

    def fake_call_chat(*_args, **_kwargs):
        calls["count"] += 1
        return json.dumps({"headline": "실제 근거 해설"}, ensure_ascii=False), {}

    monkeypatch.setattr("kr_quant.research.analyze.call_chat", fake_call_chat)
    kwargs = {
        "namespace": "rank",
        "prompt_version": "rank_v1",
        "evidence": {"ticker": "005930", "score": 70},
        "messages": [{"role": "user", "content": "설명"}],
        "sources": ["all_stocks"],
        "evidence_count": 1,
    }

    first = tier1_cached_chat_json(tmp_path, endpoint, **kwargs)
    second = tier1_cached_chat_json(tmp_path, endpoint, **kwargs)

    assert calls["count"] == 1
    assert first["status"] == "GENERATED"
    assert first["cache"]["hit"] is False
    assert second["headline"] == "실제 근거 해설"
    assert second["cache"]["hit"] is True


def test_tier1_cached_chat_does_not_store_provider_failure(tmp_path, monkeypatch):
    endpoint = SimpleNamespace(provider="OPENROUTER", model="free-model")
    calls = {"count": 0}

    def failing_call_chat(*_args, **_kwargs):
        calls["count"] += 1
        raise RuntimeError("temporary outage")

    monkeypatch.setattr("kr_quant.research.analyze.call_chat", failing_call_chat)
    kwargs = {
        "namespace": "market",
        "prompt_version": "market_v1",
        "evidence": {"vix": 20},
        "messages": [{"role": "user", "content": "설명"}],
        "sources": ["VIX"],
        "evidence_count": 1,
    }

    first = tier1_cached_chat_json(tmp_path, endpoint, **kwargs)
    second = tier1_cached_chat_json(tmp_path, endpoint, **kwargs)

    assert calls["count"] == 2
    assert first["status"] == "UNAVAILABLE"
    assert second["status"] == "UNAVAILABLE"
    assert not list((tmp_path / "data" / "cache" / "tier1_briefings").glob("*.json"))


def test_tier1_cached_chat_returns_generation_when_cache_write_fails(tmp_path, monkeypatch):
    endpoint = SimpleNamespace(provider="OPENROUTER", model="free-model")
    monkeypatch.setattr(
        "kr_quant.research.analyze.call_chat",
        lambda *_args, **_kwargs: (json.dumps({"headline": "생성 성공"}, ensure_ascii=False), {}),
    )
    monkeypatch.setattr(
        "kr_quant.research.tier1_contract._write_json_atomic",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = tier1_cached_chat_json(
        tmp_path,
        endpoint,
        namespace="dashboard",
        prompt_version="dashboard_v1",
        evidence={"rank": 1},
        messages=[{"role": "user", "content": "설명"}],
        evidence_count=1,
    )

    assert result["status"] == "GENERATED"
    assert result["headline"] == "생성 성공"
    assert result["cache"]["stored"] is False


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
