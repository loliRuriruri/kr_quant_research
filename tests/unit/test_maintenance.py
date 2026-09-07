# -*- coding: utf-8 -*-
"""P3 Maintenance tests: log sanitization and atomic IO."""
import json
import logging
from pathlib import Path
import pytest

from kr_quant.logging_config import SensitiveDataFilter, setup_logging
from kr_quant.atomic_io import write_json_atomic


def test_sensitive_data_filter():
    redactor = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Calling KRX with api_key=KRX_SECRET_12345 and Bearer eyJhbGciOiJIUzI1NiJ9",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "KRX_SECRET_12345" not in record.msg
    assert "api_key=***REDACTED***" in record.msg
    assert "Bearer ***REDACTED***" in record.msg


def test_write_json_atomic_dict_and_list(tmp_path):
    # Test dict payload
    dict_file = tmp_path / "data.json"
    write_json_atomic(dict_file, {"key": "value", "count": 10})
    assert json.loads(dict_file.read_text(encoding="utf-8")) == {"key": "value", "count": 10}

    # Test list payload
    list_file = tmp_path / "items.json"
    write_json_atomic(list_file, [{"id": 1}, {"id": 2}])
    assert json.loads(list_file.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]


def test_enrich_momentum_portfolio_with_live_prices(tmp_path, monkeypatch):
    import pandas as pd
    from datetime import date
    from types import SimpleNamespace
    from kr_quant.web.app import enrich_momentum_portfolio_with_live_prices
    monkeypatch.setattr("kr_quant.web.app.fetch_naver_live_quotes", lambda _: {})

    # Create dummy prices.parquet
    staged = tmp_path / "staged" / "live"
    staged.mkdir(parents=True)
    df_prices = pd.DataFrame([
        {"ticker": "005930", "trade_date": date(2026, 8, 27), "close": 70000.0},
        {"ticker": "005930", "trade_date": date(2026, 8, 28), "close": 71400.0},
        {"ticker": "005930", "trade_date": date(2026, 8, 31), "close": 73500.0},
    ])
    df_prices.to_parquet(staged / "prices.parquet")

    settings = SimpleNamespace(staged_dir=tmp_path / "staged")
    items = [{
        "id": "stock-005930",
        "name": "삼성전자",
        "code": "005930",
        "entry_date": "2026-08-27",
        "peak_date": "2026-09-10",
        "entry_price": 70000,
        "history_curve": [0, 2.0, 5.0, 8.0],
        "history_curve_source": "OBSERVED",
        "actual_curve": [0],
    }]

    enriched = enrich_momentum_portfolio_with_live_prices(settings, items)
    assert len(enriched) == 1
    stock = enriched[0]
    assert stock["actual_curve"] == [0.0, 2.0, 5.0]
    assert stock["current_price"] == 73500.0
    assert stock["current_return"] == 5.0
    assert stock["actual_dates"] == ["2026-08-27", "2026-08-28", "2026-08-31"]
    assert stock["trajectory_match"] >= 50.0
