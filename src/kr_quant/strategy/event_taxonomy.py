"""Versioned, conservative label taxonomy. No substring or company-name inference.

Aliases are explicit labels, not a claim to cover all KRX/KSIC classifications.
Unrecognized/ambiguous classifications intentionally produce no catalyst.
"""
from __future__ import annotations

import re
import unicodedata

MAPPING_VERSION = "normalized-domain-v2"
# Current scored-source label survey: exact aliases only. Broad KSIC groups
# (chemical, machinery, ICT etc.) deliberately do not assert an economic thesis.
DOMAIN_ALIASES = {
    "power": ("전기장비", "전기장비 제조업", "전력", "변압기", "배전", "전선", "유틸리티"),
    "semiconductor": ("반도체", "반도체 제조업", "전자부품", "전자부품 제조업", "전자부품반도체", "디스플레이", "레이저", "광학"),
    "automotive": ("자동차", "자동차부품", "자동차 및 트레일러 제조업", "자동차 신품 부품 제조업", "차량"),
    "defense": ("방산", "항공우주", "국방"),
    "healthcare": ("제약", "바이오", "의약품", "의료", "의료기기", "의료용 물질 및 의약품 제조업", "헬스케어"),
    "finance": ("은행", "금융", "금융업", "금융보험", "금융보험서비스", "보험", "보험업", "증권"),
    "battery": ("배터리", "2차전지", "이차전지", "축전지 제조업", "일차전지 및 축전지 제조업"),
    "consumer": ("화장품", "화장품 제조업", "화장품 OEM", "화장품 ODM", "유통", "소매", "소매업", "식품", "식료품", "식료품 제조업", "음식료", "음료"),
    "leisure": ("게임", "게임 소프트웨어 개발 및 공급업", "엔터테인먼트", "미디어", "콘텐츠", "여행", "레저"),
    "construction": ("건설", "건설업", "종합건설", "전문건설", "건축", "부동산", "부동산업", "인프라"),
    "transport": ("해운", "항공", "운송", "물류", "수상운송", "항공운송", "육상운송", "창고운송서비스", "운수창고", "수상 운송업", "항공 운송업"),
}
# Broad source labels can coexist with a specific label, but never assign a domain.
NEUTRAL_LABELS = ("제조업", "화학", "화학물질 및 화학제품 제조업", "화학물질 및 화학제품 제조업; 의약품 제외",
                  "소재", "금속", "알루미늄", "기타기계", "소비재", "기타", "미분류",
                  "화학물질", "정보통신", "도소매업", "전문과학기술")


def normalize_label(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if text in {"nan", "none", "nat", "null", "<na>", ""}:
        return ""
    return re.sub(r"\s+", "", text)


def classify_domain(row):
    lookup = {}
    for domain, labels in DOMAIN_ALIASES.items():
        for label in labels:
            lookup.setdefault(normalize_label(label), set()).add(domain)
    neutral = {normalize_label(x) for x in NEUTRAL_LABELS}
    fields = {k: str(row[k]).strip() if normalize_label(row.get(k)) else None
              for k in ("company", "sector", "industry")}
    matches, domains, unknown = [], set(), []
    for field in ("sector", "industry"):
        value = normalize_label(row.get(field))
        if not value or value in neutral:
            continue
        # Structured separators are considered independently; no substring matching.
        for token in re.split(r"[/|,+·]", value):
            if not token or token in neutral:
                continue
            found = lookup.get(token, set())
            if found:
                domains.update(found)
                matches.append(f"{field}:{token}")
            else:
                unknown.append(f"{field}:{token}")
    ambiguous = len(domains) > 1 or bool(domains and unknown)
    status = "AMBIGUOUS" if ambiguous else "MAPPED" if len(domains) == 1 else "UNMAPPED"
    domain = next(iter(domains)) if status == "MAPPED" else None
    return {"version": MAPPING_VERSION, "rule_id": domain, "domain": domain,
            "matched_keywords": sorted(set(matches)), "source_fields": fields,
            "ambiguity": ambiguous, "status": status, "unknown_labels": sorted(set(unknown))}
