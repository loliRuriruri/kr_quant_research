from kr_quant.ingest.tossinvest import normalize_ranking_row


def test_normalize_ranking_row_reads_nested_price():
    row = normalize_ranking_row(
        {
            "rank": 1,
            "symbol": "950260",
            "price": {"lastPrice": "18330", "changeRate": "0.3"},
        }
    )
    assert row["code"] == "950260"
    assert row["last"] == 18330
    assert abs(row["change_rate"] - 0.3) < 1e-9
    assert row["page"].endswith("A950260")
