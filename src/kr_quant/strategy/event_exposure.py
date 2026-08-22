# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

# Company Revenue Exposure & Event Sensitivity Matrix
EVENT_EXPOSURES: dict[str, list[dict[str, Any]]] = {
    # 009450 경동나비엔
    "009450": [
        {
            "event_id": "winter_heating_surge",
            "exposure_score": 0.90,
            "exposure_desc": "북미 콘덴싱 보일러 + 공기열 히트펌프 매출 비중 70%+",
            "sensitivity": "HIGH",
        },
        {
            "event_id": "q3_earnings_pead",
            "exposure_score": 0.85,
            "exposure_desc": "3분기 난방 성수기 진입 전 영업이익 흑자 서프라이즈 모멘텀",
            "sensitivity": "HIGH",
        }
    ],
    # 037070 파세코
    "037070": [
        {
            "event_id": "summer_heatwave",
            "exposure_score": 0.85,
            "exposure_desc": "창문형 에어컨 국내 1위 및 계절가전 폭염 수혜",
            "sensitivity": "HIGH",
        },
        {
            "event_id": "winter_heating_surge",
            "exposure_score": 0.80,
            "exposure_desc": "석유/캠핑용 난로 북미/중동 수출 성수기",
            "sensitivity": "HIGH",
        }
    ],
    # 441270 파인엠텍
    "441270": [
        {
            "event_id": "galaxy_s27_cycle",
            "exposure_score": 0.85,
            "exposure_desc": "삼성전자 폴더블 스마트폰 내장 힌지(Hinge) 독점 공급",
            "sensitivity": "HIGH",
        }
    ],
    # 134580 탑코미디어
    "134580": [
        {
            "event_id": "singles_blackfriday_2026",
            "exposure_score": 0.80,
            "exposure_desc": "탑툰 일본/글로벌 플랫폼 하반기 결제액 급증 및 콘텐츠 특수",
            "sensitivity": "HIGH",
        }
    ],
    # 011070 LG이노텍
    "011070": [
        {
            "event_id": "apple_iphone_18",
            "exposure_score": 0.95,
            "exposure_desc": "Apple iPhone 고사양 카메라 모듈(폴디드줌) 매출 비중 75%+",
            "sensitivity": "HIGH",
        }
    ],
    # 090460 비에이치
    "090460": [
        {
            "event_id": "apple_iphone_18",
            "exposure_score": 0.90,
            "exposure_desc": "iPhone용 FPCB(연성인쇄회로기판) 핵심 공급",
            "sensitivity": "HIGH",
        }
    ],
    # 105560 KB금융
    "105560": [
        {
            "event_id": "year_end_dividend",
            "exposure_score": 0.95,
            "exposure_desc": "예상 배당수익률 5.5%+ 및 분기 균등배당/자사주 소각 밸류업 1위",
            "sensitivity": "HIGH",
        },
        {
            "event_id": "msci_aug_2026",
            "exposure_score": 0.85,
            "exposure_desc": "MSCI Korea 지수 내 금융 섹터 최상위 비중",
            "sensitivity": "HIGH",
        }
    ],
    # 000100 유한양행
    "000100": [
        {
            "event_id": "esmo_2026",
            "exposure_score": 0.85,
            "exposure_desc": "렉라자(레이저티닙) 글로벌 1차 치료제 승인 및 ESMO 추가 임상 데이터",
            "sensitivity": "HIGH",
        }
    ],
    # 192820 코스맥스
    "192820": [
        {
            "event_id": "singles_blackfriday_2026",
            "exposure_score": 0.90,
            "exposure_desc": "중국/미국 인디 뷰티 브랜드 ODM 1위, 광군제 오더 집중",
            "sensitivity": "HIGH",
        }
    ],
    # 259960 크래프톤
    "259960": [
        {
            "event_id": "gstar_2026",
            "exposure_score": 0.85,
            "exposure_desc": "배틀그라운드 IP 인도 매출 급증 및 다크앤다커 모바일 신작 론칭",
            "sensitivity": "HIGH",
        }
    ],
    # 005930 삼성전자
    "005930": [
        {
            "event_id": "tom_monthly",
            "exposure_score": 0.95,
            "exposure_desc": "KOSPI 시총 1위로 월말 윈도드레싱 및 패시브 인덱스 수급 집중",
            "sensitivity": "HIGH",
        },
        {
            "event_id": "galaxy_s27_cycle",
            "exposure_score": 0.80,
            "exposure_desc": "MX(스마트폰) 부문 신제품 출시 및 AI 스마트폰 슈퍼사이클",
            "sensitivity": "MEDIUM",
        }
    ],
    # 000660 SK하이닉스
    "000660": [
        {
            "event_id": "tom_monthly",
            "exposure_score": 0.95,
            "exposure_desc": "KOSPI 시총 2위 및 외국인 패시브 수급 최우선 타겟",
            "sensitivity": "HIGH",
        }
    ]
}


def get_stock_event_exposure(ticker: str, event_id: str) -> dict[str, Any]:
    """Gets the exposure score and description for a specific stock and event."""
    code = str(ticker).zfill(6)
    records = EVENT_EXPOSURES.get(code, [])
    for rec in records:
        if rec["event_id"] == event_id:
            return rec
    # Default fallback exposure
    return {
        "event_id": event_id,
        "exposure_score": 0.50,
        "exposure_desc": "산업 연관성 및 계절적 수급 반영",
        "sensitivity": "MEDIUM",
    }
