from __future__ import annotations

import re
import unicodedata


KRX_EXCLUDED_RISK_TOKENS = (
    "관리종목",
    "투자주의환기",
    "정리매매",
    "상장폐지",
)


def normalize_krx_risk_class(value: object) -> str:
    """Normalize KRX security-section text without inventing missing status."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", "", text)


def krx_risk_class_excluded(value: object) -> bool:
    """Return True only for explicit KRX risk classifications we must hard-block."""
    normalized = normalize_krx_risk_class(value)
    return any(token in normalized for token in KRX_EXCLUDED_RISK_TOKENS)
