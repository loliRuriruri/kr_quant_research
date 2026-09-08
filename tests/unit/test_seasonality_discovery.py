# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time

import pandas as pd
from fastapi.testclient import TestClient

from kr_quant.web.app import app
from kr_quant.strategy.discovery_engine import pattern_from_month_stat, SeasonalityPattern
from kr_quant.strategy.event_explainer import explain_and_score_pattern
from kr_quant.strategy.seasonality import scan_seasonality_discovery
from kr_quant.settings import load_settings

client = TestClient(app)


def test_pattern_from_month_stat_with_playbook():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat, lookback_years=5)
    assert pat is not None
    assert pat.sample_count == 5
    assert pat.win_rate == 0.80
    assert hasattr(pat, "entry_stage")
    assert hasattr(pat, "entry_stage_label")
    assert hasattr(pat, "expected_p50")
    assert hasattr(pat, "expected_p90")
    assert hasattr(pat, "profit_factor")
    assert hasattr(pat, "playbook")
    assert "entry_timing" in pat.playbook
    assert "exit_timing" in pat.playbook
    assert "stop_loss" in pat.playbook
    assert pat.median_alpha is None
    assert pat.avg_mdd is None
    assert pat.recent_3y_median_alpha is None
    assert pat.entry_stage == "WATCH"
    assert pat.entry_window_str == ""
    assert pat.exit_window_str == ""
    assert all(row["market_alpha"] is None and row["mdd"] is None for row in pat.years_track)


def test_explain_and_score_pattern():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.086,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("009450", "경동나비엔", "KOSPI", m_stat, lookback_years=5)
    res = explain_and_score_pattern(pat, {"quant_score": 75.0, "return_3m": 0.05})
    assert "seasonality_score" in res
    assert 0.0 <= res["seasonality_score"] <= 100.0
    assert res["grade"] in ["S", "A", "B", "C", "D"]
    assert res["current_status"] in ["ACTIVE", "WATCH", "DISCOVERY", "WEAKENING", "BROKEN", "UNKNOWN"]
    assert "score_breakdown" in res
    assert "entry_stage" in res
    assert "entry_stage_label" in res
    assert "expected_p50" in res
    assert "expected_p90" in res
    assert "profit_factor" in res
    assert "playbook" in res
    assert "퀀트 점수 75.0" in res["current_confirmation_evidence"]
    assert any("3개월 수익률" in item for item in res["current_confirmation_evidence"])
    assert "외국인·기관 수급" in res["current_confirmation_missing"]
    assert "거래량 비율" in res["current_confirmation_missing"]


def test_current_confirmation_does_not_award_missing_defaults():
    m_stat = {
        "month": 8,
        "history": [0.12, 0.08, 0.18, -0.02, 0.07],
    }
    pat = pattern_from_month_stat("123456", "근거없음", "KOSPI", m_stat, lookback_years=5)

    res = explain_and_score_pattern(pat, {})

    assert res["score_breakdown"]["current_confirmation"] == 0.0
    assert res["current_status"] == "UNKNOWN"
    assert res["current_confirmation_evidence"] == []
    assert set(res["current_confirmation_missing"]) == {
        "3개월 모멘텀",
        "최신 퀀트 점수",
        "외국인·기관 수급",
        "거래량 비율",
    }


def test_remaining_peak_cache_fill_is_shared_between_concurrent_requests(tmp_path, monkeypatch):
    from kr_quant.strategy import seasonality

    price_path = tmp_path / "staged" / "live" / "prices.parquet"
    price_path.parent.mkdir(parents=True)
    price_path.write_bytes(b"cache-signature")
    settings = SimpleNamespace(root=tmp_path, staged_dir=tmp_path / "staged", output_dir=tmp_path / "output", status_csv=tmp_path / "status.csv")
    prices = pd.DataFrame(
        {
            "ticker": ["000001"],
            "trade_date": ["2026-08-28"],
            "close": [1000.0],
        }
    )
    calls = 0

    def fake_calculate(*args, **kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return {"available": False, "status": "LOW_SAMPLE"}

    monkeypatch.setattr(seasonality, "_prices", lambda _settings: prices)
    monkeypatch.setattr(seasonality, "calculate_remaining_peak_upside", fake_calculate)
    with seasonality._REMAINING_PEAK_LOCK:
        seasonality._REMAINING_PEAK_CACHE["signature"] = None
        seasonality._REMAINING_PEAK_CACHE["values"] = {}

    rows = [
        {
            "ticker": "000001",
            "window_name": "8월",
            "entry_stage": "WATCH",
            "entry_stage_label": "실측 피크 산출 대기",
            "entry_window_str": "",
            "exit_window_str": "",
        }
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: seasonality._enrich_remaining_peak_rows(settings, rows, lookback_years=5),
                range(2),
            )
        )

    assert calls == 1
    assert all(result[0]["remaining_peak"]["status"] == "LOW_SAMPLE" for result in results)


def test_unmapped_ticker_gets_industry_specific_catalyst_evidence():
    m_stat = {
        "month": 9,
        "history": [0.12, 0.08, -0.03, 0.15, 0.07],
        "win_rate": 0.80,
        "avg_return": 0.078,
        "median_return": 0.08,
        "years_count": 5,
    }
    pat = pattern_from_month_stat("123456", "테스트전기장비", "KOSPI", m_stat, lookback_years=5)
    assert pat is not None

    res = explain_and_score_pattern(
        pat,
        {
            "company": "테스트전기장비",
            "sector": "제조업",
            "industry": "전기장비",
            "quant_score": 72.0,
            "return_3m": 0.04,
        },
    )

    assert res["event_explanation_mode"] == "RULE_BASED"
    assert "계절성" in res["common_event_cluster"]
    assert "5개년" in res["common_event_cluster"]
    assert "전력망" in (res.get("event_hypothesis") or "")
    assert "전력망" in (res.get("interpretation") or "")
    assert "중앙값" in res["secondary_cluster"]
    assert "수주잔고" in res["secondary_cluster"]
    assert res["used_in_quant"] is False
    assert "계절적 수요 증가 및 분기 실적 모멘텀" not in res["common_event_cluster"]


def test_insufficient_sample_does_not_invent_catalyst():
    m_stat = {
        "month": 9,
        "history": [0.12, -0.04],
        "win_rate": 0.50,
        "avg_return": 0.04,
        "median_return": 0.04,
        "years_count": 2,
    }
    pat = pattern_from_month_stat("888888", "표본부족", "KOSPI", m_stat, lookback_years=2)
    res = explain_and_score_pattern(pat, {"company": "표본부족", "industry": "전기장비"})
    assert res["event_explanation_mode"] == "INSUFFICIENT_EVIDENCE"
    assert res["common_event_cluster"] == "근거 부족"
    assert res["event_hypothesis"] is None
    assert "목표가" not in res["common_event_cluster"]
    assert res["used_in_quant"] is False


def test_ten_tickers_sharing_month_hypothesis_are_flagged():
    from kr_quant.strategy.event_explainer import repeated_generic_catalysts

    rows = []
    for index in range(10):
        ticker = f"{index + 1:06d}"
        m_stat = {
            "month": 8,
            "history": [0.12, 0.08, -0.03, 0.15, 0.07],
            "win_rate": 0.80,
            "median_return": 0.08,
            "years_count": 5,
        }
        pat = pattern_from_month_stat(ticker, f"가상종목{index}", "KOSPI", m_stat, lookback_years=5)
        rows.append(explain_and_score_pattern(pat, {"company": f"가상종목{index}"}))
    quality = repeated_generic_catalysts(rows, min_tickers=10)
    assert quality["ok"] is False
    assert quality["flag"] == "GENERIC_CATALYST_REPEAT"
    assert quality["repeats"][0]["ticker_count"] >= 10
    headlines = {row["common_event_cluster"] for row in rows}
    assert len(headlines) == 10


def test_api_seasonality_discovery_playbook():
    from kr_quant.web.season_snapshot import build_bundle
    build_bundle(load_settings())
    res = client.get("/api/seasonality/discovery?horizon_days=90&lookback_years=5")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["data_context"]["price_as_of"]
    assert data["data_context"]["source"] == "KRX 일봉 기반 월간 계절성"
    assert len(data["rows"]) > 0
    row = data["rows"][0]
    assert "entry_stage" in row
    assert "entry_stage_label" in row
    assert "expected_p50" in row
    assert "expected_p90" in row
    assert "profit_factor" in row
    assert "playbook" in row
    assert "remaining_peak" in row
    remaining = row["remaining_peak"]
    assert "available" in remaining
    assert "status" in remaining
    if remaining["available"]:
        assert remaining["remaining_p50"] is not None
        assert remaining["peak_price_p50"] is not None
        assert remaining["sample_count"] >= 3
    else:
        assert row["entry_stage"] == "WATCH"
        assert row["entry_window_str"] == ""
        assert row["exit_window_str"] == ""
