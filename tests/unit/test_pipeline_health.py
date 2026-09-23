# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from kr_quant.settings import load_settings
from kr_quant.web.pipeline_health import pipeline_health

KST = ZoneInfo("Asia/Seoul")


def _settings(tmp_path: Path):
    return replace(load_settings(), root=tmp_path)


def _live(settings) -> Path:
    path = settings.staged_dir / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_prices(live: Path, day: str, *, rows: int = 2) -> None:
    frame = pd.DataFrame(
        [
            {
                "ticker": f"{i:06d}",
                "trade_date": day,
                "market": "KOSPI",
                "close": 1000 + i,
                "volume": 10,
            }
            for i in range(1, rows + 1)
        ]
    )
    frame.to_parquet(live / "prices.parquet", index=False)


def _write_master(live: Path, *, rows: int = 2) -> None:
    pd.DataFrame(
        [{"ticker": f"{i:06d}", "market": "KOSPI", "sect": "ST"} for i in range(1, rows + 1)]
    ).to_parquet(live / "master.parquet", index=False)


def _write_facts(live: Path, *, rows: int = 2) -> None:
    pd.DataFrame([{"ticker": f"{i:06d}", "available_date": "2026-08-19"} for i in range(1, rows + 1)]).to_parquet(
        live / "financial_facts.parquet", index=False
    )


def _write_quant(settings, *, as_of: str) -> None:
    out = settings.output_dir
    out.mkdir(parents=True, exist_ok=True)
    stocks = out / "latest_all_stocks.parquet"
    pd.DataFrame([{"ticker": "000001", "score": 1.0}]).to_parquet(stocks, index=False)
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


def test_1_healthy_artifact_set_ready(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    day = "2026-08-20"
    _write_prices(live, day)
    _write_master(live)
    _write_facts(live)
    _write_quant(settings, as_of=day)
    # season cache optional healthy
    season = settings.root / "data" / "cache" / "season_snapshots"
    season.mkdir(parents=True)
    (season / "dummy.json").write_text("{}", encoding="utf-8")

    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["krx"]["state"] == "HEALTHY"
    assert snap["components"]["dart_essential"]["state"] == "HEALTHY"
    assert snap["components"]["quant"]["state"] == "HEALTHY"
    assert snap["pipeline_state"] == "READY"
    assert snap["repair_required"] is False


def test_2_financial_facts_missing_repair_required(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_quant(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "MISSING"
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"
    assert snap["repair_required"] is True


def test_3_financial_facts_corrupt_repair_required(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_corrupt_parquet(live / "financial_facts.parquet")
    _write_quant(settings, as_of="2026-08-20")
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
    assert snap["ledger"]["dart_status"] == "success"


def test_5_coverage_99_cannot_mask_missing_facts(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live, rows=100)
    _write_backfill_coverage(live, pct_hint_tickers=99)
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "MISSING"
    # coverage may look high from outcomes alone
    cov = snap["components"]["dart_coverage"]
    assert cov["state"] in {"HEALTHY", "PARTIAL", "MISSING"}
    assert snap["pipeline_state"] == "REPAIR_REQUIRED"


def test_6_facts_valid_coverage_below_target_is_partial_not_missing(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live, rows=10)
    # only 1 fact ticker -> coverage below 90
    pd.DataFrame([{"ticker": "000001", "available_date": "2026-08-19"}]).to_parquet(
        live / "financial_facts.parquet", index=False
    )
    _write_quant(settings, as_of="2026-08-20")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["dart_essential"]["state"] == "HEALTHY"
    assert snap["components"]["dart_coverage"]["state"] == "PARTIAL"
    assert snap["components"]["dart_essential"]["state"] != "MISSING"


def test_7_prices_stale_needs_daily_update(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-18")
    _write_master(live)
    _write_facts(live)
    _write_quant(settings, as_of="2026-08-18")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["krx"]["state"] == "STALE"
    assert snap["pipeline_state"] == "NEEDS_DAILY_UPDATE"
    assert snap["pipeline_state"] != "WAITING_SOURCE"


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
    _write_quant(settings, as_of="2026-08-18")
    snap = pipeline_health(settings, now=datetime(2026, 8, 20, 18, 30, tzinfo=KST))
    assert snap["components"]["quant"]["state"] == "STALE"
    assert snap["pipeline_state"] == "NEEDS_DAILY_UPDATE"


def test_10_health_scan_does_not_mutate_files_ledger_config(tmp_path):
    settings = _settings(tmp_path)
    live = _live(settings)
    _write_prices(live, "2026-08-20")
    _write_master(live)
    _write_facts(live)
    _write_quant(settings, as_of="2026-08-20")
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
    snap = pipeline_health(
        settings,
        now=datetime(2026, 8, 20, 18, 30, tzinfo=KST),
        ledger=json.loads(before["ledger"]),
    )
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
