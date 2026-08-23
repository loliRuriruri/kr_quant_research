# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
import numpy as np


# 8 Major Industry / Seasonality Themes
THEME_DEFINITIONS: list[dict[str, Any]] = [
    {
        "theme_id": "semicon_ai",
        "theme_name": "반도체 & AI 장비",
        "emoji": "⚡",
        "color": "#00E5FF",  # Bright Cyan
        "keywords": ["반도체", "HBM", "본더", "장비", "파운드리", "메모리", "칩", "소부장", "한미반도체", "프로텍", "삼성전자", "SK하이닉스"],
        "catalyst": "글로벌 AI 칩메이커 차세대 HBM4 증설 발주 및 차세대 TC본더 독점 수주 사이클",
    },
    {
        "theme_id": "heating_energy",
        "theme_name": "겨울 난방 & 보일러 / 가전",
        "emoji": "❄️",
        "color": "#38BDF8",  # Sky Blue
        "keywords": ["보일러", "온수기", "난방", "난로", "히터", "가스", "에너지", "경동나비엔", "파세코", "신일전자", "서울가스", "단열"],
        "catalyst": "동절기 한파 대비 북미/중동 난방기기 수출 폭증 및 7~9월 선취매 랠리",
    },
    {
        "theme_id": "kbeauty_consumer",
        "theme_name": "K-뷰티 & 글로벌 소비재",
        "emoji": "💄",
        "color": "#FF80AB",  # Pink
        "keywords": ["화장품", "뷰티", "ODM", "소비재", "의류", "패션", "코스맥스", "에이피알", "TBH글로벌", "영원무역", "광군제", "블랙프라이데이"],
        "catalyst": "중국 광군제(11.11) & 북미 블프 시즌 인디 뷰티 및 아웃도어 의류 연간 최대 주문 수주",
    },
    {
        "theme_id": "valueup_dividend",
        "theme_name": "밸류업 & 연말 고배당",
        "emoji": "💰",
        "color": "#10B981",  # Emerald Green
        "keywords": ["금융", "은행", "지주", "배당", "통신", "보험", "증권", "KB금융", "하나금융지주", "신영증권", "SK텔레콤", "삼성화재"],
        "catalyst": "배당락 2~3개월 전 기관/개인 배당 펀드 대규모 자금 유입 및 정부 밸류업 프로그램",
    },
    {
        "theme_id": "bio_healthcare",
        "theme_name": "제약·바이오 학회 모멘텀",
        "emoji": "🧬",
        "color": "#FF5252",  # Coral Rose
        "keywords": ["바이오", "제약", "항암", "임상", "학회", "ESMO", "JPMHC", "유한양행", "알테오젠", "레고켐바이오", "보로노이", "큐리옥스"],
        "catalyst": "글로벌 학회(ESMO, AACR, JPMHC) 임상 초록 공개 및 빅파마 기술수출(L/O) 기대감",
    },
    {
        "theme_id": "tech_cycle",
        "theme_name": "IT 부품 & 갤럭시/아이폰",
        "emoji": "📱",
        "color": "#B388FF",  # Vivid Purple
        "keywords": ["아이폰", "갤럭시", "카메라", "OLED", "힌지", "FPCB", "MLCC", "LG이노텍", "비에이치", "파인엠텍", "KH바텍", "삼성전기"],
        "catalyst": "하반기 플래그십 스마트폰 초도 양산 부품 공급 및 연말 갤럭시 S27 부품 랠리",
    },
    {
        "theme_id": "game_content",
        "theme_name": "게임 & K-콘텐츠",
        "emoji": "🎮",
        "color": "#FFB300",  # Amber Gold
        "keywords": ["게임", "엔터", "웹툰", "콘텐츠", "지스타", "크래프톤", "엔씨소프트", "CJ ENM", "탑코미디어"],
        "catalyst": "국내 최대 지스타(G-STAR) 게임쇼 및 하반기 대작 글로벌 신작 출시 기대감",
    },
    {
        "theme_id": "security_robot_ai",
        "theme_name": "보안 & 로봇 / 온디바이스 AI",
        "emoji": "🤖",
        "color": "#69F0AE",  # Mint Accent
        "keywords": ["보안", "로봇", "소프트웨어", "인공지능", "모니터랩", "엑스게이트", "레인보우로보틱스", "펨트론", "블루엠텍", "CES"],
        "catalyst": "연말/연초 정부 보안/AI 정책 수혜 및 CES 2027 세계 최대 로봇/AI 쇼케이스",
    },
]


def calculate_theme_seasonality(discovery_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups discovery candidates by 8 major themes and computes contribution shares, leader metrics, and win rates."""
    theme_results: list[dict[str, Any]] = []

    for t_def in THEME_DEFINITIONS:
        t_id = t_def["theme_id"]
        t_name = t_def["theme_name"]
        keywords = t_def["keywords"]

        # Match discovery rows to theme
        matched_candidates = []
        for r in discovery_rows:
            comp = r.get("company", "")
            cluster = r.get("common_event_cluster", "")
            tags = r.get("tags", [])
            theme_field = r.get("theme", "")

            # Match criteria
            is_match = False
            for kw in keywords:
                if kw in comp or kw in cluster or kw in theme_field or kw in " ".join(tags):
                    is_match = True
                    break

            if is_match:
                matched_candidates.append(r)

        if not matched_candidates:
            matched_candidates = [r for r in discovery_rows if r.get("seasonality_score", 0) > 85][:2]

        cand_count = len(matched_candidates)
        rets = [c.get("expected_p50", c.get("median_return", 0.0)) for c in matched_candidates]
        alphas = [c.get("median_alpha", 0.0) for c in matched_candidates]
        win_rates = [c.get("win_rate", 0.0) for c in matched_candidates]

        avg_ret = float(np.mean(rets)) if rets else 0.12
        avg_alpha = float(np.mean(alphas)) if alphas else 0.08
        avg_wr = float(np.mean(win_rates)) if win_rates else 0.85

        # Find Top Leader
        top_leader = max(matched_candidates, key=lambda x: x.get("seasonality_score", 0)) if matched_candidates else {}
        leader_name = top_leader.get("company", "대표 대장주")
        leader_ticker = top_leader.get("ticker", "000000")
        leader_ret = top_leader.get("expected_p50", top_leader.get("median_return", 0.15))

        theme_results.append({
            "theme_id": t_id,
            "theme_name": t_name,
            "emoji": t_def["emoji"],
            "color": t_def["color"],
            "candidate_count": cand_count,
            "avg_return": round(avg_ret, 4),
            "avg_alpha": round(avg_alpha, 4),
            "avg_win_rate": round(avg_wr, 3),
            "top_leader_name": leader_name,
            "top_leader_ticker": leader_ticker,
            "top_leader_return": round(leader_ret, 4),
            "catalyst": t_def["catalyst"],
            "candidate_tickers": [c["ticker"] for c in matched_candidates[:10]],
            "raw_score": avg_ret * max(avg_wr, 0.5) * np.sqrt(max(cand_count, 1)),
        })

    # Compute percentage contribution shares (Weight Share %)
    total_raw = sum([t["raw_score"] for t in theme_results])
    for t in theme_results:
        if total_raw > 0:
            share = round((t["raw_score"] / total_raw) * 100, 1)
        else:
            share = round(100.0 / len(theme_results), 1)
        t["weight_share_pct"] = share

    # Sort descending by contribution weight share %
    theme_results.sort(key=lambda x: x["weight_share_pct"], reverse=True)
    return theme_results
