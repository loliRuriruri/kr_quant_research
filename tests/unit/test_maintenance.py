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
    assert stock["history_curve_source"] == "UNAVAILABLE"
    assert stock["trajectory_match"] is None


def test_curve_sync_marks_outperformance_as_excess_not_failure():
    from kr_quant.web.app import compute_curve_sync

    sync, samples, note, status = compute_curve_sync(
        [0, 1, 5, 20, 39.4],
        [0, 0.2, 0.3, 0.4, 0.5],
    )
    assert status == "초과"
    assert "위로 뚫음" in note
    assert samples >= 1
    assert sync is not None


def test_momentum_history_curve_uses_prior_years_not_example_path(tmp_path, monkeypatch):
    import pandas as pd
    from datetime import date
    from types import SimpleNamespace
    from kr_quant.web.app import enrich_momentum_portfolio_with_live_prices
    monkeypatch.setattr("kr_quant.web.app.fetch_naver_live_quotes", lambda _: {})

    staged = tmp_path / "staged" / "live"
    staged.mkdir(parents=True)
    rows = []
    for year, closes in ((2024, [100, 103, 108, 112]), (2025, [100, 102, 106, 111])):
        days = [date(year, 8, 27), date(year, 8, 28), date(year, 8, 29), date(year, 9, 1)]
        for day, close in zip(days, closes):
            rows.append({"ticker": "005930", "trade_date": day, "close": float(close)})
    rows.extend([
        {"ticker": "005930", "trade_date": date(2026, 8, 27), "close": 200.0},
        {"ticker": "005930", "trade_date": date(2026, 8, 28), "close": 202.0},
    ])
    pd.DataFrame(rows).to_parquet(staged / "prices.parquet")
    settings = SimpleNamespace(staged_dir=tmp_path / "staged")
    stock = enrich_momentum_portfolio_with_live_prices(settings, [{
        "code": "005930",
        "entry_date": "2026-08-27",
        "peak_date": "2026-09-01",
        "entry_price": 200,
        "history_curve": [0, 50, 90],
        "history_curve_source": "EXAMPLE",
    }])[0]
    assert stock["history_curve_source"] == "OBSERVED"
    assert stock["history_curve"][0] == 0.0
    assert stock["history_curve"][1] == 2.5
    assert stock["actual_curve"] == [0.0, 1.0]
    assert stock["sync_rate"] is not None
    assert stock["trajectory_samples"] >= 1
    assert stock["sync_status"] in {"초과", "동기", "미달"}
