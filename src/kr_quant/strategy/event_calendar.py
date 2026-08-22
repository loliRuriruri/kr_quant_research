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
    default_entry_window: str  # e.g. "D-60 ~ D-40"
    default_exit_window: str   # e.g. "D-5 ~ D0"
    invalidating_rule: str


# 10 Major Event Categories & 15 MVP Institutional Event Strategies
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
        "default_entry_window": "D-5 ~ D-2",
        "default_exit_window": "D+3 ~ D+5",
        "invalidating_rule": "글로벌 매크로 급변 및 환율 급등",
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
        "default_entry_window": "D-75 ~ D-40 (7월 하순 ~ 9월 초)",
        "default_exit_window": "D-5 ~ D+10",
        "invalidating_rule": "이상 고온(Warm Winter) 예보 또는 3분기 실적 역성장",
    },
    {
        "event_id": "summer_heatwave",
        "group_id": "05_weather",
        "group_name": "Weather & Power Demand",
        "strategy_name": "여름 폭염 · 냉방 · 전력 피크",
        "title": "여름 폭염 & 냉방/제습기 선취매 랠리",
        "target_date_2026": "2026-07-01",
        "date_certainty": 0.85,
        "binary_risk": "LOW",
        "description": "본격 폭염 시작 전 4~6월 선반영 급등 및 전력망 부하 수혜",
        "default_entry_window": "D-60 ~ D-20 (4월 ~ 5월)",
        "default_exit_window": "D-5 ~ D0 (7월 초)",
        "invalidating_rule": "초여름 저온 현상 및 장기 장마",
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
        "default_entry_window": "D-60 ~ D-20 (7월 ~ 8월 중순)",
        "default_exit_window": "D-3 ~ D+3",
        "invalidating_rule": "초도 물량 감산 보도 또는 수율 이슈",
    },
    {
        "event_id": "galaxy_s27_cycle",
        "group_id": "06_tech_cycle",
        "group_name": "Tech Product Cycle",
        "strategy_name": "갤럭시 S / Z폴드 부품 공급망",
        "title": "삼성 갤럭시 차세대 플래그십 언팩 사이클",
        "target_date_2026": "2027-01-20",
        "date_certainty": 0.85,
        "binary_risk": "LOW",
        "description": "연말(11~12월) 부품 공급 시작에 맞춘 선취매 랠리",
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
        "default_entry_window": "D-50 ~ D-20 (8월 말 ~ 9월)",
        "default_exit_window": "D-5 ~ D-1 (학회 개막 직전 매도)",
        "invalidating_rule": "임상 유효성 지표 미달 또는 기술수출 계약 결렬",
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
        "default_entry_window": "D+5 ~ D+20 (해제 충격 소화 후)",
        "default_exit_window": "D+40",
        "invalidating_rule": "오버행 해소 전 추가 대량 블록딜 출회",
    },
]


def get_upcoming_events(as_of_date: str | None = None, horizon_days: int = 90) -> list[dict[str, Any]]:
    """Calculates D-Days and filters events within the forward horizon_days window."""
    ref_dt = pd.to_datetime(as_of_date).date() if as_of_date else date.today()

    results: list[dict[str, Any]] = []

    for ev in EVENT_CATALOG:
        t_str = ev.get("target_date_2026")
        if not t_str:
            # Handle monthly recurring (like TOM)
            if ev.get("month_pattern") == "every_month_end":
                # Compute current month end or next month end
                m_end = pd.Timestamp(ref_dt).replace(day=ev.get("base_day", 28)).date()
                if m_end < ref_dt:
                    m_end = (pd.Timestamp(ref_dt) + pd.DateOffset(months=1)).replace(day=ev.get("base_day", 28)).date()
                t_str = str(m_end)
            else:
                continue

        ev_date = pd.to_datetime(t_str).date()
        d_day = (ev_date - ref_dt).days

        # Classify horizon window
        if d_day < -10 or d_day > horizon_days:
            continue

        if d_day <= 7:
            horizon_tag = "upcoming_7d"
        elif d_day <= 30:
            horizon_tag = "upcoming_30d"
        else:
            horizon_tag = "upcoming_90d"

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
            "default_entry_window": ev["default_entry_window"],
            "default_exit_window": ev["default_exit_window"],
            "invalidating_rule": ev["invalidating_rule"],
        })

    results.sort(key=lambda x: x["d_day"])
    return results
