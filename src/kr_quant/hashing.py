from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(
        _normalize(obj),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def canonicalize_yaml_text(text: str) -> str:
    loaded = yaml.safe_load(text)
    return canonical_json(loaded)


def hash_config_files(paths: Iterable[Path]) -> str:
    payload: dict[str, str] = {}
    for path in sorted(paths, key=lambda p: p.as_posix()):
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            payload[path.name] = canonicalize_yaml_text(text)
        else:
            payload[path.name] = sha256_bytes(text.encode("utf-8"))
    return sha256_json(payload)


def source_bundle_hash(file_hashes: dict[str, str]) -> str:
    return sha256_json({k: file_hashes[k] for k in sorted(file_hashes)})


def _normalize(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return round(obj, 12)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    return str(obj)
