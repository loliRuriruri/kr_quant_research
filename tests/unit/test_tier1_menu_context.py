from __future__ import annotations

import json

from fastapi.testclient import TestClient

from kr_quant.context import macro_brief
from kr_quant.research import analyze
from kr_quant.web import app as web_app


client = TestClient(web_app.app)


def _fake_chat(payload: dict):
    return json.dumps(payload, ensure_ascii=False), {}


def test_rank_tier1_briefing_uses_rank_change_and_factor_context(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "_ranking_tier1_snapshot",
        lambda settings, limit=12: {
            "as_of": "2026-08-26",
            "universe_count": 2,
            "low_confidence_count": 0,
            "missing": [],
            "top_rows": [
                {
                    "ticker": "005930",
                    "company": "삼성전자",
                    "rank": 1,
                    "previous_rank": 2,
                    "rank_change": 1,
                    "score": 80.0,
                    "score_change": 1.2,
                    "dominant_factors": [{"factor": "가치", "score": 24.0}],
                    "weak_factors": [{"factor": "모멘텀", "score": 8.0}],
                    "data_confidence": 96.0,
                }
            ],
            "movers": [{"ticker": "005930", "rank_change": 1}],
        },
    )
    monkeypatch.setattr(
        analyze,
        "call_chat",
        lambda *args, **kwargs: _fake_chat(
            {
                "headline": "삼성전자 순위 1단계 상승",
                "changes": ["2위에서 1위로 상승"],
                "top_explanations": [{"ticker": "005930", "summary": "현재 가치 점수가 상대적으로 높음"}],
                "cautions": ["이전 팩터 점수가 없어 변화 원인을 단정할 수 없음"],
            }
        ),
    )

    body = client.get("/api/rank/tier1-briefing").json()

    assert body["ok"] is True
    assert body["used_in_quant"] is False
    assert body["evidence"]["as_of"] == "2026-08-26"
    assert body["evidence"]["item_count"] == 2
    assert body["changes"] == ["2위에서 1위로 상승"]


def test_market_tier1_briefing_uses_actual_macro_rows(monkeypatch):
    fake_macro = {
        "fetched_at": "2026-08-26T15:00:00+00:00",
        "brief": {
            "overall": {"tone": "혼합", "good": 2, "bad": 2, "neutral": 1},
            "domestic": {
                "stance": {"tone": "부담"},
                "items": [
                    {"id": "kr_us_diff", "value": -0.88, "unit": "%p", "delta": None, "tone": "부담", "as_of": "2026-08-13"},
                ],
            },
            "international": {
                "stance": {"tone": "혼합"},
                "items": [
                    {"id": "DGS10", "value": 4.7, "unit": "%", "delta": -0.04, "tone": "우호", "as_of": "2026-08-24"},
                    {"id": "DGS2", "value": 4.24, "unit": "%", "delta": 0.0, "tone": "중립", "as_of": "2026-08-24"},
                    {"id": "T10Y2Y", "value": 0.47, "unit": "%p", "delta": 0.01, "tone": "우호", "as_of": "2026-08-25"},
                    {"id": "DEXKOUS", "value": 1385.0, "unit": "원", "delta": -8.3, "tone": "중립", "as_of": "2026-08-21"},
                ],
            },
            "yield_comparison": {"us_2y": 4.24, "us_10y": 4.7, "us_spread": 0.47},
            "as_of": {"fred": "2026-08-25", "ecos": "2026-08-13", "yahoo": "2026-08-26"},
        },
        "yahoo": {"indexes": [{"symbol": "^VIX", "last": 18.4, "ret_1d": 0.02, "as_of": "2026-08-26"}]},
        "yencarry": {},
        "margin_debt": {},
    }
    monkeypatch.setattr(macro_brief, "build_macro_dashboard", lambda settings, refresh=False: fake_macro)
    monkeypatch.setattr(
        analyze,
        "call_chat",
        lambda *args, **kwargs: _fake_chat(
            {
                "headline": "금리와 변동성 방향이 혼재",
                "risk_posture": "중립",
                "macro_insight": "10년물 하락은 우호적이지만 한미 금리차는 부담",
                "action_tip": "원화와 VIX의 후속 방향 확인",
                "drivers": [{"id": "DGS10", "direction": "우호", "reason": "직전 대비 -0.04%p"}],
            }
        ),
    )

    body = client.get("/api/market/tier1-briefing").json()

    assert body["ok"] is True
    assert body["evidence"]["item_count"] == 6
    assert body["evidence"]["missing"] == []
    assert body["drivers"][0]["id"] == "DGS10"
