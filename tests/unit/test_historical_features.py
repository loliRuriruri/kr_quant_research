from copy import deepcopy

import pytest

from kr_quant.research.historical_features import select_as_of_features, score_historical_pattern
from kr_quant.research.pre_entry_replay import payload_hash

DECISION = "2025-09-01T09:00:00+09:00"


def records():
    data = {"financial_features": {"quant_score": 70., "return_3m": .1, "volume_ratio": 1.2},
            "flow": {"foreign_net": 100., "institution_net": 200.},
            "event": {"common_event": "fixture hypothesis", "secondary_event": "fixture only",
                      "confidence": "LOW", "invalidating_rules": "check filings"}}
    return [{"ticker": "009450", "kind": kind, "available_at": "2025-08-29T19:00:00+09:00",
             "effective_at": "2025-08-29T15:30:00+09:00", "valid_until": "2025-09-02T00:00:00+09:00",
             "source": "fixture", "data": values, "sha256": payload_hash(values)} for kind, values in data.items()]


def score(rows):
    return score_historical_pattern(records=rows, ticker="009450", company="fixture", market="KOSPI",
        month_stat={"month": 9, "history_records": [{"year": 2022, "return": .1},
                    {"year": 2023, "return": .2}, {"year": 2024, "return": -.05}]}, decision_at=DECISION)


def test_real_scorer_uses_supplied_event_not_current_knowledge(monkeypatch):
    from kr_quant.strategy import event_explainer
    class Forbidden(dict):
        def get(self, *args):
            raise AssertionError("current knowledge read")
    monkeypatch.setattr(event_explainer, "EVENT_KNOWLEDGE_BASE", Forbidden())
    rows = records()
    before = deepcopy(rows)
    result = score(rows)
    assert result["status"] == "SCORED_UNVERIFIED"
    assert result["verified"] is False
    assert result["row"]["event_confidence"] == "LOW"
    assert result["row"]["score_breakdown"]["event_explanation"] == 3
    assert result["row"]["event_explanation_mode"] == "HISTORICAL_INPUT_UNVERIFIED"
    assert rows == before


def test_future_correction_does_not_rewrite_past():
    rows = records()
    base = score(rows)
    correction = deepcopy(rows[0])
    correction["available_at"] = "2025-09-02T10:00:00+09:00"
    correction["data"]["quant_score"] = 0
    correction["sha256"] = "corrupt future payload ignored"
    assert score(rows + [correction]) == base


def test_visible_revision_selected():
    rows = records()
    correction = deepcopy(rows[0])
    correction["available_at"] = "2025-08-30T10:00:00+09:00"
    correction["data"]["quant_score"] = 20
    correction["sha256"] = payload_hash(correction["data"])
    result = select_as_of_features(rows + [correction], ticker="009450", decision_at=DECISION)
    assert result["selected"]["financial_features"]["data"]["quant_score"] == 20


@pytest.mark.parametrize("problem", ["missing", "duplicate", "expired", "hash", "naive", "null", "event"])
def test_invalid_or_missing_inputs_do_not_get_latest_defaults(problem):
    rows = records()
    if problem == "missing":
        rows.pop()
    elif problem == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif problem == "expired":
        rows[0]["valid_until"] = "2025-08-31T00:00:00+09:00"
    elif problem == "hash":
        rows[0]["sha256"] = "0" * 64
    elif problem == "naive":
        rows[0]["available_at"] = "2025-08-29"
    elif problem == "null":
        rows[0]["data"]["quant_score"] = None
        rows[0]["sha256"] = payload_hash(rows[0]["data"])
    else:
        rows[2]["data"] = {}
        rows[2]["sha256"] = payload_hash({})
    result = score(rows)
    assert result["status"] == "BLOCKED" and result["row"] is None


def test_no_expired_new_version_fallback():
    rows = records()
    newer = deepcopy(rows[0])
    newer.update(available_at="2025-08-30T00:00:00+09:00", valid_until="2025-08-31T00:00:00+09:00")
    assert score(rows + [newer])["status"] == "BLOCKED"
