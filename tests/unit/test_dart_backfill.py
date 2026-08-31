from datetime import date, datetime, timedelta, timezone

import pandas as pd

from kr_quant.ingest.live import dart_report_schedule, plan_dart_backfill_targets, should_retry_dart_job


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
