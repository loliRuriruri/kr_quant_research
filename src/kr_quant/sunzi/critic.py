"""Strategic critic with Yang persona lock. Overlay only. First person. No character quotes, no orders."""

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

PERSONA_VERSION = "yang_interpreter_v1"

PERSONA_BANNED = (
    "양웬리라면",
    "양 웬리라면",
    "양웬리의 관점",
    "양 웬리의 관점",
    "양웬리식으로",
    "양 웬리식으로",
    "양웬리처럼",
    "양 웬리처럼",
    "이 페르소나는",
    "Strategic Critic은",
    "이 캐릭터는",
    "양웬리의 해석은",
    "양 웬리의 해석은",
)

POSTURE_HINT = {
    "ENGAGE": "조건이 꽤 잘 맞아. 완벽하진 않지만 손실을 통제할 방법은 있고, 기다린다고 훨씬 좋아질 이유도 크지 않아 보여. 연구 우선순위만 높일게. 출진 명령은 아니야.",
    "WAIT": "논리는 아직 살아 있어. 다만 지금 가격에서 굳이 먼저 위험을 떠안을 이유는 없어 보여. 기다리면 정보가 늘 테니, 서두를 필요는 없겠지.",
    "OBSERVE": "흥미롭긴 해. 그런데 아직 빈칸이 너무 많아. 좋은 이야기는 충분한데 확인된 사실이 부족하네. 다음 데이터가 나오기 전엔 관찰 쪽이 더 합리적이야.",
    "RETREAT": "처음 생각했던 전제 몇 개가 약해지고 있어. 기존 논리를 지키려고 이유를 계속 붙이는 건 좋은 습관이 아니야. 한 발 물러나서 무엇이 틀렸는지 다시 보는 편이 낫겠어.",
    "AVOID": "싸움 자체가 마음에 들지 않아. 맞아야만 살아남는 구조고, 틀렸을 때 퇴로도 좁아. 이런 건 굳이 내가 해결할 문제가 아니겠지.",
}

ONE_LINE = {
    "ENGAGE": "조건은 괜찮아. 연구 우선순위만 높일게.",
    "WAIT": "굳이 지금 들어갈 이유는 없어 보여.",
    "OBSERVE": "지금 필요한 건 확신이 아니라 확인이야.",
    "RETREAT": "전제를 다시 보는 편이 낫겠어.",
    "AVOID": "이 싸움은 내가 나설 일이 아니야.",
}

ASPECT_YANG = [
    {
        "id": "dao",
        "han": "道",
        "ko": "정렬",
        "sunzi": "말과 돈의 흐름이 같은 방향인가.",
        "yang": "말은 그럴듯해도, 결국 돈이 어디로 움직였느냐가 중요하지.",
    },
    {
        "id": "tian",
        "han": "天",
        "ko": "시장",
        "sunzi": "시간이 우리 편인가.",
        "yang": "천시는 승리조건 중 하나지, 매수 버튼은 아니야.",
    },
    {
        "id": "di",
        "han": "地",
        "ko": "업종",
        "sunzi": "싸울 장소를 우리가 고를 수 있는가.",
        "yang": "같은 싸움이라면 지형부터 고르는 편이 낫지.",
    },
    {
        "id": "jiang",
        "han": "將",
        "ko": "자본배분",
        "sunzi": "이 지휘관에게 자본을 맡겨도 되는가.",
        "yang": "계획을 발표한 것과, 그 계획으로 돈을 벌었다는 건 다른 이야기야.",
    },
    {
        "id": "fa",
        "han": "法",
        "ko": "규율",
        "sunzi": "지도와 병참을 믿을 수 있는가.",
        "yang": "좋은 작전도 지도가 틀리면 별 소용 없거든.",
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


def persona_failure_flags(*texts: str) -> list[str]:
    blob = " ".join(str(t or "") for t in texts)
    return [p for p in PERSONA_BANNED if p in blob]


def _interp_dao(dao: dict[str, Any], row: dict[str, Any]) -> str:
    s = _num(dao.get("score")) or 50.0
    fcf = _num(row.get("fcf_yield"))
    if s >= 70 and (fcf is None or fcf >= 0):
        return "말은 꽤 그럴듯해. 지금까지는 실적과 현금 방향이 크게 어긋나진 않아. 적어도 이 부분은 자기 말을 어느 정도 지키고 있어."
    if s >= 45:
        return "말과 돈이 완전히 같진 않아. FCF가 따라오지 않으면 성장이라는 표현은 조금 더 조심해서 써야겠어."
    return "연설이 멋있어도 현금이 고개를 저으면, 그 연설을 믿기 어렵지."


def _interp_tian(tian: dict[str, Any]) -> str:
    s = _num(tian.get("score"))
    regime = str(tian.get("regime_ko") or tian.get("regime") or "")
    if s is not None and s < 45:
        return f"천시가 편하진 않아. 지금은 {regime or '부담'} 쪽에 가깝고, 날씨 좋다고 전투를 시작할 필요는 없겠지."
    if s is not None and s >= 60:
        return f"천시는 나쁘지 않아. {regime or '우호'} 쪽이지만, 그 이유만으로 싸울 필요는 없어. 천시는 승리조건 중 하나지, 매수 버튼은 아니니까."
    return "시장이 극단은 아니야. 그렇다고 시간이 우리 편이라고 단정하진 않겠어."


def _interp_di(di: dict[str, Any]) -> str:
    s = _num(di.get("score")) or 50.0
    state = str(di.get("state_ko") or "")
    if s >= 65:
        return f"지형은 괜찮아. 업종이 {state or '버티고'} 있고, 혼자만 뛰는 모양새는 아니야. 같은 싸움이라면 이런 곳에서 하는 편이 낫겠지."
    if s <= 40 or state in {"부진", "약화"}:
        return f"지형이 마음에 들지 않아. {state or '약한 땅'}에서 혼자 잘난 싸움은 비싸거든."
    return "땅은 평범해. 고를 수 있다면 더 나은 언덕을 찾고 싶어."


def _interp_jiang(jiang: dict[str, Any], row: dict[str, Any]) -> str:
    s = _num(jiang.get("score")) or 50.0
    if s >= 65:
        return "지금까지는 맡긴 자본을 아주 엉뚱한 곳에 쓰진 않았어. 다만 계획을 발표한 것과 그 계획으로 돈을 벌었다는 건 다른 이야기야."
    if any(x in _flags(row.get("risk_flags")) for x in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")):
        return "지휘관이 자꾸 지분을 희석하면, 그 사람에게 자본을 맡기기 어려워. 조금 더 확인하는 편이 낫겠어."
    return "용맹한 구호보다 돈을 어디에 쓰는지가 보여야 해. 아직 그 확인이 부족해."


def _interp_fa(fa: dict[str, Any], conf: float | None) -> str:
    if fa.get("fa_gate_pass") is False:
        return "여기서는 조금 조심해야겠어. 숫자가 비거나 규율이 흔들리면, 좋은 작전도 지도가 틀린 거나 마찬가지야. 이 상태에서 확신부터 높이고 싶진 않아."
    if conf is not None and conf < 70:
        return "통과는 했어도 지도 신뢰가 높진 않아. 빈칸이 있으면 말투부터 낮추는 게 맞아."
    return "지도와 병참은 당장 무너지진 않아. 그래도 법도를 통과했다고 출진할 이유는 없지."


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
    consensus = "시장이 이미 아는 이야기는 실적·국면·업종 점수에 많이 들어가 있어. 그걸 또 찬양할 필요는 없지."
    variant = "NO_CLEAR_VARIANT_VIEW"
    if value >= 20 and growth < 14:
        variant = "싸 보여. 싸 보이는 데는 보통 이유가 있지."
    elif growth >= 20 and value < 14:
        variant = "성장은 보이지만, 그 미래는 이미 가격이 먼저 알고 있을 수 있어."
    elif posture == "WAIT" and dao_s >= 60:
        variant = "회사 숫자는 괜찮은데 전장이 등을 돌렸어. 오늘은 관망이 이득이야."
    elif posture == "ENGAGE":
        variant = "전장과 규율이 같이 맞으면 연구 우선순위만 높일게. 출진 명령은 아니야."
    sunzi_interpretation = {
        "dao": _interp_dao(dao, row),
        "tian": _interp_tian(tian),
        "di": _interp_di(di),
        "jiang": _interp_jiang(jiang, row),
        "fa": _interp_fa(fa, conf),
    }
    one_line = ONE_LINE[posture]
    comment = POSTURE_HINT[posture]
    insufficient = posture == "OBSERVE" or (conf is not None and conf < 70)
    wait_test = {
        "cost_of_waiting": "1주 기다린다고 이 후보가 사라지진 않아 보여.",
        "benefit_of_waiting": "실적이나 가격이 한 번 더 확인되면, 확신을 덜 얹어도 돼.",
    }
    if posture == "ENGAGE":
        wait_test = {
            "cost_of_waiting": "기다린다고 조건이 훨씬 좋아질 이유는 크지 않아 보여.",
            "benefit_of_waiting": "그래도 한 번 더 보면 내가 틀린 지점을 더 빨리 알 수 있지.",
        }
    bear = []
    for item in (dao.get("contrary") or [])[:2]:
        bear.append(str(item))
    for item in (jiang.get("contrary") or [])[:1]:
        bear.append(str(item))
    if not bear:
        if posture == "WAIT":
            bear.append("좋은 회사와 좋은 타이밍을 섞어 보면, 지금은 후자가 비어 있어.")
        elif posture == "AVOID":
            bear.append("규율이 흔들린 상태에서의 낙관은, 지도가 틀린 작전이야.")
        else:
            bear.append("내가 틀린 쪽은 대개 가격이 이미 알고 있는 이야기지.")
    input_conf = conf if conf is not None else 55.0
    critic_conf = round(min(input_conf, 82.0 if posture == "ENGAGE" else 70.0 if posture == "WAIT" else 60.0), 1)
    flags = persona_failure_flags(comment, one_line, consensus, variant, *sunzi_interpretation.values())
    return {
        "used_in_quant": False,
        "persona_version": PERSONA_VERSION,
        "id": "critic",
        "label": "전략검토",
        "score": score,
        "posture": posture,
        "posture_ko": POSTURE_KO[posture],
        "one_line_judgment": one_line,
        "sunzi_interpretation": sunzi_interpretation,
        "no_action_required": no_action,
        "insufficient_intelligence": insufficient,
        "confidence": critic_conf,
        "axes": axes,
        "consensus": consensus,
        "variant": variant,
        "consensus_view": consensus,
        "variant_view": variant,
        "strongest_bear_evidence": bear[:3],
        "waiting_test": wait_test,
        "comment": comment,
        "persona_failure_flags": flags,
        "disclaimer": "이 판단은 Quant와 합산하지 않아. 착수는 매수가 아니고, 내 판단도 틀릴 수 있어.",
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
    focus_name: str | None = None,
    scope: str = "quant",
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
        f"道天地將法으로 세면, 天은 ‘{regime}’"
        + (f" {tian_s:.0f}점" if tian_s is not None else "")
        + f", 法 통과 {fa_pass_n}/{n}"
        + (f", 道 평균 {dao_s:.0f}점" if dao_s is not None else "")
        + "."
    )
    if str(tian.get("regime") or "") == "RISK_OFF" or (tian_s is not None and tian_s < 45):
        yang_line = (
            "전장이 등을 돌린 날에는 좋은 회사도 좋은 싸움이 아니야. "
            f"오늘 명단 {n}개 중 대기가 {wait_n}이야. 굳이 지금 들어갈 이유는 없어 보여."
        )
    elif engage_n > 0 and engage_n >= wait_n:
        yang_line = (
            f"조건이 맞아 착수가 {engage_n}개야. 그래도 출진 명령은 아니야. "
            "연구 우선순위만 높이고, 손실을 통제할 방법부터 볼게."
        )
    elif avoid_n >= max(1, n // 4):
        yang_line = (
            f"法이 안 되는 후보가 {avoid_n}개야. 숫자가 예뻐도 지도가 흔들리면 그 전쟁은 시작하지 않는 편이 낫지."
        )
    elif observe_n + retreat_n >= wait_n:
        yang_line = (
            "관심은 가. 그런데 빈칸이 많아. 정보가 부족한 채로 움직이는 쪽이, 가만히 있는 것보다 위험할 수 있어."
        )
    else:
        yang_line = (
            f"회사 숫자는 남아 있어도 오늘은 싸울 날이 아니야. 대기 {wait_n}개. "
            "좋은 전장을 찾았다고 항상 싸워야 하는 건 아니니까."
        )
    if fa_s is not None and fa_s >= 80 and (tian_s is not None and tian_s < 45):
        yang_line += " 규율은 통과했는데 하늘이 허락하지 않는 전형적인 날이야."
    if focus_name:
        sunzi_line = f"‘{focus_name}’만 따로 세봤어. " + sunzi_line
        yang_line = f"유명해서 본 게 아니라, 싸울 이유가 있는지 확인하려고 펼쳤어. " + yang_line
    elif scope == "all":
        sunzi_line = "퀀트 상위만이 아니라 명부까지 넓혀 세봤어. " + sunzi_line
        yang_line = "숨은 이름이라고 좋은 싸움은 아니야. " + yang_line
    flags = persona_failure_flags(sunzi_line, yang_line)
    return {
        "title": "오늘 전장",
        "sunzi_line": sunzi_line,
        "yang_line": yang_line,
        "voice": "좋은 이야기보다 실제 조건부터 볼게. 내 판단도 틀릴 수 있어.",
        "persona_version": PERSONA_VERSION,
        "persona_failure_flags": flags,
    }
