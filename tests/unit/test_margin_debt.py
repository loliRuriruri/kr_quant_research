# -*- coding: utf-8 -*-
from kr_quant.context.margin_debt import get_margin_debt_snapshot, fetch_margin_debt_history


def test_margin_debt_snapshot():
    res = get_margin_debt_snapshot(refresh=True)
    assert isinstance(res, dict)
    if res.get("ok"):
        assert "margin_debt_trillion" in res
        assert "deposit_trillion" in res
        assert "margin_deposit_ratio" in res
        assert "status" in res
        assert "warning" in res
        assert res["margin_debt_trillion"] >= 0
        assert res["deposit_trillion"] >= 0
        assert res["status"] in {"DANGER", "CAUTION", "NEUTRAL", "OPPORTUNITY"}
        assert len(res["history"]) > 0
