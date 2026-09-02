# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

from kr_quant.web import publish
from kr_quant.web.jobs import RUNNER, _maybe_publish
from kr_quant.web.publish import (
    URL_RE,
    classify_publication_errors,
    evaluate_manual_override,
    evaluate_publication_readiness,
    load_publish_config,
)


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
    assert result["blocked"] is True
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


def test_classify_stale_mismatch_as_safety_block():
    assert classify_publication_errors(["PRICE_DATA_STALE", "AS_OF_DATE_MISMATCH"]) == "blocked"
    assert classify_publication_errors(["NO_ELIGIBLE_CANDIDATES"]) == "failed"
    assert classify_publication_errors([]) == "ready"


def test_safety_block_keeps_last_successful_deploy(monkeypatch, tmp_path):
    prior = dict(publish._STATE)
    hydrated = publish._HYDRATED
    try:
        publish._HYDRATED = True
        publish._STATE.update(
            {
                "last_ok": True,
                "last_success_at": "2026-08-28T10:00:00+00:00",
                "published_as_of": "2026-08-28",
                "last_url": "https://korea-quant-research.pages.dev/",
                "last_event": "success",
                "last_deploy_kind": "data",
                "last_error": None,
            }
        )
        monkeypatch.setattr(publish, "_root", lambda: tmp_path)
        monkeypatch.setattr(
            publish,
            "publication_readiness",
            lambda root=None: {
                "ready": False,
                "errors": ["PRICE_DATA_STALE", "AS_OF_DATE_MISMATCH"],
                "as_of_date": "2026-08-28",
                "expected_price_date": "2026-08-31",
                "current_local_as_of": "2026-08-28",
                "current_expected_as_of": "2026-08-31",
                "eligible_rows": 100,
                "block_kind": "blocked",
            },
        )
        monkeypatch.setattr(publish, "_run", lambda *args, **kwargs: pytest.fail("must not build after safety block"))
        result = publish.publish_public_snapshot(deploy=True)
        assert result["blocked"] is True
        assert publish._STATE["last_ok"] is True
        assert publish._STATE["published_as_of"] == "2026-08-28"
        assert publish._STATE["last_event"] == "blocked"
        assert publish._STATE["last_success_at"] == "2026-08-28T10:00:00+00:00"
    finally:
        publish._STATE.clear()
        publish._STATE.update(prior)
        publish._HYDRATED = hydrated


def test_publish_sync_false_when_public_as_of_differs_from_local(monkeypatch):
    prior = dict(publish._STATE)
    hydrated = publish._HYDRATED
    try:
        publish._HYDRATED = True
        publish._STATE.update({"published_as_of": "2026-08-26", "last_ok": True, "last_success_at": "2026-08-26T12:00:00+00:00"})
        monkeypatch.setattr(
            publish,
            "publication_readiness",
            lambda root=None: {
                "ready": False,
                "errors": ["PRICE_DATA_STALE"],
                "as_of_date": "2026-08-28",
                "expected_price_date": "2026-08-31",
                "current_local_as_of": "2026-08-28",
                "current_expected_as_of": "2026-08-31",
                "block_kind": "blocked",
            },
        )
        monkeypatch.setattr(publish, "read_snapshot_as_of", lambda root=None: "2026-08-26")
        sync = publish.publish_sync_status()
        assert sync["in_sync"] is False
        assert sync["published_as_of"] == "2026-08-26"
        assert sync["current_local_as_of"] == "2026-08-28"
        assert sync["current_expected_as_of"] == "2026-08-31"
        assert "PRICE_DATA_STALE" in sync["blocking_reasons"]
    finally:
        publish._STATE.clear()
        publish._STATE.update(prior)
        publish._HYDRATED = hydrated


def test_maybe_publish_checks_guard_before_upload_log(monkeypatch):
    monkeypatch.setattr(
        "kr_quant.web.publish.maybe_publish_after_job",
        lambda kind: {"ok": False, "blocked": True, "error": "PUBLICATION_BLOCKED: PRICE_DATA_STALE"},
    )
    RUNNER.logs.clear()
    _maybe_publish("live")
    text = "\n".join(RUNNER.logs)
    assert "갱신 가능 여부" in text
    assert "올리는 중" not in text
    assert "안전 차단" in text


def test_code_only_status_keeps_published_as_of(monkeypatch, tmp_path):
    prior = dict(publish._STATE)
    hydrated = publish._HYDRATED
    try:
        publish._HYDRATED = True
        publish._STATE.update({"published_as_of": "2026-08-26", "last_ok": True, "last_deploy_kind": "data"})
        monkeypatch.setattr(publish, "_root", lambda: tmp_path)
        monkeypatch.setattr(publish, "load_publish_config", lambda: {"project": "test", "branch": "main"})
        monkeypatch.setattr(
            publish,
            "publication_readiness",
            lambda root=None: {"ready": False, "errors": ["PRICE_DATA_STALE"], "as_of_date": "2026-08-28", "eligible_rows": 10},
        )
        monkeypatch.setattr(
            publish,
            "_run",
            lambda cmd, cwd, timeout: SimpleNamespace(returncode=0, stdout="https://test.pages.dev", stderr=""),
        )
        result = publish.publish_public_snapshot(deploy=True, code_only=True)
        assert result["ok"] is True
        assert result["code_only"] is True
        assert publish._STATE["published_as_of"] == "2026-08-26"
        assert publish._STATE["last_deploy_kind"] == "code"
    finally:
        publish._STATE.clear()
        publish._STATE.update(prior)
        publish._HYDRATED = hydrated


def test_verify_public_snapshot_detects_secrets_and_local_paths(tmp_path):
    dist = tmp_path / "dist-public"
    dist.mkdir()

    # Missing build.json
    res = publish.verify_public_snapshot(dist)
    assert res["valid"] is False
    assert "BUILD_JSON_MISSING" in res["errors"]

    # Write valid build.json
    build_info = {
        "project": "korea-quant-research",
        "schema_version": "1.1.0",
        "git_commit": "abc1234",
        "data_as_of": "2026-09-01",
        "web_deployed_at": "2026-09-02T18:00:00Z",
        "files": ["index.html", "data/test.json"],
    }
    (dist / "build.json").write_text(publish.json.dumps(build_info), encoding="utf-8")
    (dist / "index.html").write_text("<html>safe</html>", encoding="utf-8")
    (dist / "data").mkdir()
    (dist / "data" / "test.json").write_text('{"safe": true}', encoding="utf-8")

    clean_res = publish.verify_public_snapshot(dist)
    assert clean_res["valid"] is True
    assert clean_res["errors"] == []
    assert clean_res["build_info"]["git_commit"] == "abc1234"

    # Leak secret pattern
    (dist / "data" / "leak.json").write_text('{"key": "sk-1234567890abcdef"}', encoding="utf-8")
    leak_res = publish.verify_public_snapshot(dist)
    assert leak_res["valid"] is False
    assert any("SECRET_PATTERN_LEAK" in e for e in leak_res["errors"])
    (dist / "data" / "leak.json").unlink()

    # Leak local path
    (dist / "data" / "path_leak.json").write_text('{"path": "C:\\\\Users\\\\alice\\\\quant\\\\data"}', encoding="utf-8")
    path_res = publish.verify_public_snapshot(dist)
    assert path_res["valid"] is False
    assert any("LOCAL_PATH_LEAK" in e for e in path_res["errors"])
    (dist / "data" / "path_leak.json").unlink()

    # Forbidden file
    (dist / ".env").write_text("SECRET=123", encoding="utf-8")
    env_res = publish.verify_public_snapshot(dist)
    assert env_res["valid"] is False
    assert any("FORBIDDEN_FILE" in e for e in env_res["errors"])


def test_publish_sync_status_includes_build_info(monkeypatch, tmp_path):
    dist = tmp_path / "dist-public"
    dist.mkdir()
    build_info = {
        "project": "korea-quant-research",
        "schema_version": "1.1.0",
        "git_commit": "feedbeef123",
        "data_as_of": "2026-09-01",
        "web_deployed_at": "2026-09-02T18:30:00Z",
        "bundle_sha256": "fakehash",
    }
    (dist / "build.json").write_text(publish.json.dumps(build_info), encoding="utf-8")
    monkeypatch.setattr(publish, "_root", lambda: tmp_path)
    monkeypatch.setattr(publish, "publication_readiness", lambda root=None: {"current_local_as_of": "2026-09-01", "errors": []})

    status = publish.publish_sync_status(tmp_path)
    assert status["build_info"] is not None
    assert status["build_info"]["git_commit"] == "feedbeef123"
    assert status["build_info"]["schema_version"] == "1.1.0"
    assert status["build_info"]["data_as_of"] == "2026-09-01"
    assert status["build_info"]["web_deployed_at"] == "2026-09-02T18:30:00Z"

