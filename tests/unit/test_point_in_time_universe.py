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


def test_listing_history_keeps_delisted_names_before_exit():
    from kr_quant.universe.point_in_time import update_listing_history, universe_as_of

    first = pd.DataFrame(
        [
            {"ticker": "000001", "list_date": "2020-01-02", "company": "A", "market": "KOSPI"},
            {"ticker": "000003", "list_date": "2010-01-02", "company": "Gone", "market": "KOSPI"},
        ]
    )
    history = update_listing_history(None, first, date(2024, 12, 30))
    later_master = pd.DataFrame(
        [{"ticker": "000001", "list_date": "2020-01-02", "company": "A", "market": "KOSPI"}]
    )
    history = update_listing_history(history, later_master, date(2025, 12, 30))

    past, evidence = universe_as_of(
        date(2025, 6, 1),
        master=later_master,
        history=history,
    )
    assert "000003" in set(past["ticker"])
    assert evidence["reconstruction_source"] == "LISTING_HISTORY"
    assert evidence["survivorship_bias_controlled"] is True

    future, _ = universe_as_of(date(2026, 1, 15), master=later_master, history=history)
    assert "000003" not in set(future["ticker"])


def test_later_listing_never_enters_past_universe():
    from kr_quant.universe.point_in_time import update_listing_history, universe_as_of

    master = pd.DataFrame(
        [
            {"ticker": "000001", "list_date": "2020-01-02", "market": "KOSPI"},
            {"ticker": "009999", "list_date": "2027-01-02", "market": "KOSPI"},
        ]
    )
    history = update_listing_history(None, master, date(2026, 8, 31))
    members, _ = universe_as_of(date(2026, 8, 31), master=master, history=history)
    assert "009999" not in set(members["ticker"])
    filtered, life = filter_master_as_of(master, date(2026, 8, 31))
    assert "009999" not in set(filtered["ticker"].astype(str).str.zfill(6))
    assert life["excluded_not_yet_listed"] == 1


def test_facts_as_of_drops_future_available_dates():
    from kr_quant.universe.point_in_time import facts_as_of

    facts = pd.DataFrame(
        [
            {"ticker": "000001", "available_date": "2026-08-01", "value": 1},
            {"ticker": "000002", "available_date": "2026-09-15", "value": 2},
        ]
    )
    usable = facts_as_of(facts, date(2026, 8, 31))
    assert set(usable["ticker"]) == {"000001"}


def test_validate_three_historical_dates_rejects_future_listings(tmp_path):
    from kr_quant.universe.point_in_time import validate_historical_universes

    master = pd.DataFrame(
        [
            {"ticker": "000001", "list_date": "2019-01-02"},
            {"ticker": "000002", "list_date": "2021-01-02"},
            {"ticker": "000003", "list_date": "2025-01-02"},
        ]
    )
    dates = [date(2020, 6, 1), date(2022, 6, 1), date(2024, 6, 1)]
    report = validate_historical_universes(dates, master=master, output_dir=tmp_path)
    assert report["ok"] is True
    assert report["dates"] == [item.isoformat() for item in dates]
    counts = {item["as_of_date"]: item["member_count"] for item in report["reports"]}
    assert counts["2020-06-01"] == 1
    assert counts["2022-06-01"] == 2
    assert counts["2024-06-01"] == 2


def test_pit_portfolio_requires_three_snapshots(tmp_path):
    from kr_quant.universe.point_in_time import pit_portfolio_study

    missing = pit_portfolio_study(tmp_path)
    assert missing["research_grade"] == "UNAVAILABLE"
    assert missing["survivorship_bias_controlled"] is False
    assert missing["used_in_quant"] is False

    for day in ("2026-01-02", "2026-02-02", "2026-03-02"):
        folder = tmp_path / f"as_of_date={day}"
        folder.mkdir()
        pd.DataFrame(
            [{"ticker": "000001", "top20_eligible": True}, {"ticker": "000002", "top20_eligible": True}]
        ).to_parquet(folder / "universe_snapshot.parquet", index=False)

    ready = pit_portfolio_study(tmp_path, cost_bps=10)
    assert ready["research_grade"] == "PIT_ARCHIVED_UNIVERSE"
    assert ready["survivorship_bias_controlled"] is True
    assert ready["distinct_from"] == "CURRENT_TOP20_RETROSPECTIVE"
    assert ready["used_in_quant"] is False


def test_archived_snapshot_beats_current_master(tmp_path):
    from kr_quant.universe.point_in_time import universe_as_of

    as_of = date(2026, 3, 2)
    folder = tmp_path / f"as_of_date={as_of.isoformat()}"
    folder.mkdir()
    pd.DataFrame([{"ticker": "000010"}, {"ticker": "000020"}]).to_parquet(
        folder / "universe_snapshot.parquet", index=False
    )
    master = pd.DataFrame([{"ticker": "000001", "list_date": "2000-01-01"}])
    members, evidence = universe_as_of(as_of, master=master, output_dir=tmp_path)
    assert set(members["ticker"]) == {"000010", "000020"}
    assert evidence["survivorship_bias_controlled"] is True
    assert evidence["reconstruction_source"] == "ARCHIVED_SNAPSHOT"
