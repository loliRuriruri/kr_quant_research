from kr_quant.us13f.edgar import pick_infotable_name
from kr_quant.us13f.enrich import _annotate_security
from kr_quant.us13f.names import korean_for_issuer, korean_for_ticker
from kr_quant.us13f.parse import aggregate_holdings, common_holdings, compare_holdings, parse_infotable, trend_rows

XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>2000000000</value>
    <shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>500000000</value>
    <shrsOrPrnAmt><sshPrnamt>250</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>100000000</value>
    <shrsOrPrnAmt><sshPrnamt>50</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parse_and_aggregate():
    rows = parse_infotable(XML)
    assert len(rows) == 3
    book = aggregate_holdings(rows)
    assert book["037833100"]["shares"] == 1250
    assert book["037833100"]["value"] == 2500000000
    assert abs(book["037833100"]["weight"] + book["67066G104"]["weight"] - 1) < 1e-9


def test_compare_new_exit_increase():
    prev = aggregate_holdings(
        [
            {"cusip": "AAA", "issuer": "Old", "value": 10, "shares": 10},
            {"cusip": "BBB", "issuer": "Hold", "value": 20, "shares": 5},
        ]
    )
    curr = aggregate_holdings(
        [
            {"cusip": "BBB", "issuer": "Hold", "value": 40, "shares": 9},
            {"cusip": "CCC", "issuer": "NewCo", "value": 80, "shares": 2},
        ]
    )
    changes = {r["cusip"]: r["action"] for r in compare_holdings(prev, curr)}
    assert changes["AAA"] == "exit"
    assert changes["BBB"] == "increase"
    assert changes["CCC"] == "new"


def test_common_and_trend():
    a = {"X": {"cusip": "X", "issuer": "Ex", "value": 10, "shares": 1, "weight": 1}}
    b = {"X": {"cusip": "X", "issuer": "Ex", "value": 20, "shares": 2, "weight": 1}}
    common = common_holdings({"A": a, "B": b}, min_filers=2)
    assert common[0]["n_filers"] == 2
    changes = {
        "A": [{"cusip": "X", "issuer": "Ex", "action": "new", "value_delta": 10}],
        "B": [{"cusip": "X", "issuer": "Ex", "action": "increase", "value_delta": 5}],
    }
    trend = trend_rows(changes)
    assert trend[0]["score"] == 2


def test_pick_infotable_largest_xml():
    payload = {
        "directory": {
            "item": [
                {"name": "primary_doc.xml", "size": "5000"},
                {"name": "56757.xml", "size": "44724"},
                {"name": "index.html", "size": "100"},
            ]
        }
    }
    assert pick_infotable_name(payload) == "56757.xml"
    payload2 = {
        "directory": {
            "item": [
                {"name": "primary_doc.xml", "size": "100"},
                {"name": "form13fInfoTable.xml", "size": "200"},
                {"name": "other.xml", "size": "9999"},
            ]
        }
    }
    assert pick_infotable_name(payload2) == "form13fInfoTable.xml"


def test_korean_names_and_tickers():
    assert korean_for_ticker("AAPL")[0] == "애플"
    hint = korean_for_issuer("PALANTIR TECHNOLOGIES INC")
    assert hint[0] == "PLTR"
    assert "팔란티어" in hint[1]
    row = {"cusip": "037833100", "issuer": "APPLE INC"}
    _annotate_security(row, {"037833100": {"ticker": "AAPL", "type": "Common Stock"}})
    assert row["ticker"] == "AAPL"
    assert row["issuer_ko"] == "애플"
    assert "아이폰" in row["note_ko"]
