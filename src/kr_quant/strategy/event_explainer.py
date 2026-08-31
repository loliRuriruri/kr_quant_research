# -*- coding: utf-8 -*-
from __future__ import annotations

from statistics import median
from typing import Any
from kr_quant.strategy.discovery_engine import SeasonalityPattern

# Known domain event clusters database for automated matching
EVENT_KNOWLEDGE_BASE: dict[str, dict[str, Any]] = {
    # 009450 경동나비엔
    "009450": {
        "common_event": "북미 난방/HVAC 성수기 전 선주문 및 하반기 실적 기대감 형성",
        "secondary_event": "콘덴싱 온수기·보일러 북미 시장점유율 1위 및 히트펌프 신제품 론칭",
        "confidence": "HIGH",
        "failed_causes": {
            "2021": "글로벌 원자재 가격(구리·철강) 급등 및 미국 서부 해상 물류 대란으로 마진 압박",
            "2023": "미국 주택 착공 일시 둔화에 따른 재고 조정",
        },
        "invalidating_rules": "FY1 EPS Revision 하향 반전, 미국 주택 경기 급랭, RS60 < -10% 이탈",
    },
    # 441270 파인엠텍
    "441270": {
        "common_event": "삼성전자 갤럭시 Z폴드/플립 차세대 내장 힌지(Hinge) 부품 양산 공급",
        "secondary_event": "폴더블 신제품 출시 및 글로벌 출하량 확대 사이클",
        "confidence": "HIGH",
        "failed_causes": {
            "2023": "폴더블 스마트폰 초기 출시 지연 및 수율 안정화 기간 소요",
        },
        "invalidating_rules": "삼성전자 폴더블 출시 일정 연기, 힌지 이원화 경쟁 심화, 기관 순매도 지속",
    },
    # 134580 탑코미디어
    "134580": {
        "common_event": "탑툰 일본/글로벌 플랫폼 하반기 결제액 급증 및 K-콘텐츠 특수",
        "secondary_event": "하반기 연말 프로모션 및 웹툰 IP 영상화 라이선싱",
        "confidence": "HIGH",
        "failed_causes": {
            "2022": "신규 플랫폼 론칭 마케팅비 일시 급증으로 단기 적자 전환",
        },
        "invalidating_rules": "글로벌 트래픽 감소, 환율 급변(엔화 약세), 영업이익 적자 지속",
    },
    # 037070 파세코
    "037070": {
        "common_event": "여름철 창문형 에어컨 국내 1위 폭염 특수 및 겨울 석유난로 수출",
        "secondary_event": "계절 가전 성수기 진입에 따른 분기 영업이익 급증",
        "confidence": "HIGH",
        "failed_causes": {
            "2022": "긴 장마와 저온 현상으로 인한 에어컨 판매량 일시 부진",
        },
        "invalidating_rules": "초여름 장마 장기화 예보, 원자재가 상승, RS60 역배열",
    },
    # 105560 KB금융
    "105560": {
        "common_event": "하반기 고배당 선취매 유입 및 밸류업 자사주 소각 모멘텀",
        "secondary_event": "분기 균등 배당 안정성 및 외국인 패시브 자금 매수",
        "confidence": "HIGH",
        "failed_causes": {
            "2020": "금융당국 배당 제한 권고 및 대손충당금 일시 대량 적립",
        },
        "invalidating_rules": "부동산 PF 추가 부실로 인한 대손비용 급증, 배당 삭감 공시",
    },
    # 067080 대화제약
    "067080": {
        "common_event": "리포락셀(세계 최초 경구용 파클리탁셀 항암제) 중국 NMPA 승인 및 아시아 라이선스아웃 모멘텀",
        "secondary_event": "하반기 글로벌 종양학회 임상 성과 발표 및 개량신약 처방 확대",
        "confidence": "HIGH",
        "failed_causes": {
            "2022": "바이오 섹터 전반의 고금리 유동성 위축 및 임상 심사 지연",
        },
        "invalidating_rules": "중국 규제당국 허가 지연, 기술수출 계약 파기 공시, RS60 < -10% 이탈",
    },
    # 000240 한국앤컴퍼니
    "000240": {
        "common_event": "한국타이어앤테크 지분법 이익 급증 및 북미/유럽 고수익 교체용(RE) 타이어 성수기",
        "secondary_event": "차량용/산업용 납축전지(ES) 글로벌 수출 호조 및 주주환원 배당 증액",
        "confidence": "HIGH",
        "failed_causes": {
            "2023": "지배구조 분쟁 및 경영권 분쟁 소송에 따른 변동성",
        },
        "invalidating_rules": "원자재(천연고무·유가) 급등으로 인한 타이어 마진 훼손, 배당 축소",
    },
    # 006110 삼아알미늄
    "006110": {
        "common_event": "LG에너지솔루션·SK온·삼성SDI 3사 2차전지 배터리용 초극박 알루미늄박 공급 확대",
        "secondary_event": "하반기 글로벌 전기차 신차 출시 사이클 및 양극박 증설 라인 본격 가동",
        "confidence": "HIGH",
        "failed_causes": {
            "2023": "전기차 캐즘(Chasm) 우려 및 배터리사 재고 조정",
        },
        "invalidating_rules": "글로벌 배터리 고객사 증설 철회, 알루미늄 판가 급락, 기관 대량 매도",
    },
    # 011790 SKC
    "011790": {
        "common_event": "앱솔릭스(Absolics) 반도체 글라스 기판(Glass Substrate) 북미 빅테크 공급 가시화",
        "secondary_event": "하반기 AI 데이터센터 차세대 패키징 기판 양산 및 동박(SK넥실리스) 턴어라운드",
        "confidence": "HIGH",
        "failed_causes": {
            "2023": "동박 초과공급 및 화학 시황 부진 장기화",
        },
        "invalidating_rules": "글라스 기판 양산 수율 확보 실패, 동박 판가 추가 하락, 분기 적자 확대",
    },
    # 015760 한국전력
    "015760": {
        "common_event": "연말 전기요금 누적 인상 효과 및 SMP(전력도매가격) 하향 안정화로 대규모 흑자 전환",
        "secondary_event": "동절기 난방 전력 수요 급증 및 에너지공기업 재무건전성 개선",
        "confidence": "HIGH",
        "failed_causes": {
            "2022": "우크라이나 전쟁 발 국제 LNG/유가 폭등으로 사상 최대 적자 기록",
        },
        "invalidating_rules": "국제 유가 90달러 돌파, 정부 요금 동결 압박, 한전채 발행 한도 이슈",
    },
    # 017800 현대엘리베이터
    "017800": {
        "common_event": "국내외 초고층 빌딩 및 아파트 입주 마무리 분기 엘리베이터 설치 매출 집중",
        "secondary_event": "안정적 유지보수(MRO) 현금흐름 및 자사주 소각·고배당 밸류업 프로그램",
        "confidence": "HIGH",
        "failed_causes": {
            "2021": "국내 건설 분양 경기 침체 및 원자재(후판) 단가 인상",
        },
        "invalidating_rules": "국내 주택 착공 실적 급감, 경영권 분쟁 리스크 재점화",
    },
}


# A deterministic fallback is intentionally kept separate from the curated
# knowledge base.  It is used when a ticker has no manually reviewed event
# thesis, so the UI can show a useful, evidence-backed hypothesis without
# presenting a generic month label as if it were live news.
_TICKER_CATALYST_HINTS: dict[str, dict[str, str]] = {
    "161580": {
        "event": "반도체·디스플레이 장비 투자와 고객사 가동률 회복",
        "focus": "수주잔고·신규 장비 발주·고객사 CAPEX 확인",
        "risk": "고객사 CAPEX 지연 또는 장비 수주 공백",
    },
    "267260": {
        "event": "전력망·변압기 투자와 북미 수주잔고 매출 인식",
        "focus": "수주잔고 증가·납기·원자재 스프레드 확인",
        "risk": "북미 발주 지연 또는 원자재·운임 비용 상승",
    },
    "003570": {
        "event": "자동차 부품·방산 수주 및 납품 일정",
        "focus": "완성차 생산량·방산 수출 계약·납품 인식 확인",
        "risk": "자동차 생산 감소 또는 방산 수출 일정 지연",
    },
    "204270": {
        "event": "스마트폰·커버글라스 신제품 양산과 고객사 재고 보충",
        "focus": "신제품 양산 수율·고객사 주문·가동률 확인",
        "risk": "신제품 수율 저하 또는 고객사 발주 축소",
    },
}


_DOMAIN_CATALYST_RULES: tuple[dict[str, Any], ...] = (
    {
        "keywords": ("전기장비", "전력", "변압", "배전", "전선", "유틸리티"),
        "event": "전력망·인프라 CAPEX 수주와 납품 매출 인식",
        "focus": "수주잔고·출하량·원가 스프레드 확인",
        "risk": "수주 지연·원자재 가격 상승",
    },
    {
        "keywords": ("반도체", "전자부품", "디스플레이", "기타기계", "레이저", "광학"),
        "event": "고객사 신제품 양산·장비 발주와 가동률 회복",
        "focus": "고객사 CAPEX·수주 공시·가동률 확인",
        "risk": "고객사 재고조정·CAPEX 지연",
    },
    {
        "keywords": ("자동차", "자동차부품", "차량"),
        "event": "신차 생산·전장 수요와 부품 출하 사이클",
        "focus": "완성차 생산·수출·부품 믹스 확인",
        "risk": "완성차 생산 둔화·원가 부담",
    },
    {
        "keywords": ("방산", "항공우주", "국방"),
        "event": "방산 수출 계약·납품 인식과 후속 수주 기대",
        "focus": "수주 공시·납품 일정·수출 승인 확인",
        "risk": "수출 승인 지연·납품 일정 변경",
    },
    {
        "keywords": ("제약", "바이오", "의료", "헬스"),
        "event": "학회·임상·허가 일정과 파이프라인 가치 재평가",
        "focus": "임상 데이터·허가 일정·기술이전 계약 확인",
        "risk": "임상 지연·허가 불확실성·기술이전 무산",
    },
    {
        "keywords": ("은행", "금융", "보험", "증권"),
        "event": "금리·순이자마진과 배당·밸류업 수급 재평가",
        "focus": "순이자마진·대손비용·배당정책 확인",
        "risk": "대손비용 증가·금리 하락·배당 축소",
    },
    {
        "keywords": ("배터리", "2차전지", "화학", "금속", "알루미늄", "소재"),
        "event": "배터리·소재 고객사 가동률과 원재료 스프레드 회복",
        "focus": "출하량·판가·원재료 스프레드 확인",
        "risk": "고객사 재고조정·판가 하락·원재료 급등",
    },
    {
        "keywords": ("화장품", "유통", "소매", "식품", "음식료", "소비재"),
        "event": "프로모션·명절·글로벌 쇼핑 시즌의 주문 선반영",
        "focus": "판매량·재고·프로모션 효과 확인",
        "risk": "소비 둔화·재고 부담·프로모션 비용 증가",
    },
    {
        "keywords": ("게임", "엔터", "미디어", "콘텐츠", "여행", "레저"),
        "event": "신작·공연·여행 수요와 결제액 증가 사이클",
        "focus": "출시 일정·트래픽·예약매출 확인",
        "risk": "출시 지연·흥행 실패·마케팅비 증가",
    },
    {
        "keywords": ("건설", "건축", "부동산", "인프라"),
        "event": "착공·분양·인프라 발주와 매출 인식 사이클",
        "focus": "수주잔고·착공·원가율 확인",
        "risk": "착공 지연·미분양·원가율 악화",
    },
    {
        "keywords": ("해운", "항공", "운송", "물류"),
        "event": "운임·물동량·여행 수요 회복과 실적 레버리지",
        "focus": "운임지수·물동량·유가 확인",
        "risk": "운임 급락·유가 상승·물동량 둔화",
    },
)


_MONTH_CATALYST_HINTS: dict[int, str] = {
    1: "연초 예산 집행과 신규 제품·수주 계획",
    2: "춘절 이후 공급망 정상화와 1분기 주문 재개",
    3: "주주환원·정기주총과 1분기 실적 기대",
    4: "1분기 실적 발표와 봄철 수요 전환",
    5: "상반기 재고·발주 조정과 여름 성수기 선반영",
    6: "여름 성수기 주문과 하반기 CAPEX 선반영",
    7: "휴가철 소비·신제품 출시와 2분기 실적 확인",
    8: "하반기 발주 재개와 신제품·학회 일정",
    9: "3분기 실적 가시화와 연말 주문 선반영",
    10: "3분기 실적 발표와 연말 재고·배당 기대",
    11: "글로벌 쇼핑·연말 주문과 배당 매집",
    12: "연말 배당·리밸런싱과 다음 해 수주 기대",
}


def _text_value(value: Any) -> str:
    """Return a usable label while ignoring pandas NaN/None placeholders."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def _pct_text(value: Any, digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number * 100:+.{digits}f}%"


def _fallback_event_context(pattern: SeasonalityPattern, stock_row: dict[str, Any]) -> dict[str, str]:
    """Build a stock/industry-aware catalyst hypothesis for uncurated tickers."""
    ticker = str(pattern.ticker).zfill(6)
    hint = _TICKER_CATALYST_HINTS.get(ticker)
    if hint:
        return {**hint, "source": "종목별 업종 매핑"}

    labels = " ".join(
        value
        for value in (
            _text_value(stock_row.get("company")),
            _text_value(stock_row.get("sector")),
            _text_value(stock_row.get("industry")),
        )
        if value
    ).lower()
    for rule in _DOMAIN_CATALYST_RULES:
        if any(keyword.lower() in labels for keyword in rule["keywords"]):
            return {**rule, "source": "업종·산업 분류 매핑"}

    month = int(getattr(pattern, "target_start_month", 0) or 0)
    month_hint = _MONTH_CATALYST_HINTS.get(month, "계절성 수요·분기 실적 확인")
    industry = _text_value(stock_row.get("industry")) or _text_value(stock_row.get("sector")) or "해당 업종"
    return {
        "event": f"{industry}의 {month}월 {month_hint}",
        "focus": "다음 분기 매출·수주·거래대금 확인",
        "risk": "실적 추정치 하향·거래대금 급감",
        "source": "월별 계절성·업종 매핑",
    }


def _append_statistical_evidence(
    pattern: SeasonalityPattern,
    event: str,
    focus: str,
) -> tuple[str, str]:
    """Keep the headline readable while exposing the actual sample evidence."""
    years = max(int(pattern.sample_count or 0), 0)
    wins = sum(1 for row in pattern.years_track if float(row.get("return", 0.0) or 0.0) > 0)
    month = int(getattr(pattern, "target_start_month", 0) or 0)
    headline = f"{event} · {month}월 {wins}/{years}개년 상승"
    evidence = (
        f"근거: 중앙값 {_pct_text(pattern.median_return)} · 최근 3년 승률 {_pct_text(pattern.recent_3y_win_rate, 0)}"
        f" · 확인: {focus}"
    )
    return headline, evidence


def explain_and_score_pattern(pattern: SeasonalityPattern, stock_row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assigns AI explanation, computes 100-pt v1.1 discovery score, and determines current status."""
    ticker = str(pattern.ticker).zfill(6)
    s_row = stock_row or {}

    kb = EVENT_KNOWLEDGE_BASE.get(ticker)
    if kb:
        common_event, statistical_evidence = _append_statistical_evidence(
            pattern,
            kb["common_event"],
            kb["secondary_event"],
        )
        sec_event = statistical_evidence
        event_conf = kb["confidence"]
        failed_analysis = [
            f"{yr}년: {kb['failed_causes'].get(str(yr), '대외 매크로 변동 및 단기 차익 실현')}"
            for yr in [f["year"] for f in pattern.failed_years]
        ]
        invalidation = kb["invalidating_rules"]
        explanation_mode = "CURATED_TICKER"
        explanation_source = "종목별 검토 이벤트 지식베이스"
    else:
        context = _fallback_event_context(pattern, s_row)
        common_event, sec_event = _append_statistical_evidence(
            pattern,
            context["event"],
            context["focus"],
        )
        event_conf = "MEDIUM" if pattern.pattern_confidence == "HIGH" else "UNKNOWN"
        failed_analysis = [
            f"{f['year']}년: {context['risk']}로 계절성 가설 무효화 (수익률 {f['return']*100:+.1f}%)"
            for f in pattern.failed_years
        ]
        invalidation = f"{context['risk']}, FY1 EPS Revision 음전환, 거래대금 급감, RS60 < -10% 이탈"
        explanation_mode = "RULE_BASED"
        explanation_source = context["source"]

    def number(key: str) -> float | None:
        value = s_row.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # --- 1. Historical Pattern Score (observed monthly returns only) ---
    # Win Rate (15)
    s_wr = min(pattern.win_rate * 15.0, 15.0)
    # Median monthly return (15). This is not benchmark excess return.
    s_return = min(max(pattern.median_return, 0.0) * 120.0, 15.0)
    # Sample Count (10)
    s_cnt = min(pattern.sample_count * 2.0, 10.0)
    # Payoff (5)
    s_payoff = 5.0 if pattern.median_return > 0.05 else 3.0
    score_hist = round(s_wr + s_return + s_cnt + s_payoff, 1)

    # --- 2. Recent Validation Score (Max 20 pts) ---
    # Recent 3Y Win Rate (10)
    s_r3_wr = min(pattern.recent_3y_win_rate * 10.0, 10.0)
    recent_returns = [float(row.get("return", 0.0) or 0.0) for row in pattern.years_track[-3:]]
    recent_median_return = float(median(recent_returns)) if recent_returns else 0.0
    s_r3_return = min(max(recent_median_return, 0.0) * 100.0, 10.0)
    score_rec = round(s_r3_wr + s_r3_return, 1)

    # --- 3. Current Confirmation Score (Max 20 pts) ---
    quant_score = number("quant_score")
    ret_3m = number("return_3m")
    foreign_net = number("foreign_net")
    institution_net = number("institution_net")
    volume_ratio = number("volume_ratio")

    current_evidence: list[str] = []
    current_missing: list[str] = []

    s_rs = 0.0
    if ret_3m is None:
        current_missing.append("3개월 모멘텀")
    else:
        s_rs = 5.0 if ret_3m > 0.03 else 3.0 if ret_3m > -0.05 else 1.0
        current_evidence.append(f"3개월 수익률 {ret_3m * 100:+.1f}%")

    s_eps = 0.0
    if quant_score is None:
        current_missing.append("최신 퀀트 점수")
    else:
        s_eps = min(max(quant_score, 0.0) * 0.065, 5.0)
        current_evidence.append(f"퀀트 점수 {quant_score:.1f}")

    s_flow = 0.0
    if foreign_net is None and institution_net is None:
        current_missing.append("외국인·기관 수급")
    else:
        foreign = foreign_net or 0.0
        institution = institution_net or 0.0
        s_flow = 4.0 if foreign > 0 and institution > 0 else 2.0 if foreign + institution > 0 else 0.0
        current_evidence.append(f"외인 {foreign:+,.0f}주 · 기관 {institution:+,.0f}주")

    s_vol = 0.0
    if volume_ratio is None:
        current_missing.append("거래량 비율")
    else:
        s_vol = 2.0 if volume_ratio >= 1.2 else 1.0 if volume_ratio >= 1.0 else 0.0
        current_evidence.append(f"거래량 비율 {volume_ratio:.2f}배")

    # Curated event knowledge is explanatory context, not current confirmation.
    s_real = 0.0
    score_curr = round(s_rs + s_eps + s_flow + s_vol + s_real, 1)

    # --- 4. Event Explanation Score (Max 10 pts) ---
    if event_conf == "HIGH":
        score_expl = 10.0
    elif event_conf == "MEDIUM":
        score_expl = 7.0
    elif event_conf == "LOW":
        score_expl = 3.0
    else:
        score_expl = 1.0

    # Total Score
    total_score = round(score_hist + score_rec + score_curr + score_expl, 1)
    total_score = max(0.0, min(100.0, total_score))

    # Pre-pricing Penalty
    pre_pricing = False
    if ret_3m is not None and ret_3m > 0.35:
        pre_pricing = True
        total_score = max(0.0, total_score - 10.0)

    # Grade
    if total_score >= 85.0:
        grade = "S"
    elif total_score >= 75.0:
        grade = "A"
    elif total_score >= 65.0:
        grade = "B"
    elif total_score >= 55.0:
        grade = "C"
    else:
        grade = "D"

    # Status Determination
    if not current_evidence:
        status = "UNKNOWN"
    elif ret_3m is not None and quant_score is not None and ret_3m < -0.15 and quant_score < 48:
        status = "BROKEN"
    elif pattern.recent_3y_win_rate < 0.50:
        status = "WEAKENING"
    elif total_score >= 78.0 and pattern.win_rate >= 0.70 and ret_3m is not None and ret_3m >= 0:
        status = "ACTIVE"
    elif total_score >= 68.0:
        status = "WATCH"
    elif event_conf == "UNKNOWN":
        status = "UNKNOWN"
    else:
        status = "DISCOVERY"

    return {
        "pattern_id": pattern.pattern_id,
        "ticker": ticker,
        "company": pattern.company,
        "market": pattern.market,
        "window_name": pattern.window_name,
        "sample_count": pattern.sample_count,
        "win_rate": pattern.win_rate,
        "median_return": pattern.median_return,
        "median_alpha": pattern.median_alpha,
        "avg_mdd": pattern.avg_mdd,
        "best_year": pattern.best_year,
        "worst_year": pattern.worst_year,
        "recent_3y_win_rate": pattern.recent_3y_win_rate,
        "recent_5y_win_rate": pattern.recent_5y_win_rate,
        "years_track": pattern.years_track,
        "failed_years": pattern.failed_years,
        "failed_analysis": failed_analysis,
        "common_event_cluster": common_event,
        "secondary_cluster": sec_event,
        "event_confidence": event_conf,
        "event_explanation_mode": explanation_mode,
        "event_explanation_source": explanation_source,
        "current_status": status,
        "grade": grade,
        "seasonality_score": total_score,
        "score_breakdown": {
            "historical_pattern": score_hist,
            "recent_validation": score_rec,
            "current_confirmation": score_curr,
            "event_explanation": score_expl,
        },
        "current_confirmation_evidence": current_evidence,
        "current_confirmation_missing": current_missing,
        "pre_pricing_flag": pre_pricing,
        "invalidating_conditions": invalidation,
        # Mobile Dashboard Playbook & Timing additions
        "entry_stage": getattr(pattern, "entry_stage", "WATCH"),
        "entry_stage_label": getattr(pattern, "entry_stage_label", "⚡ 진입 유효"),
        "entry_window_str": getattr(pattern, "entry_window_str", ""),
        "exit_window_str": getattr(pattern, "exit_window_str", ""),
        "expected_p50": getattr(pattern, "expected_p50", pattern.median_return),
        "expected_p90": getattr(pattern, "expected_p90", pattern.median_return * 1.8),
        "profit_factor": getattr(pattern, "profit_factor", 3.5),
        "playbook": getattr(pattern, "playbook", {}),
    }
