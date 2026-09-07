from copy import deepcopy
from dataclasses import asdict

import pytest

from kr_quant.research.pre_entry_replay import payload_hash, replay_prepared_ranking
from kr_quant.strategy.discovery_engine import pattern_from_month_stat

DECISION = "2025-09-02T09:00:00+09:00"
MARKET = "2025-09-01"


def inputs():
    rows = [{"ticker": "000001", "pattern_id": "a", "entry_stage": "TODAY_ENTRY",
             "seasonality_score": 55., "remaining_peak": {"available": True,
             "price_as_of": MARKET, "remaining_p50": 0.1}},
            {"ticker": "000002", "pattern_id": "b", "entry_stage": "PRE_ENTRY_15",
             "seasonality_score": 95., "remaining_peak": {"available": True,
             "price_as_of": MARKET, "remaining_p50": 0.3}}]
    data = {"candidates": rows,
            "eligibility": [{"ticker": r["ticker"], "eligible": True} for r in rows],
            "quotes": [{"ticker": r["ticker"], "last_close": 2000., "as_of": MARKET, "chg_pct": 0.01} for r in rows]}
    result = []
    for kind, values in data.items():
        payload = {"rows": values, "decision_at": DECISION, "market_date": MARKET, "model_id": "fixture-v1"}
        result.append({"payload": payload, "metadata": {"input": kind, "partition_id": kind,
                       "available_at": "2025-09-01T19:00:00+09:00", "effective_end": "2025-09-01T15:30:00+09:00",
                       "provenance_ref": "fixture-only", "sha256": payload_hash(payload)}})
    return result


def run(parts):
    return replay_prepared_ranking(parts, decision_at=DECISION, market_date=MARKET)


def test_rank_and_input_immutability():
    parts = inputs()
    original = deepcopy(parts)
    result = run(parts)
    assert result["status"] == "RANKED_UNVERIFIED" and result["verified"] is False
    assert [r["ticker"] for r in result["rows"]] == ["000001", "000002"]
    assert parts == original


def test_hash_and_future_availability_blocked():
    parts = inputs()
    parts[0]["payload"]["rows"][0]["seasonality_score"] = 999.
    assert run(parts)["status"] == "BLOCKED"
    parts = inputs()
    parts[0]["metadata"]["available_at"] = "2026-01-01T00:00:00Z"
    assert run(parts)["status"] == "BLOCKED"
    assert run(parts[:2])["status"] == "BLOCKED"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "date", "unknown", "peak", "context"])
def test_bad_snapshot_blocked_even_with_recomputed_hash(mutation):
    parts = inputs()
    if mutation == "duplicate":
        parts[1]["payload"]["rows"].append(parts[1]["payload"]["rows"][0])
    elif mutation == "missing":
        parts[1]["payload"]["rows"].pop()
    elif mutation == "date":
        parts[2]["payload"]["rows"][0]["as_of"] = "2025-09-02"
    elif mutation == "unknown":
        parts[1]["payload"]["rows"][0]["eligible"] = None
    elif mutation == "peak":
        parts[0]["payload"]["rows"][0]["remaining_peak"]["price_as_of"] = "2025-08-31"
    else:
        parts[0]["payload"]["decision_at"] = "2025-08-01T09:00:00+09:00"
    for p in parts:
        p["metadata"]["sha256"] = payload_hash(p["payload"])
    assert run(parts)["status"] == "BLOCKED"


def test_suspension_excluded_without_current_universe(monkeypatch):
    from kr_quant.strategy import seasonality
    def forbidden(*args, **kwargs):
        raise AssertionError("current source must never be read")
    monkeypatch.setattr(seasonality, "_clean_active_tickers", forbidden)
    monkeypatch.setattr(seasonality, "_latest_quotes", forbidden)
    parts = inputs()
    parts[1]["payload"]["rows"][0]["eligible"] = False
    parts[1]["metadata"]["sha256"] = payload_hash(parts[1]["payload"])
    result = run(parts)
    assert [r["ticker"] for r in result["rows"]] == ["000002"]
    assert result["excluded_count"] == 1


def pattern(records, as_of="2025-09-01", month=8):
    return pattern_from_month_stat("000001", "fixture", "KOSPI",
                                   {"month": month, "history_records": records}, as_of_date=as_of)


def test_future_returns_do_not_change_historical_pattern():
    past = [{"year": 2023, "return": .1}, {"year": 2024, "return": -.1}]
    base = asdict(pattern(past, "2025-08-31"))
    assert asdict(pattern(past + [{"year": 2025, "return": 99}, {"year": 2026, "return": -99}], "2025-08-31")) == base
    assert pattern(past + [{"year": 2025, "return": .2}]).sample_count == 3


def test_year_boundary_duplicate_missing_and_invalid_return():
    rows = [{"year": 2023, "return": .1}, {"year": 2024, "return": -.1}]
    assert pattern(rows, "2025-01-01", month=12).sample_count == 2
    for bad in [rows + [rows[0]], [{"year": 2023, "return": None}, rows[1]],
                [{"year": 2023, "return": float("inf")}, rows[1]]]:
        with pytest.raises(ValueError):
            pattern(bad)
    with pytest.raises(ValueError):
        pattern_from_month_stat("000001", "fixture", "KOSPI", {"month": 8, "history": [.1, .2]}, as_of_date="2025-09-01")


def test_decision_requires_previous_date_and_timezone():
    for decision in ["2025-09-01T09:00:00+09:00", "2025-09-02"]:
        with pytest.raises(ValueError):
            replay_prepared_ranking(inputs(), decision_at=decision, market_date=MARKET)


def test_live_adapter_uses_same_core(monkeypatch):
    from kr_quant.strategy import seasonality
    parts = inputs()
    quotes = {r["ticker"]: r for r in parts[2]["payload"]["rows"]}
    monkeypatch.setattr(seasonality, "_clean_active_tickers", lambda _: set(quotes))
    monkeypatch.setattr(seasonality, "_latest_quotes", lambda settings, tickers: quotes)
    assert seasonality.rank_pre_entry_candidates(None, parts[0]["payload"]["rows"]) == run(parts)["rows"]


@pytest.mark.parametrize("mode", ["low_price", "rally", "peak_unavailable"])
def test_ineligible_pre_entry_rules_are_preserved(mode):
    parts = inputs()
    if mode == "low_price":
        parts[2]["payload"]["rows"][0]["last_close"] = 999.
    elif mode == "rally":
        parts[0]["payload"]["rows"][0]["entry_stage"] = "RALLY_ACTIVE"
    else:
        parts[0]["payload"]["rows"][0]["remaining_peak"] = {"available": False}
    for part in parts:
        part["metadata"]["sha256"] = payload_hash(part["payload"])
    assert [r["ticker"] for r in run(parts)["rows"]] == ["000002"]
