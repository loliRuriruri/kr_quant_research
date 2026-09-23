# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from kr_quant.web.pipeline_plan import InvalidPipelineMode, action_kinds, plan_pipeline


def _health(**components):
    base = {
        "pipeline_state": "READY",
        "expected_price_date": "2026-08-20",
        "components": {
            "krx": {"state": "HEALTHY", "as_of": "2026-08-20"},
            "master": {"state": "HEALTHY"},
            "dart_essential": {"state": "HEALTHY"},
            "dart_coverage": {"state": "HEALTHY", "coverage_pct": 99.0},
            "quant": {"state": "HEALTHY", "as_of": "2026-08-20"},
            "kis": {"state": "HEALTHY"},
            "season": {"state": "HEALTHY"},
        },
        "repair_required": False,
        "busy": False,
    }
    base["components"].update(components)
    return base


def test_invalid_mode_fails_closed():
    with pytest.raises(InvalidPipelineMode):
        plan_pipeline(_health(), mode="nope")


def test_11_all_healthy_no_destructive_repair():
    plan = plan_pipeline(_health(), mode="normal")
    kinds = action_kinds(plan)
    assert "REFRESH_KRX" not in kinds
    assert "REPAIR_DART_ESSENTIAL" not in kinds
    assert "REBUILD_QUANT" not in kinds
    assert "DART_MAINTENANCE_BATCH" not in kinds


def test_12_only_krx_stale_refresh_krx():
    health = _health(krx={"state": "STALE", "as_of": "2026-08-18"})
    health["pipeline_state"] = "NEEDS_DAILY_UPDATE"
    plan = plan_pipeline(health, mode="normal")
    kinds = action_kinds(plan)
    assert kinds[0] == "REFRESH_KRX"
    assert "REPAIR_DART_ESSENTIAL" not in kinds


def test_13_facts_missing_repairs_before_quant():
    health = _health(
        dart_essential={"state": "MISSING", "reason": "financial_facts_missing"},
        quant={"state": "BLOCKED", "blocked_by": ["dart_essential"]},
    )
    health["pipeline_state"] = "REPAIR_REQUIRED"
    health["repair_required"] = True
    plan = plan_pipeline(health, mode="recover")
    kinds = action_kinds(plan)
    assert "REPAIR_DART_ESSENTIAL" in kinds
    assert "REBUILD_QUANT" in kinds
    assert kinds.index("REPAIR_DART_ESSENTIAL") < kinds.index("REBUILD_QUANT")


def test_14_only_quant_stale_rebuild_quant_only():
    health = _health(quant={"state": "STALE", "as_of": "2026-08-18"})
    health["pipeline_state"] = "NEEDS_DAILY_UPDATE"
    plan = plan_pipeline(health, mode="normal")
    kinds = action_kinds(plan)
    assert "REBUILD_QUANT" in kinds
    assert "REFRESH_KRX" not in kinds
    assert "REPAIR_DART_ESSENTIAL" not in kinds


def test_15_16_17_recover_never_schedules_long_jobs():
    health = _health(
        dart_essential={"state": "MISSING"},
        quant={"state": "BLOCKED", "blocked_by": ["dart_essential"]},
        dart_coverage={"state": "PARTIAL", "coverage_pct": 10.0},
    )
    health["pipeline_state"] = "REPAIR_REQUIRED"
    plan = plan_pipeline(health, mode="recover")
    kinds = set(action_kinds(plan))
    assert "krx-history" not in kinds
    assert "KRX_HISTORY" not in kinds
    assert "DART_FULL_COVERAGE" not in kinds
    assert "DART_CONTINUOUS" not in kinds
    assert "FULL_UPDATE" not in kinds
    assert "LIVE_FULL_UPDATE" not in kinds
    assert "DART_MAINTENANCE_BATCH" not in kinds


def test_18_normal_may_schedule_one_maintenance_batch():
    health = _health(dart_coverage={"state": "PARTIAL", "coverage_pct": 70.0})
    plan = plan_pipeline(health, mode="normal")
    kinds = action_kinds(plan)
    assert kinds.count("DART_MAINTENANCE_BATCH") == 1


def test_19_kis_stale_does_not_force_quant_rebuild():
    health = _health(kis={"state": "STALE"})
    plan = plan_pipeline(health, mode="normal")
    kinds = action_kinds(plan)
    assert "REFRESH_KIS" in kinds
    assert "REBUILD_QUANT" not in kinds
