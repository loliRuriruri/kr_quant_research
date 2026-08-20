from kr_quant.ingest.ecos import parse_rows


def test_ecos_parse_empty_and_rows():
    empty = parse_rows({"RESULT": {"CODE": "INFO-200", "MESSAGE": "없음"}}, "StatisticSearch")
    assert empty == []
    rows = parse_rows(
        {"StatisticSearch": {"row": [{"DATA_VALUE": "3.50", "TIME": "20260818", "ITEM_NAME1": "기준금리", "UNIT_NAME": "%"}]}},
        "StatisticSearch",
    )
    assert rows[0]["TIME"] == "20260818"


def test_ecos_bad_key_raises():
    try:
        parse_rows({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키 오류"}}, "StatisticSearch")
    except RuntimeError as exc:
        assert "INFO-100" in str(exc)
    else:
        raise AssertionError("expected error")
