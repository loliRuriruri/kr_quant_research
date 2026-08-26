from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from kr_quant.hashing import sha256_json


TIER1_CONTRACT_VERSION = "tier1_briefing_v1.0.0"
TIER1_CACHE_VERSION = "tier1_data_hash_cache_v1"


def _clean_items(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in (values or []) if str(value).strip()))


def _evidence_payload(
    *,
    as_of: str | None,
    sources: Iterable[str] | None,
    evidence_count: int,
    missing: Iterable[str] | None,
) -> dict[str, Any]:
    clean_sources = _clean_items(sources)
    clean_missing = _clean_items(missing)
    count = max(0, int(evidence_count or 0))
    if count <= 0:
        coverage = "NONE"
    elif clean_missing:
        coverage = "PARTIAL"
    else:
        coverage = "SUFFICIENT"
    return {
        "as_of": as_of,
        "sources": clean_sources,
        "item_count": count,
        "missing": clean_missing,
        "coverage": coverage,
    }


def tier1_success(
    endpoint: Any,
    payload: dict[str, Any],
    *,
    as_of: str | None = None,
    sources: Iterable[str] | None = None,
    evidence_count: int = 0,
    missing: Iterable[str] | None = None,
    prompt_version: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "GENERATED",
        "ai_generated": True,
        "used_in_quant": False,
        "provider": getattr(endpoint, "provider", None),
        "model": getattr(endpoint, "model", None),
        "tier": "Tier 1 무료 설명 엔진",
        "contract_version": TIER1_CONTRACT_VERSION,
        "prompt_version": prompt_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": _evidence_payload(
            as_of=as_of,
            sources=sources,
            evidence_count=evidence_count,
            missing=missing,
        ),
        **payload,
    }


def tier1_unavailable(
    endpoint: Any,
    *,
    code: str = "TIER1_GENERATION_FAILED",
    message: str = "무료 AI 설명을 생성하지 못했습니다. 원본 계산 결과는 그대로 사용할 수 있습니다.",
    as_of: str | None = None,
    sources: Iterable[str] | None = None,
    evidence_count: int = 0,
    missing: Iterable[str] | None = None,
    prompt_version: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "UNAVAILABLE",
        "ai_generated": False,
        "used_in_quant": False,
        "provider": getattr(endpoint, "provider", None),
        "model": getattr(endpoint, "model", None),
        "tier": "Tier 1 무료 설명 엔진",
        "contract_version": TIER1_CONTRACT_VERSION,
        "prompt_version": prompt_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error_code": code,
        "message": message,
        "evidence": _evidence_payload(
            as_of=as_of,
            sources=sources,
            evidence_count=evidence_count,
            missing=missing,
        ),
    }


def tier1_deterministic_fallback(
    endpoint: Any,
    payload: dict[str, Any],
    *,
    as_of: str | None = None,
    sources: Iterable[str] | None = None,
    evidence_count: int = 0,
    missing: Iterable[str] | None = None,
    prompt_version: str,
) -> dict[str, Any]:
    """Return a calculation-only explanation without pretending AI succeeded."""
    return {
        "ok": True,
        "status": "DETERMINISTIC_FALLBACK",
        "ai_generated": False,
        "used_in_quant": False,
        "provider": getattr(endpoint, "provider", None),
        "model": getattr(endpoint, "model", None),
        "tier": "규칙 기반 대체 설명",
        "contract_version": TIER1_CONTRACT_VERSION,
        "prompt_version": prompt_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": _evidence_payload(
            as_of=as_of,
            sources=sources,
            evidence_count=evidence_count,
            missing=missing,
        ),
        **payload,
    }


def _cache_namespace(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "briefing")).strip("-.")
    return cleaned[:80] or "briefing"


def tier1_cache_identity(
    endpoint: Any,
    *,
    namespace: str,
    prompt_version: str,
    evidence: Any,
) -> dict[str, str]:
    """Build a stable identity that changes with model, prompt, or source evidence."""
    evidence_hash = sha256_json(evidence)
    cache_key = sha256_json(
        {
            "cache_version": TIER1_CACHE_VERSION,
            "contract_version": TIER1_CONTRACT_VERSION,
            "namespace": namespace,
            "provider": getattr(endpoint, "provider", None),
            "model": getattr(endpoint, "model", None),
            "prompt_version": prompt_version,
            "evidence_hash": evidence_hash,
        }
    )
    return {"evidence_hash": evidence_hash, "cache_key": cache_key}


def _read_generated_cache(path: Path, identity: dict[str, str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(cached, dict) or cached.get("status") != "GENERATED":
        return None
    cache_meta = cached.get("cache") or {}
    if cache_meta.get("key") != identity["cache_key"] or cache_meta.get("evidence_hash") != identity["evidence_hash"]:
        return None
    result = dict(cached)
    result["cache"] = {**cache_meta, "hit": True}
    return result


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def tier1_cached_chat_json(
    cache_root: Path,
    endpoint: Any,
    *,
    namespace: str,
    prompt_version: str,
    evidence: Any,
    messages: list[dict[str, str]],
    as_of: str | None = None,
    sources: Iterable[str] | None = None,
    evidence_count: int = 0,
    missing: Iterable[str] | None = None,
    timeout: int = 15,
    payload_prefix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a JSON briefing once per exact source snapshot.

    Only successful AI generations are persisted. A provider failure is returned
    as UNAVAILABLE so a later request can retry instead of replaying a failure.
    """
    identity = tier1_cache_identity(
        endpoint,
        namespace=namespace,
        prompt_version=prompt_version,
        evidence=evidence,
    )
    cache_dir = Path(cache_root) / "data" / "cache" / "tier1_briefings"
    cache_path = cache_dir / f"{_cache_namespace(namespace)}_{identity['cache_key'][:24]}.json"
    cached = _read_generated_cache(cache_path, identity)
    if cached is not None:
        return cached

    try:
        from kr_quant.research.analyze import _extract_json, call_chat

        raw_text, _ = call_chat(endpoint, messages, timeout=timeout, json_mode=True)
        payload = {**(payload_prefix or {}), **_extract_json(raw_text)}
    except Exception as exc:
        print(f"Tier 1 {namespace} briefing unavailable: {exc}")
        result = tier1_unavailable(
            endpoint,
            as_of=as_of,
            sources=sources,
            evidence_count=evidence_count,
            missing=missing,
            prompt_version=prompt_version,
        )
        result["cache"] = {
            "version": TIER1_CACHE_VERSION,
            "hit": False,
            "key": identity["cache_key"],
            "evidence_hash": identity["evidence_hash"],
            "stored": False,
        }
        return result

    result = tier1_success(
        endpoint,
        payload,
        as_of=as_of,
        sources=sources,
        evidence_count=evidence_count,
        missing=missing,
        prompt_version=prompt_version,
    )
    result["cache"] = {
        "version": TIER1_CACHE_VERSION,
        "hit": False,
        "key": identity["cache_key"],
        "evidence_hash": identity["evidence_hash"],
        "stored": True,
    }
    try:
        _write_json_atomic(cache_path, result)
    except (OSError, TypeError, ValueError) as exc:
        print(f"Tier 1 {namespace} cache write skipped: {exc}")
        result["cache"]["stored"] = False
    return result
