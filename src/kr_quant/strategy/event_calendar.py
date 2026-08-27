# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd


@dataclass
class CalendarEvent:
    event_id: str
    group_id: str  # 01..10
    group_name: str
    strategy_name: str
    title: str
    target_date: str  # YYYY-MM-DD
    announcement_date: str | None
    date_certainty: float  # 0.0 ~ 1.0
    binary_risk: str  # LOW, MEDIUM, HIGH
    description: str
    beneficiary_sectors: list[str]
    beneficiary_stocks: list[dict[str, Any]]
    default_entry_window: str
    default_exit_window: str
    invalidating_rule: str


# 10 Major Event Categories & 20 Comprehensive Institutional Event Strategies (through Q4 & Year-End/New Year)
EVENT_CATALOG: list[dict[str, Any]] = [
    # 01. Market Calendar
    {
        "event_id": "tom_monthly",
        "group_id": "01_market_cal",
        "group_name": "Market Calendar",
        "strategy_name": "Turn-of-the-Month (TOM)",
        "title": "월말/월초 효과 (Turn of Month)",
        "month_pattern": "every_month_end",
        "base_day": 28,
        "date_certainty": 1.0,
        "binary_risk": "LOW",
        "description": "기관/연기금 월말 윈도드레싱 및 월초 신규 자금 유입 수급 랠리",
        "beneficiary_sectors": ["KOSPI 대형주", "외국인·기관 수급 집중주", "프로그램 매수 수혜주"],
        "beneficiary_stocks": [
            {"ticker": "005930", "company": "삼성전자", "role": "KOSPI 시총 1위 윈도드레싱 최우선주"},
            {"ticker": "000660", "company": "SK하이닉스", "role": "외국인 패시브 바스켓 최우선 매수"},
            {"ticker": "005380", "company": "현대차", "role": "기관 월초 리밸런싱 선호 대형주"},
            {"ticker": "035420", "company": "NAVER", "role": "플랫폼 성장주 월초 수급 유입"}
        ],
        "default_entry_window": "D-3 ~ D-1",
        "default_exit_window": "D+2 ~ D+3",
        "invalidating_rule": "외국인/기관 동반 대규모 순매도 또는 선물 베이시스 급격한 백워데이션",
    },
    {
        "event_id": "chuseok_holiday",
        "group_id": "01_market_cal",
        "group_name": "Market Calendar",
        "strategy_name": "추석 연휴 전후 캘린더",
        "title": "추석 명절 연휴 전후 효과",
        "target_date_2026": "2026-09-24",
        "date_certainty": 1.0,
        "binary_risk": "LOW",
        "description": "긴 연휴 전 불확실성 회피 매도 후 연휴 직전/직후 저가 매수세 유입",
        "beneficiary_sectors": ["유통/식품", "선물세트 소비", "여행/항공", "CJ그룹 지주"],
        "beneficiary_stocks": [
            {"ticker": "001040", "company": "CJ", "role": "추석 명절 선물세트 및 식품/미디어 소비 랠리"},
            {"ticker": "097950", "company": "CJ제일제당", "role": "가공식품 및 명절 선물세트 판매 호조"},
            {"ticker": "028260", "company": "삼성물산", "role": "패션/리조트 연휴 소비 수혜"},
            {"ticker": "035760", "company": "CJ ENM", "role": "추석 연휴 극장/콘텐츠 시청 시간 급증"}
        ],
        "default_entry_window": "D-5 ~ D-2",
        "default_exit_window": "D+3 ~ D+5",
        "invalidating_rule": "글로벌 매크로 급변 및 환율 급등",
    },
    {
        "event_id": "major_shareholder_tax_2026",
        "group_id": "01_market_cal",
        "group_name": "Market Calendar",
        "strategy_name": "대주주 양도세 회피 매도 & 12월 말 저점 반등",
        "title": "대주주 양도세 회피 매물 출회 및 연말 저점 반등 랠리",
        "target_date_2026": "2026-12-24",
        "date_certainty": 1.0,
        "binary_risk": "MEDIUM",
        "description": "12월 중순 대주주 요건 회피 개인 큰손 매물 출회 후 12월 24~28일 저점 강력 반등",
        "beneficiary_sectors": ["개인 비중 높은 코스닥 성장주", "2차전지/로봇/AI", "낙폭과대 바이오"],
        "beneficiary_stocks": [
            {"ticker": "247540", "company": "에코프로비엠", "role": "연말 개인 양도세 매물 출회 후 12월 말 저가 반등"},
            {"ticker": "086520", "company": "에코프로", "role": "개인 수급 집중주 연말 반등 랠리"},
            {"ticker": "277810", "company": "레인보우로보틱스", "role": "코스닥 로봇 성장주 연말 수급 복귀"}
        ],
        "default_entry_window": "D-5 ~ D-1 (12월 20일 ~ 24일)",
        "default_exit_window": "D+5 ~ D+15 (1월 초)",
        "invalidating_rule": "세법 개정안 변경 또는 거시경제 급변",
    },
    {
        "event_id": "santa_january_effect",
        "group_id": "01_market_cal",
        "group_name": "Market Calendar",
        "strategy_name": "연말 산타랠리 & 1월 효과 (January Effect)",
        "title": "연말 산타랠리 & 1월 효과 코스닥 중소형주 랠리",
        "target_date_2026": "2027-01-05",
        "date_certainty": 0.9,
        "binary_risk": "LOW",
        "description": "연말 배당락 이후 기관/외국인 신규 북클로징 자금 집행 및 코스닥 1월 효과",
        "beneficiary_sectors": ["코스닥 중소형 성장주", "연초 정부 정책 수혜주", "신규 수급 유입주"],
        "beneficiary_stocks": [
            {"ticker": "035420", "company": "NAVER", "role": "연초 신규 자금 유입 성장주"},
            {"ticker": "356680", "company": "엑스게이트", "role": "보안/AI 연초 정책 수혜 중소형주"},
            {"ticker": "168360", "company": "펨트론", "role": "반도체 검사장비 코스닥 1월 랠리"}
        ],
        "default_entry_window": "D-10 ~ D-3 (12월 26일 ~ 30일)",
        "default_exit_window": "D+10 ~ D+15 (1월 중순)",
        "invalidating_rule": "연초 글로벌 금리 급등 및 환율 불안",
    },
    # 02. Passive Flow
    {
        "event_id": "msci_aug_2026",
        "group_id": "02_passive_flow",
        "group_name": "Passive Flow",
        "strategy_name": "MSCI Korea Rebalance",
        "title": "MSCI 8월 분기 리뷰 & 리밸런싱",
        "target_date_2026": "2026-08-31",
        "date_certainty": 0.95,
        "binary_risk": "MEDIUM",
        "description": "MSCI 신규 편입 후보군의 패시브 자금 유입 선취매",
        "beneficiary_sectors": ["MSCI 신규 편입 후보군", "유동시총 급증주", "비중 상향 대형주"],
        "beneficiary_stocks": [
            {"ticker": "105560", "company": "KB금융", "role": "MSCI Korea 금융 섹터 대표주"},
            {"ticker": "000810", "company": "삼성화재", "role": "외국인 지분율 안정 대형주"},
            {"ticker": "267260", "company": "HD현대일렉트릭", "role": "시총 급증에 따른 비중 상향 후보"}
        ],
        "default_entry_window": "D-45 ~ D-15",
        "default_exit_window": "D-1 ~ D0 (리밸런싱 당일 종가)",
        "invalidating_rule": "시총 급락으로 편입 기준선 미달 또는 외국인 지분율 한도 소진",
    },
    {
        "event_id": "msci_nov_2026",
        "group_id": "02_passive_flow",
        "group_name": "Passive Flow",
        "strategy_name": "MSCI Korea Rebalance",
        "title": "MSCI 11월 반기 리뷰 & 리밸런싱",
        "target_date_2026": "2026-11-30",
        "date_certainty": 0.95,
        "binary_risk": "MEDIUM",
        "description": "글로벌 패시브 추종 펀드의 기계적 매수 유입 선반영",
        "beneficiary_sectors": ["MSCI 반기 편입 유력주", "글로벌 수급 수혜주"],
        "beneficiary_stocks": [
            {"ticker": "192820", "company": "코스맥스", "role": "K-뷰티 글로벌 수출 호조 시총 확대"},
            {"ticker": "259960", "company": "크래프톤", "role": "글로벌 게임 실적 기반 시총 상위 유지"}
        ],
        "default_entry_window": "D-45 ~ D-15",
        "default_exit_window": "D-1 ~ D0",
        "invalidating_rule": "시총 급락 또는 편출 리스크 발생",
    },
    {
        "event_id": "kospi200_dec_2026",
        "group_id": "02_passive_flow",
        "group_name": "Passive Flow",
        "strategy_name": "KOSPI200 / KOSDAQ150 정기변경",
        "title": "KOSPI200 / KOSDAQ150 12월 정기변경",
        "target_date_2026": "2026-12-10",
        "date_certainty": 0.9,
        "binary_risk": "LOW",
        "description": "국내 대표 인덱스 편입 예상 종목에 대한 기관/패시브 선취매",
        "beneficiary_sectors": ["KOSPI200 편입 후보", "KOSDAQ150 편입 후보", "중형 우량주"],
        "beneficiary_stocks": [
            {"ticker": "053610", "company": "프로텍", "role": "반도체 장비 우량 중형주"},
            {"ticker": "086790", "company": "하나금융지주", "role": "인덱스 비중 확대 금융주"}
        ],
        "default_entry_window": "D-60 ~ D-20",
        "default_exit_window": "D-1 ~ D0",
        "invalidating_rule": "유동비율 변동 또는 관리종목/거래정지 사유 발생",
    },
    # 03. Earnings & Fundamental
    {
        "event_id": "q3_earnings_pead",
        "group_id": "03_earnings",
        "group_name": "Earnings & Fundamental",
        "strategy_name": "Pre-Earnings Revision & PEAD",
        "title": "3분기 실적 시즌 어닝 서프라이즈 드리프트 (PEAD)",
        "target_date_2026": "2026-10-25",
        "date_certainty": 0.85,
        "binary_risk": "MEDIUM",
        "description": "FY1 EPS 상향 조정과 실적 발표 후 양의 드리프트(PEAD) 모멘텀",
        "beneficiary_sectors": ["3분기 수출 호조주", "난방/가전 성수기 진입주", "영업이익 서프라이즈 후보"],
        "beneficiary_stocks": [
            {"ticker": "009450", "company": "경동나비엔", "role": "북미 온수기/보일러 수출 실적 서프라이즈"},
            {"ticker": "192820", "company": "코스맥스", "role": "인디 화장품 글로벌 수출 호조 실적 상향"},
            {"ticker": "011070", "company": "LG이노텍", "role": "iPhone 신제품 양산에 따른 3Q 영업이익 급증"}
        ],
        "default_entry_window": "D-30 ~ D-5",
        "default_exit_window": "D+5 ~ D+20",
        "invalidating_rule": "잠정 실적 쇼크 또는 가이던스 하향 조정",
    },
    # 04. Shareholder Return
    {
        "event_id": "year_end_dividend",
        "group_id": "04_shareholder",
        "group_name": "Shareholder Return",
        "strategy_name": "연말 배당 선취매 랠리 (Dividend Record)",
        "title": "연말 고배당주 선취매 랠리",
        "target_date_2026": "2026-12-29",
        "date_certainty": 1.0,
        "binary_risk": "LOW",
        "description": "배당락(12월 말) 2~3개월 전부터 유입되는 배당 펀드 및 개인 선취매",
        "beneficiary_sectors": ["은행/금융지주 (배당수익률 5~7%)", "통신사", "손해보험", "밸류업 지주사"],
        "beneficiary_stocks": [
            {"ticker": "105560", "company": "KB금융", "role": "밸류업 1위 및 연간 배당수익률 5.5%+"},
            {"ticker": "086790", "company": "하나금융지주", "role": "고배당 + 분기배당 균등 안정성"},
            {"ticker": "017670", "company": "SK텔레콤", "role": "전통의 배당 방어주 (수익률 6%+)"},
            {"ticker": "001720", "company": "신영증권", "role": "가치투자 증권사 전통 고배당"}
        ],
        "default_entry_window": "D-75 ~ D-25 (9월 중순 ~ 11월)",
        "default_exit_window": "D-5 ~ D-1 (배당락 직전)",
        "invalidating_rule": "실적 악화로 인한 배당 삭감(DPS Cut) 공시",
    },
    # 05. Weather & Power Demand
    {
        "event_id": "winter_heating_surge",
        "group_id": "05_weather",
        "group_name": "Weather & Power Demand",
        "strategy_name": "겨울 난방 · 보일러 선취매",
        "title": "겨울 한파 & 난방/보일러 선취매 랠리",
        "target_date_2026": "2026-11-01",
        "date_certainty": 0.85,
        "binary_risk": "LOW",
        "description": "난방 가동 및 성수기 진입 전 7~9월 선취매 랠리 및 10~11월 실적 반영",
        "beneficiary_sectors": ["콘덴싱 보일러 / 온수기", "공기열 히트펌프(HVAC)", "석유/캠핑 난로", "도시가스/LNG", "단열재"],
        "beneficiary_stocks": [
            {"ticker": "009450", "company": "경동나비엔", "role": "북미 보일러/온수기 1위 및 7~9월 선취매 챔피언"},
            {"ticker": "037070", "company": "파세코", "role": "석유/심지식 난로 북미/중동 수출 성수기 (10월 승률 75%)"},
            {"ticker": "002700", "company": "신일전자", "role": "동절기 난방 가전 (히터/팬히터) 라인업"},
            {"ticker": "017390", "company": "서울가스", "role": "겨울철 도시가스 난방 사용량 급증"}
        ],
        "default_entry_window": "D-75 ~ D-40 (7월 하순 ~ 9월 초)",
        "default_exit_window": "D-5 ~ D+10",
        "invalidating_rule": "이상 고온(Warm Winter) 예보 또는 3분기 실적 역성장",
    },
    # 06. Tech Product Cycle
    {
        "event_id": "apple_iphone_18",
        "group_id": "06_tech_cycle",
        "group_name": "Tech Product Cycle",
        "strategy_name": "iPhone 공급망 부품 선취매",
        "title": "Apple iPhone 신제품 공개 및 양산 사이클",
        "target_date_2026": "2026-09-15",
        "date_certainty": 0.9,
        "binary_risk": "MEDIUM",
        "description": "초도 물량 양산(7~8월) 및 언팩(9월) 전 국내 디스플레이/카메라 부품사 랠리",
        "beneficiary_sectors": ["카메라 모듈(폴디드줌)", "OLED 패널", "연성인쇄회로기판(FPCB)", "MLCC/적층세라믹"],
        "beneficiary_stocks": [
            {"ticker": "011070", "company": "LG이노텍", "role": "iPhone 고사양 카메라 모듈(폴디드줌) 독점 공급"},
            {"ticker": "090460", "company": "비에이치", "role": "iPhone 디스플레이용 FPCB 메인 공급사"},
            {"ticker": "034220", "company": "LG디스플레이", "role": "iPhone Pro 라인업 OLED 패널 공급"},
            {"ticker": "009150", "company": "삼성전기", "role": "초소형 고용량 IT용 MLCC 공급"}
        ],
        "default_entry_window": "D-60 ~ D-20 (7월 ~ 8월 중순)",
        "default_exit_window": "D-3 ~ D+3",
        "invalidating_rule": "초도 물량 감산 보도 또는 수율 이슈",
    },
    {
        "event_id": "ces_2027_tech",
        "group_id": "06_tech_cycle",
        "group_name": "Tech Product Cycle",
        "strategy_name": "CES 2027 세계 최대 가전/AI/로봇 쇼케이스",
        "title": "CES 2027 세계 최대 IT 전시회 (온디바이스 AI / 로봇 / 자율주행)",
        "target_date_2026": "2027-01-06",
        "date_certainty": 1.0,
        "binary_risk": "LOW",
        "description": "연말(11~12월)부터 유입되는 글로벌 빅테크 혁신 기술 및 로봇/AI 테마 랠리",
        "beneficiary_sectors": ["온디바이스 AI", "휴머노이드/협동 로봇", "자율주행/전장", "스마트홈 가전"],
        "beneficiary_stocks": [
            {"ticker": "277810", "company": "레인보우로보틱스", "role": "삼성전자 연계 휴머노이드 로봇 신제품 공개"},
            {"ticker": "005930", "company": "삼성전자", "role": "차세대 온디바이스 AI 가전 쇼케이스"},
            {"ticker": "066570", "company": "LG전자", "role": "스마트 라이프 솔루션 및 전장/AI 홈"},
            {"ticker": "042700", "company": "한미반도체", "role": "차세대 HBM 본더 및 AI 반도체 장비"}
        ],
        "default_entry_window": "D-45 ~ D-15 (11월 중순 ~ 12월)",
        "default_exit_window": "D-1 ~ D+2 (개막 직전/당일)",
        "invalidating_rule": "빅테크 AI 투자 감축 보도 또는 행사 취소",
    },
    {
        "event_id": "galaxy_s27_cycle",
        "group_id": "06_tech_cycle",
        "group_name": "Tech Product Cycle",
        "strategy_name": "갤럭시 S / Z폴드 부품 공급망",
        "title": "삼성 갤럭시 S27 플래그십 언팩 사이클",
        "target_date_2026": "2027-01-20",
        "date_certainty": 0.85,
        "binary_risk": "LOW",
        "description": "연말(11~12월) 부품 공급 시작에 맞춘 선취매 랠리",
        "beneficiary_sectors": ["폴더블 힌지(Hinge)", "초박막강화유리(UTG)", "FPCB", "AI 스마트폰 부품"],
        "beneficiary_stocks": [
            {"ticker": "441270", "company": "파인엠텍", "role": "삼성 내장 힌지 독점 공급"},
            {"ticker": "060720", "company": "KH바텍", "role": "외장 힌지 전통 공급사"},
            {"ticker": "085670", "company": "뉴프렉스", "role": "스마트폰 카메라 FPCB 공급"},
            {"ticker": "005930", "company": "삼성전자", "role": "MX 사업부 플래그십 론칭 주체"}
        ],
        "default_entry_window": "D-60 ~ D-25 (11월 ~ 12월)",
        "default_exit_window": "D-5 ~ D0",
        "invalidating_rule": "출시 일정 연기 또는 공급사 교체",
    },
    # 07. Bio / Healthcare Catalyst
    {
        "event_id": "esmo_2026",
        "group_id": "07_bio_catalyst",
        "group_name": "Bio / Healthcare Catalyst",
        "strategy_name": "ESMO / AACR 유럽종양학회 모멘텀",
        "title": "ESMO 2026 유럽종양학회 (임상 초록 발표)",
        "target_date_2026": "2026-10-18",
        "date_certainty": 0.9,
        "binary_risk": "HIGH",
        "description": "학회 초록(Abstract) 공개 전후의 파이프라인 기대감 랠리",
        "beneficiary_sectors": ["항암 표적치료제", "면역항암제/이중항체", "ADC(항체약물접합체)", "기술수출(L/O) 유력 바이오"],
        "beneficiary_stocks": [
            {"ticker": "000100", "company": "유한양행", "role": "렉라자(레이저티닙) 글로벌 1차 병용 초록 발표"},
            {"ticker": "196170", "company": "알테오젠", "role": "SC 제형 피하주사 플랫폼 추가 파트너십"},
            {"ticker": "141080", "company": "리가켐바이오", "role": "차세대 ADC 항암 파이프라인 데이터 공개"}
        ],
        "default_entry_window": "D-50 ~ D-20 (8월 말 ~ 9월)",
        "default_exit_window": "D-5 ~ D-1 (학회 개막 직전 매도)",
        "invalidating_rule": "임상 유효성 지표 미달 또는 기술수출 계약 결렬",
    },
    {
        "event_id": "jpmhc_2027",
        "group_id": "07_bio_catalyst",
        "group_name": "Bio / Healthcare Catalyst",
        "strategy_name": "JP모건 헬스케어 컨퍼런스 (JPMHC)",
        "title": "JP모건 헬스케어 컨퍼런스 2027 (글로벌 빅파마 기술수출)",
        "target_date_2026": "2027-01-11",
        "date_certainty": 1.0,
        "binary_risk": "HIGH",
        "description": "11~12월부터 공식 초청 발표 및 글로벌 파트너링 미팅 기대감 선취매",
        "beneficiary_sectors": ["빅파마 초청 K-바이오", "글로벌 기술수출 유력사", "CDMO/바이오시밀러"],
        "beneficiary_stocks": [
            {"ticker": "196170", "company": "알테오젠", "role": "메인트랙 공식 발표 및 신규 제약사 계약 미팅"},
            {"ticker": "206650", "company": "유바이오로직스", "role": "글로벌 백신 공급 및 신규 파이프라인"},
            {"ticker": "310210", "company": "보로노이", "role": "표적치료제 글로벌 L/O 파트너십 논의"}
        ],
        "default_entry_window": "D-50 ~ D-20 (11월 중순 ~ 12월 초)",
        "default_exit_window": "D-3 ~ D0 (행사 개막 직전)",
        "invalidating_rule": "임상 중단 공시 또는 글로벌 기술수출 협상 결렬",
    },
    # 08. Game / Content / Entertainment
    {
        "event_id": "gstar_2026",
        "group_id": "08_game_content",
        "group_name": "Game / Content / Entertainment",
        "strategy_name": "지스타(G-STAR) & 신작 출시 사이클",
        "title": "G-STAR 2026 및 하반기 대작 게임 쇼케이스",
        "target_date_2026": "2026-11-19",
        "date_certainty": 0.95,
        "binary_risk": "MEDIUM",
        "description": "국내 최대 게임 전시회 전 신작 기대감 및 사전예약 지표 급증",
        "beneficiary_sectors": ["글로벌 PC/콘솔 대작 게임", "모바일 MMORPG", "웹툰/IP 게임화"],
        "beneficiary_stocks": [
            {"ticker": "259960", "company": "크래프톤", "role": "배틀그라운드 IP 및 신작 쇼케이스"},
            {"ticker": "036570", "company": "NC", "role": "차세대 대작 게임 시연 및 티징"},
            {"ticker": "134580", "company": "탑코미디어", "role": "인기 웹툰 IP 게임화 및 콘텐츠 밸류체인"}
        ],
        "default_entry_window": "D-60 ~ D-20",
        "default_exit_window": "D-5 ~ D0",
        "invalidating_rule": "사전예약률 부진 또는 출시일 연기",
    },
    # 09. Consumer / Travel / Shopping
    {
        "event_id": "singles_blackfriday_2026",
        "group_id": "09_consumer_shopping",
        "group_name": "Consumer / Travel / Shopping",
        "strategy_name": "광군제 / 블랙프라이데이 글로벌 쇼핑",
        "title": "중국 광군제(11.11) & 북미 블랙프라이데이 특수",
        "target_date_2026": "2026-11-11",
        "date_certainty": 1.0,
        "binary_risk": "LOW",
        "description": "K-뷰티/웹툰/소비재의 4분기 연간 최대 매출 시즌 선반영",
        "beneficiary_sectors": ["K-뷰티 / 인디 화장품 ODM", "글로벌 웹툰 플랫폼", "의류 OEM", "소비재/물류"],
        "beneficiary_stocks": [
            {"ticker": "192820", "company": "코스맥스", "role": "글로벌 인디 뷰티 1위 광군제/블프 수주 폭증"},
            {"ticker": "134580", "company": "탑코미디어", "role": "탑툰 글로벌 결제액 4분기 연간 최고치 달성"},
            {"ticker": "084870", "company": "TBH글로벌", "role": "중국/아시아 소비 시즌 의류 판매 랠리"},
            {"ticker": "111770", "company": "영원무역", "role": "북미 아웃도어 의류 OEM 수출 호조"}
        ],
        "default_entry_window": "D-60 ~ D-20 (9월 ~ 10월 중순)",
        "default_exit_window": "D-5 ~ D0",
        "invalidating_rule": "대중국 수출 규제 또는 소비 심리지수 급락",
    },
    # 10. Policy / Corporate / Special Situation
    {
        "event_id": "ipo_lockup_watch",
        "group_id": "10_special_situation",
        "group_name": "Policy / Special Situation",
        "strategy_name": "IPO 락업(의무보유) 해제 수급 리스크",
        "title": "대형 신규상장주 의무보유확약(락업) 해제 모니터링",
        "month_pattern": "dynamic_lockup",
        "target_date_2026": "2026-09-30",
        "date_certainty": 1.0,
        "binary_risk": "HIGH",
        "description": "락업 물량 > 10% 해제 시 기관 출회 매물 주의 및 해제 후 저점 탐색",
        "beneficiary_sectors": ["신규 상장 대형주 (오버행 주의)", "의무보유 소화 후 반등주"],
        "beneficiary_stocks": [
            {"ticker": "259960", "company": "크래프톤", "role": "상장 락업 해소 후 펀더멘털 저평가 반등"},
            {"ticker": "441270", "company": "파인엠텍", "role": "기관 보호예수 매물 소화 후 수급 안정화"}
        ],
        "default_entry_window": "D+5 ~ D+20 (해제 충격 소화 후)",
        "default_exit_window": "D+40",
        "invalidating_rule": "오버행 해소 전 추가 대량 블록딜 출회",
    },
]


def get_upcoming_events(as_of_date: str | None = None, horizon_days: int = 180) -> list[dict[str, Any]]:
    """Calculates D-Days and filters events within the forward horizon_days window (default 180 days for full year-end coverage)."""
    ref_dt = pd.to_datetime(as_of_date).date() if as_of_date else date.today()

    results: list[dict[str, Any]] = []

    for ev in EVENT_CATALOG:
        t_str = ev.get("target_date_2026")
        if not t_str:
            if ev.get("month_pattern") == "every_month_end":
                m_end = pd.Timestamp(ref_dt).replace(day=ev.get("base_day", 28)).date()
                if m_end < ref_dt:
                    m_end = (pd.Timestamp(ref_dt) + pd.DateOffset(months=1)).replace(day=ev.get("base_day", 28)).date()
                t_str = str(m_end)
            else:
                continue

        ev_date = pd.to_datetime(t_str).date()
        d_day = (ev_date - ref_dt).days

        if d_day < -10 or d_day > horizon_days:
            continue

        if d_day <= 7:
            horizon_tag = "upcoming_7d"
        elif d_day <= 30:
            horizon_tag = "upcoming_30d"
        elif d_day <= 90:
            horizon_tag = "upcoming_90d"
        else:
            horizon_tag = "upcoming_180d"

        results.append({
            "event_id": ev["event_id"],
            "group_id": ev["group_id"],
            "group_name": ev["group_name"],
            "strategy_name": ev["strategy_name"],
            "title": ev["title"],
            "target_date": t_str,
            "d_day": d_day,
            "horizon_tag": horizon_tag,
            "date_certainty": ev["date_certainty"],
            "binary_risk": ev["binary_risk"],
            "description": ev["description"],
            "beneficiary_sectors": ev.get("beneficiary_sectors", []),
            "beneficiary_stocks": ev.get("beneficiary_stocks", []),
            "default_entry_window": ev["default_entry_window"],
            "default_exit_window": ev["default_exit_window"],
            "invalidating_rule": ev["invalidating_rule"],
        })

    results.sort(key=lambda x: x["d_day"])
    return results
