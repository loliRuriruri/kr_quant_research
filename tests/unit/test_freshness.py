import json
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from kr_quant.freshness import expected_price_date, freshness_snapshot, runtime_spec, trading_session_lag
from kr_quant.ingest.live import calendar_guard
from kr_quant.settings import load_settings
import kr_quant.web.scheduler as scheduler
from kr_quant.web.scheduler import _STATE, _catch_up_due, _next_slot, load_scheduler_config

KST = ZoneInfo("Asia/Seoul")


def test_expected_price_date_before_and_after_close():
    before = datetime(2026, 8, 20, 10, 0, tzinfo=KST)
    after = datetime(2026, 8, 20, 18, 30, tzinfo=KST)
    assert expected_price_date(before).isoformat() == "2026-08-19"
    assert expected_price_date(after).isoformat() == "2026-08-20"


def test_expected_price_date_weekend_and_holiday():
    saturday = datetime(2026, 8, 22, 19, 0, tzinfo=KST)
    holiday = datetime(2026, 8, 17, 19, 0, tzinfo=KST)
    assert expected_price_date(saturday).isoformat() == "2026-08-21"
    assert expected_price_date(holiday).isoformat() == "2026-08-14"


def test_trading_session_lag_ignores_weekend():
    assert trading_session_lag(date(2026, 8, 21), date(2026, 8, 24)) == 1
    assert trading_session_lag(date(2026, 8, 24), date(2026, 8, 24)) == 0


def test_freshness_snapshot_reports_source_coverage_and_stale_strategy(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    live = settings.staged_dir / "live"
    live.mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "000001", "trade_date": "2026-08-20"},
            {"ticker": "000002", "trade_date": "2026-08-20"},
        ]
    ).to_parquet(live / "prices.parquet", index=False)
    pd.DataFrame([{"ticker": "000001"}, {"ticker": "000002"}]).to_parquet(live / "master.parquet", index=False)
    pd.DataFrame(
        [{"ticker": "000001", "available_date": "2026-08-19", "period_end": "2026-06-30"}]
    ).to_parquet(live / "financial_facts.parquet", index=False)
    cache = settings.root / "data" / "cache" / "strategy_lab.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"source_price_as_of": "2026-08-19", "rows": []}), encoding="utf-8")

    snap = freshness_snapshot(
        settings,
        now=datetime(2026, 8, 20, 18, 30, tzinfo=KST),
        screen_as_of="2026-08-20",
    )

    assert snap["lag_trading_days"] == 0
    assert snap["sources"]["financial_facts"]["coverage"]["coverage_pct"] == 50.0
    assert snap["sources"]["strategy_cache"]["state"] == "stale"
    assert snap["derived_stale"] == ["strategy_cache"]
    assert snap["contract_status"] == "partial"


def test_runtime_spec_does_not_enable_orders_or_overlay_scores():
    spec = runtime_spec(load_settings())
    assert spec["orders"] is False
    assert spec["overlays"]["flow"] is False
    assert spec["overlays"]["strategy"] is False
    assert spec["overlays"]["portfolio"] is False
    assert spec["overlays"]["sector"] is False
    assert spec["overlays"]["screens"] is False
    assert spec["overlays"]["llm_research"] is False
    assert spec["momentum_enabled"] is True
    assert spec["quant_weights"]["value"] == 30


def test_old_prices_do_not_make_matching_old_ranking_fresh(tmp_path):
    settings = replace(load_settings(), root=tmp_path)
    live = settings.staged_dir / 'live'
    live.mkdir(parents=True)
    pd.DataFrame([{'ticker': '000001', 'trade_date': '2026-09-04'}]).to_parquet(live / 'prices.parquet')
    snap = freshness_snapshot(settings, now=datetime(2026, 9, 8, 8, tzinfo=KST), screen_as_of='2026-09-04')
    assert snap['sources']['quant_ranking']['state'] == 'stale'
    assert snap['sources']['quant_ranking']['aligned_with_stored_prices'] is True
    assert snap['sources']['financial_facts']['freshness_verified'] is False
    assert snap['sources']['official_flow']['state'] == 'missing'
    assert not settings.db_path.exists()


def test_latest_flow_date_does_not_hide_stale_tickers(tmp_path):
    from kr_quant.flow.store import open_settings, upsert_flows
    from kr_quant.freshness import _official_flow_freshness
    settings = replace(load_settings(), root=tmp_path)
    con = open_settings(settings)
    upsert_flows(con, [
        {'ticker': '000001', 'trade_date': date(2026, 9, 7), 'investor_type': 'FOREIGN'},
        {'ticker': '000002', 'trade_date': date(2026, 9, 4), 'investor_type': 'FOREIGN'},
    ])
    con.close()
    result = _official_flow_freshness(settings, date(2026, 9, 7))
    assert result['state'] == 'partial'
    assert result['coverage'] == {'stored_tickers': 2, 'current_tickers': 1, 'not_current_tickers': 1}


def test_calendar_guard_allows_three_year_history():
    assert calendar_guard(750) >= 2250
    assert calendar_guard(10) >= 90
    assert calendar_guard(1) >= 81


def test_scheduler_next_slot_skips_weekend():
    cfg = load_scheduler_config()
    friday_night = datetime(2026, 8, 21, 19, 30, tzinfo=KST)
    nxt = _next_slot(cfg, friday_night)
    assert nxt.date().isoformat() == "2026-08-24"
    assert nxt.hour == int(cfg["krx_prices"]["hour"])


def test_scheduler_catches_up_missed_stale_trading_day(monkeypatch):
    import kr_quant.freshness as freshness

    cfg = {"job_kind": "smart-sync", "hour": 19, "minute": 10}
    now = datetime(2026, 8, 25, 20, 0, tzinfo=KST)
    previous = _STATE.get("last_fire")
    try:
        _STATE["last_fire"] = None
        monkeypatch.setattr(
            freshness,
            "freshness_snapshot",
            lambda *args, **kwargs: {
                "stale_price": True,
                "sources": {"quant_ranking": {"state": "stale"}},
            },
        )
        assert _catch_up_due(cfg, now) is True
        _STATE["last_fire"] = now.isoformat()
        assert _catch_up_due(cfg, now) is False
    finally:
        _STATE["last_fire"] = previous


def test_scheduler_save_preserves_public_deploy_config(tmp_path, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "scheduler.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "enabled": True,
                "job_kind": "live",
                "hour": 18,
                "minute": 30,
                "publish_public": {"enabled": True, "after_jobs": ["live", "screen"], "project": "keep-me"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "load_settings", lambda: settings)
    monkeypatch.setattr("kr_quant.web.publish.publish_status", lambda: {"enabled": True})

    scheduler.save_scheduler_config(
        {"enabled": True, "job_kind": "smart-sync", "hour": 19, "minute": 10, "lookback_days": 80}
    )

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["publish_public"]["project"] == "keep-me"
    assert saved["job_kind"] == "smart-sync"
    assert saved["hour"] == 19


def test_scheduler_runtime_state_survives_restart(tmp_path, monkeypatch):
    settings = replace(load_settings(), root=tmp_path)
    prior = {key: _STATE.get(key) for key in ("last_fire", "last_skip", "last_error", "last_result")}
    monkeypatch.setattr(scheduler, "load_settings", lambda: settings)
    try:
        _STATE.update(
            {
                "last_fire": "2026-08-31T19:10:00+09:00",
                "last_skip": None,
                "last_error": None,
                "last_result": {"started": True, "kind": "smart-sync"},
            }
        )
        scheduler._persist_runtime_state()
        _STATE.update({"last_fire": None, "last_skip": "reset", "last_error": "reset", "last_result": None})
        scheduler._restore_runtime_state()
        assert _STATE["last_fire"] == "2026-08-31T19:10:00+09:00"
        assert _STATE["last_result"]["kind"] == "smart-sync"
        assert _STATE["last_skip"] is None
    finally:
        _STATE.update(prior)
