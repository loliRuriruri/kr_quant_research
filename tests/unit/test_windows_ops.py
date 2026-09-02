# -*- coding: utf-8 -*-
"""P2-5 Windows operations and scheduler offline catch-up tests."""
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace
import pytest

from kr_quant.web.scheduler import _catch_up_due, _STATE

KST = ZoneInfo("Asia/Seoul")


def test_catch_up_due_detects_offline_missed_when_stale(monkeypatch):
    cfg = {"enabled": True, "job_kind": "smart-sync", "hour": 19, "minute": 10}
    # Morning at 09:30 KST (before evening scheduled time)
    morning = datetime(2026, 9, 2, 9, 30, tzinfo=KST)

    prior = dict(_STATE)
    try:
        _STATE.clear()
        # Mock freshness returning stale_price = True
        monkeypatch.setattr(
            "kr_quant.freshness.freshness_snapshot",
            lambda settings, now=None: {"stale_price": True, "sources": {}},
        )
        assert _catch_up_due(cfg, now=morning) is True

        # Now simulate it just fired 10 minutes ago
        _STATE["last_fire"] = datetime(2026, 9, 2, 9, 20, tzinfo=KST).isoformat()
        assert _catch_up_due(cfg, now=morning) is False

        # If fired 2 hours ago and prices are still stale, should be due again
        _STATE["last_fire"] = datetime(2026, 9, 2, 7, 20, tzinfo=KST).isoformat()
        assert _catch_up_due(cfg, now=morning) is True
    finally:
        _STATE.clear()
        _STATE.update(prior)


def test_catch_up_due_evening_missed_run(monkeypatch):
    cfg = {"enabled": True, "job_kind": "smart-sync", "hour": 19, "minute": 10}
    # 20:30 KST on a Wednesday (trading day, after scheduled 19:10)
    evening = datetime(2026, 9, 2, 20, 30, tzinfo=KST)

    prior = dict(_STATE)
    try:
        _STATE.clear()
        monkeypatch.setattr(
            "kr_quant.freshness.freshness_snapshot",
            lambda settings, now=None: {"stale_price": False, "sources": {"quant_ranking": {"state": "stale"}}},
        )
        assert _catch_up_due(cfg, now=evening) is True

        # If already fired today, should not be due
        _STATE["last_fire"] = datetime(2026, 9, 2, 19, 15, tzinfo=KST).isoformat()
        assert _catch_up_due(cfg, now=evening) is False
    finally:
        _STATE.clear()
        _STATE.update(prior)


def test_catch_up_due_skips_when_everything_fresh(monkeypatch):
    cfg = {"enabled": True, "job_kind": "smart-sync", "hour": 19, "minute": 10}
    # 14:00 KST on a Wednesday, prices and ranks are fresh
    midday = datetime(2026, 9, 2, 14, 0, tzinfo=KST)

    prior = dict(_STATE)
    try:
        _STATE.clear()
        monkeypatch.setattr(
            "kr_quant.freshness.freshness_snapshot",
            lambda settings, now=None: {"stale_price": False, "sources": {"quant_ranking": {"state": "fresh"}}},
        )
        assert _catch_up_due(cfg, now=midday) is False
    finally:
        _STATE.clear()
        _STATE.update(prior)
