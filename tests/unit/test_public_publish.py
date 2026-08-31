# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

from kr_quant.web import publish
from kr_quant.web.publish import URL_RE, evaluate_manual_override, evaluate_publication_readiness, load_publish_config


def test_publish_config_defaults_to_pages_project():
    cfg = load_publish_config()
    assert cfg["project"] == "korea-quant-research"
    assert "live" in cfg["after_jobs"]
    assert "screen" in cfg["after_jobs"]
    assert "demo" not in cfg["after_jobs"]


def test_parse_pages_url_from_wrangler_output():
    text = "Deployment complete! Take a peek over at https://3a19cc91.korea-quant-research.pages.dev"
    urls = URL_RE.findall(text)
    assert urls[-1].startswith("https://")
    assert "pages.dev" in urls[-1]


def test_publication_readiness_accepts_only_current_live_success():
    result = evaluate_publication_readiness(
        {
            "source_mode": "live",
            "status": "success",
            "warnings": [],
            "as_of_date": "2026-08-26",
        },
        {
            "expected_price_date": "2026-08-26",
            "price_max_date": "2026-08-26",
            "screen_as_of": "2026-08-26",
            "stale_price": False,
            "stale_screen": False,
        },
        eligible_rows=100,
    )
    assert result["ready"] is True
    assert result["errors"] == []


def test_publication_readiness_blocks_demo_partial_stale_and_empty_results():
    result = evaluate_publication_readiness(
        {
            "source_mode": "demo",
            "status": "partial",
            "warnings": ["STATUS_FEED_MISSING"],
            "as_of_date": "2026-08-24",
        },
        {
            "expected_price_date": "2026-08-26",
            "price_max_date": "2026-08-25",
            "screen_as_of": "2026-08-24",
            "stale_price": True,
            "stale_screen": True,
        },
        eligible_rows=0,
    )
    assert result["ready"] is False
    assert set(result["errors"]) == {
        "SOURCE_MODE_NOT_LIVE",
        "QUALITY_NOT_SUCCESS",
        "QUALITY_WARNINGS_PRESENT",
        "PRICE_DATA_STALE",
        "SCREEN_DATA_STALE",
        "AS_OF_DATE_MISMATCH",
        "NO_ELIGIBLE_CANDIDATES",
    }


def test_publication_readiness_blocks_invalid_evidence_contract():
    result = evaluate_publication_readiness(
        {"source_mode": "live", "status": "success", "warnings": [], "as_of_date": "2026-08-26"},
        {
            "expected_price_date": "2026-08-26",
            "price_max_date": "2026-08-26",
            "screen_as_of": "2026-08-26",
            "stale_price": False,
            "stale_screen": False,
        },
        eligible_rows=100,
        evidence_registry={"contract_version": "1.0", "menus": {}},
    )

    assert result["ready"] is False
    assert "EVIDENCE_CONTRACT_INVALID" in result["errors"]
    assert result["evidence_validation"]["valid"] is False


def test_publication_guard_stops_before_build_or_deploy(monkeypatch, tmp_path):
    monkeypatch.setattr(publish, "_root", lambda: tmp_path)
    monkeypatch.setattr(
        publish,
        "load_publish_config",
        lambda: {
            "enabled": True,
            "after_jobs": ["live", "screen"],
            "project": "korea-quant-research",
            "branch": "main",
        },
    )
    monkeypatch.setattr(
        publish,
        "publication_readiness",
        lambda root=None: {
            "ready": False,
            "errors": ["SOURCE_MODE_NOT_LIVE", "AS_OF_DATE_MISMATCH"],
            "eligible_rows": 0,
        },
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("publication build/deploy command must not run after a failed guard")

    monkeypatch.setattr(publish, "_run", fail_if_called)
    result = publish.publish_public_snapshot(deploy=True)

    assert result["ok"] is False
    assert result["step"] == "guard"
    assert "SOURCE_MODE_NOT_LIVE" in result["error"]


def test_manual_override_accepts_legacy_stale_warning_but_not_empty_or_demo():
    legacy = evaluate_manual_override(
        {
            "ready": False,
            "errors": ["SOURCE_MODE_NOT_LIVE", "QUALITY_NOT_SUCCESS", "PRICE_DATA_STALE"],
            "source_mode": None,
            "eligible_rows": 275,
        }
    )
    assert legacy["allowed"] is True
    assert legacy["legacy_source_unknown"] is True

    empty = evaluate_manual_override(
        {"ready": False, "errors": ["NO_ELIGIBLE_CANDIDATES"], "source_mode": "live", "eligible_rows": 0}
    )
    assert empty["allowed"] is False

    demo = evaluate_manual_override(
        {"ready": False, "errors": ["SOURCE_MODE_NOT_LIVE"], "source_mode": "demo", "eligible_rows": 10}
    )
    assert demo["allowed"] is False
    assert "EXPLICIT_NON_LIVE_SOURCE" in demo["blocking_errors"]


def test_code_only_build_reuses_public_data_and_bypasses_data_guard(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(publish, "_root", lambda: tmp_path)
    monkeypatch.setattr(publish, "load_publish_config", lambda: {"project": "test", "branch": "main"})
    monkeypatch.setattr(
        publish,
        "publication_readiness",
        lambda root=None: {
            "ready": False,
            "errors": ["PRICE_DATA_STALE", "AS_OF_DATE_MISMATCH"],
            "source_mode": "live",
            "eligible_rows": 10,
        },
    )

    def fake_run(cmd, cwd, timeout):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout="dist-public ready", stderr="")

    monkeypatch.setattr(publish, "_run", fake_run)
    result = publish.publish_public_snapshot(deploy=False, code_only=True)

    assert result["ok"] is True
    assert result["code_only"] is True
    assert "--reuse-data" in commands[0]
