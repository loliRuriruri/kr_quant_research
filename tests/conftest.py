from __future__ import annotations

import os
from pathlib import Path

import pytest

from kr_quant.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _silent_notifications():
    os.environ["STOCK_SCREENER_SILENT"] = "1"


@pytest.fixture(scope="session")
def settings():
    return load_settings(ROOT)
