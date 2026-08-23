"""Yang Wen-li inspired strategic critic. Overlay only. No character quotes, no orders."""

from __future__ import annotations

from typing import Any

from kr_quant.context.explain import clean_reason_list

POSTURE_KO = {
    "ENGAGE": "착수",
    "WAIT": "대기",
    "OBSERVE": "관찰",
    "RETREAT": "후퇴",
    "AVOID": "회피",
}

POSTURE_HINT = {
    "ENGAGE": "전장 조건은 맞습니다. 그래도 영웅이 될 필요는 없고, 조사 우선순위만 올리죠. 주문은 아닙니다.",
    "WAIT": "회사는 괜찮아 보여도, 오늘은 싸울 날이 아닙니다. 살아서 차나 마시는 쪽이 이깁니다.",
    "OBSERVE": "관심은 갑니다만, 정보가 부족한 채로 움직이는 쪽이 더 위험합니다.",
    "RETREAT": "이기고 싶은 마음보다, 질 이유가 더 잘 보입니다. 물러나는 것도 전략입니다.",
    "AVOID": "法이 안 되면 착수할 일이 아닙니다. 그런 싸움은 사양하죠.",
}

ASPECT_YANG = [
    {
        "id": "dao",
        "han": "道",
        "ko": "정렬",
        "sunzi": "위와 아래가 같은 뜻을 품는가. 말·실적·현금이 한 방향인가.",
        "yang": "멋진 전략보다, 현금이 고개를 끄덕이는지가 중요합니다.",
    },
    {
        "id": "tian",
        "han": "天",
        "ko": "시장",
        "sunzi": "하늘(시기·국면)이 이 싸움을 허용하는가.",
        "yang": "좋은 장수도 궂은 날씨엔 출진하지 않습니다. 오늘은 天부터 보죠.",
    },
    {
        "id": "di",
        "han": "地",
        "ko": "업종",
        "sunzi": "지형(업종·경쟁)이 유리한가.",
        "yang": "혼자서 잘난 종목보다, 서 있는 땅이 먼저입니다.",
    },
    {
        "id": "jiang",
        "han": "將",
        "ko": "자본배분",
        "sunzi": "장수(경영)가 약속을 성과와 규율로 바꾸는가.",
        "yang": "용맹한 말보다, 돈을 어디에 쓰는지가 장수의 실력입니다.",
    },
    {
        "id": "fa",
        "han": "法",
        "ko": "규율",
        "sunzi": "법도(데이터·리스크·공시)가 이 후보를 믿을 만큼 단단한가.",
        "yang": "숫자가 예뻐도 장부가 흔들리면, 그 전쟁은 시작하지 않습니다.",
    },
]


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
    consensus = "시장이 이미 아는 이야기는 실적·국면·업종 점수에 많이 들어가 있습니다. 그걸 또 찬양할 필요는 없죠."
    variant = "NO_CLEAR_VARIANT_VIEW"
    if value >= 20 and growth < 14:
        variant = "싸 보입니다. 싸 보이는 데는 보통 이유가 있습니다."
    elif growth >= 20 and value < 14:
        variant = "성장은 보이지만, 그 미래는 이미 가격이 먼저 알고 있을 수 있습니다."
    elif posture == "WAIT" and dao_s >= 60:
        variant = "회사 숫자는 괜찮은데, 전장(天·地)이 등을 돌렸습니다. 오늘은 관망이 이깁니다."
    elif posture == "ENGAGE":
        variant = "전장과 규율이 같이 맞으면 조사 우선순위만 올립니다. 출진 명령은 아닙니다."
    return {
        "used_in_quant": False,
        "id": "critic",
        "label": "양웬리의 해석",
        "score": score,
        "posture": posture,
        "posture_ko": POSTURE_KO[posture],
        "no_action_required": no_action,
        "axes": axes,
        "consensus": consensus,
        "variant": variant,
        "comment": POSTURE_HINT[posture],
        "disclaimer": (
            "손자가 전장 조건을 세면, 양웬리는 그걸 ‘이 싸움이 필요한가’로 번역합니다. "
            "원작 대사를 쓰지 않으며 Quant와 합산하지 않고 주문이 아닙니다."
        ),
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    vals: list[float] = []
    for row in rows:
        num = _num(row.get(key))
        if num is not None:
            vals.append(num)
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def compose_yang_briefing(
    tian: dict[str, Any] | None,
    postures: dict[str, int] | None,
    n: int,
    fa_pass_n: int,
    aspect_scores: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Board-level briefing: Sunzi counts the field, Yang interprets whether to fight."""
    tian = tian or {}
    postures = postures or {}
    scores = aspect_scores or {}
    regime = str(tian.get("regime_ko") or "미산정")
    tian_s = _num(tian.get("score"))
    wait_n = int(postures.get("WAIT") or 0)
    engage_n = int(postures.get("ENGAGE") or 0)
    avoid_n = int(postures.get("AVOID") or 0)
    observe_n = int(postures.get("OBSERVE") or 0)
    retreat_n = int(postures.get("RETREAT") or 0)
    dao_s = _num(scores.get("dao"))
    fa_s = _num(scores.get("fa"))

    sunzi_line = (
        f"손자의 집계입니다. 天은 ‘{regime}’"
        + (f" {tian_s:.0f}점" if tian_s is not None else "")
        + f", 法 통과 {fa_pass_n}/{n}종목"
        + (f", 道 평균 {dao_s:.0f}점" if dao_s is not None else "")
        + "."
    )
    if str(tian.get("regime") or "") == "RISK_OFF" or (tian_s is not None and tian_s < 45):
        yang_line = (
            "양웬리의 해석은 단순합니다. 전장이 등을 돌린 날에는 좋은 회사도 좋은 싸움이 아닙니다. "
            f"오늘 명단 {n}종목 중 대기가 {wait_n}입니다. 영웅이 되고 싶은 마음은 접고, 살아남는 쪽을 고르죠."
        )
    elif engage_n > 0 and engage_n >= wait_n:
        yang_line = (
            f"조건이 맞아 착수가 {engage_n}종목입니다. 그래도 출진 명령은 아닙니다. "
            "조사 우선순위만 올리고, 차는 식기 전에 마시죠."
        )
    elif avoid_n >= max(1, n // 4):
        yang_line = (
            f"法이 안 되는 후보가 {avoid_n}종목입니다. 숫자가 예뻐도 장부가 흔들리면 그 전쟁은 시작하지 않습니다."
        )
    elif observe_n + retreat_n >= wait_n:
        yang_line = (
            "관심은 가지만 확신이 없습니다. 정보가 부족한 채로 움직이는 쪽이, 가만히 있는 것보다 위험할 수 있습니다."
        )
    else:
        yang_line = (
            f"회사 숫자는 남아 있어도 오늘은 싸울 날이 아닙니다. 대기 {wait_n}종목. "
            "이기고 지는 것보다, 안 싸워도 되는 싸움을 피하는 게 낫습니다."
        )
    if fa_s is not None and fa_s >= 80 and (tian_s is not None and tian_s < 45):
        yang_line += " 규율은 통과했는데 하늘이 허락하지 않는 전형적인 날입니다."
    return {
        "title": "양웬리의 오늘 브리핑",
        "sunzi_line": sunzi_line,
        "yang_line": yang_line,
        "voice": "손자가 전장을 세고, 양웬리가 그걸 해석합니다.",
    }
