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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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


_STATE: dict[str, Any] = {
    "last_ok": None,
    "last_at": None,
    "last_url": None,
    "last_error": None,
    "last_log": "",
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
        "after_jobs": [str(x) for x in (pub.get("after_jobs") or ["live", "screen", "demo"])],
        "project": str(pub.get("project") or "korea-quant-research"),
        "branch": str(pub.get("branch") or "main"),
    }


def publish_status() -> dict[str, Any]:
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


def publish_public_snapshot(*, deploy: bool = True) -> dict[str, Any]:
    cfg = load_publish_config()
    root = _root()
    _safe_print("[1/2] 로컬 스냅샷 생성 중 (1분 안팎 걸릴 수 있습니다)...", flush=True)
    build = _run([_node(), str(root / "scripts" / "build-public.mjs")], root, timeout=300)
    log = (build.stdout or "") + "\n" + (build.stderr or "")
    if build.stdout:
        _safe_print(build.stdout.strip()[-500:], flush=True)
    if build.returncode != 0:
        err = (build.stderr or build.stdout or "build failed")[-800:]
        _safe_print("[FAIL] 스냅샷 생성 실패\n" + err, flush=True)
        _STATE.update({"last_ok": False, "last_at": datetime.now(timezone.utc).isoformat(), "last_error": "build failed", "last_log": log[-4000:]})
        return {"ok": False, "step": "build", "error": err, "cfg": cfg}

    if not deploy:
        _STATE.update({"last_ok": True, "last_at": datetime.now(timezone.utc).isoformat(), "last_error": None, "last_log": log[-2000:]})
        return {"ok": True, "step": "build", "deployed": False, "log": log[-400:]}

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
    _STATE.update({
        "last_ok": ok,
        "last_at": datetime.now(timezone.utc).isoformat(),
        "last_url": url if ok else None,
        "last_error": err,
        "last_log": log[-4000:],
    })
    status_path = root / "logs" / "public_publish.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(publish_status(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": ok, "step": "deploy", "url": url if ok else None, "error": err}


def maybe_publish_after_job(kind: str) -> dict[str, Any] | None:
    cfg = load_publish_config()
    if not cfg["enabled"]:
        return None
    if kind not in cfg["after_jobs"]:
        return None
    return publish_public_snapshot(deploy=True)
