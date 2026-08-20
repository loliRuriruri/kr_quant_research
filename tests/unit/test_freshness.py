from datetime import datetime
from zoneinfo import ZoneInfo

from kr_quant.freshness import expected_price_date, runtime_spec
from kr_quant.ingest.live import calendar_guard
from kr_quant.settings import load_settings
from kr_quant.web.scheduler import _next_slot, load_scheduler_config

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


def test_calendar_guard_allows_three_year_history():
    assert calendar_guard(750) >= 2250
    assert calendar_guard(10) >= 90
    assert calendar_guard(1) >= 81


def test_scheduler_next_slot_skips_weekend():
    cfg = load_scheduler_config()
    friday_night = datetime(2026, 8, 21, 19, 0, tzinfo=KST)
    nxt = _next_slot(cfg, friday_night)
    assert nxt.date().isoformat() == "2026-08-24"
    assert nxt.hour == int(cfg["krx_prices"]["hour"])
