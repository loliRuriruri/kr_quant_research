# -*- coding: utf-8 -*-
from kr_quant.ingest.kis import KisInvestorAdapter, parse_investor_payload
from kr_quant.universe.identifiers import (
    EMPTY_TICKER,
    UNSUPPORTED_TICKER_FORMAT,
    canonical_ticker,
    is_numeric_ticker,
    provider_symbol,
    provider_supports,
)


def test_alphanumeric_krx_code_is_not_collapsed_to_another_name():
    assert canonical_ticker("0220W0") == "0220W0"
    assert canonical_ticker("0220W0") != canonical_ticker("000220")
    assert canonical_ticker("0220W0") != "000220"
    assert canonical_ticker("0220W0") != "002200"


def test_numeric_samsung_still_pads():
    assert canonical_ticker("5930") == "005930"
    assert canonical_ticker("005930") == "005930"
    assert canonical_ticker("005930.0") == "005930"
    assert canonical_ticker("A005930") == "005930"
    assert is_numeric_ticker("005930")


def test_kis_rejects_alphanumeric_without_mutating():
    symbol, err = provider_symbol("kis", "0220W0")
    assert symbol is None
    assert err == UNSUPPORTED_TICKER_FORMAT
    assert not provider_supports("kis", "0220W0")
    assert provider_supports("kis", "005930")
    assert provider_symbol("kis", "005930") == ("005930", None)


def test_toss_keeps_alphanumeric_and_prefixes_numeric():
    assert provider_symbol("toss", "005930") == ("A005930", None)
    assert provider_symbol("toss", "0220W0") == ("0220W0", None)
    assert provider_symbol("krx", "0220W0") == ("0220W0", None)
    assert provider_symbol("kis", "")[1] == EMPTY_TICKER


def test_kis_collect_does_not_call_network_for_alpha_code(monkeypatch):
    adapter = KisInvestorAdapter("k", "s", "https://example.invalid")
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("KIS HTTP must not run for unsupported tickers")

    monkeypatch.setattr(adapter, "token", boom)
    monkeypatch.setattr(adapter, "fetch_stock_investor", boom)
    assert adapter.collect_stock("0220W0") == []
    assert called["n"] == 0


def test_kis_parse_keeps_canonical_alpha_code():
    rows = parse_investor_payload(
        {"output": {"stck_bsop_date": "20260828", "frgn_ntby_qty": "1"}},
        "0220W0",
    )
    assert rows
    assert rows[0]["ticker"] == "0220W0"
    assert rows[0]["ticker"] != "000220"
