"""道 / 將 research overlays. Deterministic from scored fields. Not Quant."""

from __future__ import annotations

from typing import Any

from kr_quant.context.explain import clean_reason_list


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:
        return None
    return num


def _clip(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _flags(raw: Any) -> list[str]:
    return [str(x) for x in clean_reason_list(raw) if x]


def _apply_filings(evidence: list[str], contrary: list[str], filings: list[dict[str, Any]] | None, tone_key: str) -> None:
    added = 0
    for item in filings or []:
        if not isinstance(item, dict):
            continue
        tone = item.get(tone_key)
        title = str(item.get("event_ko") or item.get("title") or "").strip()
        day = str(item.get("report_date") or "")
        if not title:
            continue
        bit = f"공시 {day} {title}".strip()
        if tone == "evidence" and bit not in evidence:
            evidence.append(bit)
            added += 1
        elif tone == "contrary" and bit not in contrary:
            contrary.append(bit)
            added += 1
        if added >= 3:
            break


def dao_panel(row: dict[str, Any], filings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Alignment: strategy vs earnings, cash, shareholders. Overlay only."""
    growth = _num(row.get("growth_score")) or 0.0
    quality = _num(row.get("quality_score")) or 0.0
    rev = _num(row.get("revenue_yoy"))
    op = _num(row.get("op_yoy"))
    fcf = _num(row.get("fcf_yield"))
    flags = _flags(row.get("risk_flags"))
    data_flags = _flags(row.get("data_flags"))
    evidence: list[str] = []
    contrary: list[str] = []
    earn = 50.0
    if rev is not None and op is not None:
        if rev > 0 and op > 0:
            earn = 80.0 + min(20.0, growth)
            evidence.append("매출·영업이익 성장이 같은 방향입니다.")
        elif rev < 0 and op < 0:
            earn = 25.0
            contrary.append("매출과 영업이익이 같이 줄었습니다.")
        else:
            earn = 45.0
            contrary.append("매출과 영업이익 방향이 어긋납니다.")
    cash = 50.0
    if fcf is not None:
        if fcf > 0.04:
            cash = 80.0
            evidence.append(f"FCF 수익률 {fcf * 100:.1f}%로 이익이 현금으로 남습니다.")
        elif fcf > 0:
            cash = 60.0
            evidence.append("FCF는 플러스입니다.")
        else:
            cash = 30.0
            contrary.append("FCF 수익률이 마이너스라 서사와 현금이 어긋날 수 있습니다.")
    share = 75.0
    if any(x in flags for x in ("DILUTION_12M_HIGH", "CB_BW_OVERHANG", "REPEATED_CB_BW")):
        share = 25.0
        contrary.append("희석·전환사채가 있어 주주 정렬이 약합니다.")
    elif "DILUTION_12M_MEDIUM" in flags:
        share = 50.0
        contrary.append("최근 1년 희석이 있습니다.")
    else:
        evidence.append("큰 희석 플래그는 없습니다.")
    if any("STALE" in x or "PIT" in x for x in data_flags + flags):
        contrary.append("공시 시점·PIT 플래그가 있어 道 근거가 약할 수 있습니다.")
    _apply_filings(evidence, contrary, filings, "dao_tone")
    industry = 55.0 + min(20.0, quality * 0.4)
    score = _clip(earn * 0.25 + cash * 0.20 + share * 0.20 + industry * 0.15 + min(100.0, quality * 3.5) * 0.20)
    conf = "B"
    if not evidence:
        conf = "C"
    if len(contrary) >= 2:
        conf = "C"
    if _num(row.get("data_confidence")) is not None and float(row["data_confidence"]) < 70:
        conf = "D"
        contrary.append("데이터 신뢰도가 낮아 道 확신을 낮춥니다.")
    return {
        "used_in_quant": False,
        "id": "dao",
        "label": "道 정렬",
        "score": round(score, 1),
        "confidence": conf,
        "evidence": evidence,
        "contrary": contrary,
        "comment": (
            "회사가 말하는 성장·현금·주주 방향이 숫자와 같은지 본 조사 점수입니다. Quant에 넣지 않습니다."
            if evidence
            else "증거가 적어 道는 참고만 하세요. Quant에 넣지 않습니다."
        ),
    }


def jiang_panel(row: dict[str, Any], filings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Management / capital allocation. Overlay only."""
    roic = _num(row.get("roic"))
    fcf = _num(row.get("fcf_yield"))
    stab = _num(row.get("financial_score")) or 0.0
    flags = _flags(row.get("risk_flags"))
    evidence: list[str] = []
    contrary: list[str] = []
    cap = 50.0
    if fcf is not None:
        cap = 75.0 if fcf > 0.03 else 40.0 if fcf > 0 else 20.0
        (evidence if fcf > 0 else contrary).append(f"FCF 수익률 {fcf * 100:.1f}%.")
    roic_s = 50.0
    if roic is not None:
        roic_s = _clip(roic * 400.0)  # 12.5% -> 50, 25% -> 100
        if roic >= 0.1:
            evidence.append(f"ROIC {roic * 100:.1f}%.")
        else:
            contrary.append(f"ROIC {roic * 100:.1f}%로 자본 효율이 낮습니다.")
    disc = 80.0
    if "LEVERAGE_STRESS" in flags or "THIN_EQUITY" in flags:
        disc = 30.0
        contrary.append("레버리지·자본 얇음 플래그가 있습니다.")
    if any(x in flags for x in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")):
        disc = min(disc, 25.0)
        contrary.append("희석·전환사채 규율이 약합니다.")
    _apply_filings(evidence, contrary, filings, "jiang_tone")
    fa = row.get("fa_gate_pass")
    elig = 80.0 if fa is True else 40.0 if fa is False else 55.0
    score = _clip(cap * 0.30 + roic_s * 0.25 + disc * 0.25 + min(100.0, stab * 10) * 0.10 + elig * 0.10)
    conf = "B" if evidence else "C"
    if len(contrary) >= 2:
        conf = "C"
    return {
        "used_in_quant": False,
        "id": "jiang",
        "label": "將 자본배분",
        "score": round(score, 1),
        "confidence": conf,
        "evidence": evidence,
        "contrary": contrary,
        "comment": "경영진 자본배분·ROIC·희석 규율을 본 조사 점수입니다. Quant 순위는 바꾸지 않습니다.",
    }
