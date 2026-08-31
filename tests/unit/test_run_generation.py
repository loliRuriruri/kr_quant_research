import json
from dataclasses import replace

import pandas as pd

from kr_quant.run_generation import (
    begin_generation,
    commit_generation,
    current_output_path,
    is_updating,
    load_manifest,
    publish_run_generation,
)
from kr_quant.settings import load_settings


def _frame(as_of: str, ticker: str, rank: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "as_of_date": as_of,
                "quant_rank": rank,
                "universe_eligible": True,
            }
        ]
    )


def test_readers_do_not_see_mixed_generation_before_commit(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    old = publish_run_generation(
        settings,
        run_id="run-old",
        as_of="2026-08-28",
        all_stocks=_frame("2026-08-28", "000001", 1),
        top100=_frame("2026-08-28", "000001", 1),
        top20=_frame("2026-08-28", "000001", 1),
        quality={"run_id": "run-old", "as_of_date": "2026-08-28", "status": "success"},
        universe_evidence={"as_of": "2026-08-28"},
        universe_snapshot=_frame("2026-08-28", "000001", 1),
        price_integrity_issues=pd.DataFrame([{"ticker": "000001", "issue": "none"}]),
    )
    assert old["as_of_date"] == "2026-08-28"

    begin_generation(settings, "run-new")
    mixed = _frame("2026-08-31", "000002", 1)
    mixed.to_parquet(settings.output_dir / "generations" / "run-new" / "latest_all_stocks.parquet", index=False)
    (settings.output_dir / "generations" / "run-new" / "data_quality_report.json").write_text(
        '{"run_id": "run-new", "as_of_date": "2026-08-31"}',
        encoding="utf-8",
    )

    assert is_updating(settings) is True
    assert load_manifest(settings)["run_id"] == "run-old"
    assert current_output_path(settings, "latest_all_stocks.parquet").parent.name == "run-old"
    stocks = pd.read_parquet(current_output_path(settings, "latest_all_stocks.parquet"))
    quality = current_output_path(settings, "data_quality_report.json").read_text(encoding="utf-8")
    assert stocks.iloc[0]["as_of_date"] == "2026-08-28" or str(stocks.iloc[0]["as_of_date"]).startswith("2026-08-28")
    assert "2026-08-28" in quality
    assert "run-old" in quality


def test_failed_generation_keeps_previous_manifest(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    publish_run_generation(
        settings,
        run_id="run-ok",
        as_of="2026-08-28",
        all_stocks=_frame("2026-08-28", "000001", 1),
        top100=_frame("2026-08-28", "000001", 1),
        top20=_frame("2026-08-28", "000001", 1),
        quality={"run_id": "run-ok", "as_of_date": "2026-08-28", "status": "success"},
        universe_evidence={"as_of": "2026-08-28"},
        universe_snapshot=_frame("2026-08-28", "000001", 1),
        price_integrity_issues=pd.DataFrame([{"ticker": "000001"}]),
    )
    begin_generation(settings, "run-fail")
    try:
        commit_generation(settings, run_id="run-fail", as_of="2026-08-31")
    except OSError:
        pass
    assert load_manifest(settings)["run_id"] == "run-ok"
    assert current_output_path(settings, "data_quality_report.json").parent.name == "run-ok"


def test_commit_exposes_one_as_of_for_quality_and_stocks(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    publish_run_generation(
        settings,
        run_id="run-new",
        as_of="2026-08-31",
        all_stocks=_frame("2026-08-31", "005930", 1),
        top100=_frame("2026-08-31", "005930", 1),
        top20=_frame("2026-08-31", "005930", 1),
        quality={"run_id": "run-new", "as_of_date": "2026-08-31", "status": "success"},
        universe_evidence={"as_of": "2026-08-31"},
        universe_snapshot=_frame("2026-08-31", "005930", 1),
        price_integrity_issues=pd.DataFrame([{"ticker": "005930"}]),
    )
    manifest = load_manifest(settings)
    stocks = pd.read_parquet(current_output_path(settings, "latest_all_stocks.parquet"))
    quality = json.loads(current_output_path(settings, "data_quality_report.json").read_text(encoding="utf-8"))
    assert manifest["as_of_date"] == "2026-08-31"
    assert str(stocks.iloc[0]["as_of_date"])[:10] == "2026-08-31"
    assert str(quality["as_of_date"])[:10] == "2026-08-31"
    assert is_updating(settings) is False
