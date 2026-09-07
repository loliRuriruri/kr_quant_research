from copy import deepcopy

import pandas as pd
import pytest

from kr_quant.research.pit_readiness import profile_source, validate_replay_inputs


def record():
    return {"input": "prices", "partition_id": "2025-01-02", "sha256": "a" * 64,
            "available_at": "2025-01-02T18:30:00+09:00",
            "effective_end": "2025-01-02T15:30:00+09:00", "provenance_ref": "fixture"}


def validate(rows, decision="2025-01-03T09:00:00+09:00"):
    return validate_replay_inputs(rows, decision_at=decision, required_inputs=("prices",))


def test_valid_contract_does_not_certify_evidence():
    assert validate([record()]) == {"status": "CONTRACT_VALID", "verified": False, "issues": []}


@pytest.mark.parametrize("field,value,code", [
    ("available_at", "2025-01-04T00:00:00Z", "AVAILABLE_AT_FUTURE"),
    ("effective_end", "2025-01-04T00:00:00Z", "EFFECTIVE_END_FUTURE"),
    ("available_at", "2025-01-02", "AVAILABLE_AT_INVALID"),
    ("available_at", "NaT", "AVAILABLE_AT_INVALID"),
    ("available_at", None, "AVAILABLE_AT_INVALID"),
    ("sha256", "x", "HASH_INVALID"),
    ("provenance_ref", "", "PROVENANCE_MISSING"),
    ("partition_id", "", "IDENTITY_MISSING"),
])
def test_bad_input_is_blocked(field, value, code):
    item = record()
    item[field] = value
    result = validate([item])
    assert result["status"] == "BLOCKED"
    assert code in [issue["code"] for issue in result["issues"]]


def test_missing_duplicate_and_timezone_boundary():
    assert validate([])["issues"][0]["code"] == "INPUT_MISSING"
    assert validate([record(), deepcopy(record())])["status"] == "BLOCKED"
    assert validate([record()], "2025-01-02T09:30:00Z")["status"] == "CONTRACT_VALID"
    assert validate([record()], "2025-01-02T09:29:59Z")["status"] == "BLOCKED"
    with pytest.raises(ValueError):
        validate([record()], "2025-01-03")


def test_profile_is_read_only_and_counts_affected_duplicate_rows(tmp_path):
    path = tmp_path / "fixture.parquet"
    pd.DataFrame({"ticker": ["001", "001", "002"], "trade_date": ["2025-01-01", "2025-01-01", None]}).to_parquet(path)
    before = path.read_bytes()
    result = profile_source(tmp_path, path.name, ("ticker", "trade_date"))
    assert result["duplicate_key_rows"] == 2
    assert result["null_key_rows"] == 1
    assert result["date_ranges"]["trade_date"]["null_or_invalid"] == 1
    assert result["tickers"] == 2
    assert result["historical_availability"] == "UNVERIFIED"
    assert result["source_unchanged"] and path.read_bytes() == before
    assert profile_source(tmp_path, "absent.parquet", ("ticker",))["status"] == "MISSING"


def test_profile_financial_grain_and_fallback_indicator(tmp_path):
    pd.DataFrame({"ticker": ["001", "001"], "period_end": ["2025-03-31"] * 2,
                  "available_date": ["2025-03-31", "2025-05-15"],
                  "rcept_no": [None, "202505150001"], "revision_id": [1, 1]}).to_parquet(tmp_path / "facts.parquet")
    result = profile_source(tmp_path, "facts.parquet", ("ticker", "rcept_no"))
    assert result["available_equals_period_end"] == 1
    assert result["receipt_missing"] == 1


def test_empty_contract_is_not_valid():
    for required in [(), ("",), ("prices", "prices")]:
        with pytest.raises(ValueError):
            validate_replay_inputs([], decision_at="2025-01-03T00:00:00Z", required_inputs=required)


def test_source_changed_during_read_is_not_profiled(tmp_path, monkeypatch):
    from kr_quant.research import pit_readiness
    pd.DataFrame({"ticker": ["001"]}).to_parquet(tmp_path / "fixture.parquet")
    hashes = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(pit_readiness, "sha256_file", lambda path: next(hashes))
    result = profile_source(tmp_path, "fixture.parquet", ("ticker",))
    assert result["status"] == "SOURCE_CHANGED"
    assert result["source_unchanged"] is False
