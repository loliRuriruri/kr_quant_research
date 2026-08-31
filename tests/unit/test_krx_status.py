from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from kr_quant.ingest.live import build_krx_status_snapshot
from kr_quant.orchestration.run import _load_status


def _settings(tmp_path):
    return SimpleNamespace(
        staged_dir=tmp_path / "staged",
        status_csv=tmp_path / "raw" / "status" / "krx_status.csv",
        config={"universe": {"markets": ["KOSPI", "KOSDAQ"]}},
    )


def test_krx_status_snapshot_combines_master_risk_and_current_daily_trade(tmp_path):
    settings = _settings(tmp_path)
    as_of = date(2026, 8, 28)
    master = pd.DataFrame(
        [
            {"ticker": "005930", "company": "삼성전자", "market": "KOSPI", "sect": "우량기업부"},
            {"ticker": "111111", "company": "관리", "market": "KOSPI", "sect": "관리종목(소속부없음)"},
            {"ticker": "222222", "company": "환기", "market": "KOSDAQ", "sect": "투자주의환기종목"},
            {"ticker": "333333", "company": "정리", "market": "KOSDAQ", "sect": "정리매매 종목"},
            {"ticker": "444444", "company": "무거래", "market": "KOSDAQ", "sect": "중견기업부"},
            {"ticker": "555555", "company": "누락", "market": "KOSPI", "sect": "중견기업부"},
        ]
    )
    prices = pd.DataFrame(
        [
            {"ticker": "005930", "trade_date": as_of, "market": "KOSPI", "close": 70_000, "volume": 100},
            {"ticker": "111111", "trade_date": as_of, "market": "KOSPI", "close": 1_500, "volume": 100},
            {"ticker": "222222", "trade_date": as_of, "market": "KOSDAQ", "close": 2_000, "volume": 100},
            {"ticker": "333333", "trade_date": as_of, "market": "KOSDAQ", "close": 500, "volume": 100},
            {"ticker": "444444", "trade_date": as_of, "market": "KOSDAQ", "close": 3_000, "volume": 0},
        ]
    )

    snapshot = build_krx_status_snapshot(settings, as_of, master=master, prices=prices)
    statuses = snapshot.set_index("ticker")["status"].to_dict()

    assert statuses == {
        "005930": "ACTIVE",
        "111111": "ADMIN_ISSUE",
        "222222": "INVESTMENT_INELIGIBLE",
        "333333": "DELIST_PROCESS",
        "444444": "NO_CURRENT_TRADE",
        "555555": "UNVERIFIED",
    }
    persisted = pd.read_csv(settings.status_csv, dtype={"ticker": str})
    assert set(persisted["source"]) == {"KRX_OPEN_API_MASTER_AND_DAILY"}
    assert persisted.loc[persisted["ticker"] == "005930", "basis"].iloc[0] == "KRX_DAILY_TRADED"


def test_status_loader_requires_exact_day_and_preserves_leading_zero(tmp_path):
    path = tmp_path / "krx_status.csv"
    pd.DataFrame(
        [
            {"ticker": "005930", "as_of_date": "2026-08-27", "status": "ACTIVE"},
            {"ticker": "000660", "as_of_date": "2026-08-28", "status": "NO_CURRENT_TRADE"},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    current, current_ok = _load_status(path, date(2026, 8, 28))
    missing, missing_ok = _load_status(path, date(2026, 8, 29))

    assert current_ok is True
    assert current == {"000660": "NO_CURRENT_TRADE"}
    assert missing_ok is False
    assert missing == {}
