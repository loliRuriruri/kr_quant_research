from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GROK_BIN = Path.home() / ".grok" / "bin" / "grok.exe"
AUTH_PATH = Path.home() / ".grok" / "auth.json"

_URL_RE = re.compile(r"https://[^\s)>\]]+")
_CODE_LABEL_RE = re.compile(
    r"(?:Then enter this code|Confirm this code in your browser|enter this code|user code)\s*:?\s*([A-Z0-9][A-Z0-9-]{3,})",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"\b([A-Z0-9]{4,8}(?:-[A-Z0-9]{3,8}){1,3})\b")

_lock = threading.Lock()
_connect_state: dict[str, Any] = {
    "status": "idle",
    "error": None,
    "started_at": None,
    "verification_url": None,
    "user_code": None,
    "detail": None,
}


def grok_cli() -> Path | None:
    if GROK_BIN.exists():
        return GROK_BIN
    which = subprocess.run(["where", "grok"], capture_output=True, text=True, timeout=8)
    if which.returncode == 0:
        line = (which.stdout or "").splitlines()
        if line:
            return Path(line[0].strip())
    return None


def _parse_expiry(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            return _parse_expiry(int(text))
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _entries() -> list[dict[str, Any]]:
    if not AUTH_PATH.exists():
        return []
    try:
        data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out = []
    for _id, body in data.items():
        if isinstance(body, dict) and (body.get("key") or body.get("access_token")):
            out.append(body)
    return out


def session_status() -> dict[str, Any]:
    rows = _entries()
    if not rows:
        return {
            "connected": False,
            "email": None,
            "expires_at": None,
            "expired": True,
            "cli": bool(grok_cli()),
            "auth_file": AUTH_PATH.exists(),
        }
    row = rows[0]
    exp = _parse_expiry(row.get("expires_at") or row.get("expiry") or row.get("expires_in"))
    now = datetime.now(timezone.utc)
    expired = bool(exp and exp <= now)
    return {
        "connected": not expired,
        "email": row.get("email"),
        "expires_at": exp.isoformat() if exp else None,
        "expired": expired,
        "cli": bool(grok_cli()),
        "auth_file": True,
        "auth_mode": row.get("auth_mode"),
    }


def load_session_token() -> str | None:
    """Return the stored Grok session token. Never log this value."""
    for row in _entries():
        token = row.get("key") or row.get("access_token")
        if not token:
            continue
        exp = _parse_expiry(row.get("expires_at") or row.get("expiry"))
        if exp and exp <= datetime.now(timezone.utc):
            continue
        return str(token)
    return None


def connect_state() -> dict[str, Any]:
    with _lock:
        return {**_connect_state, "session": session_status()}


def parse_login_output(text: str) -> dict[str, str | None]:
    """Pull the public device-code URL/code. Never return tokens."""
    urls = _URL_RE.findall(text or "")
    verification_url = None
    for url in urls:
        cleaned = url.rstrip(".,;\"'")
        if any(part in cleaned.lower() for part in ("device", "activate", "verify", "auth.x.ai", "accounts.x.ai")):
            verification_url = cleaned
            break
    if not verification_url and urls:
        verification_url = urls[0].rstrip(".,;\"'")
    user_code = None
    labeled = _CODE_LABEL_RE.search(text or "")
    if labeled:
        user_code = labeled.group(1).strip().rstrip(".,")
    if not user_code:
        for match in _CODE_RE.finditer(text or ""):
            candidate = match.group(1)
            if "http" in candidate.lower():
                continue
            user_code = candidate
            break
    detail = None
    if "Waiting for authorization" in (text or ""):
        detail = "브라우저에서 승인 대기 중"
    elif "Authorization denied" in (text or ""):
        detail = "브라우저에서 요청을 거절했습니다"
    elif "Device code expired" in (text or ""):
        detail = "승인 코드가 만료되었습니다. 다시 연결하세요"
    return {"verification_url": verification_url, "user_code": user_code, "detail": detail}


def _safe_cli_error(text: str) -> str:
    cleaned: list[str] = []
    for line in (text or "").splitlines():
        if re.search(r"eyJ[A-Za-z0-9_-]{20,}", line):
            continue
        if re.search(r"\b(access_token|refresh_token|id_token|bearer)\b", line, re.I):
            continue
        if len(line) > 240:
            continue
        cleaned.append(line.strip())
    msg = " ".join(x for x in cleaned if x)
    return (msg or "login failed")[:400]


def start_connect(*, force: bool = False) -> dict[str, Any]:
    cli = grok_cli()
    if not cli:
        raise RuntimeError("이 PC에서 grok.exe를 찾지 못했습니다. Grok 앱이 설치되어 있어야 연결할 수 있습니다.")
    if not force and session_status().get("connected"):
        return {"already": True, **connect_state()}
    with _lock:
        if _connect_state["status"] == "running":
            return connect_state()
        _connect_state.update(
            {
                "status": "running",
                "error": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "verification_url": None,
                "user_code": None,
                "detail": "승인 코드를 받는 중",
            }
        )
    thread = threading.Thread(target=_run_login, args=(cli,), daemon=True)
    thread.start()
    return connect_state()


def _run_login(cli: Path) -> None:
    proc: subprocess.Popen[str] | None = None
    opened = False
    timer: threading.Timer | None = None
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            [str(cli), "login", "--device-auth"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
            creationflags=creationflags,
        )

        def _kill_after_timeout() -> None:
            if proc and proc.poll() is None:
                proc.kill()

        timer = threading.Timer(300, _kill_after_timeout)
        timer.daemon = True
        timer.start()
        chunks: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            parsed = parse_login_output("".join(chunks))
            with _lock:
                if parsed.get("verification_url"):
                    _connect_state["verification_url"] = parsed["verification_url"]
                if parsed.get("user_code"):
                    _connect_state["user_code"] = parsed["user_code"]
                if parsed.get("detail"):
                    _connect_state["detail"] = parsed["detail"]
            url = parsed.get("verification_url")
            if url and not opened:
                opened = True
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
        if timer:
            timer.cancel()
        rc = proc.wait()
        ok = rc == 0 and session_status()["connected"]
        with _lock:
            _connect_state["status"] = "success" if ok else "error"
            if not ok:
                _connect_state["error"] = _safe_cli_error("".join(chunks)) or f"login failed (exit {rc})"
                if not _connect_state.get("detail"):
                    _connect_state["detail"] = "브라우저에서 승인이 끝나지 않았습니다"
    except subprocess.TimeoutExpired:
        if timer:
            timer.cancel()
        if proc:
            proc.kill()
        with _lock:
            _connect_state["status"] = "error"
            _connect_state["error"] = "로그인 시간이 초과되었습니다. 브라우저에서 승인한 뒤 다시 시도하세요."
    except Exception as exc:  # noqa: BLE001
        if timer:
            timer.cancel()
        if proc and proc.poll() is None:
            proc.kill()
        with _lock:
            _connect_state["status"] = "error"
            _connect_state["error"] = str(exc)[:400]
