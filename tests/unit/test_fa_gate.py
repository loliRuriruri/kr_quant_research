from kr_quant.sunzi.fa import fa_gate


def test_fa_pass_does_not_touch_quant():
    gate = fa_gate(
        {
            "data_confidence": 88,
            "weighted_metric_coverage": 0.93,
            "universe_eligible": True,
            "top20_eligible": True,
            "exclusion_reasons": [],
            "risk_flags": [],
            "quant_score": 81,
        }
    )
    assert gate["used_in_quant"] is False
    assert gate["fa_gate_pass"] is True
    assert gate["a_candidate"] is True
    assert gate["fa_label"] in {"🛡️ 재무적격", "재무적격", "法 통과"}
    assert gate["comment"]


def test_fa_fail_on_stale_and_low_confidence():
    gate = fa_gate(
        {
            "data_confidence": 40,
            "weighted_metric_coverage": 0.5,
            "universe_eligible": True,
            "exclusion_reasons": "STALE_FINANCIALS",
            "risk_flags": "CB_BW_OVERHANG",
        }
    )
    assert gate["fa_gate_pass"] is False
    assert "LOW_CONFIDENCE" in gate["fa_reasons"]
    assert "CRITICAL_EXCLUSION" in gate["fa_reasons"]
    assert "CRITICAL_RISK" in gate["fa_reasons"]
    assert gate["used_in_quant"] is False
