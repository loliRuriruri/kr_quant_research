from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ENV_KEYS = [
    "OPENDART_API_KEY",
    "KRX_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "XAI_BASE_URL",
    "CUSTOM_LLM_BASE_URL",
    "CUSTOM_LLM_API_KEY",
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "KIS_BASE_URL",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "NAVER_MAP_CLIENT_ID",
    "NAVER_MAP_CLIENT_SECRET",
    "TOSS_CLIENT_ID",
    "TOSS_CLIENT_SECRET",
    "FRED_API_KEY",
    "BOK_ECOS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "OPENDART_SLEEP_SEC",
]

KEEP = "__keep__"
LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def mask_secret(value: str | None, visible: int = 4) -> dict:
    if not value:
        return {"configured": False, "masked": "", "length": 0}
    tail = value[-visible:] if len(value) >= visible else value
    return {"configured": True, "masked": f"{'•' * 8}{tail}", "length": len(value)}


def parse_env_value(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


def quote_env_value(value: str) -> str:
    if value == "" or any(ch in value for ch in ' \t#"\'\\=+'):
        return json.dumps(value, ensure_ascii=False)
    return value


def read_env_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = LINE_RE.match(stripped)
        if not m:
            continue
        out[m.group(1)] = parse_env_value(m.group(2))
    return out


def upsert_env_file(path: Path, updates: dict[str, str | None]) -> dict[str, str]:
    """Update known keys. None means leave unchanged. Empty string clears."""
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    current = read_env_map(path)
    wanted = {k: updates[k] for k in updates if updates[k] is not None}

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        m = LINE_RE.match(line.strip()) if line.strip() and not line.strip().startswith("#") else None
        if not m:
            new_lines.append(line)
            continue
        key = m.group(1)
        if key in wanted:
            new_lines.append(f"{key}={quote_env_value(wanted[key])}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in wanted.items():
        if key not in seen:
            new_lines.append(f"{key}={quote_env_value(value)}")

    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines), encoding="utf-8")

    current.update({k: v for k, v in wanted.items()})
    return current


def apply_env_to_process(path: Path) -> None:
    load_dotenv(path, override=True)
    parsed = read_env_map(path)
    for key in ENV_KEYS:
        if key in parsed:
            if parsed[key] == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = parsed[key]
