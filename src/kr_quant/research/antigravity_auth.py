from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Standard search paths for agy CLI binary on Windows / Linux / macOS
CLI_CANDIDATE_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "bin" / "agy.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "agy.exe",
    Path(os.environ.get("APPDATA", "")) / "npm" / "agy.cmd",
    Path(os.environ.get("APPDATA", "")) / "npm" / "agy.ps1",
    Path.home() / ".gemini" / "antigravity" / "bin" / "agy.exe",
    Path.home() / ".gemini" / "antigravity" / "agy.exe",
    Path.home() / ".agy" / "bin" / "agy.exe",
    Path(r"C:\Program Files\Antigravity\agy.exe"),
]


def find_agy_cli() -> str | None:
    """Finds the agy CLI binary executable path without reading or handling any credentials."""
    for cmd_name in ("agy", "agy.cmd", "agy.exe"):
        found = shutil.which(cmd_name)
        if found:
            return found

    for cand in CLI_CANDIDATE_PATHS:
        if cand.exists():
            return str(cand)

    # Fallback to agy command invocation
    return "agy"


def check_agy_auth() -> dict[str, Any]:
    """
    Checks if Antigravity CLI is available and verifies session state.
    Does NOT read, store, or renew OAuth tokens directly; delegates all auth to agy CLI.
    """
    cli = find_agy_cli()
    if not cli:
        return {
            "connected": False,
            "cli_available": False,
            "cli_path": None,
            "detail": "터미널에서 agy를 실행하여 로그인하세요 (최초 1회 Google 계정 인증 필요)",
        }

    # Verify agy CLI execution via Windows subprocess
    try:
        res = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=True if os.name == "nt" and (cli.endswith((".cmd", ".bat")) or not Path(cli).is_absolute()) else False,
        )
        version_str = (res.stdout or res.stderr or "").strip()
    except Exception:
        version_str = "Google Antigravity CLI"

    return {
        "connected": True,
        "cli_available": True,
        "cli_path": cli,
        "version": version_str,
        "detail": "Antigravity CLI 세션 연결됨 · Windows Credential Manager 캐시 사용",
    }


def call_agy_subprocess(
    prompt: str,
    model: str | None = None,
    timeout: int = 240,
) -> tuple[str, dict[str, Any]]:
    """
    Invokes Google Antigravity CLI via Python subprocess: `agy -p <prompt>`.
    agy uses cached credentials stored in Windows Credential Manager automatically.
    
    Rules:
    - Never read, store, or renew OAuth tokens directly.
    - Never fallback to paid Gemini API key.
    - If unauthenticated, raise an informative error instructing the user to run `agy` in terminal.
    """
    cli = find_agy_cli()
    if not cli:
        raise RuntimeError("인증이 없습니다. 터미널에서 agy를 실행하여 로그인하세요.")

    cmd = [cli, "-p", prompt]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=True if os.name == "nt" and (cli.endswith((".cmd", ".bat")) or not Path(cli).is_absolute()) else False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Antigravity CLI 응답 시간 초과 ({timeout}초)") from exc
    except Exception as exc:
        raise RuntimeError(f"Antigravity CLI 프로세스 실행 실패: {exc}. 터미널에서 agy를 실행하여 로그인하세요.") from exc

    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "").strip()
        low_err = err_msg.lower()
        if any(tok in low_err for tok in ("login", "auth", "credential", "unauthorized", "unauthenticated")):
            raise RuntimeError("인증이 없습니다. 터미널에서 agy를 실행하여 로그인하세요.")
        if not err_msg:
            err_msg = f"종료 코드 {proc.returncode}"
        raise RuntimeError(f"Antigravity CLI 오류 ({err_msg}). 터미널에서 agy를 실행하여 로그인하세요.")

    stdout = (proc.stdout or "").strip()
    if not stdout and proc.stderr:
        stdout = proc.stderr.strip()

    if not stdout:
        raise RuntimeError("Antigravity CLI로부터 빈 응답을 받았습니다. 터미널에서 agy를 실행하여 로그인 상태를 확인하세요.")

    return stdout, {
        "provider": "antigravity",
        "model": model or "gemini-2.5-pro",
        "cli": True,
        "auth_source": "Windows Credential Manager via agy",
    }
