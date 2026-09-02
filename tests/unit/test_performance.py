# -*- coding: utf-8 -*-
"""P2-4 Performance and predicate pushdown tests."""
import time
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest

from kr_quant.freshness import _read_price_max, _read_financial_max
from kr_quant.portfolio.analysis import _prices as portfolio_prices
from kr_quant.strategy.run import _prices as strategy_prices
from kr_quant.timing.snapshot import load_prices, last_closes
from kr_quant.web.app import _corp_code, _has_usable_rank_rows, _local_company_names


def test_read_price_max_metadata_speed(tmp_path):
    df = pd.DataFrame({"trade_date": ["2026-08-28", "2026-08-29", "2026-09-01"], "close": [100, 105, 110]})
    p = tmp_path / "prices.parquet"
    df.to_parquet(p)

    t0 = time.perf_counter()
    max_d = _read_price_max(p)
    elapsed = time.perf_counter() - t0

    assert str(max_d) == "2026-09-01"
    assert elapsed < 0.1


def test_read_financial_max_column_pruning(tmp_path):
    df = pd.DataFrame({
        "available_date": ["2026-08-01", "2026-08-15"],
        "junk_col_1": ["x", "y"],
        "junk_col_2": [1, 2],
    })
    p = tmp_path / "financial.parquet"
    df.to_parquet(p)

    max_d = _read_financial_max(p)
    assert str(max_d) == "2026-08-15"


def test_strategy_prices_predicate_pushdown(tmp_path):
    folder = tmp_path / "data" / "staged" / "live"
    folder.mkdir(parents=True)
    df = pd.DataFrame({
        "ticker": ["005930", "000660", "035420"],
        "trade_date": ["2026-09-01", "2026-09-01", "2026-09-01"],
        "close": [70000, 120000, 200000],
        "open": [69000, 119000, 199000],
    })
    df.to_parquet(folder / "prices.parquet")
    settings = SimpleNamespace(staged_dir=tmp_path / "data" / "staged")

    filtered = strategy_prices(settings, tickers=["005930"], columns=["ticker", "close"])
    assert len(filtered) == 1
    assert filtered.iloc[0]["ticker"] == "005930"
    assert "open" not in filtered.columns


def test_portfolio_prices_predicate_pushdown(tmp_path):
    folder = tmp_path / "data" / "staged" / "live"
    folder.mkdir(parents=True)
    df = pd.DataFrame({
        "ticker": ["005930", "000660"],
        "trade_date": ["2026-09-01", "2026-09-01"],
        "close": [70000, 120000],
    })
    df.to_parquet(folder / "prices.parquet")
    settings = SimpleNamespace(staged_dir=tmp_path / "data" / "staged")

    res = portfolio_prices(settings, tickers=["000660"])
    assert len(res) == 1
    assert res.iloc[0]["ticker"] == "000660"


def test_corp_code_cache(monkeypatch, tmp_path):
    folder = tmp_path / "data" / "staged" / "live"
    folder.mkdir(parents=True)
    df = pd.DataFrame({
        "stock_code": ["005930", "000660"],
        "corp_code": ["00126380", "00164779"],
    })
    df.to_parquet(folder / "company.parquet")
    settings = SimpleNamespace(staged_dir=tmp_path / "data" / "staged")
    monkeypatch.setattr("kr_quant.web.app.load_settings", lambda: settings)

    c1 = _corp_code("005930", {})
    assert c1 == "00126380"

    (folder / "company.parquet").unlink()
    c2 = _corp_code("005930", {})
    assert c2 == "00126380"
