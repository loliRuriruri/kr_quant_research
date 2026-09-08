from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

import kr_quant.freshness as freshness
import kr_quant.ingest.live as live
import kr_quant.web.jobs as jobs
from kr_quant.exceptions import SourceNotReady


def _settings(tmp_path):
    csv = tmp_path / "krx_status.csv"
    return SimpleNamespace(
        krx_api_key="krx",
        status_csv=csv,
        staged_dir=tmp_path / "staged",
        config={"universe": {"markets": ["KOSPI", "KOSDAQ"]}},
    )


def _fresh(*, stored="2026-09-07", expected="2026-09-08", stale=True):
    return {
        "price_max_date": stored,
        "expected_price_date": expected,
        "stale_price": stale,
    }


def test_job_krx_prices_does_not_claim_success_when_expected_session_missing(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    fetched = []
    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(freshness, "wanted_price_date", lambda now=None: date(2026, 9, 8))
    monkeypatch.setattr(freshness, "freshness_snapshot", lambda *args, **kwargs: _fresh())
    monkeypatch.setattr(
        jobs,
        "probe_expected_krx",
        lambda *args, **kwargs: {
            "ready": False,
            "retryable": True,
            "failure_kind": "not_published",
            "missing_markets": ["KOSPI", "KOSDAQ"],
        },
    )
    monkeypatch.setattr(live, "fetch_krx_master", lambda *args, **kwargs: fetched.append("master") or pd.DataFrame())
    monkeypatch.setattr(live, "fetch_krx_prices_range", lambda *args, **kwargs: fetched.append("prices") or pd.DataFrame())

    result = jobs.job_krx_prices("auto")

    assert fetched == []
    assert result["pipeline_status"] == "partial"
    assert result["as_of"] == "2026-09-08"
    assert result["source_ready"] is False
    assert "2026-09-08" in result["next_action"]
    assert "2026-09-07" in result["next_action"]
    assert "완료" not in (result.get("note") or "")


def test_job_krx_prices_targets_expected_date_not_walkback(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    seen = {}

    def fake_master(s, as_of):
        seen["master_as_of"] = as_of
        return pd.DataFrame([{"ticker": "005930"}])

    def fake_prices(s, as_of, lookback_days=10, **kwargs):
        seen["price_as_of"] = as_of
        seen["require_as_of"] = kwargs.get("require_as_of")
        return pd.DataFrame([{"ticker": "005930", "trade_date": as_of}])

    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(freshness, "wanted_price_date", lambda now=None: date(2026, 9, 8))
    monkeypatch.setattr(
        freshness,
        "freshness_snapshot",
        lambda *args, **kwargs: _fresh(stored="2026-09-08", stale=False),
    )
    monkeypatch.setattr(jobs, "probe_expected_krx", lambda *args, **kwargs: {"ready": True, "missing_markets": []})
    monkeypatch.setattr(live, "fetch_krx_master", fake_master)
    monkeypatch.setattr(live, "fetch_krx_prices_range", fake_prices)

    result = jobs.job_krx_prices("auto")

    assert seen["master_as_of"] == date(2026, 9, 8)
    assert seen["price_as_of"] == date(2026, 9, 8)
    assert seen["require_as_of"] is True
    assert result["pipeline_status"] == "success"
    assert result["as_of"] == "2026-09-08"
    assert "next_action" not in result


def test_job_krx_prices_stays_partial_if_fetch_cannot_store_expected_day(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(freshness, "wanted_price_date", lambda now=None: date(2026, 9, 8))
    monkeypatch.setattr(freshness, "freshness_snapshot", lambda *args, **kwargs: _fresh())
    monkeypatch.setattr(jobs, "probe_expected_krx", lambda *args, **kwargs: {"ready": True, "missing_markets": []})
    monkeypatch.setattr(live, "fetch_krx_master", lambda *args, **kwargs: pd.DataFrame([{"ticker": "005930"}]))

    def boom(*args, **kwargs):
        raise SourceNotReady("KRX 2026-09-08 일봉이 아직 없습니다.")

    monkeypatch.setattr(live, "fetch_krx_prices_range", boom)

    result = jobs.job_krx_prices("auto")

    assert result["pipeline_status"] == "partial"
    assert "아직 없습니다" in result["next_action"]
    assert result["freshness"]["price_max_date"] == "2026-09-07"


def test_fetch_krx_prices_range_require_as_of_does_not_count_older_days(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    live_dir = settings.staged_dir / "live"
    live_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "005930", "trade_date": date(2026, 9, 7), "market": "KOSPI", "close": 1},
            {"ticker": "005930", "trade_date": date(2026, 9, 7), "market": "KOSDAQ", "close": 1},
        ]
    ).to_parquet(live_dir / "prices.parquet", index=False)
    settings.raw_dir = tmp_path / "raw"
    settings.krx_api_key = "k"
    settings.config = {
        "universe": {"markets": ["KOSPI", "KOSDAQ"]},
        "ingest": {"krx_base_url": "https://example.invalid"},
    }

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_daily_maybe(self, as_of, market):
            return []

    monkeypatch.setattr(live, "KrxOpenApiAdapter", FakeAdapter)
    monkeypatch.setattr(live, "live_dir", lambda s: live_dir)

    with pytest.raises(SourceNotReady, match="2026-09-08"):
        live.fetch_krx_prices_range(settings, date(2026, 9, 8), lookback_days=10, require_as_of=True)
