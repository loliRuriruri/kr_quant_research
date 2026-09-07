"""Seeking Alpha style Quant Factor Scorecard generator (A+ to F grades).

Calculates standardized factor letter grades (A+, A, A-, B+, B, B-, C+, C, C-, D, F)
for Value, Quality, Growth, Momentum, and Stability based on factor scores.
Overlay only — never mutates fundamental quant_score.
"""

from __future__ import annotations

from typing import Any
import math


def _score_to_grade(score: float | None, max_score: float) -> tuple[str, float]:
    """Converts a factor score out of max_score to a letter grade and percentage (0~100)."""
    if score is None or max_score <= 0 or not math.isfinite(float(score)):
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

    try:
        q_score = float(stock_row.get("quant_score"))
    except (TypeError, ValueError):
        q_score = None
    if q_score is not None and (not math.isfinite(q_score) or not 0 <= q_score <= 100):
        q_score = None

    # A score band is neither a trade recommendation nor an OOS validation.
    if stock_row.get("universe_eligible") is False:
        decision, decision_ko = "INELIGIBLE", "선정 제외 · 제외 사유 확인"
    elif q_score is None:
        decision, decision_ko = "UNAVAILABLE", "점수 자료 없음"
    elif q_score >= 80.0:
        decision = "HIGH_SCORE"
        decision_ko = "높은 점수 구간 (80점 이상)"
    elif q_score >= 68.0:
        decision = "UPPER_SCORE"
        decision_ko = "중상위 점수 구간 (68~80점 미만)"
    elif q_score >= 50.0:
        decision = "MID_SCORE"
        decision_ko = "중간 점수 구간 (50~68점 미만)"
    elif q_score >= 35.0:
        decision = "LOW_SCORE"
        decision_ko = "낮은 점수 구간 (35~50점 미만)"
    else:
        decision = "VERY_LOW_SCORE"
        decision_ko = "낮은 점수 구간 (35점 미만)"

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
        try:
            val = float(raw_val) if raw_val is not None else None
        except (TypeError, ValueError):
            val = None
        if val is not None and not math.isfinite(val):
            val = None
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
            "score": round(val, 1) if val is not None else None,
            "max": max_val,
            "percentile": pct,
            "grade": grade,
            "submetrics": sub_list,
        })

    return {
        "used_in_quant": False,
        "ticker": stock_row.get("ticker"),
        "company": stock_row.get("company"),
        "quant_score": round(q_score, 1) if q_score is not None else None,
        "decision": decision,
        "decision_ko": decision_ko,
        "factors": factor_cards,
        "disclaimer": "KR Quant 자체 점수의 배점 대비 비율과 등급입니다. 업종 내 순위 백분위나 매매 권고, 미래 성과 확률이 아닙니다. 적격성·자료 시점·검증 결과는 별도로 확인하세요.",
    }
