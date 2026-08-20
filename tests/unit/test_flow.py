from kr_quant.flow.investor import classify_setups, filter_trading, search_empty_houses, summarize_records
from kr_quant.flow.universe import KNOWN_ETF, local_name
from kr_quant.flow.scan import amount_bucket_stats, analyze_hit_rate, filter_by_min_krw


def test_dual_and_pe_from_toss_shape():
    recs = [
        {
            "date": "2026-08-20",
            "foreigner": {"netBuyVolume": "100"},
            "institution": {
                "netBuyVolume": "50",
                "breakdown": {"privateEquityFund": {"netBuyVolume": "40"}},
            },
            "individual": {"netBuyVolume": "-150"},
        },
        {
            "date": "2026-08-19",
            "foreigner": {"netBuyVolume": "10"},
            "institution": {
                "netBuyVolume": "5",
                "breakdown": {"privateEquityFund": {"netBuyVolume": "-5"}},
            },
            "individual": {"netBuyVolume": "-15"},
        },
    ]
    out = summarize_records(recs, days=5)
    assert out["dual"] is True
    assert out["pe_buy"] is True
    assert out["foreign_net"] == 110
    assert out["pe_net"] == 35
    assert out["used_in_quant"] is False
    assert out["empty"] is False
    assert out["comeback"] is False


def test_hit_rate():
    stats = analyze_hit_rate([{"ret_5d": 0.02}, {"ret_5d": -0.01}, {"ret_5d": 0.03}], "ret_5d")
    assert stats["n"] == 3
    assert abs(stats["hit"] - round(2 / 3, 3)) < 1e-9
    assert stats["avg"] > 0
    assert stats["median"] == 0.02


def test_amount_filter_and_buckets():
    rows = [
        {"pe_krw": 2_000_000_000, "ret_5d": 0.04},
        {"pe_krw": 12_000_000_000, "ret_5d": -0.02},
        {"pe_krw": 500_000_000, "ret_5d": 0.01},
    ]
    big = filter_by_min_krw(rows, "pe_krw", 1_000_000_000)
    assert len(big) == 2
    buckets = amount_bucket_stats(rows, "pe_krw")
    labels = [b["label"] for b in buckets]
    assert labels == ["전체", "10억+", "50억+", "100억+"]
    assert buckets[0]["n"] == 3
    assert buckets[1]["n"] == 2
    assert buckets[3]["n"] == 1


def _day(date, foreign, inst, individual, rate=None):
    rec = {
        "date": date,
        "foreigner": {"netBuyVolume": str(foreign)},
        "institution": {"netBuyVolume": str(inst), "breakdown": {}},
        "individual": {"netBuyVolume": str(individual)},
    }
    if rate is not None:
        rec["foreignerHolding"] = {"holdingRate": str(rate), "holdingQuantity": "1"}
    return rec


def test_empty_house_and_comeback():
    recs = [
        _day("2026-08-20", 40, 20, -60, 0.04),
        _day("2026-08-19", 10, 5, -15, 0.039),
        _day("2026-08-18", -80, -50, 130, 0.041),
        _day("2026-08-17", -90, -40, 130, 0.045),
        _day("2026-08-14", -20, -10, 30, 0.05),
    ]
    out = summarize_records(recs, days=5)
    assert out["empty"] is True
    assert out["retail_absorb"] is True
    assert out["comeback"] is True
    assert out["sell_streak"] == 0
    assert out["foreign_holding_rate"] == 0.04
    assert out["foreign_rate_chg"] == 0.04 - 0.05

    sold = [
        _day("2026-08-20", -10, -8, 18, 0.02),
        _day("2026-08-19", -5, -4, 9, 0.021),
    ]
    gone = summarize_records(sold, days=5)
    assert gone["empty"] is True
    assert gone["comeback"] is False
    assert gone["sell_streak"] == 2

    rows = [
        {"ticker": "000001", "company": "알파", "empty": True, "comeback": False, "retail_absorb": True, "foreign_holding_rate": 0.02, "empty_krw": 8_000_000_000},
        {"ticker": "000002", "company": "베타", "empty": False, "comeback": True, "retail_absorb": False, "foreign_holding_rate": 0.12, "empty_krw": 1_000_000_000},
        {"ticker": "000003", "company": "감마", "empty": True, "comeback": False, "retail_absorb": False, "foreign_holding_rate": 0.08, "empty_krw": 500_000_000},
    ]
    assert [r["ticker"] for r in search_empty_houses(rows, mode="empty")] == ["000001", "000003"]
    assert [r["ticker"] for r in search_empty_houses(rows, query="베타", mode="all")] == ["000002"]
    assert [r["ticker"] for r in search_empty_houses(rows, mode="low_foreign")] == ["000001"]
    assert [r["ticker"] for r in search_empty_houses(rows, mode="empty", min_exit_krw=1_000_000_000)] == ["000001"]


def test_pe_accum_and_trading_filter():
    recs = [
        _day("2026-08-20", 10, 20, -30),
        _day("2026-08-19", 8, 12, -20),
    ]
    recs[0]["institution"]["breakdown"] = {"privateEquityFund": {"netBuyVolume": "5"}}
    recs[1]["institution"]["breakdown"] = {"privateEquityFund": {"netBuyVolume": "4"}}
    out = summarize_records(recs, days=5)
    assert out["pe_buy"] is True
    assert out["pe_streak"] == 2
    assert out["pe_accum"] is True
    assert out["dual"] is True
    assert "쌍끌이" in classify_setups(out)
    assert "사모매집" in classify_setups(out)
    assert "쌍끌이+사모" in classify_setups(out)

    rows = [
        {"ticker": "111111", "company": "퀀트안", "in_quant": True, "dual": True, "pe_buy": False, "empty": False, "comeback": False, "dual_krw": 9e9, "pe_krw": 0, "empty_krw": 0, "setups": ["쌍끌이"]},
        {"ticker": "222222", "company": "쌍끌이밖", "in_quant": False, "dual": True, "pe_buy": True, "pe_accum": True, "empty": False, "comeback": False, "dual_krw": 3e9, "pe_krw": 1e9, "empty_krw": 0, "setups": ["쌍끌이", "사모매집"]},
        {"ticker": "333333", "company": "빈집밖", "in_quant": False, "dual": False, "pe_buy": False, "empty": True, "comeback": False, "dual_krw": 0, "pe_krw": 0, "empty_krw": 4e9, "setups": ["빈집"]},
    ]
    outside = filter_trading(rows, mode="setup", exclude_quant=True)
    assert [r["ticker"] for r in outside] == ["333333", "222222"]
    assert [r["ticker"] for r in filter_trading(rows, mode="dual", exclude_quant=True)] == ["222222"]
    assert [r["ticker"] for r in filter_trading(rows, mode="dual_pe", exclude_quant=False)] == ["222222"]
    assert [r["ticker"] for r in filter_trading(rows, query="빈집", mode="empty", exclude_quant=True)] == ["333333"]


def test_etf_local_names():
    assert local_name("069500") == "KODEX 200"
    assert local_name("114800") == "KODEX 인버스"
    assert local_name("252710") == "TIGER 200선물인버스2X"
    assert "069500" in KNOWN_ETF
