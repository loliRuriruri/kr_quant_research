# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from kr_quant.run_generation import commit_generation, generation_dir
from kr_quant.settings import load_settings
from kr_quant.web.pipeline_health import (
    REQUIRED_FACTS,
    REQUIRED_PRICES,
    pipeline_health,
)
from kr_quant.web.season_snapshot import _folder as season_folder

KST = ZoneInfo("Asia/Seoul")


def _settings(tmp_path: Path):
    return replace(load_settings(), root=tmp_path)


def _live(settings) -> Path:
    path = settings.staged_dir / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _price_row(ticker: str, day: str) -> dict:
    return {
        "ticker": ticker,
        "trade_date": day,
        "market": "KOSPI",
        "close": 1000.0,
        "volume": 10,
        "market_cap": 1.0e12,
        "trading_value": 5.0e8,
    }


def _write_prices(live: Path, day: str, *, rows: int = 2, drop: str | None = None) -> None:
    frame = pd.DataFrame([_price_row(f"{i:06d}", day) for i in range(1, rows + 1)])
    if drop:
        frame = frame.drop(columns=[drop])
    frame.to_parquet(live / "prices.parquet", index=False)


def _write_master(live: Path, *, rows: int = 2) -> None:
    pd.DataFrame(
        [{"ticker": f"{i:06d}", "market": "KOSPI", "sect": "ST"} for i in range(1, rows + 1)]
    ).to_parquet(live / "master.parquet", index=False)


def _fact_row(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "security_id": ticker,
        "available_date": "2026-08-19",
        "canonical_account": "revenue",
        "fs_div": "CFS",
        "currency": "KRW",
        "bsns_year": 2026,
        "reprt_code": "11011",
        "normalized_value": 1.0,
        "period_end": "2026-06-30",
    }


def _write_facts(live: Path, *, rows: int = 2, drop: str | None = None, ticker_only: bool = False) -> None:
    if ticker_only:
        frame = pd.DataFrame([{"ticker": f"{i:06d}"} for i in range(1, rows + 1)])
    else:
        frame = pd.DataFrame([_fact_row(f"{i:06d}") for i in range(1, rows + 1)])
        if drop:
            frame = frame.drop(columns=[drop])
    frame.to_parquet(live / "financial_facts.parquet", index=False)


def _write_committed_quant(settings, *, as_of: str, run_id: str = "krq-test-gen") -> None:
    folder = generation_dir(settings, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": "000001", "score": 1.0, "as_of_date": as_of}]).to_parquet(
        folder / "latest_all_stocks.parquet", index=False
    )
    (folder / "data_quality_report.json").write_text(
        json.dumps({"as_of_date": as_of, "status": "success", "run_id": run_id}),
        encoding="utf-8",
    )
    for name in (
        "latest_top20.csv",
        "latest_top100.csv",
        "universe_evidence.json",
        "latest_universe_snapshot.parquet",
        "price_integrity_issues.parquet",
    ):
        path = folder / name
        if name.endswith(".csv"):
            path.write_text("ticker\n000001\n", encoding="utf-8")
        elif name.endswith(".json"):
            path.write_text(json.dumps({"as_of_date": as_of, "run_id": run_id}), encoding="utf-8")
        else:
            pd.DataFrame([{"ticker": "000001", "as_of_date": as_of}]).to_parquet(path, index=False)
    commit_generation(settings, run_id=run_id, as_of=as_of)


def _write_legacy_aliases_only(settings, *, as_of: str) -> None:
    out = settings.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": "000001", "score": 1.0}]).to_parquet(out / "latest_all_stocks.parquet", index=False)
    (out / "data_quality_report.json").write_text(
        json.dumps({"as_of_date": as_of, "status": "success"}), encoding="utf-8"
    )


def _write_backfill_coverage(live: Path, *, pct_hint_tickers: int = 99) -> None:
    outcomes = {f"{i:06d}": {"outcome": "usable_facts"} for i in range(1, pct_hint_tickers + 1)}
    (live / "dart_backfill_state.json").write_text(
        json.dumps({"ticker_outcomes": outcomes, "completed_cycles": 1}), encoding="utf-8"
    )


def _write_corrupt_parquet(path: Path) -> None:
    path.write_bytes(b"not-a-parquet-file")


def _write_season_canonical(settings) -> None:
    root = season_folder(settings)
    root.mkdir(parents=True, exist_ok=True)
    (root / "current.json").write_text(json.dumps({"state": "ready"}), encoding="utf-8")


def test_1_healthy_artifact_set_ready(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    day = "2026-08-20"
    _write_prices(live, day)
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of=day)
    _write_season_canonical(settings)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["krx"]["state"] == "HEALTHY"
    assert snap["components"]["dart_essential"]["state"] == "HEALTHY"
    assert snap["components"]["quant"]["state"] == "HEALTHY"
    assert snap["components"]["season"]["state"] == "HEALTHY"
    assert snap["pipeline_state"] == "READY"


def test_2_financial_facts_missing_repair_required(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_committed_quant(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "MISSING"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_3_financial_facts_corrupt_repair_required(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_corrupt_parquet(live / "financial_facts.parquet")
    _write_committed_quant(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "CORRUPT"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_4_ledger_dart_success_cannot_mask_missing_facts(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    ledger = {"steps": {"dart": {"status": "success"}, "quant": {"status": "success"}}}
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST), ledger=ledger)
    assert snap["components"]["dart_essential"]["state"] == "MISSING"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_5_coverage_99_cannot_mask_missing_facts(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live, rows=100)
    _write_backfill_coverage(live, pct_hint_tickers=99)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "MISSING"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_6_facts_valid_coverage_below_target_is_partial_not_missing(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live, rows=10)
    pd.DataFrame([_fact_row("000001")]).to_parquet(live / "financial_facts.parquet", index=False)
    _write_committed_quant(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "HEALTHY"
    assert snap["components"]["dart_coverage"]["state"] == "PARTIAL"


def test_7_prices_stale_needs_daily_update(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-18")
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of="2026-08-18")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["krx"]["state"] == "STALE"
    assert snap["pipeline_state"] == "NEEDS_DAILY_UPDATE"


def test_8_quant_output_missing_repair_required(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] == "MISSING"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_9_quant_as_of_older_than_prices_stale(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of="2026-08-18")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] == "STALE"
    assert snap["pipeline_state"] == "NEEDS_DAILY_UPDATE"


def test_10_health_scan_does_not_mutate_files_ledger_config(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of="2026-08-20")
    cfg = settings.root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    marker = cfg / "pipeline_health_probe.json"
    marker.write_text("{}", encoding="utf-8")
    ledger_path = settings.root / "data" / "cache" / "smart_run_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps({"steps": {"dart": {"status": "success"}}}), encoding="utf-8")
    before = {
        "prices": (live / "prices.parquet").stat().st_mtime_ns,
        "facts": (live / "financial_facts.parquet").stat().st_mtime_ns,
        "master": (live / "master.parquet").stat().st_mtime_ns,
        "marker": marker.read_text(encoding="utf-8"),
        "ledger": ledger_path.read_text(encoding="utf-8"),
    }
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST), ledger=json.loads(before["ledger"]))
    assert snap["authority"] == "artifact"
    assert (live / "prices.parquet").stat().st_mtime_ns == before["prices"]
    assert (live / "financial_facts.parquet").stat().st_mtime_ns == before["facts"]
    assert (live / "master.parquet").stat().st_mtime_ns == before["master"]
    assert marker.read_text(encoding="utf-8") == before["marker"]
    assert ledger_path.read_text(encoding="utf-8") == before["ledger"]


def test_quant_blocked_by_missing_dart_essential(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] == "BLOCKED"
    assert "dart_essential" in snap["components"]["quant"]["blocked_by"]


def test_aliases_without_manifest_are_not_healthy(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_legacy_aliases_only(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] in {"MISSING", "CORRUPT"}
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_manifest_with_missing_generation_file_is_not_healthy(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    run_id = "krq-broken-gen"
    folder = generation_dir(settings, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (settings.output_dir / "current_manifest.json").write_text(
        json.dumps({"run_id": run_id, "as_of_date": "2026-08-20", "generation_dir": str(folder)}),
        encoding="utf-8",
    )
    (folder / "data_quality_report.json").write_text(
        json.dumps({"as_of_date": "2026-08-20", "run_id": run_id}), encoding="utf-8"
    )
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] in {"MISSING", "CORRUPT"}
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_committed_manifest_artifacts_healthy_when_aligned(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    day = "2026-08-20"
    _write_prices(live, day)
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of=day)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] == "HEALTHY"
    assert snap["components"]["quant"]["run_id"]


def test_facts_ticker_only_is_corrupt(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live, ticker_only=True)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "CORRUPT"
    assert snap["components"]["dart_essential"]["reason"] == "schema_missing_columns"
    missing = set(snap["components"]["dart_essential"]["missing_columns"])
    assert "canonical_account" in missing
    assert missing <= set(REQUIRED_FACTS)


def test_facts_missing_required_consumer_column_is_corrupt(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live, drop="normalized_value")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "CORRUPT"
    assert "normalized_value" in snap["components"]["dart_essential"]["missing_columns"]


def test_prices_missing_required_quant_field_is_corrupt(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20", drop="market_cap")
    _write_master(live)
    _write_facts(live)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["krx"]["state"] == "CORRUPT"
    assert "market_cap" in snap["components"]["krx"]["missing_columns"]
    assert "market_cap" in REQUIRED_PRICES


def test_canonical_season_path_detected(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of="2026-08-20")
    _write_season_canonical(settings)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["season"]["state"] == "HEALTHY"
    assert "research_snapshots" in str(snap["components"]["season"]["path"]).replace("\\", "/")


def test_legacy_wrong_season_cache_alone_not_healthy(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_committed_quant(settings, as_of="2026-08-20")
    wrong = settings.root / "data" / "cache" / "season_snapshots"
    wrong.mkdir(parents=True)
    (wrong / "dummy.json").write_text("{}", encoding="utf-8")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["season"]["state"] == "MISSING"
