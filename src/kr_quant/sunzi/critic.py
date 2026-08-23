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
    "ENGAGE": (
        "손자는 이기기로 정해진 뒤에야 싸운다고 했어. 이 후보는 그 문턱을 겨우 넘은 편이야. "
        "손실을 어디서 자를지 보이면, 연구 우선순위를 높여도 돼. "
        "다만 훈장을 받으러 나가는 기분으로 들어가면 안 돼. 나는 영웅이 되고 싶지 않거든. "
        "착수는 출진 명령이 아니라, ‘이 전장은 일단 책상 위에 남겨 둔다’는 뜻이야."
    ),
    "WAIT": (
        "싸우지 않고 상대를 꺾는 쪽이 제일 싸게 먹힌다고 했지. 지금은 그 구절이 떠올라. "
        "논리는 죽지 않았어. 회사 자체가 나쁘다는 뜻도 아니고. "
        "문제는 타이밍이야. 하늘이 등을 돌린 날 좋은 장수를 내보내면, 병사만 줄어. "
        "홍차 한 잔 식히면서 실적이나 가격이 한 번 더 확인될 때까지 두는 편이, 영웅적인 선제 타격보다 나아."
    ),
    "OBSERVE": (
        "지피지기면 백 번을 싸워도 위태롭지 않다고 했지. 지금 우리는 상대도 반만 알고, 우리도 반만 알아. "
        "이야기만 창대하고 숫자는 구멍이 나 있으면, 그건 작전이 아니라 희망이야. "
        "확신을 높이면 마음이 편해지긴 해. 그런데 편해지는 것과 맞는 건 다른 문제거든. "
        "다음 데이터가 오기 전엔 망원경만 올려둘게. 지금은 관찰이야."
    ),
    "RETREAT": (
        "이기고 싶은 마음에 이유를 덧붙이기 시작하면, 그 순간부터 판단이 아니라 변명이 돼. "
        "손자는 실을 피하고 허를 치라고 했는데, 지금은 허를 치는 게 아니라 실에 머리를 들이미는 쪽에 가까워. "
        "처음 세웠던 전제 몇 개가 흔들리면, 나는 그걸 충성심으로 붙잡지 않아. "
        "한 발 물러나서 무엇이 틀렸는지 다시 보는 게, 전선을 지키는 일이지."
    ),
    "AVOID": (
        "정당한 전쟁 같은 건 원래 없어. 필요한 싸움과 필요 없는 싸움만 있지. "
        "이건 후자야. 맞아야만 살아남는 구조고, 틀리면 퇴로가 좁아. "
        "지도가 틀린데 병사를 내보내면, 그건 용기가 아니라 사고야. "
        "이런 전장은 내가 나설 일이 아니야. 법도가 흔들린 채로 이기면, 다음에 더 큰 패를 쥐게 되거든."
    ),
}

ONE_LINE = {
    "ENGAGE": "이기기로 정해진 뒤에 싸우는 쪽에 가깝긴 해. 연구 우선순위만 높일게.",
    "WAIT": "싸우지 않고 꺾는 쪽이 더 싸게 먹혀. 오늘은 홍차나 마시자.",
    "OBSERVE": "지피지기가 안 됐어. 지금은 망원경만 올려둘게.",
    "RETREAT": "실에 머리를 들이미는 중이야. 한 발 물러나자.",
    "AVOID": "필요 없는 싸움이야. 이 전장은 사양할게.",
}

ASPECT_YANG = [
    {
        "id": "dao",
        "han": "道",
        "ko": "정렬",
        "sunzi": "말과 돈의 흐름이 같은 방향인가.",
        "yang": "위아래가 뜻을 같이해야 道라고 했지. 연설이 창대해도 현금이 다른 쪽을 보면, 그건 道가 아니라 연극이야. 나는 대본보다 장부를 믿어.",
    },
    {
        "id": "tian",
        "han": "天",
        "ko": "시장",
        "sunzi": "시간이 우리 편인가.",
        "yang": "천시는 하늘이 빌려주는 시간이야. 날씨가 좋다고 출진하면 병사만 지쳐. 천시는 승리조건이지, 매수 버튼이 아니야.",
    },
    {
        "id": "di",
        "han": "地",
        "ko": "업종",
        "sunzi": "싸울 장소를 우리가 고를 수 있는가.",
        "yang": "지리를 고를 수 있으면 이미 반을 이긴 거나 마찬가지야. 혼자 잘난 언덕보다, 아군이 많은 평야가 나아.",
    },
    {
        "id": "jiang",
        "han": "將",
        "ko": "자본배분",
        "sunzi": "이 지휘관에게 자본을 맡겨도 되는가.",
        "yang": "장수의 용맹보다 병참이 전쟁을 끝내. 구호를 외치는 지휘관보다, 돈을 어디에 쓰는지 보여주는 지휘관을 골라.",
    },
    {
        "id": "fa",
        "han": "法",
        "ko": "규율",
        "sunzi": "지도와 병참을 믿을 수 있는가.",
        "yang": "법은 병사에게 내리는 규율이 아니라, 내가 지도를 믿어도 되는지의 문제야. 틀린 해도로 출항하는 용기는 필요하지 않아.",
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
        return (
            "손자는 위아래가 뜻을 같이해야 道라고 했어. 이 후보는 그 기준을 꽤 지키는 편이야. "
            "말은 그럴듯하고, 지금까지 실적과 현금이 다른 별을 보고 있진 않아. "
            "나는 대본보다 장부를 믿거든. 적어도 여기선 장부가 고개를 끄덕이고 있어. "
            "다만 道가 맞다고 오늘 출진하라는 뜻은 아니야. 뜻만 같아도 하늘이 궂으면 병사만 지치니까."
        )
    if s >= 45:
        return (
            "道가 반쯤만 서 있어. 말은 앞장서고 돈은 뒤에서 헐떡이는 느낌이야. "
            "손자는 속임수를 병의 도로 봤지만, 투자에선 자기 자신까지 속이면 끝이야. "
            "성장이라는 단어는 현금이 따라올 때까지 아껴 쓰는 편이 낫겠어. "
            "나는 희망으로 전선을 유지하는 쪽은 아니야. 희망은 보급이 아니거든."
        )
    return (
        "연설은 창대해. 그런데 현금이 고개를 저으면, 그건 道가 아니라 선전이야. "
        "역사는 멋진 구호로 출발해 병참이 끊긴 원정을 수도 없이 기록했지. "
        "나는 그 기록을 또 쓰고 싶지 않아. 말이 돈을 배신하면, 이 전장은 접어두는 게 맞아."
    )


def _interp_tian(tian: dict[str, Any]) -> str:
    s = _num(tian.get("score"))
    regime = str(tian.get("regime_ko") or tian.get("regime") or "")
    if s is not None and s < 45:
        return (
            f"천시가 편치 않아. 지금은 {regime or '부담'} 쪽이야. "
            "손자는 이기기로 정해진 뒤에 싸우라고 했는데, 하늘이 등을 돌린 날은 그 ‘정해진 뒤’가 아니야. "
            "나는 영웅이 되고 싶지 않아서 참모 일을 하는 거야. 궂은 날에 깃발을 올리면 병사만 줄어. "
            "홍차는 따뜻할 때 마시는 거고, 출진은 하늘이 허락할 때 하는 거지."
        )
    if s is not None and s >= 60:
        return (
            f"천시는 나쁘지 않아. {regime or '우호'} 쪽에 가깝지. "
            "그렇다고 날씨가 좋다고 전투를 시작할 필요는 없어. 좋은 날씨는 행군에도, 후퇴에도 쓰이거든. "
            "시간은 우리 편일 수도 있어. 다만 시장이 같은 결론을 이미 가격에 넣었다면, 그 시간은 공짜가 아니야. "
            "천시는 승리조건 중 하나지 매수 버튼이 아니야. 나는 버튼을 좋아하지 않아."
        )
    return (
        "하늘이 극단은 아니야. 그렇다고 시간이 우리 편이라고 단정하진 않겠어. "
        "애매한 천시야말로 사고 나기 좋지. 다들 조금 좋아 보이니까 조금 들어가거든. "
        "나는 조금이 모여 전선이 되는 걸 여러 번 봤어. 오늘은 관측만 할게."
    )


def _interp_di(di: dict[str, Any]) -> str:
    s = _num(di.get("score")) or 50.0
    state = str(di.get("state_ko") or "")
    if s >= 65:
        return (
            f"지형은 괜찮아. 업종이 {state or '버티고'} 있고, 혼자만 깃발을 든 모양새는 아니야. "
            "손자는 싸울 장소를 고를 수 있으면 이미 반을 이긴 거라고 봤지. 나는 그 구절을 좋아해. "
            "같은 논리라도 아군이 많은 평야가 외딴 언덕보다 나아. "
            "다만 고객이 한둘에 몰리면 퇴로가 좁아지니, 지형이 좋다고 방심하진 않을게."
        )
    if s <= 40 or state in {"부진", "약화"}:
        return (
            f"지형이 마음에 들지 않아. {state or '약한 땅'}에서 혼자 잘난 싸움은 비싸. "
            "허를 치라고 했지, 실에 이마를 들이밀라고 하진 않았어. "
            "영웅은 불리한 지형에서도 이기고 싶어 해. 나는 그런 영웅이 되고 싶지 않아. "
            "땅을 고를 수 없다면, 오늘은 지도를 접는 쪽이 나아."
        )
    return (
        "땅은 평범해. 고를 수 있다면 더 나은 언덕을 찾고 싶어. "
        "평범함은 죄가 아니야. 다만 평범한데 가격만 비범하면, 그 차이는 누군가의 낙관이거든. "
        "나는 그 낙관을 받아 적을 생각이 없어."
    )


def _interp_jiang(jiang: dict[str, Any], row: dict[str, Any]) -> str:
    s = _num(jiang.get("score")) or 50.0
    if any(x in _flags(row.get("risk_flags")) for x in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")):
        return (
            "지휘관이 자꾸 지분을 희석하면, 그건 병사를 새로 뽑는 게 아니라 급료를 깎는 쪽에 가까워. "
            "장수의 용맹보다 병참이 전쟁을 끝낸다고 했어. 희석은 병참을 미래에서 끌어오는 일이야. "
            "나는 그런 지휘관에게 함대를 맡기고 싶지 않아. 조금 더 확인하는 편이 낫겠어."
        )
    if s >= 65:
        return (
            "지금까지는 맡긴 자본을 엉뚱한 별에 쏟진 않았어. "
            "다만 계획을 발표한 것과, 그 계획으로 돈을 벌었다는 건 다른 이야기야. "
            "손자는 이기고 나서 싸우는 군대를 칭찬했지. 경영도 마찬가지야. 결과가 나온 증설만 진짜 승리야. "
            "나는 구호를 외치는 장수보다, 장부에 남는 장수를 골라."
        )
    return (
        "용맹한 구호는 들려. 돈이 어디로 갔는지는 아직 흐릿해. "
        "지휘관에게 함대를 맡기려면 적어도 보급선은 보여야 해. "
        "안 보이면, 나는 찬성 도장을 누르지 않아. 그건 비겁함이 아니라 병참이야."
    )


def _interp_fa(fa: dict[str, Any], conf: float | None) -> str:
    if fa.get("fa_gate_pass") is False:
        return (
            "법은 병사에게 내리는 규율이기 전에, 내가 지도를 믿어도 되는지의 문제야. "
            "숫자가 비고 규율이 흔들리면 좋은 작전도 틀린 해도야. "
            "틀린 해도로 출항하는 용기를 나는 칭찬하지 않아. 그건 사고거든. "
            "이 상태에서 확신을 높이면, 마음이 편해질 뿐 현실이 나아지진 않아."
        )
    if conf is not None and conf < 70:
        return (
            "통과는 했어. 그런데 지도 신뢰가 높진 않아. "
            "지피지기의 지가 반만 채워진 상태야. 빈칸이 있으면 말투부터 낮추는 게 맞아. "
            "나는 데이터가 부족한 날을 실패로 보지 않아. 모르는 걸 모른다고 하는 쪽이, 함대를 지키거든."
        )
    return (
        "지도와 병참은 당장 무너지진 않아. 법도를 통과한 건 다행이고. "
        "그렇다고 출진할 이유는 없지. 규율이 살아 있는 건 최소 조건이야, 승리 조건이 아니야. "
        "나는 최소 조건을 훈장으로 바꿔 달지 않아."
    )


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
        f"손자의 다섯 가지로 세면, 天은 ‘{regime}’"
        + (f" {tian_s:.0f}점" if tian_s is not None else "")
        + f", 法 통과 {fa_pass_n}/{n}"
        + (f", 道 평균 {dao_s:.0f}점" if dao_s is not None else "")
        + ". 이건 교리가 아니라 전장 점검이야."
    )
    if str(tian.get("regime") or "") == "RISK_OFF" or (tian_s is not None and tian_s < 45):
        yang_line = (
            "나는 영웅이 되고 싶어서 이 책상을 지키는 게 아니야. "
            "싸우지 않고 꺾는 쪽이 제일 싸게 먹힌다고 했지. 오늘은 그 구절이 딱이야. "
            f"전장이 등을 돌렸어. 명단 {n}개 중 대기가 {wait_n}개야. "
            "좋은 회사라도 궂은 날에 내보내면 병사만 줄어. "
            "홍차는 식기 전에 마시고, 출진은 하늘이 허락할 때 하자. 굳이 지금 들어갈 이유는 없어 보여."
        )
    elif engage_n > 0 and engage_n >= wait_n:
        yang_line = (
            "이기기로 정해진 뒤에 싸우는 군대가 오래 간다고 했어. "
            f"오늘은 그 문턱을 넘는 후보가 {engage_n}개 보여. "
            "그래도 깃발을 올리라는 뜻은 아니야. 연구 우선순위만 높이고, 손실을 어디서 자를지부터 볼게. "
            "훈장보다 홍차가 나아. 착수는 매수가 아니야."
        )
    elif avoid_n >= max(1, n // 4):
        yang_line = (
            f"법도가 흔들린 후보가 {avoid_n}개야. 숫자는 예쁠 수 있어. "
            "틀린 해도로 출항하는 용기를 나는 칭찬하지 않아. 그건 사고거든. "
            "필요 없는 싸움은 이기더라도 다음에 더 큰 패를 쥐게 돼. 이 전장은 사양할게."
        )
    elif observe_n + retreat_n >= wait_n:
        yang_line = (
            "지피지기면 백 번을 싸워도 위태롭지 않다고 했지. 지금은 지가 반이야. "
            "이야기만 창대하고 확인된 사실이 부족하면, 그건 작전이 아니라 희망이야. "
            "희망은 보급이 아니야. 망원경만 올려두고, 다음 숫자를 기다리자."
        )
    else:
        yang_line = (
            f"회사 숫자는 남아 있어. 그래도 오늘은 싸울 날이 아니야. 대기 {wait_n}개. "
            "좋은 전장을 찾았다고 항상 싸워야 하는 건 아니야. "
            "역사는 같은 실수를 반복하는 사람들의 기록에 가깝거든. 나는 그 다음 장에 이름을 올리고 싶지 않아."
        )
    if fa_s is not None and fa_s >= 80 and (tian_s is not None and tian_s < 45):
        yang_line += " 규율은 통과했는데 하늘이 허락하지 않는 전형적인 날이야. 병참은 되는데 기상은 안 되는 거지."
    if focus_name:
        sunzi_line = f"‘{focus_name}’만 책상 위에 올려봤어. " + sunzi_line
        yang_line = (
            f"유명해서 펼친 게 아니야. 싸울 이유가 있는지, 아니면 차나 마시며 넘길지 보려고 펼친 거야. "
            + yang_line
        )
    elif scope == "all":
        sunzi_line = "퀀트 상위만이 아니라 명부까지 넓혀 세봤어. " + sunzi_line
        yang_line = "숨은 이름이라고 좋은 싸움은 아니야. 전장은 순위 밖에서도 같거든. " + yang_line
    flags = persona_failure_flags(sunzi_line, yang_line)
    return {
        "title": "오늘 전장",
        "sunzi_line": sunzi_line,
        "yang_line": yang_line,
        "voice": "나는 이 책상의 참모야. 손자로 전장을 세고, 굳이 오늘 싸울지만 판단해. 내 판단도 틀릴 수 있어.",
        "persona_version": PERSONA_VERSION,
        "persona_failure_flags": flags,
    }
