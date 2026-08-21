"""Seeking Alpha style Quant Factor Scorecard generator (A+ to F grades).

Calculates standardized factor letter grades (A+, A, A-, B+, B, B-, C+, C, C-, D, F)
for Value, Quality, Growth, Momentum, and Stability based on factor scores.
Overlay only — never mutates fundamental quant_score.
"""

from __future__ import annotations

from typing import Any


def _score_to_grade(score: float | None, max_score: float) -> tuple[str, float]:
    """Converts a factor score out of max_score to a letter grade and percentage (0~100)."""
    if score is None or max_score <= 0:
        return "N/A", 0.0
    pct = max(0.0, min(100.0, (float(score) / float(max_score)) * 100.0))
    if pct >= 92.0:
        grade = "A+"
    elif pct >= 84.0:
        grade = "A"
    elif pct >= 76.0:
        grade = "A-"
    elif pct >= 68.0:
        grade = "B+"
    elif pct >= 60.0:
        grade = "B"
    elif pct >= 52.0:
        grade = "B-"
    elif pct >= 44.0:
        grade = "C+"
    elif pct >= 36.0:
        grade = "C"
    elif pct >= 28.0:
        grade = "C-"
    elif pct >= 18.0:
        grade = "D"
    else:
        grade = "F"
    return grade, round(pct, 1)


def build_factor_scorecard(stock_row: dict[str, Any]) -> dict[str, Any]:
    """Builds Seeking Alpha style 5-factor scorecard for a given stock dict."""
    if not stock_row:
        return {"configured": False, "used_in_quant": False, "factors": []}

    q_score = float(stock_row.get("quant_score") or 0)

    # Quant Decision label (Seeking Alpha style)
    if q_score >= 80.0:
        decision = "STRONG_BUY"
        decision_ko = "적극 매수 우위 (Strong Buy)"
    elif q_score >= 68.0:
        decision = "BUY"
        decision_ko = "매수 우위 (Buy)"
    elif q_score >= 50.0:
        decision = "HOLD"
        decision_ko = "보유 관망 (Hold)"
    elif q_score >= 35.0:
        decision = "SELL"
        decision_ko = "매도 주의 (Sell)"
    else:
        decision = "STRONG_SELL"
        decision_ko = "적극 매도/비중 축소 (Strong Sell)"

    # Factor specifications: [Key, Label, Max, Submetrics]
    specs = [
        (
            "value",
            "가치 (Valuation)",
            "value_score",
            30.0,
            [
                {"name": "PER", "value": stock_row.get("per"), "fmt": "{:.1f}"},
                {"name": "PBR", "value": stock_row.get("pbr"), "fmt": "{:.2f}"},
                {"name": "EV/EBIT", "value": stock_row.get("ev_ebit"), "fmt": "{:.1f}"},
                {"name": "FCF 수익률", "value": stock_row.get("fcf_yield"), "fmt": "{:.1%}"},
            ],
        ),
        (
            "quality",
            "수익성/품질 (Profitability)",
            "quality_score",
            25.0,
            [
                {"name": "ROIC", "value": stock_row.get("roic"), "fmt": "{:.1%}"},
                {"name": "ROE", "value": stock_row.get("roe"), "fmt": "{:.1%}"},
            ],
        ),
        (
            "growth",
            "성장성 (Growth)",
            "growth_score",
            25.0,
            [
                {"name": "매출액 YoY", "value": stock_row.get("revenue_yoy"), "fmt": "{:+.1%}"},
                {"name": "영업이익 YoY", "value": stock_row.get("op_yoy"), "fmt": "{:+.1%}"},
            ],
        ),
        (
            "momentum",
            "모멘텀 (Momentum)",
            "momentum_score",
            10.0,
            [
                {"name": "3개월 수익률", "value": stock_row.get("return_3m"), "fmt": "{:+.1%}"},
                {"name": "6개월 수익률", "value": stock_row.get("return_6m"), "fmt": "{:+.1%}"},
                {"name": "12개월 수익률", "value": stock_row.get("return_12m"), "fmt": "{:+.1%}"},
            ],
        ),
        (
            "stability",
            "재무 안정성 (Safety)",
            "financial_score",
            10.0,
            [
                {"name": "위험 패널티", "value": stock_row.get("risk_penalty"), "fmt": "-{:.1f}"},
                {"name": "데이터 신뢰도", "value": stock_row.get("data_confidence"), "fmt": "{:.1f}"},
            ],
        ),
    ]

    factor_cards = []
    for f_id, label, key, max_val, submetrics in specs:
        raw_val = stock_row.get(key)
        val = float(raw_val) if raw_val is not None else 0.0
        grade, pct = _score_to_grade(val, max_val)

        sub_list = []
        for sm in submetrics:
            v = sm.get("value")
            if v is None:
                txt = "—"
            else:
                try:
                    txt = sm["fmt"].format(float(v))
                except Exception:  # noqa: BLE001
                    txt = str(v)
            sub_list.append({"name": sm["name"], "display": txt})

        factor_cards.append({
            "id": f_id,
            "label": label,
            "score": round(val, 1),
            "max": max_val,
            "percentile": pct,
            "grade": grade,
            "submetrics": sub_list,
        })

    return {
        "used_in_quant": False,
        "ticker": stock_row.get("ticker"),
        "company": stock_row.get("company"),
        "quant_score": round(q_score, 1),
        "decision": decision,
        "decision_ko": decision_ko,
        "factors": factor_cards,
        "disclaimer": "Seeking Alpha 스타일 팩터 성적표는 Quant 점수 요약 시각화이며, 자의적 수정 없이 기존 점수를 100% 반영합니다.",
    }
