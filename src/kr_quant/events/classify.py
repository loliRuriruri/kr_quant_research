"""DART report-name classifier. Overlay only. No Quant write."""

from __future__ import annotations

from typing import Any

EVENT_KO = {
    "BUYBACK": "자사주 취득",
    "BUYBACK_CANCELLATION": "자사주 취득 철회",
    "CB_ISSUE": "전환사채",
    "BW_ISSUE": "신주인수권부사채",
    "RIGHTS_OFFERING": "유상증자",
    "LARGE_CONTRACT": "대형 계약",
    "EARNINGS": "잠정·실적",
    "DIVIDEND": "배당",
    "AUDIT_RISK": "감사 위험",
    "MAJOR_SHAREHOLDER": "지분 변동",
    "OTHER": "기타 공시",
}

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BUYBACK_CANCELLATION", ("자기주식취득 신탁계약해지", "자기주식 취득결정 철회", "자기주식취득 철회")),
    ("BUYBACK", ("자기주식취득", "자기주식 취득", "자사주취득")),
    ("CB_ISSUE", ("전환사채권", "전환사채")),
    ("BW_ISSUE", ("신주인수권부사채",)),
    ("RIGHTS_OFFERING", ("유상증자",)),
    ("LARGE_CONTRACT", ("단일판매ㆍ공급계약", "단일판매·공급계약", "공급계약체결", "수주")),
    ("EARNINGS", ("매출액또는손익구조", "잠정실적", "영업실적")),
    ("DIVIDEND", ("현금ㆍ현물배당", "현금배당결정", "배당결정")),
    ("AUDIT_RISK", ("감사의견", "의견거절", "한정의견")),
    ("MAJOR_SHAREHOLDER", ("주식등의대량보유", "최대주주변경", "임원ㆍ주요주주")),
)


def classify_report(name: Any) -> str:
    text = str(name or "").replace(" ", "")
    if not text:
        return "OTHER"
    for code, needles in _RULES:
        if any(n.replace(" ", "") in text for n in needles):
            return code
    return "OTHER"


def classify_row(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("report_nm") or item.get("report_name") or ""
    code = classify_report(name)
    rcept = str(item.get("rcept_no") or "")
    day = str(item.get("rcept_dt") or "")
    if len(day) == 8 and day.isdigit():
        day = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    ticker = "".join(ch for ch in str(item.get("stock_code") or item.get("ticker") or "") if ch.isdigit()).zfill(6)
    if ticker == "000000":
        ticker = ""
    return {
        "used_in_quant": False,
        "event_type": code,
        "event_ko": EVENT_KO.get(code, code),
        "title": str(name),
        "report_date": day,
        "receipt_no": rcept,
        "ticker": ticker,
        "company": item.get("corp_name"),
        "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}" if rcept else None,
        "dao_tone": "contrary" if code in {"CB_ISSUE", "BW_ISSUE", "RIGHTS_OFFERING", "AUDIT_RISK"} else "evidence" if code in {"EARNINGS", "LARGE_CONTRACT", "DIVIDEND"} else None,
        "jiang_tone": "contrary" if code in {"CB_ISSUE", "BW_ISSUE", "RIGHTS_OFFERING", "AUDIT_RISK"} else "evidence" if code in {"BUYBACK"} else None,
    }
