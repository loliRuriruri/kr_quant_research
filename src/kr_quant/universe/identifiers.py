# -*- coding: utf-8 -*-
"""Canonical ticker contract.

KRX short codes are 6 characters and may include letters (e.g. 0220W0).
Never strip letters and re-pad; that can map one security onto another.
"""
from __future__ import annotations

from typing import Any, Iterable

UNSUPPORTED_TICKER_FORMAT = "UNSUPPORTED_TICKER_FORMAT"
EMPTY_TICKER = "EMPTY_TICKER"

# Providers that only accept 6-digit numeric stock codes.
NUMERIC_ONLY_PROVIDERS = frozenset({"kis", "naver", "opendart_stock"})


def canonical_ticker(raw: Any) -> str:
    """Preserve KRX 6-character short codes, including letters.

    Digit-only values shorter than 6 are left-padded (005930).
    Toss-style A005930 is reduced to 005930.
    Excel-ish 005930.0 is reduced to 005930.
    """
    text = str(raw or "").strip().upper()
    if not text or text in {"NAN", "NONE", "NAT"}:
        return ""
    if text.endswith(".0") and text[:-2].replace(".", "").isdigit():
        text = text[:-2]
    if text.startswith("A") and len(text) == 7 and text[1:].isalnum():
        text = text[1:]
    text = "".join(ch for ch in text if ch.isalnum())
    if not text:
        return ""
    if text.isdigit():
        return text.zfill(6)
    if len(text) < 6:
        return text.zfill(6)
    if len(text) > 6:
        return text[-6:]
    return text


def is_numeric_ticker(code: Any) -> bool:
    text = canonical_ticker(code)
    return bool(text) and text.isdigit() and len(text) == 6


def provider_supports(provider: str, raw: Any) -> bool:
    code = canonical_ticker(raw)
    if not code:
        return False
    if provider.lower() in NUMERIC_ONLY_PROVIDERS:
        return code.isdigit()
    return True


def provider_symbol(provider: str, raw: Any) -> tuple[str | None, str | None]:
    """Return (symbol_for_provider, error_code).

    error_code is UNSUPPORTED_TICKER_FORMAT or EMPTY_TICKER when the
    caller must not make a network request.
    """
    code = canonical_ticker(raw)
    if not code:
        return None, EMPTY_TICKER
    kind = provider.lower().strip()
    if kind in NUMERIC_ONLY_PROVIDERS and not code.isdigit():
        return None, UNSUPPORTED_TICKER_FORMAT
    if kind == "toss":
        return (f"A{code}" if code.isdigit() else code), None
    return code, None


def canonical_map(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        code = canonical_ticker(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out
