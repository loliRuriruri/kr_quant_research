from kr_quant.flow.events import daily_chart, from_official_rows, sample_rebalance


def test_provisional_and_unknown_rows_cannot_change_confirmed_signals():
    confirmed = [
        dict(ticker="005930", trade_date="2026-09-07", investor_type=kind,
             net_value=-10, is_final=True)
        for kind in ("FOREIGN", "INSTITUTION_TOTAL")
    ]
    provisional = [
        dict(ticker="005930", trade_date="2026-09-08", investor_type=kind,
             net_value=999999, is_final=False)
        for kind in ("FOREIGN", "INSTITUTION_TOTAL")
    ]
    unknown = [dict(ticker="000660", trade_date="2026-09-08",
                    investor_type="FUND", net_value=999999)]
    for calculate in (daily_chart, from_official_rows, sample_rebalance):
        assert calculate(confirmed + provisional + unknown) == calculate(confirmed)


def test_only_unconfirmed_rows_produce_no_official_candidates():
    rows = [dict(ticker="005930", trade_date="2026-09-08",
                 investor_type="FOREIGN", net_value=100, is_final=False)]
    assert from_official_rows(rows)["tickers"] == 0
    assert sample_rebalance(rows)["empty"] is True
    assert daily_chart(rows) == []
