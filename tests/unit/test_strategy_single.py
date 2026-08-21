# -*- coding: utf-8 -*-
from kr_quant.settings import load_settings
from kr_quant.strategy.run import backtest_single_stock


def test_backtest_single_stock():
    s = load_settings()
    res = backtest_single_stock(s, "005930")
    assert isinstance(res, dict)
    if res.get("ok"):
        assert res["ticker"] == "005930"
        assert res["bars"] > 0
        assert "strategies" in res
        assert len(res["strategies"]) == 4
        assert "best_name" in res


def test_backtest_single_stock_invalid():
    s = load_settings()
    res = backtest_single_stock(s, "99999999_invalid")
    assert res.get("ok") is False
