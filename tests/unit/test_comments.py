from kr_quant.web.comments import (
    empty_comment,
    empty_comment_short,
    flow_comment,
    flow_comment_short,
    pe_comment,
    quant_comment,
    quant_comment_short,
    toss_comment,
    trade_comment,
    us13f_comment,
)


def test_quant_comment_explains_rank_and_drivers():
    text = quant_comment(
        {
            "quant_rank": 1,
            "quant_score": 79.8,
            "value_score": 22.9,
            "quality_score": 21.1,
            "growth_score": 22.9,
            "momentum_score": 5.5,
            "financial_score": 7.3,
            "risk_penalty": 0,
            "weighted_metric_coverage": 0.93,
            "data_confidence": 92.8,
            "data_flags": "SHARE_ADJ_MOMENTUM|INSUFFICIENT_HISTORY",
        }
    )
    assert "1위" in text
    assert "조건 통과" in text
    assert "Quant 79.8점" in text
    assert "가치" in text or "성장" in text
    assert "커버리지 93%" in text
    assert "매수 신호" in text
    assert "quant_score" not in text
    short = quant_comment_short(
        {
            "quant_rank": 1,
            "value_score": 22.9,
            "quality_score": 21.1,
            "growth_score": 22.9,
            "momentum_score": 5.5,
            "financial_score": 7.3,
            "weighted_metric_coverage": 0.93,
        }
    )
    assert "1위" in short
    assert "우위" in short
    assert len(short) < len(text)


def test_flow_and_empty_and_trade_comments_are_korean():
    row = {
        "days": 5,
        "foreign_net": 110,
        "institution_net": 50,
        "dual_krw": 12_000_000_000,
        "pe_net": 35,
        "pe_krw": 3_000_000_000,
        "pe_buy": True,
        "pe_streak": 3,
        "dual": True,
        "empty": True,
        "empty_krw": 8_000_000_000,
        "sell_streak": 4,
        "foreign_holding_rate": 0.032,
        "comeback": False,
        "in_quant": False,
        "setups": ["쌍끌이", "사모매집"],
        "ta": {"labels": ["스토 과매도", "구름 위"]},
    }
    flow = flow_comment(row)
    assert "외인" in flow and "기관" in flow
    assert "사모" in flow
    assert "Quant" in flow or "퀀트" in flow
    pe = pe_comment(row)
    assert "사모" in pe
    assert "3일 연속" in pe
    empty = empty_comment(row)
    assert "순매도" in empty
    assert "외인 지분" in empty
    trade = trade_comment(row)
    assert "퀀트 TOP100 밖" in trade
    assert "스토 과매도" in trade
    assert "외인" in flow_comment_short(row)
    assert "쌍매도" in empty_comment_short(row)


def test_toss_and_13f_comments():
    toss = toss_comment({"rank": 2, "change_rate": 0.042, "trading_amount": 5e10}, "급상승")
    assert "토스 급상승 2위" in toss
    assert "Quant" in toss
    neu = us13f_comment(
        {"filer_ko": "버크셔", "issuer_ko": "애플", "value": 120_000_000, "weight": 0.08},
        "new",
    )
    assert "버크셔가" in neu
    assert "애플을" in neu
    assert "신규" in neu
    assert "13F" in neu or "시차" in neu
