from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Callable
from uuid import uuid4

from kr_quant.hashing import sha256_json


TIER1_CONTRACT_VERSION = "tier1_briefing_v1.0.0"
TIER1_CACHE_VERSION = "tier1_data_hash_cache_v2_analysis"

ANALYSIS_GUIDANCE = """출력 JSON 필드와 길이 제한은 유지하세요. 메뉴 사용법 대신 제공된 결과를 분석하세요.
요약의 첫 문장은 현재 결론, 다음 문장은 그 결론을 지지하거나 반박하는 실제 수치·대상·기준일입니다.
가능하면 가장 강한 근거와 충돌하는 근거를 비교하고, 다음 확인 항목을 구체적으로 하나 제시하세요.
자료가 없으면 어떤 판단이 불가능한지 한 번만 밝히세요. 같은 면책 문구를 각 필드에 반복하지 마세요.
과거 관측과 올해 확인 사실, 업종 가설을 구분하세요. 뉴스 제목만으로 사건의 원인·실적 효과를 확정하지 마세요.
없는 수치·인과관계·목표가·매매 지시를 만들지 말고, 기존 계산 점수와 순위를 바꾸지 마세요."""


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
        **payload,
        "ok": True,
        "status": "GENERATED",
        "ai_generated": True,
        "used_in_quant": False,
        "provider": getattr(endpoint, "provider", None),
        "model": getattr(endpoint, "model", None),
        "tier": "무료 AI 해석" if str(getattr(endpoint, "model", "")).endswith(":free") else "승인된 AI 해석",
        "contract_version": TIER1_CONTRACT_VERSION,
        "prompt_version": prompt_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence": _evidence_payload(
            as_of=as_of,
            sources=sources,
            evidence_count=evidence_count,
            missing=missing,
        ),
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
    if getattr(endpoint, "provider", None) == "tier1_unavailable":
        code = "TIER1_FREE_ROUTE_NOT_CONFIGURED"
        message = "무료 AI 연결이 없습니다. 유료 자동 전환은 차단되어 있으며 원본 계산 결과는 그대로 사용할 수 있습니다."
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
        **payload,
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
    payload_validator: Callable[[dict[str, Any]], None] | None = None,
    fallback_endpoint: Any = None,
    wall_timeout: float | None = None,
    allow_fallback: bool = True,
    routine_endpoint: Any = None,
    analysis_pro_endpoint: Any = None,
) -> dict[str, Any]:
    """Generate a JSON briefing once per exact source snapshot.

    Only successful AI generations are persisted. A provider failure is returned
    as UNAVAILABLE so a later request can retry instead of replaying a failure.
    """
    if allow_fallback:
        from kr_quant.research.approved_season_ai import policy
        cfg = policy(cache_root)
        if fallback_endpoint is None and cfg.get("grok_fallback_enabled") is True:
            try:
                from kr_quant.research.providers import resolve_tier1_analysis_endpoint
                from kr_quant.settings import load_settings
                candidate = resolve_tier1_analysis_endpoint(load_settings())
                if getattr(candidate, "configured", False) and getattr(candidate, "provider", "") != "tier1_unavailable":
                    fallback_endpoint = candidate
            except Exception:  # noqa: BLE001
                fallback_endpoint = None
        if fallback_endpoint is not None or cfg.get("routine_paid_enabled") is True:
            from kr_quant.research.approved_season_ai import approved_briefing
            return approved_briefing(cache_root, endpoint, fallback_endpoint,
                namespace=namespace, prompt_version=prompt_version, evidence=evidence,
                messages=messages, as_of=as_of, sources=sources, evidence_count=evidence_count,
                missing=missing, payload_prefix=payload_prefix, payload_validator=payload_validator,
                routine_endpoint=routine_endpoint, analysis_pro_endpoint=analysis_pro_endpoint)
    identity = tier1_cache_identity(
        endpoint,
        namespace=namespace,
        prompt_version=prompt_version,
        evidence=evidence,
    )
    cache_dir = Path(cache_root) / "data" / "cache" / "tier1_briefings"
    cache_path = cache_dir / f"{_cache_namespace(namespace)}_{identity['cache_key'][:24]}.json"
    cached = _read_generated_cache(cache_path, identity)
    if cached is not None and payload_validator is not None:
        try:
            payload_validator(cached)
        except ValueError:
            cached = None
    if cached is not None:
        return cached

    try:
        from kr_quant.research.analyze import _extract_json, call_chat

        analytical_messages = [{"role": "system", "content": ANALYSIS_GUIDANCE}, *messages]
        if wall_timeout is None:
            raw_text, _ = call_chat(endpoint, analytical_messages, timeout=timeout, json_mode=True)
        else:
            from kr_quant.research.approved_season_ai import bounded_chat
            raw_text, _ = bounded_chat(endpoint, analytical_messages, timeout, wall_timeout)
        payload = {**(payload_prefix or {}), **_extract_json(raw_text)}
        if payload_validator is not None:
            payload_validator(payload)
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
