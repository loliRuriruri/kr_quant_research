from datetime import date, datetime, timezone

import pandas as pd

from kr_quant.universe.point_in_time import (
    build_universe_snapshot,
    filter_master_as_of,
    strategy_universe_evidence,
)


def test_filter_master_as_of_excludes_future_listings_and_known_delistings():
    master = pd.DataFrame(
        [
            {"ticker": "000001", "list_date": "2020-01-02", "delist_date": None},
            {"ticker": "000002", "list_date": "2027-01-02", "delist_date": None},
            {"ticker": "000003", "list_date": "2010-01-02", "delist_date": "2025-12-30"},
            {"ticker": "000004", "list_date": None, "delist_date": None},
        ]
    )

    filtered, evidence = filter_master_as_of(master, date(2026, 8, 31))

    assert set(filtered["ticker"]) == {"000001", "000004"}
    assert evidence["excluded_not_yet_listed"] == 1
    assert evidence["excluded_already_delisted"] == 1
    assert evidence["state"] == "PARTIAL_LISTING_LIFE"


def test_universe_snapshot_marks_contemporaneous_capture():
    master = pd.DataFrame(
        [
            {"ticker": "1", "company": "하나", "list_date": "2020-01-02"},
            {"ticker": "2", "company": "둘", "list_date": "2021-01-02"},
        ]
    )
    prices = pd.DataFrame([{"ticker": "000001", "trade_date": "2026-08-31", "close": 1000}])

    snapshot, evidence = build_universe_snapshot(
        master,
        prices,
        as_of=date(2026, 8, 31),
        source_mode="live",
        captured_at=datetime(2026, 8, 31, 10, tzinfo=timezone.utc),
    )

    observed = snapshot.set_index("ticker")["observed_price_on_as_of"].to_dict()
    assert observed == {"000001": True, "000002": False}
    assert evidence["capture_state"] == "CONTEMPORANEOUS"
    assert evidence["survivorship_bias_controlled"] is True


def test_strategy_discloses_current_cohort_survivorship_limit(tmp_path):
    dated = tmp_path / "as_of_date=2026-08-29"
    dated.mkdir()
    pd.DataFrame([{"ticker": "000001"}]).to_parquet(dated / "universe_snapshot.parquet", index=False)

    evidence = strategy_universe_evidence(
        tmp_path,
        rows=[{"from": "2023-01-02", "to": "2026-08-28"}],
        selection_as_of="2026-08-28",
    )

    assert evidence["selection_mode"] == "CURRENT_TOP20_RETROSPECTIVE"
    assert evidence["survivorship_bias_controlled"] is False
    assert evidence["research_grade"] == "LIMITED_CURRENT_COHORT"
    assert evidence["archived_snapshot_count"] == 1
    assert "상장폐지" in evidence["limitation"]
