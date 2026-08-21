from kr_quant.factors.scorecard import _score_to_grade, build_factor_scorecard


def test_score_to_grade():
    assert _score_to_grade(28.0, 30.0)[0] in {"A+", "A"}
    assert _score_to_grade(22.0, 25.0)[0] in {"A+", "A"}
    assert _score_to_grade(15.0, 30.0)[0] == "HOLD" or _score_to_grade(15.0, 30.0)[0] in {"B-", "C+", "C"}
    assert _score_to_grade(3.0, 30.0)[0] == "F"


def test_build_factor_scorecard():
    mock_stock = {
        "ticker": "005930",
        "company": "삼성전자",
        "quant_score": 82.5,
        "value_score": 26.0,
        "quality_score": 23.0,
        "growth_score": 20.0,
        "momentum_score": 7.5,
        "financial_score": 9.0,
        "per": 12.5,
        "pbr": 1.2,
        "roic": 0.15,
        "revenue_yoy": 0.18,
    }
    card = build_factor_scorecard(mock_stock)
    assert card["used_in_quant"] is False
    assert card["decision"] == "STRONG_BUY"
    assert len(card["factors"]) == 5
    v_factor = next(f for f in card["factors"] if f["id"] == "value")
    assert v_factor["grade"] in {"A+", "A"}
