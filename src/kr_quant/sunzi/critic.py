"""Yang Wen-li inspired strategic critic. Overlay only. No character quotes, no orders."""

from __future__ import annotations

from typing import Any

POSTURE_KO = {
    "ENGAGE": "착수",
    "WAIT": "대기",
    "OBSERVE": "관찰",
    "RETREAT": "후퇴",
    "AVOID": "회피",
}

POSTURE_HINT = {
    "ENGAGE": "연구 우선순위가 비교적 높습니다. 매수가 아닙니다.",
    "WAIT": "논리는 남아 있어도 지금 위험을 질 이유는 약합니다.",
    "OBSERVE": "관심은 가지만 정보가 더 필요합니다.",
    "RETREAT": "보상 대비 위험이 나빠진 쪽으로 읽습니다.",
    "AVOID": "法 미달이나 구조적 흠이 있어 착수하지 않습니다.",
}


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
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    text = str(raw or "")
    return [p for p in text.replace("|", ",").split(",") if p and p not in {"[]", "None"}]


def _part(parts: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(parts, dict):
        return {}
    item = parts.get(key)
    return item if isinstance(item, dict) else {}


def critic_panel(row: dict[str, Any], parts: dict[str, Any] | None = None) -> dict[str, Any]:
    fa = _part(parts, "fa")
    dao = _part(parts, "dao")
    tian = _part(parts, "tian")
    di = _part(parts, "di")
    jiang = _part(parts, "jiang")
    fa_pass = fa.get("fa_gate_pass")
    if fa_pass is None:
        fa_pass = row.get("fa_gate_pass")
    flags = _flags(row.get("risk_flags"))
    stab = _num(row.get("financial_score")) or 0.0
    value = _num(row.get("value_score")) or 0.0
    growth = _num(row.get("growth_score")) or 0.0
    pen = _num(row.get("risk_penalty")) or 0.0
    fcf = _num(row.get("fcf_yield"))
    conf = _num(row.get("data_confidence"))
    cap = _clip(stab * 10)
    if any(x in flags for x in ("LEVERAGE_STRESS", "THIN_EQUITY", "NEGATIVE_EQUITY")):
        cap = min(cap, 25.0)
    if any(x in flags for x in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")):
        cap = min(cap, 30.0)
    payoff = _clip(value / 30.0 * 100.0 - pen * 4)
    option = 55.0
    if fcf is not None:
        option = 75.0 if fcf > 0.04 else 60.0 if fcf > 0 else 30.0
    situ = []
    for panel in (tian, di):
        sc = _num(panel.get("score"))
        if sc is not None:
            situ.append(sc)
    situational = _clip(sum(situ) / len(situ)) if situ else 50.0
    evidence = _num(dao.get("score")) or 50.0
    contrary_n = len(dao.get("contrary") or []) + len(jiang.get("contrary") or [])
    adversarial = _clip(100.0 - contrary_n * 18.0)
    axes = {
        "capital_preservation": round(cap, 1),
        "asymmetric_payoff": round(payoff, 1),
        "optionality": round(_clip(option), 1),
        "situational_advantage": round(situational, 1),
        "evidence_strength": round(_clip(evidence), 1),
        "adversarial_robustness": round(adversarial, 1),
    }
    score = round(sum(axes.values()) / 6.0, 1)
    regime = str(tian.get("regime") or "")
    di_state = str(di.get("state_ko") or "")
    dao_s = _num(dao.get("score")) or 50.0
    if fa_pass is False:
        posture = "AVOID"
    elif conf is not None and conf < 70:
        posture = "OBSERVE"
    elif contrary_n >= 3 or (dao_s < 40 and cap < 40):
        posture = "RETREAT"
    elif regime == "RISK_OFF" or di_state in {"부진", "약화"}:
        posture = "WAIT"
    elif fa_pass is True and dao_s >= 65 and (_num(jiang.get("score")) or 0) >= 55 and regime != "RISK_OFF":
        posture = "ENGAGE"
    else:
        posture = "OBSERVE"
    no_action = posture in {"WAIT", "OBSERVE", "RETREAT", "AVOID"}
    consensus = "시장이 이미 아는 이야기는 실적·국면·업종 점수에 많이 들어가 있습니다."
    variant = "NO_CLEAR_VARIANT_VIEW"
    if value >= 20 and growth < 14:
        variant = "숫자는 싼데 성장 점수는 약합니다. 싼 이유가 남아 있을 수 있습니다."
    elif growth >= 20 and value < 14:
        variant = "성장은 보이지만 가치 점수가 낮아 기대가 가격에 많이 들어 있을 수 있습니다."
    elif posture == "WAIT" and dao_s >= 60:
        variant = "회사 숫자는 괜찮은데 전장(天·地)이 불리해 지금은 관망이 낫습니다."
    elif posture == "ENGAGE":
        variant = "전장과 규율이 같이 맞으면 조사 우선순위를 올립니다. 주문은 아닙니다."
    return {
        "used_in_quant": False,
        "id": "critic",
        "label": "전략 검토",
        "score": score,
        "posture": posture,
        "posture_ko": POSTURE_KO[posture],
        "no_action_required": no_action,
        "axes": axes,
        "consensus": consensus,
        "variant": variant,
        "comment": POSTURE_HINT[posture],
        "disclaimer": (
            "손자 전장 조건 위에 불필요한 싸움을 피하는 쪽의 반대심문입니다. "
            "은하영웅전설 대사를 쓰지 않으며 Quant와 합산하지 않고 주문이 아닙니다."
        ),
    }
