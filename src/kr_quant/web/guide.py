from __future__ import annotations

from typing import Any

EXCLUSION_KO = {
    "CORE_DATA_INCOMPLETE": "필수 재무·가격이 없어 순위에 넣지 않음",
    "LIQUIDITY_FAIL": "60일 거래대금 또는 거래일수 미달",
    "MARKET_CAP_FAIL": "시가총액이 하한(300억) 미만",
    "FINANCIAL_MODEL_NOT_AVAILABLE": "금융업 — 일반기업 공식 적용 금지",
    "REIT_MODEL_NOT_AVAILABLE": "리츠 등 별도 자산가치 모델 필요",
    "INFRA_FUND_MODEL_NOT_AVAILABLE": "인프라·선박펀드 등 별도 모델 필요",
    "SPAC": "기업인수목적회사",
    "PREFERRED_SHARE": "우선주",
    "NOT_COMMON_STOCK": "보통주가 아님",
    "NON_COMMON_SECURITY": "ETF·ETN 등 주권이 아님",
    "STALE_FINANCIALS": "최근 재무 결산일이 270일을 넘김",
    "NEGATIVE_EQUITY": "자본총계 또는 지배주주지분 ≤ 0",
    "AUDIT_OPINION_FAIL": "감사의견 부적정·의견거절 등",
    "DISTRESS_STATUS": "파산·회생·영업정지",
    "TRADING_STATUS_EXCLUDED": "거래정지·관리·상장폐지 절차",
    "TRADING_STATUS_UNVERIFIED": "거래 가능 여부 피드가 없어 후보 선정을 보류함",
    "FILING_LINEAGE_CONFLICT": "정정·철회 공시 이력을 확정할 수 없음",
    "MARKET_EXCLUDED": "KOSPI/KOSDAQ이 아님",
    "RECONCILIATION_FAIL": "자산 = 부채 + 자본 검증 실패",
}

WARNING_KO = {
    "STATUS_FEED_MISSING": "거래정지·관리종목 일별 피드가 없어 후보 선정을 보류함 (partial)",
    "MODEL_BREAK": "모델 버전이 바뀌어 전일 점수와 비교하지 않음",
    "SOURCE_NOT_READY": "당일 KRX 시세가 준비되지 않아 점수를 내지 않음",
}

WARNING_FIX = {
    "STATUS_FEED_MISSING": (
        "config의 status_feed.path(기본 data/raw/status/manual_status.csv)에 "
        "ticker, as_of_date, status 열을 채워 거래정지·관리종목을 넣으세요. "
        "파일이 없으면 거래 가능 여부를 확인할 수 없어 모든 후보 선정을 보류합니다."
    ),
    "MODEL_BREAK": "모델 버전이 바뀐 실행입니다. 전일과 점수 비교는 하지 말고 이번 결과만 보세요. 별도 수정은 필요 없습니다.",
    "SOURCE_NOT_READY": "장 마감 후 오른쪽 위 '시세 받기'로 KRX 일봉을 받은 뒤 실행 탭에서 재계산하세요.",
}

STATUS_LABEL = {
    "success": "완료",
    "partial": "일부 완료",
    "failed": "실패",
    "error": "오류",
    "no-run": "아직 실행 안 함",
    "running": "실행 중",
    "idle": "대기",
}


def explain_run_status(quality: dict[str, Any] | None, *, status_csv_exists: bool = False) -> dict[str, Any]:
    """Why a run is partial/failed, and what to improve. Overlay copy only."""
    quality = quality or {}
    status = str(quality.get("status") or "no-run")
    warnings = [str(w) for w in (quality.get("warnings") or []) if w]
    why: list[str] = []
    improve: list[str] = []
    if status == "partial":
        if not warnings:
            why.append("점수는 나왔지만 운영 경고가 있어 일부 완료입니다.")
            improve.append("실행 탭 로그와 대시보드 데이터 품질 칸을 확인하세요.")
        for code in warnings:
            why.append(WARNING_KO.get(code, code))
            improve.append(WARNING_FIX.get(code, "해당 경고 원인을 해소한 뒤 재계산하세요."))
        if "STATUS_FEED_MISSING" in warnings and not status_csv_exists:
            improve.append("지금 status CSV 파일이 없습니다. 경로를 만들고 일별 거래정지 목록을 넣으면 완료로 올라갑니다.")
    elif status == "failed":
        why.append("스크리닝이 실패했습니다.")
        improve.append("실행 탭 로그에서 원인(시세 없음, 키 오류 등)을 보고 다시 실행하세요.")
        for code in warnings:
            why.append(WARNING_KO.get(code, code))
            improve.append(WARNING_FIX.get(code, "해당 경고를 해소한 뒤 재실행하세요."))
    elif status == "success":
        why.append("이번 스크리닝이 끝까지 갔습니다.")
        if warnings:
            why.extend(WARNING_KO.get(code, code) for code in warnings)
    elif status == "no-run":
        why.append("아직 스크리닝을 돌리지 않았습니다.")
        improve.append("실행 탭에서 데모 또는 실데이터 수집을 먼저 하세요.")
    return {
        "status": status,
        "label": STATUS_LABEL.get(status, status),
        "why": why,
        "improve": improve,
        "warnings": warnings,
        "used_in_quant": False,
    }


def pad_ticker(ticker: str | int | None) -> str:
    text = str(ticker or "").replace(".0", "").strip().upper()
    if 5 <= len(text) <= 6 and text.isalnum() and any(ch.isalpha() for ch in text):
        return text.zfill(6)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else text


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num or num in {float("inf"), float("-inf")}:
        return None
    return num


def format_krw(value: Any) -> str | None:
    num = _as_float(value)
    if num is None:
        return None
    sign = "-" if num < 0 else ""
    mag = abs(num)
    if mag >= 1e12:
        return f"{sign}{mag / 1e12:.2f}조원"
    if mag >= 1e8:
        return f"{sign}{mag / 1e8:.0f}억원"
    return f"{sign}{mag:,.0f}원"


def format_list_date(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def format_pct(value: Any, digits: int = 1) -> str | None:
    num = _as_float(value)
    if num is None:
        return None
    return f"{num * 100:.{digits}f}%"


def format_multiple(value: Any, digits: int = 1) -> str | None:
    num = _as_float(value)
    if num is None:
        return None
    return f"{num:.{digits}f}배"


DATA_FLAG_KO = {
    "DEBT_ASSUMED_ZERO": "무차입 경영 (차입금 0 가정 — 재무 레버리지 리스크 극히 낮음)",
    "SFA_ASSUMED_ZERO": "단기금융자산 0으로 보수적 산정",
    "NEGATIVE_EV_REVIEW": "순현금이 시총을 초과하는 순현금 우량 상태 (EV 음수)",
    "NEGATIVE_FCF": "대규모 CAPEX 투자 또는 운전자본 확대로 최근 잉여현금흐름(FCF) 일시적 음수",
    "LOSS_MAKING": "최근 결산 실적 영업적자/순손실",
    "ZERO_DENOM": "분모 0으로 인한 산출 보정",
    "MOMENTUM_DISABLED_NO_ADJ_CLOSE": "모멘텀 지표 미반영",
    "SHARE_ADJ_MOMENTUM": "모멘텀은 상장주식수로 분할만 보정했습니다",
    "MOMENTUM_UNRELIABLE": "모멘텀 지표 커버리지가 낮습니다",
    "VALUE_UNRELIABLE": "가치 팩터 데이터 일부 결측",
    "QUALITY_UNRELIABLE": "품질 팩터 데이터 일부 결측",
    "GROWTH_UNRELIABLE": "성장 팩터 데이터 일부 결측",
    "STABILITY_UNRELIABLE": "안정 팩터 데이터 일부 결측",
    "EPS_PROXY_LOW_CONFIDENCE": "EPS는 추정값이라 신뢰도가 낮습니다",
    "TAX_RATE_FALLBACK": "세율은 법정 표준 기본값을 썼습니다",
    "ROIC_CASH_CLASSIFICATION_SIMPLE": "ROIC 현금 분류는 단순 방식입니다",
    "CAPEX_PARTIAL": "설비투자(CAPEX) 일부 세부 내역 추정치 반영",
    "Q4_DERIVATION_ANOMALY": "4분기 재무를 연간-누적으로 추정했습니다",
    "INSUFFICIENT_HISTORY": "가격 이력이 짧아 일부 기간 수익률은 비었습니다",
    "PREFERRED_CAPITAL_UNKNOWN": "우선주 자본을 확정하지 못했습니다",
    "PEER_TAXONOMY_WEAK": "업종 분류가 약해 비교군이 넓습니다",
}

RISK_FLAG_KO = {
    "REV_DECLINE_STREAK": "최근 2분기 이상 매출 감소세 지속",
    "OP_DECLINE_STREAK": "최근 2분기 이상 영업이익 감소세 지속",
    "FCF_DETERIORATION": "잉여현금흐름(FCF) 악화 추세",
    "LEVERAGE_STRESS": "부채비율 또는 차입금 의존도 레버리지 부담",
    "THIN_EQUITY": "자기자본비율이 얇아 자본 확충 필요",
    "DILUTION_12M_HIGH": "최근 1년 희석이 큽니다 (유상증자/CB 대규모 발행)",
    "DILUTION_12M_MEDIUM": "최근 1년 희석이 있습니다",
    "CB_BW_OVERHANG": "전환사채(CB)·신주인수권(BW) 잠재 오버행 매물 부담",
    "REPEATED_CB_BW": "전환사채·신주인수권 반복 발행 이력",
    "ONE_OFF_EARNINGS_RISK": "자산매각 등 일회성 영업외이익 착시 가능성",
}


def flag_notes(raw: Any, mapping: dict[str, str]) -> list[dict[str, str]]:
    from kr_quant.context.explain import clean_reason_list

    notes = []
    for code in clean_reason_list(raw):
        notes.append({"code": code, "label": mapping.get(code, code)})
    return notes


def stock_brief(row: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic Korean intro from scored row + optional master profile. No LLM."""
    profile = profile or {}
    name = str(row.get("company") or row.get("ticker") or "").strip()
    code = pad_ticker(row.get("ticker"))
    market = str(row.get("market") or "").strip()
    sector = str(row.get("sector") or "").strip()
    industry = str(row.get("industry") or "").strip()
    kind = str(profile.get("kind") or "보통주").strip()
    where = " ".join(x for x in [market, sector, industry] if x)
    headline = f"{name}({code})은 {where} {kind}입니다." if where else f"{name}({code})입니다."

    extras: list[str] = []
    listed = format_list_date(profile.get("list_date") or row.get("list_date"))
    cap = format_krw(profile.get("market_cap") or row.get("market_cap"))
    if listed:
        extras.append(f"{listed} 상장")
    if cap:
        extras.append(f"시가총액 약 {cap}")
    if extras:
        headline += " " + ", ".join(extras) + "."

    paragraphs: list[str] = []
    as_of = str(row.get("as_of_date") or "").strip()
    rank = row.get("quant_rank")
    score = _as_float(row.get("quant_score"))
    bits: list[str] = []
    if as_of:
        bits.append(f"기준일 {as_of}")
    if score is not None:
        bits.append(f"Quant 점수 {score:.1f}점")
    if rank == rank and rank not in (None, ""):
        try:
            bits.append(f"조건 통과 종목 중 {int(rank)}위")
        except (TypeError, ValueError):
            pass
    gates = []
    if row.get("top20_eligible"):
        gates.append("TOP20 가능")
    elif row.get("top100_eligible"):
        gates.append("TOP100 가능")
    elif row.get("universe_eligible"):
        gates.append("유니버스 통과")
    if gates:
        bits.append(gates[0])
    if bits:
        paragraphs.append("이 스크리너에서는 " + ", ".join(bits) + "입니다.")

    val_bits: list[str] = []
    per = format_multiple(row.get("per"))
    pbr = format_multiple(row.get("pbr"))
    roic = format_pct(row.get("roic"))
    roe = format_pct(row.get("roe"))
    if per:
        val_bits.append(f"PER {per}")
    if pbr:
        val_bits.append(f"PBR {pbr}")
    if roic:
        val_bits.append(f"ROIC {roic}")
    if roe:
        val_bits.append(f"ROE {roe}")
    if val_bits:
        paragraphs.append("수익성·밸류는 " + ", ".join(val_bits) + "입니다.")

    grow_bits: list[str] = []
    rev = format_pct(row.get("revenue_yoy"))
    opy = format_pct(row.get("op_yoy"))
    if rev:
        grow_bits.append(f"매출 YoY {rev}")
    if opy:
        grow_bits.append(f"영업이익 YoY {opy}")
    nda = _as_float(row.get("net_debt_assets"))
    ic = _as_float(row.get("interest_coverage"))
    if nda is not None:
        grow_bits.append("순현금 구조" if nda < 0 else f"순부채/자산 {nda * 100:.1f}%")
    if ic is not None:
        grow_bits.append(f"이자보상배율 {ic:.1f}배")
    if grow_bits:
        paragraphs.append("성장·재무는 " + ", ".join(grow_bits) + "입니다.")

    notes = [n["label"] for n in flag_notes(row.get("data_flags"), DATA_FLAG_KO)]
    if notes:
        paragraphs.append("참고: " + "; ".join(notes[:3]) + ".")

    facts = [
        {"label": "시장", "value": market or "—"},
        {"label": "업종", "value": " / ".join(x for x in [sector, industry] if x) or "—"},
        {"label": "상장일", "value": listed or "—"},
        {"label": "시가총액", "value": cap or "—"},
        {"label": "종목유형", "value": kind or "—"},
        {"label": "결산월", "value": (str(int(profile["acc_mt"])) + "월") if _as_float(profile.get("acc_mt")) else "—"},
    ]
    return {"headline": headline, "paragraphs": paragraphs, "facts": facts}


def external_links(ticker: str | int | None, company: str | None = None) -> list[dict[str, str]]:
    from urllib.parse import quote

    code = pad_ticker(ticker)
    name = company or code
    return [
        {
            "label": "네이버 시세",
            "url": f"https://finance.naver.com/item/main.naver?code={code}",
        },
        {
            "label": "네이버 종목분석",
            "url": f"https://finance.naver.com/item/coinfo.naver?code={code}",
        },
        {
            "label": "다음 금융",
            "url": f"https://finance.daum.net/quotes/A{code}",
        },
        {
            "label": "FnGuide",
            "url": f"https://wcomp.fnguide.com/CompanyInfo/Snapshot?gicode=A{code}",
        },
        {
            "label": "DART 검색",
            "url": f"https://dart.fss.or.kr/dsab001/main.do?autoSearch=Y&textCrpNm={quote(name)}",
        },
        {
            "label": "KIND",
            "url": (
                "https://kind.krx.co.kr/disclosureSimpleSearch.do"
                f"?method=disclosureSimpleSearchMain&repIsuSrtCd={code}&searchCorpName={quote(name)}"
            ),
        },
        {
            "label": "토스증권",
            "url": f"https://www.tossinvest.com/stocks/A{code}",
        },
        {
            "label": "토스 골라보기",
            "url": "https://www.tossinvest.com/screener",
        },
    ]


def selection_guide(cfg: dict[str, Any]) -> dict[str, Any]:
    uni = cfg.get("universe", {})
    liq = uni.get("liquidity", {})
    top100 = uni.get("top100", {})
    top20 = uni.get("top20", {})
    min_cap = int(uni.get("min_market_cap_krw", 0))
    min_tv = int(liq.get("min_median_trading_value_krw", 0))
    return {
        "universe": [
            "시장은 KOSPI·KOSDAQ 보통주만 넣습니다. 우선주·ETF·스팩·리츠는 뺍니다.",
            f"시가총액 {min_cap / 1e8:.0f}억원 이상이어야 합니다.",
            f"최근 {liq.get('window_trading_days', 60)}거래일 중앙 거래대금이 {min_tv / 1e8:.0f}억원 이상이어야 합니다.",
            f"{liq.get('lookback_trading_days', 63)}거래일 중 {liq.get('min_observations_in_63d', 45)}일 이상 거래가 있어야 합니다.",
            "금융업(은행·보험·증권)은 일반기업 FCF·EV/EBIT 공식을 쓰지 않아 제외합니다.",
            "자본잠식, 감사의견 부적정/거절, 파산·회생은 hard exclusion입니다.",
            "매출·영업이익·지배주주순이익·자산/부채/자본·CFO·CAPEX·종가가 없으면 순위를 주지 않습니다.",
        ],
        "top100": [
            f"가중 지표 커버리지 {float(top100.get('min_weighted_coverage', 0.8)) * 100:.0f}% 이상",
            f"데이터 신뢰도 {top100.get('min_data_confidence', 70)} 이상",
            "회계등식(자산=부채+자본) 검증을 통과해야 합니다.",
        ],
        "top20": [
            f"커버리지 {float(top20.get('min_weighted_coverage', 0.9)) * 100:.0f}% 이상",
            f"데이터 신뢰도 {top20.get('min_data_confidence', 80)} 이상",
            "TTM 영업이익, 지배주주순이익, 영업현금흐름이 모두 양수여야 합니다.",
            "hard exclusion이 없어야 합니다. GPT가 점수를 고치지 않습니다.",
        ],
        "confidence": [
            "신뢰도는 점수에 곱하지 않습니다. 게이트로만 씁니다.",
            "구성: 커버리지 45% + 공시시점(PIT) 20% + 재무 신선도 15% + 대사 10% + 이력 10%.",
            "신선도: 최근 결산일 150일 이내 만점, 270일 초과면 탈락(STALE).",
            "모멘텀이 꺼진 버전에서는 모멘텀 10점을 커버리지 분모에서 빼므로, 나머지 지표가 채워지면 TOP20 문턱을 넘을 수 있습니다.",
        ],
        "score": [
            "공식 점수 100점: Value 30 / Quality 25 / Growth 25 / Momentum 10 / Stability 10.",
            "리스크는 별도 soft penalty(최대 15점)로 빼서 QuantScore를 만듭니다.",
            "적자 PER·음수 FCF는 서로 덜 나쁜 회사를 저평가로 순위화하지 않고 0점입니다.",
        ],
    }
