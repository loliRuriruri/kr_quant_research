"""Investor-type normalization. Overlay only. Do not alias FUND to 연기금/국민연금."""

from __future__ import annotations

from typing import Any

# Canonical codes. Display names stay close to the source label.
CANONICAL: dict[str, dict[str, Any]] = {
    "FOREIGN": {
        "ko": "외국인",
        "aliases": ("frgn", "foreign", "foreigner", "외국인", "frgn_ntby", "frgn_ntby_qty"),
    },
    "INDIVIDUAL": {
        "ko": "개인",
        "aliases": ("prsn", "individual", "retail", "개인", "prsn_ntby", "prsn_ntby_qty"),
    },
    "INSTITUTION_TOTAL": {
        "ko": "기관합계",
        "aliases": ("orgn", "institution", "orgn_ntby", "orgn_ntby_qty", "기관계", "기관합계", "기관"),
    },
    "FUND": {
        "ko": "기금",
        "aliases": ("fund", "fund_ntby", "fund_ntby_qty", "기금"),
        "note": "원천이 연기금·국민연금을 명시하지 않으면 그 이름으로 부르지 않습니다.",
    },
}

ALIAS_TO_CANON = {
    alias.lower(): code
    for code, spec in CANONICAL.items()
    for alias in spec["aliases"]
}


def normalize_investor_type(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.upper() in CANONICAL:
        return text.upper()
    return ALIAS_TO_CANON.get(text.lower()) or ALIAS_TO_CANON.get(text.lower().replace(" ", ""))


def display_name(code: str | None) -> str:
    if not code:
        return "미분류"
    spec = CANONICAL.get(str(code).upper())
    return str(spec["ko"]) if spec else str(code)


def source_note(code: str | None) -> str:
    spec = CANONICAL.get(str(code or "").upper()) or {}
    return str(spec.get("note") or "")
