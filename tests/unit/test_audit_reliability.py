"""Isolated regression evidence: no real portfolio writes or market HTTP."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pandas as pd
import pytest

from kr_quant.web.cache import invalidate_cache, ttl_cache


def test_refresh_updates_normal_cache_and_returns_independent_values():
    invalidate_cache()
    calls = []
    @ttl_cache()
    def source(refresh=False):
        calls.append(1)
        return {"rows": [len(calls)]}
    assert source()["rows"] == [1]
    assert source(refresh=True)["rows"] == [2]
    result = source(refresh=False)
    assert result["rows"] == [2]
    result["rows"].append(99)
    assert source()["rows"] == [2]


def test_cache_does_not_ignore_filter_objects():
    @ttl_cache()
    def source(filters):
        return filters["ticker"]
    assert source({"ticker": "005380"}) == "005380"
    assert source({"ticker": "005930"}) == "005930"


@pytest.fixture
def portfolio_api(tmp_path, monkeypatch):
    module = importlib.import_module("kr_quant.web.app")
    settings = SimpleNamespace(root=tmp_path, staged_dir=tmp_path / "staged")
    monkeypatch.setattr(module, "load_settings", lambda: settings)
    monkeypatch.setattr(module, "fetch_naver_live_quotes", lambda _: {})
    return module, settings


def test_empty_portfolio_is_not_replaced_by_examples(portfolio_api):
    module, _ = portfolio_api
    assert module.api_seasonality_momentum_portfolio_get()["items"] == []


def test_upsert_preserves_notes_and_rejects_bad_payload(portfolio_api):
    module, settings = portfolio_api
    module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380", "notes": "keep", "entry_price": 100}})
    module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380", "entry_price": 90}})
    path = settings.root / "data/calendar_momentum_portfolio.json"
    before = path.read_bytes()
    assert json.loads(before)[0]["notes"] == "keep"
    for body in ({}, {"item": {"code": ""}}, {"item": {"code": "005380", "entry_price": -1}}):
        with pytest.raises(Exception):
            module.api_seasonality_momentum_portfolio_post(body)
        assert path.read_bytes() == before


def test_corrupt_portfolio_is_not_silently_overwritten(portfolio_api):
    module, settings = portfolio_api
    path = settings.root / "data/calendar_momentum_portfolio.json"
    path.parent.mkdir()
    path.write_text("[broken", encoding="utf-8")
    with pytest.raises(Exception):
        module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380"}})
    assert path.read_text() == "[broken"


def test_parallel_upserts_preserve_all_items(portfolio_api):
    module, settings = portfolio_api
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: module.api_seasonality_momentum_portfolio_post({"item": {"code": f"{n:06d}"}}), range(1, 33)))
    rows = json.loads((settings.root / "data/calendar_momentum_portfolio.json").read_text())
    assert len(rows) == 32


def test_missing_quote_is_not_zero_profit(portfolio_api):
    module, settings = portfolio_api
    row = module.enrich_momentum_portfolio_with_live_prices(settings, [{"code": "005380", "entry_price": 100, "trajectory_match": 89}])[0]
    assert row["current_price"] is None
    assert row["current_return"] is None
    assert row["trajectory_match"] is None


def test_stale_live_quote_cannot_override_newer_close(portfolio_api, monkeypatch):
    module, settings = portfolio_api
    folder = settings.staged_dir / "live"
    folder.mkdir(parents=True)
    pd.DataFrame({"ticker": ["005380", "005380"], "trade_date": ["2026-08-27", "2026-08-28"], "close": [100, 120]}).to_parquet(folder / "prices.parquet")
    monkeypatch.setattr(module, "fetch_naver_live_quotes", lambda _: {"005380": {"price": 90, "trade_date": "2026-08-27"}})
    row = module.enrich_momentum_portfolio_with_live_prices(settings, [{"code": "005380", "entry_price": 100, "entry_date": "2026-08-27"}])[0]
    assert row["current_price"] == 120
    assert row["current_return"] == 20
    assert row["price_as_of"] == "2026-08-28"


def test_current_incomplete_month_excluded_from_seasonal_history():
    from kr_quant.strategy.seasonality import calculate_stock_seasonality
    frame = pd.DataFrame({"trade_date": pd.bdate_range("2025-07-01", "2025-08-08"), "close": 100.0})
    stats = calculate_stock_seasonality(frame)
    assert stats[6]["years_count"] == 1
    assert stats[7]["years_count"] == 0


def test_peer_fallback_uses_full_sector_not_only_unassigned_names():
    from kr_quant.models import MetricResult
    from kr_quant.scoring.peers import assign_peer_scores
    names = [SimpleNamespace(inputs=SimpleNamespace(industry_code=industry, sector_code="S"),
                             metrics={"m": MetricResult("m", value, "VALID", participates_in_percentile=True, counts_as_observed=True)},
                             metric_peer_context={})
             for industry, value in [("A", 1.), ("A", 2.), ("A", 3.), ("B", 4.)]]
    config = {"hierarchy": [{"level": "industry", "min_valid_n": 3}, {"level": "sector", "min_valid_n": 3}],
              "winsor": {"large_n": {"min_n": 40, "lower": 0, "upper": 1}, "medium_n": {"lower": 0, "upper": 1}}}
    assign_peer_scores(names, "m", "higher", config)
    assert names[-1].metrics["m"].peer_n == 4
    assert names[-1].metrics["m"].score == 100
    assert names[1].metrics["m"].peer_level == "industry"


def test_future_period_cannot_receive_full_freshness():
    from datetime import date
    from kr_quant.scoring.composite import freshness_component
    cfg = {"data_confidence": {"freshness_days": {"full": 180, "high": 270, "mid": 365}}}
    assert freshness_component(date(2026, 12, 31), date(2026, 9, 7), cfg) == 0


def test_concurrent_cache_miss_is_single_flight():
    import time
    calls = []
    @ttl_cache()
    def slow():
        calls.append(1)
        time.sleep(.04)
        return {"value": len(calls)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda _: slow(), range(8))) == [{"value": 1}] * 8
    assert len(calls) == 1


def test_cache_errors_retry_and_size_is_bounded():
    from kr_quant.web import cache
    invalidate_cache()
    @ttl_cache()
    def source(n):
        return {"ok": n >= 0}
    assert source(-1) == {"ok": False}
    assert not cache._CACHE_STORE
    for i in range(300):
        source(i)
    assert len(cache._CACHE_STORE) <= cache._MAX_ENTRIES


def test_failed_atomic_replace_preserves_portfolio(portfolio_api, monkeypatch):
    module, settings = portfolio_api
    module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380", "notes": "original"}})
    path = settings.root / "data/calendar_momentum_portfolio.json"
    before = path.read_bytes()
    def fail(*args):
        raise OSError("simulated disk failure")
    monkeypatch.setattr("kr_quant.atomic_io.os.replace", fail)
    with pytest.raises(OSError):
        module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380", "notes": "changed"}})
    assert path.read_bytes() == before


def test_step_direction_agreement_has_no_fifty_percent_floor(portfolio_api):
    module, settings = portfolio_api
    folder = settings.staged_dir / "live"
    folder.mkdir(parents=True)
    pd.DataFrame({"ticker": ["005380"] * 3, "trade_date": ["2026-08-26", "2026-08-27", "2026-08-28"], "close": [100, 95, 90]}).to_parquet(folder / "prices.parquet")
    result = module.enrich_momentum_portfolio_with_live_prices(settings, [{"code": "005380", "entry_date": "2026-08-26", "entry_price": 100,
                "history_curve": [0, 5, 10], "history_curve_source": "OBSERVED"}])[0]
    assert result["trajectory_match"] == 0
    assert result["trajectory_samples"] == 2


def test_empty_portfolio_stays_empty_after_last_delete(portfolio_api):
    module, _ = portfolio_api
    module.api_seasonality_momentum_portfolio_post({"item": {"code": "005380"}})
    module.api_seasonality_momentum_portfolio_post({"delete_code": "005380"})
    assert module.api_seasonality_momentum_portfolio_get()["items"] == []


def test_generation_change_bypasses_ttl():
    generation = [1]
    calls = []
    @ttl_cache(key_extra=lambda: generation[0])
    def source():
        calls.append(1)
        return len(calls)
    assert source() == source() == 1
    generation[0] = 2
    assert source() == 2


def test_peak_is_not_the_same_as_window_end_return():
    from tests.unit.test_remaining_peak import _seasonal_prices
    from kr_quant.strategy.remaining_peak import calculate_remaining_peak_upside
    data = _seasonal_prices(range(2021, 2026))
    data = pd.concat([data, pd.DataFrame([{"ticker": "005930", "trade_date": "2026-08-26", "close": 200, "adj_close": 200, "volume": 10}])], ignore_index=True)
    result = calculate_remaining_peak_upside(data, "005930", 9, as_of_date="2026-08-26")
    assert result["window_end_p50"] < result["remaining_p50"]
    assert result["validation_status"] == "IN_SAMPLE_DESCRIPTIVE_NOT_OOS"
    assert result["confidence"] != "HIGH"
