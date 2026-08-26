from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


TIER1_CONTRACT_VERSION = "tier1_briefing_v1.0.0"


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
