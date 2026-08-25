from pathlib import Path

from kr_quant.flow.store import connect, coverage, init_investor_db, load_ticker, upsert_flows
from kr_quant.flow.types import display_name, normalize_investor_type
from kr_quant.ingest.kis import parse_investor_payload
from kr_quant.sunzi.alignment import dao_panel, jiang_panel


def test_fund_is_not_called_nps():
    assert normalize_investor_type("fund_ntby_qty") == "FUND"
    assert display_name("FUND") == "기금"
    assert "국민연금" not in display_name("FUND")
    assert "연기금" not in display_name("FUND")


def test_parse_kis_fixture_without_http():
    payload = {
        "output": {
            "stck_bsop_date": "20260819",
            "prsn_ntby_qty": "-1200",
            "frgn_ntby_qty": "800",
            "orgn_ntby_qty": "300",
            "fund_ntby_qty": "40",
            "frgn_ntby_tr_pbmn": "120000000",
        }
    }
    rows = parse_investor_payload(payload, "5930")
    types = {r["investor_type"] for r in rows}
    assert types == {"INDIVIDUAL", "FOREIGN", "INSTITUTION_TOTAL", "FUND"}
    foreign = next(r for r in rows if r["investor_type"] == "FOREIGN")
    assert foreign["ticker"] == "005930"
    assert foreign["trade_date"] == "2026-08-19"
    assert foreign["net_qty"] == 800
    assert foreign["net_value"] == 120000000
    assert foreign["used_in_quant"] is False
    assert foreign["label_ko"] == "외국인"
    fund = next(r for r in rows if r["investor_type"] == "FUND")
    assert fund["label_ko"] == "기금"


def test_duckdb_roundtrip(tmp_path: Path):
    db = tmp_path / "t.duckdb"
    con = connect(db)
    init_investor_db(con)
    n = upsert_flows(
        con,
        [
            {
                "trade_date": "2026-08-19",
                "ticker": "005930",
                "investor_type": "FOREIGN",
                "investor_type_raw": "frgn_ntby_qty",
                "net_qty": 10,
                "net_value": 1000,
                "is_final": True,
                "source": "KIS",
                "run_id": "test",
            }
        ],
    )
    assert n == 1
    cov = coverage(con)
    assert cov["rows"] == 1
    assert cov["tickers"] == 1
    assert cov["used_in_quant"] is False
    rows = load_ticker(con, "5930")
    assert rows[0]["investor_type"] == "FOREIGN"
    con.close()


def test_dao_jiang_are_overlays():
    row = {
        "growth_score": 20,
        "quality_score": 18,
        "revenue_yoy": 0.12,
        "op_yoy": 0.08,
        "fcf_yield": 0.06,
        "roic": 0.15,
        "financial_score": 7,
        "risk_flags": [],
        "data_confidence": 88,
        "fa_gate_pass": True,
    }
    dao = dao_panel(row)
    jiang = jiang_panel(row)
    assert dao["used_in_quant"] is False
    assert jiang["used_in_quant"] is False
    assert dao["score"] > 50
    assert jiang["score"] > 50
    assert dao["comment"]
