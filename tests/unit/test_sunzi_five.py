from kr_quant.events.classify import classify_report, classify_row
from kr_quant.flow.events import direction_turn, from_official_rows, from_toss_cache_rows, sample_rebalance, signed_streak, window_sums
from kr_quant.ownership.nps import is_nps_holder, parse_majorstock
from kr_quant.sunzi.five import di_panel, five_aspects, tian_panel


def test_five_aspects_are_overlays():
    row = {
        "ticker": "005930",
        "company": "삼성전자",
        "industry": "반도체",
        "growth_score": 18,
        "quality_score": 20,
        "revenue_yoy": 0.1,
        "op_yoy": 0.08,
        "fcf_yield": 0.05,
        "roic": 0.14,
        "financial_score": 8,
        "data_confidence": 90,
        "weighted_metric_coverage": 0.95,
        "universe_eligible": True,
        "top20_eligible": True,
        "quant_score": 77,
        "risk_flags": [],
        "exclusion_reasons": [],
    }
    tian = tian_panel(market={"regime_score": 62, "regime": "NEUTRAL", "label": "중립", "components": []})
    di = di_panel(row, {"name": "반도체", "score": 71, "state_ko": "선행", "comment": "반도체 선행.", "rs": 80})
    five = five_aspects(row, tian=tian, sector={"name": "반도체", "score": 71, "state_ko": "선행", "comment": "반도체 선행.", "rs": 80})
    assert tian["used_in_quant"] is False
    assert di["used_in_quant"] is False
    assert five["used_in_quant"] is False
    assert five["fa_gate_pass"] is True
    assert five["parts"]["tian"]["score"] == 62
    assert five["parts"]["di"]["score"] == 71
    assert five["overlay_mean"] is not None
    assert five["quant_score"] == 77
    assert "Quant" in five["comment"]


def test_signed_streak_and_turn():
    buy = [10, 8, 4, 2, -3]
    streak = signed_streak(buy)
    assert streak["direction"] == "BUY"
    assert streak["days"] == 4
    assert streak["capped"] is False
    nets = [5, -2, -4]
    turn = direction_turn(nets, min_days=5)
    assert turn is None
    nets2 = [12, -3, -4, -5, -6, -7]
    turn2 = direction_turn(nets2, min_days=5)
    assert turn2 is not None
    assert turn2["from"] == "SELL"
    assert turn2["to"] == "BUY"
    assert turn2["prior_days"] == 5


def test_official_events_label_fund_not_nps():
    rows = []
    for i, day in enumerate(["2026-08-18", "2026-08-19", "2026-08-20"]):
        rows.append({"trade_date": day, "ticker": "005930", "investor_type": "FUND", "net_value": 100 + i})
        rows.append({"trade_date": day, "ticker": "005930", "investor_type": "FOREIGN", "net_value": 50 + i})
        rows.append({"trade_date": day, "ticker": "005930", "investor_type": "INSTITUTION_TOTAL", "net_value": 20})
    out = from_official_rows(rows, names={"005930": "삼성전자"}, min_turn=3)
    assert out["used_in_quant"] is False
    assert out["pair"] == "기금+외인"
    assert "국민연금" not in out["pair"]
    assert "연기금" not in out["pair"]
    assert out["consecutive"][0]["days"] >= 3
    assert out["paired"][0]["paired"] is True


def test_toss_events_need_daily_and_not_pension_rank():
    empty = from_toss_cache_rows([{"ticker": "005930", "company": "삼성전자"}], min_turn=5)
    assert empty["tickers"] == 0
    assert empty["skipped_no_daily"] == 1
    rows = [
        {
            "ticker": "005930",
            "company": "삼성전자",
            "daily": [
                {"date": "2026-08-20", "foreign": 10, "institution": 8},
                {"date": "2026-08-19", "foreign": 4, "institution": 3},
                {"date": "2026-08-18", "foreign": -2, "institution": 1},
            ],
        }
    ]
    out = from_toss_cache_rows(rows, min_turn=5)
    assert out["source"] == "TOSS"
    assert out["pair"] == "기관+외인"
    assert "연기금 전종목" in out["pair_note"]
    assert out["consecutive"][0]["days"] == 3


def test_window_sums_and_sample_rebalance():
    sums = window_sums([10, 4, -2, 1, 3, 5], windows=(5, 20))
    assert sums["w5"] == 16
    assert sums["w5_n"] == 5
    assert sums["w20_capped"] is True
    rows = [
        {"trade_date": "2026-08-20", "ticker": "005930", "investor_type": "INSTITUTION_TOTAL", "net_value": 100},
        {"trade_date": "2026-08-20", "ticker": "000660", "investor_type": "INSTITUTION_TOTAL", "net_value": -40},
        {"trade_date": "2026-08-19", "ticker": "005930", "investor_type": "INSTITUTION_TOTAL", "net_value": 10},
    ]
    reb = sample_rebalance(rows, names={"005930": "삼성전자", "000660": "SK하이닉스"})
    assert reb["sample"] is True
    assert reb["used_in_quant"] is False
    assert reb["buy_n"] == 1
    assert reb["sell_n"] == 1
    assert "전시장" in reb["note"]


def test_classify_dart_titles():
    assert classify_report("전환사채(해외전환사채 포함)발행결정") == "CB_ISSUE"
    assert classify_report("자기주식취득 결정") == "BUYBACK"
    assert classify_report("단일판매ㆍ공급계약체결") == "LARGE_CONTRACT"
    row = classify_row({"report_nm": "유상증자결정", "rcept_dt": "20260801", "rcept_no": "20260801000001"})
    assert row["event_type"] == "RIGHTS_OFFERING"
    assert row["jiang_tone"] == "contrary"
    assert row["used_in_quant"] is False


def test_nps_holder_and_majorstock_parse():
    assert is_nps_holder("국민연금공단")
    assert is_nps_holder("National Pension Service")
    assert not is_nps_holder("사모펀드")
    payload = {
        "list": [
            {
                "rcept_no": "20260819000001",
                "rcept_dt": "20260819",
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "repror": "국민연금공단",
                "stkrt": "8.51",
                "stkrt_irds": "0.12",
                "stkqy": "12345678",
                "stock_code": "005930",
            }
        ]
    }
    rows = parse_majorstock(payload)
    assert len(rows) == 1
    assert rows[0]["is_nps"] is True
    assert rows[0]["used_in_quant"] is False
    assert abs(rows[0]["holding_ratio"] - 0.0851) < 1e-6
    assert rows[0]["ticker"] == "005930"
