from __future__ import annotations

import os

import pandas as pd
import pytest

from kr_quant.atomic_io import write_csv_atomic, write_json_atomic, write_parquet_atomic


def test_write_parquet_atomic_replaces_target_without_temp_files(tmp_path):
    target = tmp_path / "prices.parquet"
    pd.DataFrame([{"ticker": "000001", "close": 1000}]).to_parquet(target, index=False)

    expected = pd.DataFrame(
        [
            {"ticker": "005930", "close": 70_000},
            {"ticker": "000660", "close": 200_000},
        ]
    )
    write_parquet_atomic(expected, target)

    actual = pd.read_parquet(target)
    pd.testing.assert_frame_equal(actual, expected)
    assert list(tmp_path.glob(".prices.parquet.*.tmp")) == []


def test_write_parquet_atomic_preserves_old_target_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "prices.parquet"
    original = pd.DataFrame([{"ticker": "000001", "close": 1000}])
    original.to_parquet(target, index=False)

    def fail_replace(source, destination):
        raise PermissionError("simulated reader lock")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="simulated reader lock"):
        write_parquet_atomic(pd.DataFrame([{"ticker": "005930", "close": 70_000}]), target)

    actual = pd.read_parquet(target)
    pd.testing.assert_frame_equal(actual, original)
    assert list(tmp_path.glob(".prices.parquet.*.tmp")) == []


def test_write_csv_atomic_replaces_target_and_preserves_ticker_text(tmp_path):
    target = tmp_path / "krx_status.csv"
    expected = pd.DataFrame(
        [
            {"ticker": "005930", "as_of_date": "2026-08-28", "status": "ACTIVE"},
            {"ticker": "000660", "as_of_date": "2026-08-28", "status": "ACTIVE"},
        ]
    )

    write_csv_atomic(expected, target)

    actual = pd.read_csv(target, dtype={"ticker": str})
    pd.testing.assert_frame_equal(actual, expected)
    assert list(tmp_path.glob(".krx_status.csv.*.tmp")) == []


def test_write_json_atomic_replaces_object(tmp_path):
    target = tmp_path / "current_manifest.json"
    write_json_atomic(target, {"run_id": "a", "as_of_date": "2026-08-28"})
    write_json_atomic(target, {"run_id": "b", "as_of_date": "2026-08-31"})
    assert target.read_text(encoding="utf-8").count("run_id") == 1
    assert '"b"' in target.read_text(encoding="utf-8")
    assert list(tmp_path.glob(".current_manifest.json.*.tmp")) == []
