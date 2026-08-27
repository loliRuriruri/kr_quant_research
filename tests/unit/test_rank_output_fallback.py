from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from kr_quant.web.app import _ranking_tier1_snapshot, _resolve_rank_output


def _write_all(path, *, eligible: bool, ranked: bool, as_of: str) -> None:
    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "company": "삼성전자",
                "as_of_date": as_of,
                "universe_eligible": eligible,
                "quant_rank": 1 if ranked else None,
                "quant_score": 80.0,
                "value_score": 20.0,
                "quality_score": 18.0,
                "growth_score": 16.0,
                "momentum_score": 14.0,
                "financial_score": 12.0,
                "data_confidence": 96.0,
                "weighted_metric_coverage": 1.0,
            }
        ]
    ).to_parquet(path, index=False)


def test_default_rank_resolver_skips_newest_failed_screen(tmp_path):
    failed = tmp_path / "as_of_date=2026-08-26"
    success = tmp_path / "as_of_date=2026-08-25"
    failed.mkdir()
    success.mkdir()
    _write_all(failed / "all_stocks.parquet", eligible=False, ranked=False, as_of="2026-08-26")
    _write_all(success / "all_stocks.parquet", eligible=True, ranked=True, as_of="2026-08-25")

    settings = SimpleNamespace(output_dir=tmp_path)
    resolved = _resolve_rank_output(settings, "all_stocks.parquet", "latest_all_stocks.parquet")
    snapshot = _ranking_tier1_snapshot(settings, limit=10)

    assert resolved == success / "all_stocks.parquet"
    assert snapshot["as_of"] == "2026-08-25"
    assert snapshot["universe_count"] == 1
    assert snapshot["top_rows"][0]["ticker"] == "005930"


def test_explicit_failed_date_does_not_silently_substitute_another_day(tmp_path):
    failed = tmp_path / "as_of_date=2026-08-26"
    success = tmp_path / "as_of_date=2026-08-25"
    failed.mkdir()
    success.mkdir()
    _write_all(failed / "all_stocks.parquet", eligible=False, ranked=False, as_of="2026-08-26")
    _write_all(success / "all_stocks.parquet", eligible=True, ranked=True, as_of="2026-08-25")

    settings = SimpleNamespace(output_dir=tmp_path)
    resolved = _resolve_rank_output(
        settings,
        "all_stocks.parquet",
        "latest_all_stocks.parquet",
        as_of="2026-08-26",
    )

    assert resolved == failed / "all_stocks.parquet"
