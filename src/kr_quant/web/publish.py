# -*- coding: utf-8 -*-
"""Rebuild the secret-free snapshot and deploy it to Cloudflare Pages.

Runs only on this PC. API keys stay in local .env. The public site still
cannot collect data by itself.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from kr_quant.freshness import freshness_snapshot
from kr_quant.settings import load_settings

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _safe_print(text: str, end: str = "\n", flush: bool = True) -> None:
    try:
        print(text, end=end, flush=flush)
    except Exception:
        try:
            enc = sys.stdout.encoding or "utf-8"
            safe_text = text.encode(enc, errors="replace").decode(enc)
            print(safe_text, end=end, flush=flush)
        except Exception:
            pass


SAFETY_BLOCK_ERRORS = frozenset(
    {
        "PRICE_DATA_STALE",
        "AS_OF_DATE_MISMATCH",
        "SCREEN_DATA_STALE",
        "QUALITY_WARNINGS_PRESENT",
        "SOURCE_MODE_NOT_LIVE",
        "QUALITY_NOT_SUCCESS",
    }
)
HARD_FAIL_ERRORS = frozenset(
    {
        "QUALITY_REPORT_MISSING",
        "LATEST_RESULTS_MISSING",
        "PUBLICATION_SOURCE_READ_FAILED",
        "NO_ELIGIBLE_CANDIDATES",
        "EVIDENCE_CONTRACT_INVALID",
    }
)

_STATE: dict[str, Any] = {
    "last_ok": None,
    "last_at": None,
    "last_url": None,
    "last_error": None,
    "last_log": "",
    "last_event": None,
    "last_success_at": None,
    "published_as_of": None,
    "last_deploy_kind": None,
    "last_block_reasons": None,
}
_HYDRATED = False

_DEPLOY_LOCK = threading.Lock()
_DEPLOY_STATUS: dict[str, Any] = {
    "state": "idle",
    "message": "수동 배포 대기",
    "detail": "자동 갱신과 별도로 필요할 때 언제든 실행할 수 있습니다.",
    "started_at": None,
    "finished_at": None,
    "public_url": "https://korea-quant-research.pages.dev/",
}

URL_RE = re.compile(r"https://[a-z0-9.-]+\.pages\.dev[^\s]*", re.I)


def _root() -> Path:
    return load_settings().root


def load_publish_config() -> dict[str, Any]:
    path = _root() / "config" / "scheduler.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pub = data.get("publish_public") or {}
    env_off = os.environ.get("KR_QUANT_PUBLISH", "").strip().lower() in {"0", "false", "no", "off"}
    return {
        "enabled": (not env_off) and bool(pub.get("enabled", True)),
        "after_jobs": [str(x) for x in (pub.get("after_jobs") or ["live", "screen"])],
        "project": str(pub.get("project") or "korea-quant-research"),
        "branch": str(pub.get("branch") or "main"),
    }


def classify_publication_errors(errors: list[str] | None) -> str:
    items = [str(item) for item in (errors or []) if item]
    if not items:
        return "ready"
    if any(item in HARD_FAIL_ERRORS for item in items):
        return "failed"
    if items and all(item in SAFETY_BLOCK_ERRORS for item in items):
        return "blocked"
    return "failed"


def _saved_publish_path() -> Path:
    return _root() / "logs" / "public_publish.json"


def _hydrate_publish_state() -> None:
    global _HYDRATED
    if _HYDRATED:
        return
    path = _saved_publish_path()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        if isinstance(saved, dict):
            for key in _STATE:
                if _STATE.get(key) is None and saved.get(key) is not None:
                    _STATE[key] = saved[key]
    _HYDRATED = True


def read_snapshot_as_of(root: Path | None = None) -> str | None:
    project = root or _root()
    for path in (
        project / "dist-public" / "data" / "meta.json",
        project / "dist-public" / "data" / "snapshot.json",
    ):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if path.name == "snapshot.json" and isinstance(payload, dict):
            payload = payload.get("meta") or payload
        if isinstance(payload, dict):
            value = payload.get("as_of_date") or payload.get("as_of")
            if value:
                return str(value)[:10]
    return None


def _persist_publish_state() -> None:
    path = _saved_publish_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_STATE, **load_publish_config(), "public_url": "https://korea-quant-research.pages.dev/"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_sync_status(root: Path | None = None) -> dict[str, Any]:
    _hydrate_publish_state()
    project = root or _root()
    readiness = publication_readiness(project)
    published_as_of = _STATE.get("published_as_of") or read_snapshot_as_of(project)
    current_local = readiness.get("current_local_as_of") or readiness.get("as_of_date")
    current_expected = readiness.get("current_expected_as_of") or readiness.get("expected_price_date")
    in_sync = bool(published_as_of and current_local and str(published_as_of)[:10] == str(current_local)[:10])
    blocking = list(readiness.get("errors") or [])
    return {
        "last_successful_deploy_at": _STATE.get("last_success_at") or (_STATE.get("last_at") if _STATE.get("last_ok") else None),
        "published_as_of": published_as_of,
        "current_local_as_of": current_local,
        "current_expected_as_of": current_expected,
        "in_sync": in_sync,
        "current_publish_readiness": readiness,
        "blocking_reasons": blocking,
        "deployment_url": _STATE.get("last_url") or "https://korea-quant-research.pages.dev/",
        "last_deploy_kind": _STATE.get("last_deploy_kind"),
        "last_event": _STATE.get("last_event"),
        "block_kind": readiness.get("block_kind") or classify_publication_errors(blocking),
    }


def publish_status() -> dict[str, Any]:
    _hydrate_publish_state()
    cfg = load_publish_config()
    return {**_STATE, **cfg, "public_url": "https://korea-quant-research.pages.dev/"}


def _which(name: str) -> str | None:
    from shutil import which

    hit = which(name)
    if hit:
        return hit
    if os.name == "nt":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / name
        if pf.exists():
            return str(pf)
    return None


def _run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    node_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs"
    if node_dir.exists():
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    use_shell = os.name == "nt" and cmd and str(cmd[0]).lower().endswith((".cmd", ".bat"))
    printable = " ".join(str(c) for c in cmd)
    _safe_print("  > " + printable, flush=True)
    argv: str | list[str]
    if use_shell:
        argv = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    else:
        argv = cmd
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=use_shell,
        env=env,
    )
    chunks: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            _safe_print(line, end="", flush=True)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return subprocess.CompletedProcess(cmd, 1, "".join(chunks), "timeout")
    return subprocess.CompletedProcess(cmd, proc.returncode or 0, "".join(chunks), "")


def _npx() -> str:
    return _which("npx.cmd") or _which("npx") or ("npx.cmd" if os.name == "nt" else "npx")


def _node() -> str:
    return _which("node.exe") or _which("node") or "node"


def evaluate_publication_readiness(
    quality: dict[str, Any],
    freshness: dict[str, Any],
    *,
    eligible_rows: int,
    evidence_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, fail-closed decision for public publication."""
    errors: list[str] = []
    if str(quality.get("source_mode") or "").lower() != "live":
        errors.append("SOURCE_MODE_NOT_LIVE")
    if str(quality.get("status") or "").lower() != "success":
        errors.append("QUALITY_NOT_SUCCESS")
    if quality.get("warnings"):
        errors.append("QUALITY_WARNINGS_PRESENT")
    if freshness.get("stale_price"):
        errors.append("PRICE_DATA_STALE")
    if freshness.get("stale_screen"):
        errors.append("SCREEN_DATA_STALE")

    expected = str(freshness.get("expected_price_date") or "")
    price_max = str(freshness.get("price_max_date") or "")
    screen_as_of = str(quality.get("as_of_date") or freshness.get("screen_as_of") or "")
    if not expected or price_max != expected or screen_as_of != expected:
        errors.append("AS_OF_DATE_MISMATCH")
    if eligible_rows <= 0:
        errors.append("NO_ELIGIBLE_CANDIDATES")
    evidence_validation: dict[str, Any] | None = None
    if evidence_registry is not None:
        from kr_quant.web.evidence import validate_evidence_registry

        evidence_validation = validate_evidence_registry(evidence_registry)
        if not evidence_validation.get("valid"):
            errors.append("EVIDENCE_CONTRACT_INVALID")
    unique_errors = list(dict.fromkeys(errors))
    return {
        "ready": not unique_errors,
        "errors": unique_errors,
        "block_kind": classify_publication_errors(unique_errors),
        "source_mode": quality.get("source_mode"),
        "quality_status": quality.get("status"),
        "as_of_date": screen_as_of or None,
        "expected_price_date": expected or None,
        "price_max_date": price_max or None,
        "current_local_as_of": screen_as_of or price_max or None,
        "current_expected_as_of": expected or None,
        "eligible_rows": int(eligible_rows),
        "evidence_validation": evidence_validation,
    }


def publication_readiness(root: Path | None = None) -> dict[str, Any]:
    project = root or _root()
    settings = load_settings(project)
    from kr_quant.run_generation import current_output_path

    quality_path = current_output_path(settings, "data_quality_report.json")
    latest_path = current_output_path(settings, "latest_all_stocks.parquet")
    if not quality_path.exists() or not latest_path.exists():
        missing = []
        if not quality_path.exists():
            missing.append("QUALITY_REPORT_MISSING")
        if not latest_path.exists():
            missing.append("LATEST_RESULTS_MISSING")
        try:
            fresh = freshness_snapshot(settings)
        except Exception:  # noqa: BLE001
            fresh = {}
        return {
            "ready": False,
            "errors": missing,
            "block_kind": classify_publication_errors(missing),
            "eligible_rows": 0,
            "current_local_as_of": fresh.get("screen_as_of") or fresh.get("price_max_date"),
            "current_expected_as_of": fresh.get("expected_price_date"),
            "as_of_date": fresh.get("screen_as_of"),
            "expected_price_date": fresh.get("expected_price_date"),
        }
    try:
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        latest = pd.read_parquet(latest_path, columns=["universe_eligible"])
        eligible_rows = int(
            latest["universe_eligible"]
            .map(lambda value: value is True or str(value).strip().lower() in {"1", "true", "yes"})
            .sum()
        )
        fresh = freshness_snapshot(settings, screen_as_of=quality.get("as_of_date"))
        from kr_quant.web.evidence import build_evidence_registry

        evidence_registry = build_evidence_registry(settings, quality=quality, freshness=fresh)
    except Exception as exc:
        return {
            "ready": False,
            "errors": ["PUBLICATION_SOURCE_READ_FAILED"],
            "block_kind": "failed",
            "detail": str(exc),
            "eligible_rows": 0,
        }
    return evaluate_publication_readiness(
        quality,
        fresh,
        eligible_rows=eligible_rows,
        evidence_registry=evidence_registry,
    )


def evaluate_manual_override(readiness: dict[str, Any]) -> dict[str, Any]:
    """Allow an explicit local override for warnings, never for unusable data."""
    errors = list(readiness.get("errors") or [])
    hard_errors = {
        "QUALITY_REPORT_MISSING",
        "LATEST_RESULTS_MISSING",
        "PUBLICATION_SOURCE_READ_FAILED",
        "NO_ELIGIBLE_CANDIDATES",
        "EVIDENCE_CONTRACT_INVALID",
    }
    blocking = [error for error in errors if error in hard_errors]
    source_mode = str(readiness.get("source_mode") or "").strip().lower()
    if source_mode and source_mode != "live":
        blocking.append("EXPLICIT_NON_LIVE_SOURCE")
    return {
        "allowed": not blocking,
        "blocking_errors": list(dict.fromkeys(blocking)),
        "accepted_warnings": errors if not blocking else [],
        "legacy_source_unknown": not source_mode,
    }


def publish_public_snapshot(
    *,
    deploy: bool = True,
    allow_warnings: bool = False,
    code_only: bool = False,
) -> dict[str, Any]:
    cfg = load_publish_config()
    root = _root()
    readiness = publication_readiness(root)
    override = evaluate_manual_override(readiness) if allow_warnings else None
    if not code_only and not readiness.get("ready"):
        if allow_warnings and override and override.get("allowed"):
            accepted = ", ".join(override.get("accepted_warnings") or [])
            _safe_print("[MANUAL OVERRIDE] 경고 포함 수동 배포: " + accepted, flush=True)
        else:
            errors = readiness.get("errors") or ["UNKNOWN_GUARD_FAILURE"]
            if allow_warnings and override and override.get("blocking_errors"):
                errors = override["blocking_errors"]
            error = "PUBLICATION_BLOCKED: " + ", ".join(errors)
            block_kind = classify_publication_errors(errors)
            blocked = block_kind == "blocked"
            _safe_print(("[BLOCKED] " if blocked else "[FAIL] ") + error, flush=True)
            stamp = datetime.now(timezone.utc).isoformat()
            update = {
                "last_at": stamp,
                "last_error": error,
                "last_event": "blocked" if blocked else "failed",
                "last_block_reasons": list(errors),
                "last_log": json.dumps({"readiness": readiness, "override": override}, ensure_ascii=False),
            }
            if not blocked:
                update["last_ok"] = False
            _STATE.update(update)
            _persist_publish_state()
            return {
                "ok": False,
                "blocked": blocked,
                "step": "guard",
                "error": error,
                "readiness": readiness,
                "override": override,
                "cfg": cfg,
            }
    if code_only:
        _safe_print("[1/2] 기존 공개 데이터를 유지하고 웹 패치만 빌드 중...", flush=True)
    else:
        _safe_print("[1/2] 로컬 스냅샷 생성 중 (1분 안팎 걸릴 수 있습니다)...", flush=True)
    build_cmd = [_node(), str(root / "scripts" / "build-public.mjs")]
    if code_only:
        build_cmd.append("--reuse-data")
    build = _run(build_cmd, root, timeout=300)
    log = (build.stdout or "") + "\n" + (build.stderr or "")
    if build.stdout:
        _safe_print(build.stdout.strip()[-500:], flush=True)
    if build.returncode != 0:
        err = (build.stderr or build.stdout or "build failed")[-800:]
        _safe_print("[FAIL] 스냅샷 생성 실패\n" + err, flush=True)
        _STATE.update({"last_ok": False, "last_at": datetime.now(timezone.utc).isoformat(), "last_error": "build failed", "last_log": log[-4000:]})
        return {"ok": False, "step": "build", "error": err, "cfg": cfg}

    if not deploy:
        stamp = datetime.now(timezone.utc).isoformat()
        _STATE.update(
            {
                "last_ok": True,
                "last_at": stamp,
                "last_error": None,
                "last_log": log[-2000:],
                "last_event": "code" if code_only else "success",
            }
        )
        _persist_publish_state()
        return {
            "ok": True,
            "step": "build",
            "deployed": False,
            "forced": bool(allow_warnings and not readiness.get("ready")),
            "code_only": code_only,
            "readiness": readiness,
            "log": log[-400:],
        }

    _safe_print("[2/2] Cloudflare Pages 업로드 중...", flush=True)
    deploy_cmd = [
        _npx(),
        "--yes",
        "wrangler",
        "pages",
        "deploy",
        "dist-public",
        "--project-name",
        cfg["project"],
        "--branch",
        cfg["branch"],
        "--commit-dirty=true",
    ]
    put = _run(deploy_cmd, root, timeout=180)
    log += "\n" + (put.stdout or "") + "\n" + (put.stderr or "")
    if put.stdout:
        _safe_print(put.stdout.strip()[-800:], flush=True)
    urls = URL_RE.findall(put.stdout or "") + URL_RE.findall(put.stderr or "")
    url = urls[-1] if urls else f"https://{cfg['project']}.pages.dev/"
    ok = put.returncode == 0
    err = None if ok else (put.stderr or put.stdout or "deploy failed")[-500:]
    if ok:
        _safe_print(f"[OK] 공개 사이트 갱신 완료: https://{cfg['project']}.pages.dev/", flush=True)
        _safe_print(f"     이번 배포: {url}", flush=True)
    else:
        _safe_print("[FAIL] 업로드 실패\n" + (err or ""), flush=True)
    stamp = datetime.now(timezone.utc).isoformat()
    published_as_of = _STATE.get("published_as_of")
    if ok and not code_only:
        published_as_of = read_snapshot_as_of(root) or readiness.get("as_of_date") or published_as_of
    _STATE.update(
        {
            "last_ok": ok,
            "last_at": stamp,
            "last_url": url if ok else _STATE.get("last_url"),
            "last_error": err,
            "last_log": log[-4000:],
            "last_event": ("code" if code_only else "success") if ok else "failed",
            "last_deploy_kind": ("code" if code_only else "data") if ok else _STATE.get("last_deploy_kind"),
            "last_success_at": stamp if ok else _STATE.get("last_success_at"),
            "published_as_of": published_as_of if ok else _STATE.get("published_as_of"),
            "last_block_reasons": None if ok else _STATE.get("last_block_reasons"),
        }
    )
    _persist_publish_state()
    return {
        "ok": ok,
        "step": "deploy",
        "url": url if ok else None,
        "error": err,
        "forced": bool(allow_warnings and not readiness.get("ready")),
        "code_only": code_only,
        "readiness": readiness,
        "published_as_of": _STATE.get("published_as_of"),
    }


def maybe_publish_after_job(kind: str) -> dict[str, Any] | None:
    cfg = load_publish_config()
    if not cfg["enabled"]:
        return None
    if kind not in cfg["after_jobs"]:
        return None
    return publish_public_snapshot(deploy=True)


def get_deploy_status() -> dict[str, Any]:
    _hydrate_publish_state()
    with _DEPLOY_LOCK:
        status = dict(_DEPLOY_STATUS)
    sync = publish_sync_status()
    status.update(sync)
    if status["state"] == "idle":
        event = _STATE.get("last_event")
        if event == "blocked" or (not _STATE.get("last_ok") and sync.get("block_kind") == "blocked" and _STATE.get("last_error")):
            status["state"] = "blocked"
            status["message"] = "공개판 안전 차단"
            status["detail"] = _STATE.get("last_error") or "현재 로컬 데이터는 공개 품질 가드에 걸렸습니다."
            status["finished_at"] = _STATE.get("last_at")
        elif _STATE.get("last_ok") is True:
            status["state"] = "success" if sync.get("in_sync") else "out_of_sync"
            status["message"] = "공개판 갱신 완료" if sync.get("in_sync") else "마지막 공개 성공 · 현재 로컬과 날짜가 다름"
            status["detail"] = (
                "공개 사이트에서 최신 버전을 확인할 수 있습니다."
                if sync.get("in_sync")
                else (
                    f"공개 기준일 {sync.get('published_as_of') or '—'} · 로컬 {sync.get('current_local_as_of') or '—'} · "
                    f"기대 {sync.get('current_expected_as_of') or '—'}"
                )
            )
            status["finished_at"] = _STATE.get("last_success_at") or _STATE.get("last_at")
            status["last_url"] = _STATE.get("last_url")
        elif _STATE.get("last_ok") is False:
            status["state"] = "failed"
            status["message"] = "공개판 갱신 실패"
            status["detail"] = _STATE.get("last_error") or "배포 중 오류가 발생했습니다."
            status["finished_at"] = _STATE.get("last_at")
    status["running"] = status["state"] == "running"
    status["code_only"] = _STATE.get("last_deploy_kind") == "code"
    return status


def _deploy_worker(allow_warnings: bool = False, code_only: bool = False) -> None:
    try:
        with _DEPLOY_LOCK:
            _DEPLOY_STATUS.update({
                "state": "running",
                "message": "웹 패치 빌드 중..." if code_only else "로컬 스냅샷 생성 및 검증 중...",
                "detail": (
                    "기존 공개 데이터는 유지하고 HTML/CSS/JavaScript만 최신화합니다."
                    if code_only
                    else "2,700여 개 전 종목 및 퀀트 API 스냅샷을 생성하고 있습니다."
                ),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            })
        result = publish_public_snapshot(
            deploy=True,
            allow_warnings=allow_warnings,
            code_only=code_only,
        )
        with _DEPLOY_LOCK:
            if result.get("ok"):
                _DEPLOY_STATUS.update({
                    "state": "success",
                    "message": "공개판 갱신 완료",
                    "detail": (
                        "웹 코드 패치를 배포했습니다. 공개 데이터 기준일은 기존과 동일합니다."
                        if result.get("code_only")
                        else (
                            "경고를 확인한 수동 예외 배포입니다. 공개 화면의 기준일과 품질 경고를 확인하세요."
                            if result.get("forced")
                            else "공개 사이트에서 최신 버전을 확인할 수 있습니다."
                        )
                    ),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "last_url": result.get("url"),
                })
            elif result.get("blocked"):
                _DEPLOY_STATUS.update({
                    "state": "blocked",
                    "message": "공개판 안전 차단",
                    "detail": result.get("error") or "현재 로컬 데이터는 공개 품질 가드에 걸렸습니다.",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                _DEPLOY_STATUS.update({
                    "state": "failed",
                    "message": "공개판 갱신 실패",
                    "detail": result.get("error") or "배포 과정에서 오류가 발생했습니다.",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception as exc:
        with _DEPLOY_LOCK:
            _DEPLOY_STATUS.update({
                "state": "failed",
                "message": "공개판 갱신 실패",
                "detail": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })


def start_manual_deploy(*, allow_warnings: bool = False, code_only: bool = False) -> dict[str, Any]:
    with _DEPLOY_LOCK:
        if _DEPLOY_STATUS.get("state") == "running":
            return get_deploy_status()
        _DEPLOY_STATUS.update({
            "state": "running",
            "message": "갱신·배포 작업을 시작합니다...",
            "detail": (
                "기존 공개 데이터는 유지하고 웹 코드만 최신화합니다."
                if code_only
                else (
                    "품질 경고를 사용자가 확인한 수동 예외 배포입니다."
                    if allow_warnings
                    else "작업이 백그라운드에서 진행됩니다."
                )
            ),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        })
    thread = threading.Thread(target=_deploy_worker, args=(allow_warnings, code_only), daemon=True)
    thread.start()
    return get_deploy_status()
