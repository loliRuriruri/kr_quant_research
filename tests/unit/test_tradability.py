from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from kr_quant.ingest.live import build_live_master
from kr_quant.universe.builder import classify_security
from kr_quant.universe.tradability import krx_risk_class_excluded, normalize_krx_risk_class


@pytest.mark.parametrize(
    "value",
    [
        "관리종목(소속부없음)",
        "투자주의환기종목(소속부없음)",
        "정리매매 종목",
        "상장폐지 절차 진행",
    ],
)
def test_krx_risk_class_is_hard_excluded(value: str):
    assert krx_risk_class_excluded(value)


def test_krx_risk_class_normalization_does_not_invent_status():
    assert normalize_krx_risk_class(None) == ""
    assert normalize_krx_risk_class("  관리 종목 ") == "관리종목"
    assert not krx_risk_class_excluded("중견기업부")


def test_classify_security_maps_krx_risk_to_existing_hard_reason():
    reasons = classify_security(
        {
            "company": "알파AI",
            "kind": "보통주",
            "secu_group": "주권",
            "sect": "관리종목(소속부없음)",
        },
        {"security_types": {}, "name_patterns": {}},
        {},
    )
    assert "TRADING_STATUS_EXCLUDED" in reasons


def test_build_live_master_preserves_krx_risk_class(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    pd.DataFrame(
        [
            {
                "security_id": "KR7043100004",
                "ticker": "043100",
                "company": "알파AI",
                "market": "KOSDAQ",
                "kind": "보통주",
                "secu_group": "주권",
                "sect": "관리종목(소속부없음)",
                "list_date": "20000704",
                "listed_shares": 1_000_000,
            }
        ]
    ).to_parquet(live / "krx_master.parquet", index=False)
    pd.DataFrame(
        [
            {
                "ticker": "043100",
                "trade_date": date(2026, 8, 25),
                "market_cap": 10_000_000_000,
                "listed_shares": 1_000_000,
                "close": 500,
                "company": "알파AI",
            }
        ]
    ).to_parquet(live / "prices.parquet", index=False)

    out = build_live_master(SimpleNamespace(staged_dir=tmp_path), date(2026, 8, 25))

    assert out.loc[0, "sect"] == "관리종목(소속부없음)"
    persisted = pd.read_parquet(live / "master.parquet")
    assert persisted.loc[0, "sect"] == "관리종목(소속부없음)"
