from kr_quant.events.classify import classify_report, classify_row
from kr_quant.flow.events import direction_turn, from_official_rows, from_toss_cache_rows, sample_rebalance, signed_streak, window_sums
from kr_quant.ownership.nps import is_nps_holder, parse_majorstock
import numpy as np
from fastapi.testclient import TestClient

from kr_quant.sunzi.critic import PERSONA_BANNED, POSTURE_KO, compose_yang_briefing, critic_panel
from kr_quant.sunzi.five import build_sunzi_board, di_panel, five_aspects, tian_panel
from kr_quant.web.app import app
from kr_quant.settings import load_settings


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
    assert five["critic"]["posture"] in POSTURE_KO
    assert five["critic"]["used_in_quant"] is False
    assert five["critic"]["persona_version"] == "yang_interpreter_v1"
    assert five["critic"]["one_line_judgment"]
    assert len(five["critic"]["comment"]) >= 80
    assert len(five["critic"]["sunzi_interpretation"]["tian"]) >= 60
    assert set(five["critic"]["sunzi_interpretation"]) == {"dao", "tian", "di", "jiang", "fa"}
    assert five["critic"]["persona_failure_flags"] == []


def test_critic_handles_empty_numpy_risk_flags():
    row = {
        "ticker": "005930",
        "financial_score": 8,
        "value_score": 22,
        "growth_score": 18,
        "fcf_yield": 0.05,
        "data_confidence": 90,
        "risk_flags": np.array([]),
        "exclusion_reasons": np.array([]),
    }
    parts = {
        "fa": {"fa_gate_pass": True},
        "dao": {"score": 72, "contrary": []},
        "tian": {"score": 62, "regime": "NEUTRAL"},
        "di": {"score": 71, "state_ko": "선행"},
        "jiang": {"score": 60, "contrary": []},
    }
    panel = critic_panel(row, parts)
    assert panel["posture"] in POSTURE_KO
    assert panel["used_in_quant"] is False


def test_yang_briefing_interprets_risk_off():
    brief = compose_yang_briefing(
        {"regime": "RISK_OFF", "regime_ko": "위험회피", "score": 38},
        {"WAIT": 38, "ENGAGE": 0, "OBSERVE": 0, "RETREAT": 0, "AVOID": 2},
        40,
        39,
        {"dao": 72, "fa": 90},
    )
    assert "天" in brief["sunzi_line"]
    assert "위험회피" in brief["sunzi_line"]
    blob = brief["sunzi_line"] + brief["yang_line"]
    for banned in PERSONA_BANNED:
        assert banned not in blob
    assert brief.get("persona_failure_flags") == []
    assert len(brief["yang_line"]) >= 80


def test_api_sunzi_board_returns_postures():
    client = TestClient(app)
    res = client.get("/api/sunzi?n=12")
    assert res.status_code == 200
    data = res.json()
    assert data.get("used_in_quant") is False
    if not data.get("configured"):
        assert "재계산" in (data.get("error") or "")
        return
    assert data["n"] > 0
    assert "postures" in data
    row = data["rows"][0]
    assert "dao" in row
    assert row.get("posture") in POSTURE_KO
    assert row.get("critic_score") is not None
    assert "briefing" in data
    assert "yang_line" in data["briefing"]
    assert len(data.get("aspects") or []) == 5
    board = build_sunzi_board(load_settings(), n=8)
    assert board["configured"] is True
    assert board["rows"]
    assert board["briefing"]["yang_line"]
    assert {a["id"] for a in board["aspects"]} == {"dao", "tian", "di", "jiang", "fa"}


def test_sunzi_query_can_leave_quant_top_slice():
    import pandas as pd

    s = load_settings()
    top = build_sunzi_board(s, n=8, universe="quant")
    if not top.get("configured"):
        return
    top_tickers = {r["ticker"] for r in top["rows"]}
    path = s.output_dir / "latest_all_stocks.parquet"
    if not path.exists():
        return
    df = pd.read_parquet(path)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    outside = df[~df["ticker"].isin(top_tickers)]
    if outside.empty:
        return
    rec = outside.iloc[0]
    found = build_sunzi_board(s, n=12, query=str(rec["ticker"]))
    assert found["configured"] is True
    assert str(rec["ticker"]).zfill(6) in {r["ticker"] for r in found["rows"]}
    all_board = build_sunzi_board(s, n=12, universe="all")
    assert all_board["universe"] == "all"


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
    rows = [{**row, "is_final": True} for row in rows]
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
    assert "기관합계+외국인 동반 수급" in out["pair_note"]
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
    rows = [{**row, "is_final": True} for row in rows]
    reb = sample_rebalance(rows, names={"005930": "삼성전자", "000660": "SK하이닉스"})
    assert reb["sample"] is True
    assert reb["used_in_quant"] is False
    assert reb["buy_n"] == 1
    assert reb["sell_n"] == 1
    assert "전시장" in reb["note"]


def test_event_rows_include_recent_days():
    rows = [
        {"trade_date": f"2026-08-{day:02d}", "ticker": "005930", "investor_type": kind, "net_value": 10, "is_final": True}
        for day in range(10, 20)
        for kind in ("INSTITUTION_TOTAL", "FOREIGN")
    ]
    out = from_official_rows(rows)
    assert out["consecutive"]
    recent = out["consecutive"][0]["recent"]
    assert 1 <= len(recent) <= 10
    assert recent[0]["date"] >= recent[-1]["date"]
    assert "primary" in recent[0] and "foreign" in recent[0]


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
