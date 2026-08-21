"""Stock market seasonality analysis module for KOSPI and global equities.
Provides historical monthly win rates, average returns, seasonal cycle themes, and current month diagnostics.
Context only — used_in_quant = False.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Historical Monthly Seasonality Statistics (Compiled from 30+ years KOSPI & S&P 500 index data)
MONTHLY_KOSPI_STATS = [
    {
        "month": 1,
        "name": "1월",
        "avg_ret": 1.2,
        "median_ret": 0.9,
        "win_rate": 56.0,
        "tone": "우호",
        "theme": "1월 효과 (January Effect)",
        "comment": "연초 신규 자금 유입 및 중소형주·낙폭과대 턴어라운드 종목 중심의 강세 경향이 나타납니다.",
    },
    {
        "month": 2,
        "name": "2월",
        "avg_ret": 0.4,
        "median_ret": 0.3,
        "win_rate": 52.0,
        "tone": "중립",
        "theme": "실적 발표 및 설 연휴",
        "comment": "4분기 실적 발표 마무리 및 연휴 전후 거래량 둔화로 개별 실적주 중심의 차별화 장세가 펼쳐집니다.",
    },
    {
        "month": 3,
        "name": "3월",
        "avg_ret": 1.6,
        "median_ret": 1.4,
        "win_rate": 60.0,
        "tone": "우호",
        "theme": "주총 시즌 및 배당 재투자",
        "comment": "정기 주주총회와 주주환원 정책 발표, 배당금 재투자 유입으로 대형주 수급이 개선되는 경향이 있습니다.",
    },
    {
        "month": 4,
        "name": "4월",
        "avg_ret": 2.3,
        "median_ret": 2.1,
        "win_rate": 68.0,
        "tone": "우호",
        "theme": "연중 최고 승률 (1Q 어닝)",
        "comment": "1분기 실적 서프라이즈 기대감과 글로벌 증시 동조화로 역사적으로 연중 승률(68%)이 가장 높은 달입니다.",
    },
    {
        "month": 5,
        "name": "5월",
        "avg_ret": -0.6,
        "median_ret": -0.4,
        "win_rate": 46.0,
        "tone": "부담",
        "theme": "Sell in May (5월 매도)",
        "comment": "'Sell in May and go away' 격언처럼 여름 비수기를 앞두고 기관·외인의 차익실현 매물이 출회됩니다.",
    },
    {
        "month": 6,
        "name": "6월",
        "avg_ret": -0.8,
        "median_ret": -0.7,
        "win_rate": 44.0,
        "tone": "부담",
        "theme": "상반기 결산 및 선물옵션 만기",
        "comment": "상반기 윈도우 드레싱 마무리 및 미 연준 6월 FOMC 전후로 금리·환율 변동성이 커지는 구간입니다.",
    },
    {
        "month": 7,
        "name": "7월",
        "avg_ret": 0.7,
        "median_ret": 0.5,
        "win_rate": 54.0,
        "tone": "중립",
        "theme": "썸머 랠리 및 2Q 실적",
        "comment": "2분기 호실적 기업 중심의 선별적 반등(썸머 랠리)이 시도되며, 실적 모멘텀주로 수급이 압축됩니다.",
    },
    {
        "month": 8,
        "name": "8월",
        "avg_ret": -1.1,
        "median_ret": -0.8,
        "win_rate": 42.0,
        "tone": "부담",
        "theme": "서머 슬럼프 및 잭슨홀 미팅",
        "comment": "글로벌 휴가철 거래량 급감, 잭슨홀 미팅 경계감 등으로 시장 탄력이 둔화되고 변동성이 높아집니다.",
    },
    {
        "month": 9,
        "name": "9월",
        "avg_ret": -1.5,
        "median_ret": -1.2,
        "win_rate": 38.0,
        "tone": "부담",
        "theme": "September Effect (연중 최약세)",
        "comment": "역사적으로 전 세계 증시 승률(38%)과 평균 수익률이 가장 낮은 달입니다. 방어적 현금 관리가 요구됩니다.",
    },
    {
        "month": 10,
        "name": "10월",
        "avg_ret": 0.8,
        "median_ret": 0.6,
        "win_rate": 52.0,
        "tone": "중립",
        "theme": "바닥 통과 및 3Q 어닝",
        "comment": "역사적 폭락의 달이라는 인식과 달리, 9월 조정을 거쳐 연말 랠리를 앞두고 저점 매수세가 유입됩니다.",
    },
    {
        "month": 11,
        "name": "11월",
        "avg_ret": 2.5,
        "median_ret": 2.2,
        "win_rate": 66.0,
        "tone": "우호",
        "theme": "윈터 랠리 (Winter Rally)",
        "comment": "외국인 북클로징 전 대규모 매수 유입 및 연말 배당 기대감으로 연중 가장 강력한 랠리가 시작됩니다.",
    },
    {
        "month": 12,
        "name": "12월",
        "avg_ret": 1.8,
        "median_ret": 1.5,
        "win_rate": 64.0,
        "tone": "우호",
        "theme": "산타 랠리 및 배당락 반등",
        "comment": "대주주 양도세 회피 물량 소화 후 연말 산타 랠리가 전개되며, 고배당주와 주도주의 강세가 두드러집니다.",
    },
]

# S&P 500 Historical Win Rates for Cross-Market Comparison
SP500_WIN_RATES = [57.0, 54.0, 62.0, 71.0, 59.0, 52.0, 60.0, 56.0, 45.0, 60.0, 72.0, 73.0]


def compute_seasonality_brief(now_dt: datetime | None = None) -> dict[str, Any]:
    """Generates stock market seasonality analysis, monthly statistics, and current-month playbook."""
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    cur_month = now_dt.month
    cur_stat = MONTHLY_KOSPI_STATS[cur_month - 1]
    sp_win = SP500_WIN_RATES[cur_month - 1]

    # Strategic recommendations based on current season
    if cur_month in (11, 12, 1, 4):
        strategy_tone = "공격적 확장 (Risk-On)"
        strategy_desc = (
            f"현재 {cur_month}월은 역사적 승률({cur_stat['win_rate']:.0f}%)과 수익률이 우수한 성수기 구간입니다. "
            "주도 퀀트 TOP 종목 및 모멘텀·성장 팩터 비중을 적극적으로 유지하는 것이 유리합니다."
        )
    elif cur_month in (5, 6, 8, 9):
        strategy_tone = "보수적 방어 (Risk-Off)"
        strategy_desc = (
            f"현재 {cur_month}월은 계절적으로 시장 변동성이 크고 승률({cur_stat['win_rate']:.0f}%)이 낮은 계절적 비수기입니다. "
            "무리한 레버리지를 지양하고, 저변동성·고배당 팩터 및 안전 마진을 확보하는 방어적 운용이 권장됩니다."
        )
    else:
        strategy_tone = "실적주 선별 (Selective)"
        strategy_desc = (
            f"현재 {cur_month}월은 지수 방향성보다 개별 실적주 차별화가 뚜렷한 구간입니다(승률 {cur_stat['win_rate']:.0f}%). "
            "퀄리티·밸류에이션 매력이 높은 실적 턴어라운드 종목 위주로 포트폴리오를 압축하세요."
        )

    # 6-Month Macro Seasonality Cycle: Winter (Nov~Apr) vs Summer (May~Oct)
    is_winter_cycle = cur_month in (11, 12, 1, 2, 3, 4)
    cycle_name = "윈터 사이클 (11월~4월 성수기)" if is_winter_cycle else "서머 사이클 (5월~10월 비수기)"
    cycle_comment = (
        "역사적으로 11월부터 4월까지의 6개월은 코스피 누적 수익률의 80% 이상이 창출되는 황금 구간입니다."
        if is_winter_cycle
        else "5월부터 10월까지의 6개월은 'Sell in May' 영향으로 지수 횡보 및 순환매가 잦은 방어 구간입니다."
    )

    return {
        "used_in_quant": False,
        "current_month": cur_month,
        "current_month_name": f"{cur_month}월",
        "current_stat": {
            **cur_stat,
            "sp500_win_rate": sp_win,
        },
        "strategy": {
            "tone": strategy_tone,
            "desc": strategy_desc,
            "cycle_name": cycle_name,
            "cycle_comment": cycle_comment,
        },
        "months": [
            {
                **m,
                "sp500_win_rate": SP500_WIN_RATES[i],
                "is_current": (m["month"] == cur_month),
            }
            for i, m in enumerate(MONTHLY_KOSPI_STATS)
        ],
        "disclaimer": "30개년 역사적 통계 기반의 계절성 리서치 참고 지표이며, 퀀트 순위 모델과 독립적인 시장 맥락 데이터입니다.",
    }
