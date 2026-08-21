from __future__ import annotations

from datetime import date

from kr_quant.hashing import sha256_json
from kr_quant.orchestration.run import run_from_staged
from kr_quant.fixtures import generate_demo_dataset


def test_demo_pipeline_deterministic(settings, tmp_path):
    staged = tmp_path / "staged"
    generate_demo_dataset(staged, as_of=date(2024, 12, 30))
    from dataclasses import replace
    import shutil

    # isolate outputs in tmp_path
    if (settings.root / "config").exists():
        shutil.copytree(settings.root / "config", tmp_path / "config")
    settings_tmp = replace(settings, root=tmp_path)
    # run twice
    r1 = run_from_staged(settings_tmp, date(2024, 12, 30), staged, status_path=staged / "manual_status.csv")
    h1 = r1["context"].result_hash
    r2 = run_from_staged(settings_tmp, date(2024, 12, 30), staged, status_path=staged / "manual_status.csv")
    assert r2["context"].result_hash == h1
    assert r1["context"].status in {"success", "partial"}
    assert not r1["top20"].empty
    assert set(r1["top20"]["ticker"]) <= set(r1["top100"]["ticker"])
    # excluded models must not be ranked
    ranked = set(r1["top100"]["ticker"].astype(str))
    assert "B00001" not in ranked
    assert "R00001" not in ranked
    assert "P00001" not in ranked
    assert "N00001" not in ranked
    # output files
    out = settings_tmp.output_dir / "as_of_date=2024-12-30"
    assert (out / "top20.csv").exists()
    assert (settings_tmp.output_dir / "latest_top20.csv").exists()
    assert (settings_tmp.output_dir / "data_quality_report.json").exists()
    assert (settings_tmp.output_dir / "daily_history.parquet").exists()
    assert (settings_tmp.output_dir / "latest_all_stocks.parquet").exists()

    compact = sha256_json(
        [
            {"ticker": r["ticker"], "quant_score": r["quant_score"], "quant_rank": r["quant_rank"]}
            for r in sorted(r1["records"], key=lambda x: x["ticker"])
        ]
    )
    assert compact
    assert all(r["quant_score"] >= 0 for r in r1["records"])
