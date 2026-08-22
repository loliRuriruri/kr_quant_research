# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from kr_quant.web.app import app
from kr_quant.research.infographic import generate_infographic_html

client = TestClient(app)


def test_generate_infographic_html():
    rec = {
        "ticker": "009450",
        "company": "경동나비엔",
        "as_of_date": "2026-08-21",
        "quant_score": 78.5,
        "quant_rank": 13,
        "strategy_backtest": {
            "best_name": "볼린저 평균회귀",
            "best_params_ko": "기간 20일 · 밴드폭 1.5배",
            "strategies": [
                {"name": "볼린저 평균회귀", "total_return": 0.222, "wf_hit": 0.67}
            ],
            "playbook": {
                "archetype_badge": "🔄 평균회귀형 파동",
                "entry_rule": "볼린저 하단 분할 매수",
                "exit_rule": "중심선 익절",
                "avoid_rule": "신고가 추격 매수 금지"
            }
        }
    }
    html = generate_infographic_html(rec)
    assert "<!DOCTYPE html>" in html
    assert "경동나비엔" in html
    assert "009450" in html
    assert "볼린저 평균회귀" in html
    assert "Chart.js" in html
    assert "growthRange" in html  # Valuation simulator check


def test_infographic_endpoint():
    res = client.get("/api/research/005930/infographic")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "005930" in res.text
