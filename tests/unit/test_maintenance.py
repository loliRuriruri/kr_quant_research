# -*- coding: utf-8 -*-
"""P3 Maintenance tests: log sanitization and atomic IO."""
import json
import logging
from pathlib import Path
import pytest

from kr_quant.logging_config import SensitiveDataFilter, setup_logging
from kr_quant.atomic_io import write_json_atomic


def test_sensitive_data_filter():
    redactor = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Calling KRX with api_key=KRX_SECRET_12345 and Bearer eyJhbGciOiJIUzI1NiJ9",
        args=(),
        exc_info=None,
    )
    assert redactor.filter(record) is True
    assert "KRX_SECRET_12345" not in record.msg
    assert "api_key=***REDACTED***" in record.msg
    assert "Bearer ***REDACTED***" in record.msg


def test_write_json_atomic_dict_and_list(tmp_path):
    # Test dict payload
    dict_file = tmp_path / "data.json"
    write_json_atomic(dict_file, {"key": "value", "count": 10})
    assert json.loads(dict_file.read_text(encoding="utf-8")) == {"key": "value", "count": 10}

    # Test list payload
    list_file = tmp_path / "items.json"
    write_json_atomic(list_file, [{"id": 1}, {"id": 2}])
    assert json.loads(list_file.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]
