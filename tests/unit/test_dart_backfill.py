from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from kr_quant.ingest import live
from kr_quant.ingest.live import (
    DART_NO_FILING,
    DART_PERMANENT,
    DART_TRANSIENT,
    DART_USABLE_FACTS,
    backfill_dart_financials,
    classify_dart_ticker_outcome,
    dart_coverage_report,
    dart_report_schedule,
    needs_more_dart_backfill,
    plan_dart_backfill_targets,
    should_retry_dart_job,
)
from kr_quant.settings import load_settings


def test_dart_report_schedule_follows_filing_calendar():
    august = dart_report_schedule(date(2026, 8, 31))
    assert (2026, "11013") in august
    assert (2026, "11012") in august
    assert (2026, "11014") not in august
    assert (2026, "11011") not in august

    december = dart_report_schedule(date(2026, 12, 1))
    assert (2026, "11014") in december
    following_april = dart_report_schedule(date(2027, 4, 1))
    assert (2026, "11011") in following_april


def test_dart_job_retry_policy_keeps_success_and_retries_expired_no_data():
    now = datetime(2026, 8, 31, 6, tzinfo=timezone.utc)
    old = (now - timedelta(hours=25)).isoformat()
    recent = (now - timedelta(hours=2)).isoformat()

    assert should_retry_dart_job({"status": "000", "fetched_at": old}, now=now) is False
    assert should_retry_dart_job({"status": "013", "fetched_at": recent}, now=now) is False
    assert should_retry_dart_job({"status": "013", "fetched_at": old}, now=now) is True
    assert should_retry_dart_job({"status": "ERR", "fetched_at": recent}, now=now) is True


def test_backfill_plan_is_resumable_and_prioritizes_missing_facts():
    master = pd.DataFrame(
        [
            {"ticker": "000001", "corp_code": "00000001", "company": "A", "market_cap": 300, "kind": "보통주", "secu_group": "주권"},
            {"ticker": "000002", "corp_code": "00000002", "company": "B", "market_cap": 200, "kind": "보통주", "secu_group": "주권"},
            {"ticker": "000003", "corp_code": "00000003", "company": "C", "market_cap": 100, "kind": "보통주", "secu_group": "주권"},
        ]
    )
    facts = pd.DataFrame([{"ticker": "000001", "available_date": "2026-08-14"}])

    first, state = plan_dart_backfill_targets(master, facts, batch_size=1)
    assert first["ticker"].tolist() == ["000002"]
    assert state["next_cursor"] == 1

    resumed, next_state = plan_dart_backfill_targets(
        master,
        pd.concat([facts, pd.DataFrame([{"ticker": "000002", "available_date": "2026-08-31"}])]),
        batch_size=1,
        state={**state, "cursor": state["next_cursor"]},
    )
    assert resumed["ticker"].tolist() == ["000003"]
    assert next_state["next_cursor"] == 2


def test_permanent_opendart_status_is_not_retried():
    now = datetime(2026, 8, 31, 6, tzinfo=timezone.utc)
    old = (now - timedelta(hours=25)).isoformat()
    assert should_retry_dart_job({"status": "010", "fetched_at": old}, now=now) is False
    assert should_retry_dart_job({"status": "100", "fetched_at": old}, now=now) is False


def test_ticker_outcome_splits_no_filing_from_errors():
    assert classify_dart_ticker_outcome(has_facts=True, job_rows=[{"status": "013"}]) == DART_USABLE_FACTS
    assert classify_dart_ticker_outcome(has_facts=False, job_rows=[{"status": "013"}, {"status": "000"}]) == DART_NO_FILING
    assert classify_dart_ticker_outcome(has_facts=False, job_rows=[{"status": "ERR"}]) == DART_TRANSIENT
    assert classify_dart_ticker_outcome(has_facts=False, job_rows=[{"status": "010"}]) == DART_PERMANENT


def test_coverage_splits_attempted_response_and_usable():
    master = pd.DataFrame(
        [
            {"ticker": "000001", "corp_code": "00000001", "company": "A", "kind": "보통주", "secu_group": "주권"},
            {"ticker": "000002", "corp_code": "00000002", "company": "B", "kind": "보통주", "secu_group": "주권"},
            {"ticker": "000003", "corp_code": "00000003", "company": "C", "kind": "보통주", "secu_group": "주권"},
            {"ticker": "000004", "company": "ETF호", "kind": "보통주", "secu_group": "주권"},
        ]
    )
    facts = pd.DataFrame([{"ticker": "000001"}])
    outcomes = {
        "000001": {"outcome": DART_USABLE_FACTS},
        "000002": {"outcome": DART_NO_FILING},
        "000003": {"outcome": DART_TRANSIENT},
    }
    report = dart_coverage_report(master, facts, outcomes)
    assert report["universe_tickers"] == 3
    assert report["usable_tickers"] == 1
    assert report["usable_pct"] == 33.3
    assert report["coverage_pct"] == 33.3
    assert report["response_tickers"] == 2
    assert report["attempted_tickers"] == 3
    assert report["unsupported_tickers"] == 1
    assert report["usable_target_met"] is False


def test_needs_more_backfill_separates_cycle_from_usable_target():
    assert needs_more_dart_backfill({"usable_pct": 91.0}) is False
    assert needs_more_dart_backfill({"usable_pct": 20.0}, {"completed_cycles": 1, "has_retryable": False}) is False
    assert needs_more_dart_backfill({"usable_pct": 20.0}, {"completed_cycles": 1, "has_retryable": True}) is True
    assert needs_more_dart_backfill({"coverage_pct": 16.3}, {"completed_cycles": 0}) is True


def test_backfill_start_clears_completed_at(tmp_path, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    live_dir = settings.staged_dir / "live"
    live_dir.mkdir(parents=True)
    master = pd.DataFrame(
        [
            {
                "ticker": "000001",
                "corp_code": "00000001",
                "company": "A",
                "kind": "보통주",
                "secu_group": "주권",
                "market": "KOSPI",
                "market_cap": 100,
                "listed_shares": 1,
                "list_date": "2000-01-01",
                "sect": "",
                "security_id": "KR7000000001",
            }
        ]
    )
    prices = pd.DataFrame(
        [{"ticker": "000001", "trade_date": "2026-08-31", "market_cap": 100, "listed_shares": 1, "close": 1, "company": "A", "market": "KOSPI"}]
    )
    master.to_parquet(live_dir / "krx_master.parquet", index=False)
    prices.to_parquet(live_dir / "prices.parquet", index=False)
    pd.DataFrame([{"stock_code": "000001", "corp_code": "00000001"}]).to_parquet(live_dir / "corp_map.parquet", index=False)
    (live_dir / "dart_backfill_state.json").write_text(
        '{"status": "success", "completed_at": "2026-08-30T00:00:00+00:00", "error": "old", "cursor": 0}',
        encoding="utf-8",
    )
    captured: list[dict] = []
    original = live._write_json_atomic

    def capture(path, payload):
        captured.append(dict(payload))
        original(path, payload)

    monkeypatch.setattr(live, "_write_json_atomic", capture)
    monkeypatch.setattr(live, "fetch_dart_companies", lambda *args, **kwargs: None)
    monkeypatch.setattr(live, "fetch_dart_financials", lambda *args, **kwargs: pd.DataFrame())

    backfill_dart_financials(settings, date(2026, 8, 31), batch_size=1)

    running = next(item for item in captured if item.get("status") == "running")
    assert running["completed_at"] is None
    assert running["error"] is None
    assert running["status"] == "running"


def test_same_day_same_batch_is_not_fetched_again(tmp_path, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    live_dir = settings.staged_dir / "live"
    live_dir.mkdir(parents=True)
    batch = pd.DataFrame(
        [
            {
                "ticker": "000002",
                "corp_code": "00000002",
                "company": "B",
                "kind": "보통주",
                "secu_group": "주권",
            }
        ]
    )
    prices = pd.DataFrame(
        [{"ticker": "000002", "trade_date": "2026-08-31", "market_cap": 200, "listed_shares": 1, "close": 1, "company": "B", "market": "KOSPI"}]
    )
    batch.to_parquet(live_dir / "krx_master.parquet", index=False)
    prices.to_parquet(live_dir / "prices.parquet", index=False)
    pd.DataFrame([{"stock_code": "000002", "corp_code": "00000002"}]).to_parquet(live_dir / "corp_map.parquet", index=False)
    progress = {
        "cursor": 0,
        "next_cursor": 0,
        "batch_start": 0,
        "batch_end": 1,
        "batch_size": 1,
        "total_targets": 1,
        "ticker_order": ["000002"],
        "last_batch_tickers": ["000002"],
        "completed_cycle": True,
        "completed_cycles": 1,
    }
    (live_dir / "dart_backfill_state.json").write_text(
        '{"status": "success", "as_of": "2026-08-31", "cursor": 0, "batch_start": 0, '
        '"last_batch_tickers": ["000002"], "ticker_order": ["000002"], '
        '"ticker_outcomes": {"000002": {"outcome": "usable_facts", "updated_at": "2026-08-31T01:00:00+00:00", "attempts": 1}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(live, "build_live_master", lambda *args, **kwargs: batch.copy())
    monkeypatch.setattr(live, "plan_dart_backfill_targets", lambda *args, **kwargs: (batch.copy(), progress))
    monkeypatch.setattr(live, "fetch_dart_companies", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not refetch")))
    monkeypatch.setattr(live, "fetch_dart_financials", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not refetch")))

    result = backfill_dart_financials(settings, date(2026, 8, 31), batch_size=1)

    assert result["processed_this_run"] == 0
    assert "같은 날 같은 배치" in (result.get("note") or "")
