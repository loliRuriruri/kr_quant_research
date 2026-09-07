import json

import pandas as pd
import pytest

from kr_quant.research.feature_import import import_feature_cases, load_feature_archive
from kr_quant.research.pre_entry_replay import payload_hash


def records():
    values = {"financial_features": {"quant_score": 50., "return_3m": .1, "volume_ratio": 1.},
              "flow": {"foreign_net": 1., "institution_net": 2.},
              "event": {"common_event": "fixture", "secondary_event": "fixture",
                        "confidence": "LOW", "invalidating_rules": "fixture"}}
    return [{"ticker": "005930", "kind": k, "available_at": "2025-01-01T19:00:00+09:00",
             "effective_at": "2025-01-01T15:30:00+09:00", "valid_until": "2025-01-03T00:00:00+09:00",
             "source": "fixture", "data": v, "sha256": payload_hash(v)} for k, v in values.items()]


def test_archive_load_and_gap_denominator(tmp_path):
    path = tmp_path / "features.json"
    path.write_text(json.dumps(records()), encoding="utf-8")
    before = path.read_bytes()
    result = import_feature_cases(tmp_path, archive=path, tickers=["005930", "000001"],
        decisions=["2024-01-02T09:00:00+09:00", "2025-01-02T09:00:00+09:00"])
    assert result["case_count"] == 4
    assert result["selected_count"] == 1 and result["blocked_count"] == 3
    assert result["status"] == "PARTIAL" and not result["verified"]
    assert result["reason_counts"]["MISSING_EVENT"] == 3
    assert path.read_bytes() == before


def test_legacy_dates_not_promoted_to_availability(tmp_path):
    path = tmp_path / "legacy.parquet"
    pd.DataFrame({"ticker": ["005930"], "as_of_date": ["2025-01-01"], "quant_score": [50.]}).to_parquet(path)
    rows, info = load_feature_archive(path)
    assert rows == [] and info["status"] == "INCOMPATIBLE_SCHEMA"
    assert "available_at" in info["missing_columns"]
    result = import_feature_cases(tmp_path, archive=path, tickers=["005930"], decisions=["2025-01-02T09:00:00+09:00"])
    assert result["selected_count"] == 0


@pytest.mark.parametrize("text", ['invalid json', 'null', '{"rows":[null]}', '[{"ticker":"005930"}]'])
def test_bad_file_has_no_success(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    rows, info = load_feature_archive(path)
    assert rows == [] and info["status"] != "LOADED_UNVERIFIED"


def test_empty_and_missing_are_not_success(tmp_path):
    result = import_feature_cases(tmp_path, tickers=["005930"], decisions=["2025-01-02T09:00:00+09:00"])
    assert result["status"] == "BLOCKED"
    assert len(result["sources"]) == 3
    with pytest.raises(ValueError):
        import_feature_cases(tmp_path, tickers=[], decisions=[])


def test_changed_file_rows_cannot_escape_into_cases(tmp_path, monkeypatch):
    from kr_quant.research import feature_import
    path = tmp_path / "features.json"
    path.write_text(json.dumps(records()))
    hashes = iter(["a", "b"])
    monkeypatch.setattr(feature_import, "sha256_file", lambda p: next(hashes))
    result = import_feature_cases(tmp_path, archive=path, tickers=["005930"], decisions=["2025-01-02T09:00:00+09:00"])
    assert result["status"] == "BLOCKED" and result["selected_count"] == 0


def test_loaded_records_connect_to_existing_scorer(tmp_path):
    from kr_quant.research.historical_features import score_historical_pattern
    path = tmp_path / "features.json"
    path.write_text(json.dumps(records()))
    result = import_feature_cases(tmp_path, archive=path, tickers=["005930"], decisions=["2025-01-02T09:00:00+09:00"])
    selected = list(result["cases"][0]["selected"].values())
    scored = score_historical_pattern(records=selected, ticker="005930", company="fixture", market="KOSPI",
        month_stat={"month": 1, "history_records": [{"year": 2023, "return": .1}, {"year": 2024, "return": .2}]},
        decision_at="2025-01-02T09:00:00+09:00")
    assert scored["status"] == "SCORED_UNVERIFIED"
    assert scored["row"]["sample_count"] == 2


def test_invalid_ticker_structure_is_reported(tmp_path):
    path = tmp_path / "features.json"
    rows = records()
    rows[0]["ticker"] = ["005930"]
    path.write_text(json.dumps(rows))
    loaded, info = load_feature_archive(path)
    assert loaded == [] and info["status"] == "INCOMPATIBLE_SCHEMA"
