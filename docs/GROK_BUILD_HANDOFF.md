# KR Quant Research — 기준 핸드오프 (v1.3 P0/P1)

적용 런타임: `C:\Users\a4jud\kr_quant_research` FastAPI 대시보드 (`:8790`).  
Streamlit 페이지를 새로 만들지 않는다. 기존 화면과 FastAPI 구조를 보존한다.

참고 분석(복제 금지):
- `docs/FASTJUSIK_PENSION_REFERENCE_ANALYSIS.md` — fastjusik.com/pension 화면 구조 분석
- `docs/GROK_BUILD_KR_QUANT_V1_3_FASTJUSIK_FLOW_EVENT_ADDENDUM.md` — 독립 구현 명세

## 절대 조건

- Fundamental Quant는 결정론. 수급·손자 五事·LLM은 `used_in_quant=false`.
- 한국 가격 정본은 KRX, 재무는 OpenDART. KIS는 수급·교차검증 전용 READ-ONLY.
- Fastjusik 소스·공개 API·브랜드·문구·데이터를 복사하거나 런타임 의존하지 않는다.
- API 키는 `.env`에만 두고 코드·문서·화면에 원문을 넣지 않는다.
- KIS `FUND`는 원천이 “연기금/국민연금”이라고 명시하지 않는 한 그 이름으로 부르지 않는다. 화면 표기는 **기금**.
- 종목별 일별 투자자 API는 관심종목·고유동성부터. 공식 전종목 bulk가 확인되기 전 전 종목 기금 순위를 표시하지 않는다.
- 주문·매수매도 신호·투자 조언을 만들지 않는다.

## 현재 구현 및 검증 완료 상태 (2026-08-21 기준)

1. **KIS 수급 (Flow Engine P0/P1)**:
   - `investor_flows_daily` DuckDB 스키마 + upsert/coverage (`src/kr_quant/flow/store.py`)
   - 수급 연속일수(streak), 동반매수(double buy), 방향전환(reversal) 감지 (`src/kr_quant/flow/events.py`, `src/kr_quant/flow/official.py`)
   - 종목별 90일 차트 및 윈도우 합계 (`ticker_payload`)
2. **국민연금 5%+ 대량보유 (Holdings Engine)**:
   - OpenDART 대량보유 보고서 파싱, 지분율 및 증감 추적 (`src/kr_quant/ownership/nps.py`)
   - FastAPI `GET /api/nps` 및 대시보드 `view-nps` 탭 연동
3. **DART 공시 이벤트 분류 및 백테스트 (Event & Backtest Engine)**:
   - 잠정실적, 대형수주, 자사주, 유상증자/CB/BW 자동 분류 (`src/kr_quant/events/classify.py`)
   - 공시 후 1D/5D/20D/60D 가격 수익률, BM 대비 초과수익률, 승률, MFE/MAE 일괄 백테스트 엔진 (`src/kr_quant/events/backtest.py`)
   - FastAPI `GET /api/events/backtest` 엔드포인트 연동
4. **자체 한국형 공포·탐욕 지수 (Internal Korea Fear & Greed / KR Market Sentiment)**:
   - KRX 전종목 및 외인 5일 수급 기반 100점 만점 자체 감성 지표 엔진 (`src/kr_quant/context/market_sentiment.py`)
   - 시장 모멘텀(20) + 상승/하락 확산(20) + 신고/신저(15) + 변동성(15) + 거래대금(15) + 외인수급(15)
   - 손자병법 `天(시장 국면)` 및 대시보드 시장 국면 API 연동
5. **업종(Sector) 6축 랭킹 엔진 (Sector Ranking Engine)**:
   - KSIC 업종별 상대강도(RS 25), 확산(20), 실적(20), 유동성(15), 가치(10), 가속(10) 평가 및 선행/개선/보통/약화/부진 상태 분류 (`src/kr_quant/sector/ranking.py`)
6. **손자병법 道天地將法 & 타이밍 (Sunzi & Timing Research Engine)**:
   - 天(시장국면), 地(업종), 將(AI/경영), 道(미션/해자), 法(품질/데이터 게이트) 통합 오버레이 (`src/kr_quant/sunzi/five.py`, `src/kr_quant/sunzi/fa.py`)
   - 단기(20D), 중기(60D), 장기(252D) 멀티 타임프레임 추세/거래량 상태/신뢰도 산출 (`src/kr_quant/timing/research.py`)
7. **UI 시인성 및 비주얼 디자인 개선**:
   - 1/2/3등 메탈릭 메달 배지(Gold/Silver/Bronze), 고득점 점수 필(Pill), 한국형 공포탐욕 게이지 카드, 업종/승률 컬러 배지 적용 (`styles.css`, `app.js`)
8. **테스트 검증**:
   - `pytest` 전체 34개 테스트 스위트 100% PASS 확인 완료.

## 파일 매핑

| 역할 | 파일 | 상태 |
|---|---|---|
| 수급 유형 정규화 / DuckDB | `src/kr_quant/flow/types.py`, `src/kr_quant/flow/store.py` | 완료 |
| KIS 수급 어댑터 및 수집 | `src/kr_quant/ingest/kis.py`, `src/kr_quant/flow/official.py` | 완료 |
| 국민연금 5% 대량보유 | `src/kr_quant/ownership/nps.py` | 완료 |
| DART 공시 이벤트 분류 | `src/kr_quant/events/classify.py`, `src/kr_quant/events/filings.py` | 완료 |
| DART 이벤트 포워드 백테스트 | `src/kr_quant/events/backtest.py` | 완료 |
| 한국형 공포·탐욕 지수 | `src/kr_quant/context/market_sentiment.py` | 완료 |
| 업종 6축 랭킹 엔진 | `src/kr_quant/sector/ranking.py` | 완료 |
| 손자병법 道天地將法 | `src/kr_quant/sunzi/five.py`, `src/kr_quant/sunzi/fa.py` | 완료 |
| 멀티 타임프레임 타이밍 | `src/kr_quant/timing/research.py` | 완료 |
| 화면 연동 및 UI 시인성 | `src/kr_quant/web/app.py`, `src/kr_quant/web/static/` | 완료 |

## 다음 고도화 과제 (Roadmap)

1. **DART 공시 이벤트 대규모 사후 검증 (Forward Return Backtest Engine)**:
   - 공시 이벤트 유형별 5D/20D/60D 누적 수익률, BM 대비 초과수익률, 승률, MFE/MAE 일괄 계산 배치.
2. **한국형 공포탐욕 지수 (Internal Korea Fear & Greed)**:
   - KOSPI 모멘텀(20) + Breadth(20) + 신고/신저(15) + 변동성(15) + 거래대금(15) + 외인수급(15) 자체 점수화.
3. **업종(Sector) 6축 랭킹 엔진 & 일별 히스토리**:
   - KSIC 업종별 상대강도 및 실적 개선율 일별 테이블 캐싱 및 랭킹 세부 튜닝.
