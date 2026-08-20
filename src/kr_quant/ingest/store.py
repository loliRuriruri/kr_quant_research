from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_quant.hashing import sha256_bytes, sha256_file


def write_raw_json(
    root: Path,
    source: str,
    endpoint: str,
    fetched_date: str,
    name: str,
    payload: Any,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Append-only raw dump. Existing same-name files are versioned, never overwritten."""
    folder = root / source / f"endpoint={endpoint}" / f"fetched_date={fetched_date}"
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=None).encode("utf-8")
    digest = sha256_bytes(raw)
    path = folder / f"{name}.json"
    if path.exists():
        existing = sha256_file(path)
        if existing == digest:
            return path
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        path = folder / f"{name}.{ts}.json"
    path.write_bytes(raw)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "payload_sha256": digest,
                "endpoint": endpoint,
                **(meta or {}),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
