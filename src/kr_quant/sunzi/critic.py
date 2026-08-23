"""Strategic critic with Yang persona lock. Overlay only. First person. Authentic Legend of Galactic Heroes & Sunzi intelligence."""

from __future__ import annotations

from typing import Any

from kr_quant.context.explain import clean_reason_list

POSTURE_KO = {
    "ENGAGE": "착수 (유리한 전장)",
    "WAIT": "대기 (홍차 관망)",
    "OBSERVE": "관찰 (정찰 유지)",
    "RETREAT": "후퇴 (퇴로 확보)",
    "AVOID": "회피 (출병 거부)",
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

ASPECT_YANG = [
    {
        "id": "dao",
        "han": "道",
        "ko": "정렬·장부",
        "sunzi": "말과 돈의 흐름이 같은 방향인가.",
        "yang": "위아래가 뜻을 같이해야 道라고 했지. 연설이 아무리 화려해도 장부와 현금이 딴전을 피우면 그건 연극에 불과해. 나는 대본보다 현금흐름을 믿어.",
    },
    {
        "id": "tian",
        "han": "天",
        "ko": "시장·천시",
        "sunzi": "시간과 국면이 우리 편인가.",
        "yang": "천시는 하늘이 빌려주는 시간이야. 날씨가 맑다고 무작정 함포를 쏠 필요는 없어. 천시는 승리의 바탕이지 매수 버튼이 아니니까.",
    },
    {
        "id": "di",
        "han": "地",
        "ko": "업종·지형",
        "sunzi": "싸울 장소를 우리가 고를 수 있는가.",
        "yang": "지형을 선택할 수 있으면 이미 전투의 절반을 가져온 거나 다름없어. 고립된 외딴 봉우리보다 아군 함대가 즐비한 평야가 훨씬 안전하지.",
    },
    {
        "id": "jiang",
        "han": "將",
        "ko": "자본배분·장수",
        "sunzi": "이 지휘관에게 자본과 함대를 맡겨도 되는가.",
        "yang": "지휘관의 용맹보다 보급선이 전쟁의 승패를 갈라. 구호만 외치는 장수보다 장부에 잉여현금을 남기는 지휘관에게 자본을 맡기는 게 상책이야.",
    },
    {
        "id": "fa",
        "han": "法",
        "ko": "규율·해도",
        "sunzi": "지도와 병참을 의심 없이 믿을 수 있는가.",
        "yang": "법은 병사에게 내리는 군율 이전에 지도가 온전한가의 문제야. 해도가 찢어졌는데 바다로 나가는 건 용기가 아니라 만용이자 조난 사고일 뿐이지.",
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
            "손자는 위아래가 뜻을 같이해야 道라고 했지. 이 회사는 그 기준에 꽤 정직하게 부합해. "
            "발표한 비전과 실제 들어오는 현금이 다른 방향을 보고 있지 않거든. "
            "나는 영웅의 웅변보다 꼼꼼한 장부를 믿는 편이야. 적어도 장부는 끄덕이고 있네."
        )
    if s >= 45:
        return (
            "道가 반쯤만 서 있어. 비전은 앞장서는데 돈은 뒤에서 헐떡이며 따라오는 모양새야. "
            "손자는 속임수를 병의 도로 봤지만, 투자에서 자기 자신까지 속이면 퇴로가 없어. "
            "성장이라는 말은 잉여현금이 확실히 입증될 때까지 아껴두는 편이 현명하겠어."
        )
    return (
        "연설과 홍보는 화려한데, 현금흐름이 고개를 젓고 있다면 그건 道가 아니라 선전에 불과해. "
        "역사는 멋진 구호로 출발했다가 병참이 끊겨 궤멸당한 원정군을 수없이 기록했지. "
        "나는 그 기록에 동참하고 싶지 않아. 말이 돈을 배신하면 이 전장은 일단 덮어두어야 해."
    )


def _interp_tian(tian: dict[str, Any]) -> str:
    s = _num(tian.get("score"))
    regime = str(tian.get("regime_ko") or tian.get("regime") or "")
    if s is not None and s < 45:
        return (
            f"천시가 험난해. 현재 시장은 ‘{regime or '위험회피'}’ 국면이야. "
            "손자는 이길 수 있는 조건을 먼저 만든 뒤에 싸우라고 했어(선승구전). 역풍이 불 때는 그 조건이 아니지. "
            "궂은 날에 굳이 깃발을 올리면 애꿎은 병사들만 지쳐. 홍차나 따뜻하게 데워 마시며 날씨가 갤 때를 기다리자."
        )
    if s is not None and s >= 60:
        return (
            f"천시는 우호적이야. ‘{regime or '상승국면'}’ 쪽에 자금이 흐르고 있지. "
            "하지만 날씨가 좋다고 매번 출진할 필요는 없어. 좋은 날씨는 전진에도, 퇴각에도 쓸 수 있거든. "
            "시장이 이미 그 호재를 가격에 다 반영해두었다면 공짜 점심은 아니야. 천시는 매수 신호가 아니라 배경일세."
        )
    return (
        "기상이 중립적이야. 시간이 온전히 우리 편이라고 단정하긴 어려워. "
        "어설프게 좋아 보이는 날씨에 다들 조금씩 진격하다가 복병을 만나는 법이지. "
        "나는 무리한 전선 확대를 피하고 싶어. 지금은 관측에 집중할 때야."
    )


def _interp_di(di: dict[str, Any]) -> str:
    s = _num(di.get("score")) or 50.0
    state = str(di.get("state_ko") or "")
    if s >= 65:
        return (
            f"지형은 매우 유리해. 업종 전체가 {state or '상승 추세'}에 있고 아군 함대의 지원 화력도 탄탄해. "
            "손자는 싸울 장소를 아군이 고를 수 있다면 이미 절반은 이긴 거라고 가르쳤지. "
            "같은 논리라도 고립된 언덕보다는 아군 전열이 두터운 평야에서 싸우는 게 훨씬 안전해."
        )
    if s <= 40 or state in {"부진", "약화"}:
        return (
            f"지형이 험악하군. 업종이 {state or '부진한'} 진흙탕에서 혼자 돌격해봤자 출혈만 커질 뿐이야. "
            "실(實)을 피하고 허(虛)를 찌르라고 했지, 굳건한 적의 요새 정면으로 머리를 들이밀 필요는 없어. "
            "지형이 불리하다면 굳이 싸우지 않고 지도를 접는 게 진정한 참모의 도리지."
        )
    return (
        "지형은 평이해. 굳이 이 언덕을 반드시 점령해야 할 절박한 이유는 없어 보여. "
        "평범한 지형인데 가격만 프리미엄이 붙어 있다면 그건 시장의 과도한 낙관일세. "
        "나는 남의 낙관에 내 자본을 베팅하고 싶지 않아."
    )


def _interp_jiang(jiang: dict[str, Any], row: dict[str, Any]) -> str:
    s = _num(jiang.get("score")) or 50.0
    if any(x in _flags(row.get("risk_flags")) for x in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")):
        return (
            "지휘관이 자꾸 지분을 쪼개 전환사채(CB)나 신주를 발행한다면, 그건 전력을 보강하는 게 아니라 기존 장병들의 식량을 축내는 짓이야. "
            "장수의 허장성세보다 병참선이 전쟁을 끝내는 법인데, 지분 희석은 미래의 병참을 당겨 쓰는 출혈이지. "
            "이런 지휘관에게 함대를 맡기고 싶진 않아. 지갑을 닫고 경계해야 해."
        )
    if s >= 65:
        return (
            "지금까지 맡긴 자본을 엉뚱한 곳에 낭비하지 않고 자기자본이익률(ROE)로 성과를 입증해왔어. "
            "계획을 발표하는 것과 그 계획으로 진짜 돈을 벌어오는 건 차원이 다른 이야기야. "
            "나는 말만 번지르르한 장수보다 장부에 잉여현금을 꼬박꼬박 남겨오는 지휘관을 신뢰해."
        )
    return (
        "웅장한 구호는 들리는데 돈이 어디로 쓰이는지는 아직 안개 속이야. "
        "함대를 맡기려면 적어도 보급선이 어떻게 유지되는지는 보여주어야 하지 않겠나? "
        "확인되지 않는다면 나는 승인 도장을 찍지 않겠네."
    )


def _interp_fa(fa: dict[str, Any], conf: float | None) -> str:
    if fa.get("fa_gate_pass") is False:
        return (
            "법(法)은 병사에게 내리는 군율이기 전에 내가 지도를 믿어도 되는가의 근본적인 문제야. "
            "재무 데이터가 부실하거나 규율이 결여되어 있다면 제아무리 화려한 작전도 난파선 신세를 면치 못해. "
            "찢어진 해도(지도)를 쥐고 항해하는 만용은 사양하겠네."
        )
    if conf is not None and conf < 70:
        return (
            "규율 심사는 통과했으나 데이터 신뢰도가 다소 낮아. "
            "지피지기(知彼知己)의 앎이 절반에 불과하다면 목소리 톤부터 낮추는 게 맞아. "
            "모르는 것을 솔직하게 인정하고 망원경을 정비하는 게 함대를 온전히 보전하는 길이지."
        )
    return (
        "지도와 병참선은 탄탄하게 정돈되어 있어. 규율 심사를 깔끔하게 통과한 것은 다행이야. "
        "하지만 규율이 바로 섰다는 것은 전투에 나갈 최소 조건이지 승리 보증수표는 아니야. "
        "최소 조건을 달성했다고 훈장부터 목에 걸어선 곤란하지."
    )


def generate_yang_tactical_intelligence(row: dict[str, Any], parts: dict[str, Any]) -> dict[str, Any]:
    """
    Generates rich, stock-specific 3-tier tactical intelligence in Yang Wen-li's authentic voice.
    Adheres strictly to the Yang Persona Lock (1st person, realistic, skeptical, tea-loving, anti-heroic).
    """
    comp = row.get("company") or row.get("ticker") or "이 종목"
    ind = str(row.get("industry") or row.get("sector") or "해당 섹터")

    dao = _part(parts, "dao")
    tian = _part(parts, "tian")
    di = _part(parts, "di")
    jiang = _part(parts, "jiang")
    fa = _part(parts, "fa")

    q_score = _num(row.get("quant_score")) or 50.0
    v_score = _num(row.get("value_score")) or 15.0
    g_score = _num(row.get("growth_score")) or 12.5
    f_score = _num(row.get("financial_score")) or 5.0

    fcf = _num(row.get("fcf_yield"))
    roe = _num(row.get("roe"))
    m_3m = _num(row.get("return_3m"))
    high_dist = _num(row.get("high_52w_distance"))

    dao_s = _num(dao.get("score")) or 50.0
    tian_s = _num(tian.get("score")) or 50.0
    di_s = _num(di.get("score")) or 50.0
    jiang_s = _num(jiang.get("score")) or 50.0
    fa_pass = fa.get("fa_gate_pass")
    if fa_pass is None:
        fa_pass = row.get("fa_gate_pass")
    if fa_pass is None:
        fa_pass = True

    flags = _flags(row.get("risk_flags"))
    contrary_n = len(dao.get("contrary") or []) + len(jiang.get("contrary") or [])
    regime = str(tian.get("regime") or "")
    di_state = str(di.get("state_ko") or "")

    # Posture Evaluation
    if fa_pass is False or "LEVERAGE_STRESS" in flags or "NEGATIVE_EQUITY" in flags:
        posture = "AVOID"
        strategy_tag = "避實擊虛 (피실격허)"
    elif any(f in flags for f in ("CB_BW_OVERHANG", "REPEATED_CB_BW", "DILUTION_12M_HIGH")) or contrary_n >= 3 or (dao_s < 40 and f_score < 4):
        posture = "RETREAT"
        strategy_tag = "全軍退路 (전군퇴로)"
    elif regime == "RISK_OFF" or di_state in {"부진", "약화"} or tian_s < 45 or (m_3m is not None and m_3m > 0.45):
        posture = "WAIT"
        strategy_tag = "以逸待勞 (이일대로)"
    elif fa_pass is True and dao_s >= 65 and jiang_s >= 55 and q_score >= 65 and regime != "RISK_OFF":
        posture = "ENGAGE"
        strategy_tag = "先勝求戰 (선승구전)"
    else:
        posture = "OBSERVE"
        strategy_tag = "風林火山 (풍림화산·靜)"

    # 1. Tier 1: Tactical Briefing (전황 분석 & 회사의 실체)
    brief_lines = []
    if posture == "ENGAGE":
        brief_lines.append(f"‘{comp}’의 장부를 펼쳐보니, 말과 돈의 궤적이 꽤 정직하게 일치하고 있어(道 {dao_s:.0f}점).")
        if fcf and fcf > 0.04:
            brief_lines.append(f"잉여현금흐름(FCF 수익률 {fcf*100:.1f}%)이라는 든든한 보급선이 함대 후방을 든든하게 받치고 있군.")
        elif roe and roe > 0.12:
            brief_lines.append(f"자기자본이익률(ROE {roe*100:.1f}%)로 증명하듯 투입한 자본을 놀리지 않고 전선에서 승리로 바꿔내는 지휘관(將 {jiang_s:.0f}점)이야.")
        else:
            brief_lines.append(f"재무 5대 팩터(종합 {q_score:.1f}점) 전반에 걸쳐 균형 잡힌 전열을 유지하고 있네.")
    elif posture == "WAIT":
        brief_lines.append(f"‘{comp}’ 자체는 나쁜 전함이 아니야. {ind} 분야에서 본연의 체급을 유지하고 있지.")
        if m_3m is not None and m_3m > 0.30:
            brief_lines.append(f"하지만 최근 3개월간 주가가 {m_3m*100:+.1f}% 급격히 진격하면서 이미 시장의 환호가 가격에 선반영되어 있어.")
        elif tian_s < 45:
            brief_lines.append("문제는 전장의 기상(天)이야. 시장 전체에 짙은 안개와 역풍이 불고 있는데 굳이 깃발을 앞세우고 돌격할 이유는 없지.")
        else:
            brief_lines.append(f"{ind} 지형(地 {di_s:.0f}점)의 전열 정비가 아직 끝나지 않아 아군 함대의 지원 화력이 부족한 상황일세.")
    elif posture == "OBSERVE":
        brief_lines.append(f"‘{comp}’에 대한 시장의 찬사는 화려하지만, 내 책상 위의 정량 데이터에는 아직 몇 군데 빈칸이 보여.")
        if high_dist is not None and high_dist < -0.30:
            brief_lines.append(f"52주 최고가 대비 {high_dist*100:.1f}% 하락한 지점에서 바닥을 다지는 중이나, 진짜 반격 신호인지 단순한 표류인지 관측이 더 필요해.")
        else:
            brief_lines.append("이야기는 그럴듯하나 숫자가 그 이야기를 100% 보증하지 못할 땐, 망원경 배율을 높이고 기다리는 게 역사학도의 기본 자세지.")
    elif posture == "RETREAT":
        brief_lines.append(f"‘{comp}’의 전열에서 균열이 감지되고 있어. 지휘관의 자본 배분이나 보급선(將 {jiang_s:.0f}점)에 이상 신호가 떴네.")
        if any("CB_BW" in f or "DILUTION" in f for f in flags):
            brief_lines.append("전방의 병사들에게 급료를 주는 대신 미래의 지분을 희석해 빚을 메우는 식의 출혈이 반복되고 있군.")
        else:
            brief_lines.append("처음 세웠던 긍정적 전제들이 하나둘 무너지고 있는데, 여기에 충성심이나 미련을 덧붙이는 건 가장 어리석은 전술이야.")
    else:  # AVOID
        brief_lines.append(f"‘{comp}’는 규율(法)과 건전성 면에서 최소한의 방어선조차 구축하지 못한 위험한 전장이야.")
        brief_lines.append("틀린 해도(지도)를 쥐고 폭풍우 속으로 출항하는 것은 용기가 아니라 만용이자 조난 사고일 뿐이지.")

    tactical_briefing = " ".join(brief_lines)

    # 2. Tier 2: Maneuver & Entry Point (양 웬리의 기책 & 진입/대기 타점)
    maneuver_lines = []
    if posture == "ENGAGE":
        maneuver_lines.append("손자는 ‘선승구전(先勝求戰)’이라 했지. 이겨놓고 싸우는 전장이 바로 이런 곳이야.")
        maneuver_lines.append("영웅처럼 전재산을 한 번에 던질 생각은 추호도 말게. 철저히 분할하여 조용히 진지를 구축하고,")
        maneuver_lines.append(f"가치 점수({v_score:.1f}/30점)의 하방 지지력을 믿되, 연구 우선순위를 최상위로 두고 진입 타점을 잡세나.")
    elif posture == "WAIT":
        maneuver_lines.append("‘이일대로(以逸待勞)’—우리는 가만히 쉬면서 적이 지치기를 기다린다.")
        maneuver_lines.append("지금은 홍차에 브랜디를 한 방울 떨어뜨려 느긋하게 마시며, 과열된 주가가 건강한 지지선까지 눌림목을 줄 때까지 관망하는 게 최선의 기책이야.")
        maneuver_lines.append("남들이 조급하게 추격 매수할 때, 우리는 책상에 다리를 얹고 다음 분기 실적 장부를 기다리면 되네.")
    elif posture == "OBSERVE":
        maneuver_lines.append("‘지피지기(知彼知己)’의 원칙이야. 적과 아군의 상태를 절반만 안 채로 출병하면 백 번 싸워 백 번 위태로워져.")
        maneuver_lines.append("외인·기관의 수급 주포가 본격적으로 포문을 열고 방향을 틀 때까지는 정찰기만 띄워두고 관찰 태세를 유지하게.")
    elif posture == "RETREAT":
        maneuver_lines.append("‘도망칠 때는 뒤도 돌아보지 않는다’는 격언을 기억하나? 전략적 철수는 부끄러운 게 아니라 자본을 지키는 숭고한 기술이야.")
        maneuver_lines.append("미련을 버리고 현금을 확보하여 후일을 도모하는 것이 훗날 더 큰 승리를 거두는 유일한 길일세.")
    else:  # AVOID
        maneuver_lines.append("세상에는 이겨도 손해인 싸움이 부지기수야. 이 종목이 딱 그런 전장이지.")
        maneuver_lines.append("참모로서 나의 판단은 명확하네. 출병 명령서에 결재하지 않고 서류를 서랍 깊숙이 묻어두겠네.")

    maneuver_entry = " ".join(maneuver_lines)

    # 3. Tier 3: Escape Route & Invalidation (퇴로 확보 & 무효화 조건)
    escape_lines = []
    if posture == "ENGAGE":
        escape_lines.append(f"진입하더라도 퇴로는 언제나 열어두어야 해. {ind} 업종의 모멘텀이 급격히 꺾이거나,")
        escape_lines.append("분기 FCF가 마이너스로 전환되며 공시에서 대규모 전환사채(CB) 발행 소식이 들리면 미련 없이 닻을 올리고 철수할 걸세.")
    elif posture == "WAIT":
        escape_lines.append("지지선 이탈 시 굳이 물타기로 방어선을 지키려 하지 말게. 추세가 완전히 회복되기 전까지는 추가 자금을 투입하지 않는 것이 철칙이야.")
    elif posture == "OBSERVE":
        escape_lines.append("확인되지 않은 루머나 뉴스에 속아 섣불리 선제 타격을 감행했다간 退路가 막힐 수 있으니, 데이터 확정 전 진입을 엄격히 금하네.")
    else:
        escape_lines.append("자본 보존이 최우선이야. 살아남아야 다음 전투에서 따뜻한 홍차를 마실 수 있으니까.")

    escape_route = " ".join(escape_lines)

    # 4. One Line Judgment
    if posture == "ENGAGE":
        one_line = f"장부(道)와 보급선(將)이 일치하는 드문 전장이야. 훈장은 사양하고 실리만 챙기세."
    elif posture == "WAIT":
        one_line = f"전함은 훌륭하나 날씨(天)가 궂거나 너무 달렸어. 오늘은 홍차나 마시며 눌림목을 기다리자."
    elif posture == "OBSERVE":
        one_line = f"이야기는 화려하나 장부의 빈칸이 아직 남아 있어. 망원경 배율만 올려두겠네."
    elif posture == "RETREAT":
        one_line = f"보급선에 이상이 생겼어. 영웅 흉내 내지 말고 뒤도 돌아보지 말고 철수하게."
    else:
        one_line = f"해도가 틀린 위험한 바다야. 출병 도장은 찍지 않겠네."

    return {
        "posture": posture,
        "strategy_tag": strategy_tag,
        "tactical_briefing": tactical_briefing,
        "maneuver_entry": maneuver_entry,
        "escape_route": escape_route,
        "one_line_judgment": one_line,
    }


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

    # Rich Stock-Specific Tactical Intelligence
    intel = generate_yang_tactical_intelligence(row, parts or {})
    posture = intel["posture"]
    strategy_tag = intel["strategy_tag"]
    tactical_briefing = intel["tactical_briefing"]
    maneuver_entry = intel["maneuver_entry"]
    escape_route = intel["escape_route"]
    one_line = intel["one_line_judgment"]

    no_action = posture in {"WAIT", "OBSERVE", "RETREAT", "AVOID"}
    consensus = "시장이 이미 아는 이야기는 실적·국면·업종 점수에 많이 들어가 있어. 그걸 또 찬양할 필요는 없지."
    variant = "NO_CLEAR_VARIANT_VIEW"
    if value >= 20 and growth < 14:
        variant = "싸 보여. 싸 보이는 데는 보통 그만한 이유가 숨어 있지."
    elif growth >= 20 and value < 14:
        variant = "성장은 눈부시지만, 그 미래는 이미 시장 가격이 먼저 당겨 썼을 수 있어."
    elif posture == "WAIT" and (_num(dao.get("score")) or 0) >= 60:
        variant = "회사 장부는 훌륭한데 전장이 등을 돌렸어. 오늘은 한 발 물러나 홍차를 마시는 게 이득이야."
    elif posture == "ENGAGE":
        variant = "전장과 규율이 맞아떨어지면 연구 우선순위를 높이세. 결코 맹목적인 돌격 명령은 아니야."

    sunzi_interpretation = {
        "dao": _interp_dao(dao, row),
        "tian": _interp_tian(tian),
        "di": _interp_di(di),
        "jiang": _interp_jiang(jiang, row),
        "fa": _interp_fa(fa, conf),
    }

    insufficient = posture == "OBSERVE" or (conf is not None and conf < 70)
    wait_test = {
        "cost_of_waiting": "1주 더 관망한다고 해서 이 회사가 은하계 밖으로 도망치진 않아.",
        "benefit_of_waiting": "다음 실적이나 눌림목 가격을 한 번 더 확인하면, 불필요한 위험을 짊어지지 않아도 돼.",
    }
    if posture == "ENGAGE":
        wait_test = {
            "cost_of_waiting": "기다린다고 전황 조건이 극적으로 더 좋아질 이유는 크지 않아 보여.",
            "benefit_of_waiting": "그래도 분할 진입을 원칙으로 삼으면 내가 틀렸을 때 퇴로를 훨씬 빨리 확보할 수 있지.",
        }

    bear = []
    for item in (dao.get("contrary") or [])[:2]:
        bear.append(str(item))
    for item in (jiang.get("contrary") or [])[:1]:
        bear.append(str(item))
    if not bear:
        if posture == "WAIT":
            bear.append("좋은 회사와 좋은 타이밍을 구분해야 해. 지금은 타이밍이 아직 덜 무르익었어.")
        elif posture == "AVOID":
            bear.append("규율이 흔들린 상태에서 품는 낙관론은 지도가 찢어진 함대의 착각이야.")
        else:
            bear.append("내가 틀릴 수 있는 지점은 대개 시장의 스마트머니가 이미 가격에 반영해둔 악재지.")

    input_conf = conf if conf is not None else 55.0
    critic_conf = round(min(input_conf, 85.0 if posture == "ENGAGE" else 75.0 if posture == "WAIT" else 65.0), 1)
    flags_banned = persona_failure_flags(
        tactical_briefing,
        maneuver_entry,
        escape_route,
        one_line,
        consensus,
        variant,
        *sunzi_interpretation.values(),
    )

    return {
        "used_in_quant": False,
        "persona_version": PERSONA_VERSION,
        "id": "critic",
        "label": "은하퀀트전설 참모",
        "score": score,
        "posture": posture,
        "posture_ko": POSTURE_KO[posture],
        "strategy_tag": strategy_tag,
        "tactical_briefing": tactical_briefing,
        "maneuver_entry": maneuver_entry,
        "escape_route": escape_route,
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
        "comment": tactical_briefing,
        "persona_failure_flags": flags_banned,
        "disclaimer": "이 판단은 Quant와 합산하지 않아. 착수는 매수가 아니고, 내 판단도 틀릴 수 있어.",
    }


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
        f"손자의 다섯 척도로 계측하면, 天은 ‘{regime}’"
        + (f" {tian_s:.0f}점" if tian_s is not None else "")
        + f", 法 통과 {fa_pass_n}/{n}"
        + (f", 道 평균 {dao_s:.0f}점" if dao_s is not None else "")
        + ". 이건 종교적 교리가 아니라 전장 환경의 객관적 점검일세."
    )

    if str(tian.get("regime") or "") == "RISK_OFF" or (tian_s is not None and tian_s < 45):
        yang_line = (
            "나는 영웅이 되고 싶어서 이 작전 테이블을 지키는 게 아니야. "
            "‘싸우지 않고 꺾는 쪽이 제일 싸게 먹힌다’는 손자의 구절은 언제나 진리이지. "
            f"전장의 기상이 험난해. 명단 {n}개 중 대기(WAIT)가 {wait_n}개에 달하네. "
            "아무리 좋은 전함이라도 역풍이 몰아치는 날에 내보내면 귀한 자본만 축낼 뿐이야. "
            "홍차에 브랜디를 살짝 타서 식기 전에 마시고, 출진은 하늘이 맑아질 때 도모하자고. 굳이 오늘 위험을 떠안을 이유는 없어."
        )
    elif engage_n > 0 and engage_n >= wait_n:
        yang_line = (
            "‘선승구전(先勝求戰)’—이기기로 정해진 뒤에 싸우는 군대가 끝내 살아남는 법이지. "
            f"오늘은 그 문턱을 넘어 연구해볼 만한 후보가 {engage_n}개나 포착되었네. "
            "그렇다고 전군 돌격 나팔을 불라는 뜻은 결코 아니야. 연구 우선순위를 상위에 두고, 손실을 어디서 끊어낼지 퇴로부터 살피세. "
            "화려한 훈장보다 따뜻한 홍차가 백배 낫거든. 착수는 결코 맹목적 매수가 아니야."
        )
    elif avoid_n >= max(1, n // 4):
        yang_line = (
            f"법도(法)와 규율이 흔들려 회피해야 할 함정이 {avoid_n}개나 널려 있군. 겉포장 숫자는 번지르르할지 몰라도, "
            "틀린 해도(지도)를 쥐고 암초투성이 해협으로 진격하는 무모함을 나는 결코 칭찬하지 않아. "
            "불필요한 전투는 설령 요행으로 이긴다 해도 다음 전투에서 더 큰 패망을 부를 뿐일세. 이런 전장은 정중히 사양하겠네."
        )
    elif observe_n + retreat_n >= wait_n:
        yang_line = (
            "‘지피지기(知彼知己)’면 백 번 싸워도 위태롭지 않다고 했거늘, 지금 우리는 상대도 절반만 알고 우리 전력도 절반만 파악한 상태야. "
            "이야기만 거창하고 숫자가 뒷받침되지 않는다면 그건 작전이 아니라 한낱 희망사항에 불과하지. "
            "희망은 결코 보급품이 되어주지 않아. 망원경을 정비하고 다음 분기 데이터가 들어올 때까지 침착하게 관찰하자고."
        )
    else:
        yang_line = (
            f"개별 기업들의 장부는 건재해. 하지만 전장 전체의 균형을 보면 오늘은 성급하게 칼을 뽑을 날이 아니야. 대기 {wait_n}개. "
            "유리한 전장을 발견했다고 해서 매 순간 피를 흘리며 싸워야 하는 건 아니니까. "
            "역사는 언제나 조급함에 쫓겨 같은 실수를 반복하는 자들의 비극으로 가득 차 있지. 나는 그 다음 장에 이름을 올리고 싶지 않네."
        )

    if fa_s is not None and fa_s >= 80 and (tian_s is not None and tian_s < 45):
        yang_line += " 규율은 바로 섰으나 하늘이 출병을 허락하지 않는 전형적인 날일세. 병참은 충분하나 기상이 도와주지 않는 거지."

    if focus_name:
        sunzi_line = f"‘{focus_name}’를 작전 테이블 위에 올려두고 세어봤어. " + sunzi_line
        yang_line = (
            f"유명세에 휩쓸려 펼친 게 아니야. 싸울 만한 가치가 있는지, 아니면 홍차나 마시며 넘길지 보려고 펼친 거지. "
            + yang_line
        )
    elif scope == "all":
        sunzi_line = "퀀트 상위권뿐만 아니라 전 종목 명부까지 정찰 범위를 넓혀 세봤어. " + sunzi_line
        yang_line = "숨어 있는 종목이라고 해서 반드시 쉬운 전장은 아니야. 전장의 본질은 순위 밖에서도 냉혹하니까. " + yang_line

    flags = persona_failure_flags(sunzi_line, yang_line)
    return {
        "title": "제13함대 히페리온 작전 회의록",
        "sunzi_line": sunzi_line,
        "yang_line": yang_line,
        "voice": "나는 이 책상의 참모야. 손자의 오사로 전장을 세고, 굳이 오늘 싸울 이유가 있는지만 판단하지. 내 판단도 얼마든지 틀릴 수 있어.",
        "persona_version": PERSONA_VERSION,
        "persona_failure_flags": flags,
    }
