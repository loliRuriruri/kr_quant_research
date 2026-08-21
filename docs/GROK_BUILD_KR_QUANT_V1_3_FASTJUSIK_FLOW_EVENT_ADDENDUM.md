# KR Quant Research v1.3
## FASTJUSIK-Inspired Flow / Event / Sentiment Research Addendum
### Grok Build Incremental Specification

> 적용 대상: `C:\Users\a4jud\kr_quant_research`
>
> 기준일: 2026-08-20
>
> 목적: 현재 Grok Build의 **결정론적 Fundamental Quant + KRX/OpenDART + FastAPI 운영 구조를 유지**하면서, FASTJUSIK의 공개 페이지에서 확인되는 유용한 연구 패턴을 참고해 연기금/외국인 Flow, 방향전환, 국민연금 5%+ 보유지분, Rebalancing, 한국형 시장심리, DART Event/Surprise, Event Forward Return, Strategic Holdings, 손자병법 `道天地將法` 연결을 독립 구현한다.
>
> 이 문서는 FASTJUSIK의 소스코드, CSS, JS, 이미지, 문구, 비공개 API를 복제하기 위한 문서가 아니다. 공개 화면에서 확인 가능한 **기능적 아이디어와 정보 구조를 분석해 자체 구현**하기 위한 명세다.

---

# 0. 절대 유지할 기존 Grok Build 원칙

## 0.1 Fundamental Quant는 결정론

Quant Score는 Python 코드만 계산한다.

AI / 뉴스 / 수급 / 기술 / 이벤트 / 연기금 / 손자 五事는 Fundamental Quant Score를 임의로 수정하지 않는다.

```yaml
overlays:
  used_in_quant: false
```

## 0.2 공식 정본

- 한국 주식 가격/마스터: `KRX Open API = canonical`
- 재무/공시: `OpenDART = canonical`
- KIS/Toss: 수급, 교차검증, read-only market data
- Naver: news discovery
- FRED/ECOS: macro context
- LLM: qualitative research only

## 0.3 자동매매 금지

다음을 구현하지 않는다.

- 시장가/지정가 주문
- 정정/취소
- 자동 체결
- 포지션 변경
- 잔고 기반 주문
- 주문 버튼

증권 API는 READ-ONLY로 유지한다.

## 0.4 Point-in-Time

모든 research event는 가능한 범위에서 다음을 유지한다.

```text
event_date
available_at
value_date
fetched_at
source
run_id
model_version
```

미래 공시/가격/확정 데이터를 과거 이벤트 생성에 사용하지 않는다.

---

# 1. FASTJUSIK에서 참고할 핵심 개념

## 1.1 Flow

- 연기금 당일 순매수/순매도
- 연속 순매수/순매도
- 연속일수
- 연속기간 누적금액
- 1주/1개월/장기 누적
- 연기금+외국인 동반매매
- 5거래일 이상 한 방향 후 방향전환
- 전체 시장 연기금 순매수 추이
- KOSPI/KOSDAQ 분리

## 1.2 Holdings

- 국민연금 5% 이상 DART 대량보유 공시
- 지분율
- 직전 보고 대비 지분율 변화
- 보유주식수
- 최근 가격 기준 참고 평가액

## 1.3 Rebalancing

- 시장 전체 연기금 순매수/순매도
- 매도가 특정 업종/대형주에 집중되는지
- 시장 전체가 매도인데 선택적으로 순매수되는 종목

## 1.4 Sentiment

한국 시장 전종목을 이용한 자체 공포탐욕 구조:

- 시장 모멘텀
- 상승/하락 breadth
- 신고가/신저가
- 실현 변동성
- 상승종목 거래대금 비중
- 외국인 5일 누적 수급

## 1.5 DART Event

공시에서 다음 이벤트를 기계적으로 분류:

- 잠정실적 개선
- 대형 수주/공급계약
- 자사주 매입
- 바이오/기술 관련 중요 이벤트
- 정정/안내/중복 제거

## 1.6 Event Backtest

단순 신호 노출에서 끝내지 않고:

```text
event
→ future return
→ excess return
→ win rate
→ MFE / MAE
```

를 사후 검증한다.

## 1.7 Strategic Holdings

DART `타법인출자현황` 등을 이용해 실제 해외 기업 지분 보유 여부를 확인한다.

---

# 2. 중요한 해석 원칙

FASTJUSIK 공개 백테스트에서 `연기금 3일 연속 순매수` 전체 신호를 무조건 따라가는 방식은 좋은 결과를 보장하지 않았다.

따라서 본 프로젝트에서 다음을 금지한다.

```text
연기금 매수 = 호재
연기금 연속매수 = 매수 추천
외국인 동반매수 = Quant 가점
```

대신:

```text
FLOW SIGNAL
    ↓
CONDITION
    ↓
FORWARD RETURN
    ↓
EDGE VALIDATION
```

으로 사용한다.

```yaml
flow:
  include_in_quant_score: false
```

---

# 3. 최종 Architecture

```text
                  KRX / DART / KIS / TOSS
                           │
                           ▼
                    DATA SOURCE LAYER
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
       MARKET           SECTOR          FUNDAMENTAL
          │                │                 │
          ▼                ▼                 ▼
          天               地            QUANT SCORE
          │                │                 │
          └────────────────┼─────────────────┘
                           ▼
                    VALUE TRAP / RISK
                           ▼
                     TOP100 / TOP20
              ┌────────────┼─────────────┐
              │            │             │
              ▼            ▼             ▼
          FLOW ENGINE   EVENT ENGINE   STRATEGY LAB
              │            │             │
              ▼            ▼             ▼
          PENSION       DART EVENT      OOS / WF
          FOREIGNER     SURPRISE        TIMING
          PRIVATE       CONTRACT
              │            │             │
              └───────┬────┴──────┬──────┘
                      │           │
                      ▼           ▼
                 AI RESEARCH   ROBUSTNESS
                    道 / 將
                      │
                      ▼
                      法
               DATA / RISK /
              SOURCE DISCIPLINE
                      │
                      ▼
               RESEARCH PRIORITY
```

---

# 4. Data Source Reality Check

FASTJUSIK은 공개 페이지에서 수급 데이터 출처를 `한국거래소 통계정보`라고 명시한다.

그러나 현재 KRX OPEN API 공개 서비스 목록에서 일반적으로 확인되는 주식 API는 유가증권/코스닥 일별매매정보와 종목기본정보 등이 중심이다. `전 종목 투자자별 연기금 수급 API`가 현재 보유한 KRX OPEN API Key로 직접 제공된다고 가정하면 안 된다.

따라서 구현 순서는 다음이다.

## 4.1 Source Discovery

현재 repository에서 실제 사용 가능한 source부터 감사한다.

후보:

1. Toss investor-trading
2. KIS 국내 투자자별 매매 API
3. 기존 사용 중인 별도 data endpoint
4. 사용자가 보유한 합법적인 KRX 통계 데이터 export/계약 데이터

없는 endpoint를 추측해 구현하지 않는다.

## 4.2 Flow Source Interface

```python
class InvestorFlowProvider(Protocol):
    def fetch_daily_flow(
        self,
        date: str,
        tickers: list[str] | None = None
    ) -> list["InvestorFlowRecord"]:
        ...
```

표준 투자자 그룹:

```text
PENSION
FOREIGNER
INSTITUTION
PRIVATE_EQUITY
INDIVIDUAL
FINANCIAL_INVESTMENT
INVESTMENT_TRUST
INSURANCE
OTHER
```

source가 세부 그룹을 제공하지 않으면 `N/A`.

---

# 5. Investor Flow Base Schema

DuckDB `investor_flow_daily`:

```text
trade_date
ticker
market
investor_type
net_buy_qty
net_buy_value
buy_qty
sell_qty
buy_value
sell_value
source
source_quality
is_estimated
is_final
available_at
fetched_at
run_id
```

Primary Key 후보:

```text
trade_date + ticker + investor_type + source
```

금액이 실제 거래대금이 아니라 `net_buy_qty × close` 추정이면 `is_estimated=true`를 반드시 저장한다.

---

# 6. Pension Flow Engine

새 모듈 후보:

```text
src/kr_quant/flow/pension.py
src/kr_quant/flow/streak.py
src/kr_quant/flow/reversal.py
src/kr_quant/flow/aggregation.py
src/kr_quant/flow/signals.py
```

기존 `flow/` 구조가 있으면 재사용한다.

---

# 7. 당일 연기금 Ranking

매 거래일:

```text
PENSION_DAILY_BUY_RANK
PENSION_DAILY_SELL_RANK
```

출력:

```text
rank
ticker
company
market
net_buy_value
net_buy_qty
market_cap
net_buy_value_to_market_cap
sector
quant_score
sector_score
```

절대금액뿐 아니라 `net_buy_value / market_cap`도 연구 필드로 저장해 대형주 편향을 줄인다.

---

# 8. 연속 Flow

## 8.1 정의

연속 거래일 동안 `net_buy_value > 0`이면 BUY STREAK, `< 0`이면 SELL STREAK.

```yaml
pension_flow:
  zero_breaks_streak: true
  missing_breaks_streak: true
```

## 8.2 `flow_streaks_daily`

```text
run_date
ticker
investor_type
direction
streak_days
streak_start_date
streak_end_date
cumulative_net_value
cumulative_net_qty
avg_daily_net_value
max_daily_net_value
value_to_market_cap
source_confidence
run_id
```

---

# 9. 기간 누적 Flow

최소 5D/20D/60D, 선택적으로 120D.

```text
pension_net_5d
pension_net_20d
pension_net_60d
foreigner_net_5d
foreigner_net_20d
foreigner_net_60d
institution_net_5d
institution_net_20d
institution_net_60d
```

시총 정규화 값도 저장한다.

---

# 10. 연기금 + 외국인 동반 Flow

이벤트:

```text
PENSION_FOREIGNER_DOUBLE_BUY
PENSION_FOREIGNER_DOUBLE_SELL
```

정의:

```text
PENSION net > 0 AND FOREIGNER net > 0
```

또는 반대.

추가:

```text
combined_net_value
combined_value_pct_mcap
double_buy_days_5d
double_buy_days_20d
pension_foreigner_same_direction_ratio_20d
```

---

# 11. 방향 전환

기본:

```yaml
flow_reversal:
  minimum_prior_streak_days: 5
```

이벤트:

```text
PENSION_BUY_REVERSAL
PENSION_SELL_REVERSAL
```

저장:

```text
prior_streak_days
prior_cumulative_value
today_net_value
today_value_pct_mcap
sector_state
quant_score
market_regime
```

UI에서는 `바닥/천장`이라고 단정하지 않고 `FLOW REVERSAL`로 표시한다.

---

# 12. Flow State

```text
ACCUMULATION
DISTRIBUTION
REVERSAL_UP
REVERSAL_DOWN
MIXED
NEUTRAL
LOW_DATA
```

예:

```text
ACCUMULATION:
  pension_net_20d > 0
  and pension_net_5d > 0
  and streak_direction == BUY
```

Quant에는 합산하지 않는다.

---

# 13. Market-wide Pension Flow

전체/KOSPI/KOSDAQ로 분리해 연기금 순매수 합계를 계산한다.

rolling:

```text
5D
20D
60D
```

상태 후보:

```text
STRONG_ACCUMULATION
ACCUMULATION
NEUTRAL
DISTRIBUTION
STRONG_DISTRIBUTION
```

threshold는 역사적 percentile을 우선한다.

---

# 14. Rebalancing Monitor

목적:

> 시장 전체 연기금 매도 중에도 상대적으로 매수되는 종목을 찾는다.

저장:

```text
market_pension_flow
kospi_pension_flow
kosdaq_pension_flow
large_cap_pension_flow
mid_cap_pension_flow
small_cap_pension_flow
sector_pension_flow
```

## 14.1 Relative Accumulation

```text
market_pension_flow < 0
AND stock_pension_flow > 0
```

이벤트:

```text
PENSION_RELATIVE_ACCUMULATION
```

반대는 `PENSION_RELATIVE_DISTRIBUTION`.

---

# 15. 국민연금 5%+ Holdings

OpenDART 대량보유 공시를 이용한다.

목적:

> 일별 `연기금` flow와 국민연금 단독 확정 지분을 구분한다.

## 15.1 `nps_major_holdings`

```text
filing_date
report_date
ticker
company
holder_name
ownership_pct
previous_ownership_pct
ownership_delta
shares_held
previous_shares_held
shares_delta
filing_reason
report_type
dart_receipt_no
source_url
available_at
fetched_at
run_id
```

이벤트:

```text
NPS_NEW_5PCT
NPS_STAKE_INCREASE
NPS_STAKE_DECREASE
NPS_EXIT_5PCT
```

참고 평가액:

```text
latest_close × shares_held
```

반드시 `ESTIMATED` 표시.

---

# 16. Holdings vs Daily Flow 분리

UI에서 `PENSION DAILY FLOW`와 `NPS CONFIRMED HOLDING`을 별도 패널로 표시한다.

- 일별 연기금: 여러 공적연금 합산 가능, 빠른 데이터
- NPS DART 5%: 국민연금 단독 확정 지분, 느리지만 법정 공시

---

# 17. Internal Korea Fear & Greed

외부 Fear & Greed API와 별도로 내부 설명 가능한 지표를 구현한다.

이름 후보:

```text
KR_MARKET_SENTIMENT
```

구성요소:

1. Market Momentum: KOSPI close vs 120D MA
2. Breadth: 최근 5거래일 상승/하락 종목수
3. High/Low: 120D 신고가/신저가 종목수(5일)
4. Realized Volatility: KOSPI 20D 실현변동성
5. Trading Value Participation: 상승종목 거래대금 비중(5일)
6. Foreign Flow: 외국인 5D 누적 순매수

초기 자체 가중치 후보:

```text
Momentum        20
Breadth         20
HighLow         15
Volatility      15
Trading Value   15
Foreign Flow    15
------------------
Total          100
```

이 가중치를 FASTJUSIK의 내부 공식이라고 주장하지 않는다.

상태:

```text
0~20    EXTREME_FEAR
21~40   FEAR
41~60   NEUTRAL
61~80   GREED
81~100  EXTREME_GREED
```

---

# 18. Sunzi 天 연결

Internal KR Sentiment는 `天`의 보조 input으로 사용한다.

```text
天 Market Regime
├─ Trend
├─ Breadth
├─ Liquidity
├─ Volatility
├─ Rates
├─ FX
├─ Momentum
└─ Internal Sentiment
```

초기에는 overlay:

```yaml
sunzi:
  tian:
    sentiment_overlay_only: true
```

---

# 19. DART Event Engine

모듈 후보:

```text
src/kr_quant/events/parser.py
src/kr_quant/events/classifier.py
src/kr_quant/events/dedupe.py
src/kr_quant/events/financial_event.py
src/kr_quant/events/contract_event.py
src/kr_quant/events/buyback_event.py
src/kr_quant/events/dilution_event.py
src/kr_quant/events/technology_event.py
src/kr_quant/events/repository.py
```

Canonical source는 OpenDART.

---

# 20. Event Types

```text
EARNINGS_IMPROVEMENT
EARNINGS_DETERIORATION
LARGE_CONTRACT
CONTRACT_CANCELLATION
BUYBACK
BUYBACK_CANCELLATION
DIVIDEND_INCREASE
DIVIDEND_DECREASE
CAPEX_EXPANSION
RIGHTS_OFFERING
CB_ISSUE
BW_ISSUE
MAJOR_SHAREHOLDER_CHANGE
BIO_TECH_EVENT
ACCOUNTING_RISK
AUDIT_RISK
```

---

# 21. 잠정실적 Event

가능하면 raw field:

```text
current_revenue
previous_revenue
current_operating_profit
previous_operating_profit
current_net_income
previous_net_income
yoy_change
qoq_change
```

없으면 N/A.

Consensus 데이터가 없으면 `SURPRISE`라고 부르지 않고 `EARNINGS_IMPROVEMENT`로 분류한다.

초기 후보:

```text
operating_profit > 0
AND operating_profit_yoy > 0
```

---

# 22. Large Contract Event

추출:

```text
contract_value
contract_counterparty
contract_start
contract_end
revenue_reference
contract_value / TTM_revenue
```

회사 규모 대비 중요도를 `contract_to_revenue_ratio`로 저장한다.

---

# 23. Buyback / Dilution

Buyback:

```text
BUYBACK
BUYBACK_CANCELLATION
TREASURY_SHARE_DISPOSAL
```

추출:

```text
share_count
amount
period
purpose
```

희석:

```text
RIGHTS_OFFERING
CB_ISSUE
BW_ISSUE
```

반복 여부:

```text
dilution_event_count_1y
dilution_event_count_3y
```

이는 Risk Engine과 `法` evidence로 연결 가능.

---

# 24. Event Deduplication

정정/안내/중복을 구분한다.

```text
original
correction
cancellation
duplicate
```

relation을 저장한다.

---

# 25. `corporate_events`

```text
event_id
ticker
company
event_type
event_date
available_at
title
summary
raw_metrics_json
materiality_score
source_confidence
dart_receipt_no
source_url
is_correction
is_cancellation
parent_event_id
run_id
created_at
```

Event Materiality는 0~100 연구 점수로 만들 수 있으나 Quant에 합산하지 않는다.

---

# 26. Event Forward Return Research

중요 이벤트에 대해:

```text
1D
5D
10D
20D
60D
```

forward return 저장.

추가:

```text
benchmark_return
excess_return
MFE
MAE
```

`event_forward_returns`:

```text
event_id
ticker
horizon_days
entry_date
entry_price
exit_date
exit_price
raw_return
benchmark_return
excess_return
mfe
mae
market_regime
sector_state
quant_score_at_event
data_confidence
calculated_at
```

---

# 27. No Look-ahead

공시 signal date `t`의 실제 사용 가능 시점이 불분명하면 보수적으로:

```text
t → t+1 open
```

또는 config상 `t+1 close`.

같은 날 종가를 미래정보로 사용하지 않는다.

---

# 28. Flow Backtest Lab

Flow signal도 같은 research framework를 사용한다.

```text
PENSION_STREAK_3
PENSION_STREAK_5
DOUBLE_BUY
BUY_REVERSAL
RELATIVE_ACCUMULATION
```

`flow_signals`:

```text
signal_id
signal_date
ticker
signal_type
investor_type
direction
streak_days
net_value_1d
net_value_5d
net_value_20d
net_value_60d
value_pct_market_cap
foreigner_alignment
institution_alignment
market_flow_context
sector_flow_context
quant_score
sector_score
market_regime
data_confidence
run_id
```

Forward horizon:

```text
5D
20D
60D
120D
```

---

# 29. Conditional Research

단순 신호와 조건부 조합을 모두 연구할 수 있다.

예:

```text
PENSION_STREAK >= 3
AND pension_net_20d_pct_mcap >= X
AND FOREIGNER_20D > 0
AND SECTOR_STATE = LEADING
AND QUANT >= 80
```

단, 조건을 너무 많이 탐색해 data mining하지 않도록 연구 가설을 사전에 버전관리한다.

---

# 30. Research Hypothesis Registry

`research_hypotheses`:

```text
hypothesis_id
name
version
description
signal_definition_json
created_at
status
```

상태:

```text
IN_RESEARCH
VALIDATED
REJECTED
INSUFFICIENT_SAMPLE
```

Minimum sample 예:

```yaml
research:
  minimum_signal_count: 30
```

표본이 작으면 `LOW_SAMPLE`.

---

# 31. Market / Sector Conditional Results

모든 signal 연구 결과를 다음 조건으로 분해한다.

Market:

```text
RISK_ON
NEUTRAL
RISK_OFF
```

Sector:

```text
LEADING
IMPROVING
NEUTRAL
WEAKENING
LAGGING
```

---

# 32. Pension + Quant Research Matrix

```text
                    Pension Weak    Pension Strong
Quant Low             WATCH            FLOW_ONLY
Quant High            FUND_ONLY        CONVERGENCE
```

`CONVERGENCE`는 research label일 뿐 매수 추천이 아니다.

---

# 33. Global Strategic Holdings

DART `타법인출자현황` 기반.

목적:

> “테마 관련”과 “실제 지분 보유”를 구분한다.

`strategic_holdings`:

```text
report_date
ticker
company
target_company
target_country
target_listed_status
ownership_pct
shares_owned
acquisition_cost
book_value
business_relation
source
dart_receipt_no
available_at
run_id
```

AI Research evidence class 후보:

```text
ACTUAL_EQUITY_LINK
BUSINESS_CONTRACT_LINK
NO_CONFIRMED_LINK
```

테마 점수보다는 잘못된 narrative 제거에 우선 사용한다.

---

# 34. Sunzi 道 연결

실제 strategic holding / contract / CAPEX와 회사 narrative가 일치하면 `道 Alignment` evidence로 사용한다.

반대로 실체가 없으면 contrary evidence.

---

# 35. 경제/실적 캘린더

우선순위는 낮지만 optional로 구현 가능.

경제:

```text
FOMC
BOK
CPI
PPI
GDP
Employment
Option/Futures Expiry
```

실적:

```text
ticker
event_date
event_type
estimated_eps
actual_eps
estimated_revenue
actual_revenue
source
confidence
```

Consensus source가 없으면 추정하지 않는다.

---

# 36. UI — Main Dashboard

현재 FastAPI `:8790` dashboard를 canonical로 유지한다.

추가 카드:

## Flow

```text
연기금 오늘 순매수
연기금 5D 누적
외국인 5D
연기금 Flow Regime
```

## Sentiment

```text
Internal KR Sentiment
Market Regime
```

## Events

```text
오늘 중요 DART Event
```

---

# 37. Flow Dashboard

새 화면 후보:

```text
/flow/pension
```

탭:

```text
당일
연속수급
동반수급
방향전환
기간누적
시장요약
보유지분
```

당일 컬럼:

```text
Rank
Ticker
Company
Market
Sector
Pension Net
Pension Qty
Pension / MCap
Foreigner Net
Quant
Sector Score
Flow State
```

---

# 38. Stock Detail — Flow Panel

```text
Pension 1D
Pension 5D
Pension 20D
Pension 60D
Pension Streak
Foreigner 5D/20D/60D
Institution 5D/20D
Double Flow State
Flow Confidence
```

차트:

```text
price
pension cumulative flow
foreigner cumulative flow
institution cumulative flow
individual cumulative flow
```

1M / 3M / 6M / 1Y range.

---

# 39. NPS Holdings Panel

```text
Confirmed NPS Ownership
Current %
Previous %
Delta
Shares
Estimated Value
Report Date
DART link
```

---

# 40. Rebalancing Dashboard

```text
Market Pension Flow
KOSPI Flow
KOSDAQ Flow
Sector Flow Ranking
Relative Accumulation
Relative Distribution
```

---

# 41. Internal Sentiment Dashboard

component bar:

```text
Momentum
Breadth
High/Low
Volatility
Trading Value
Foreign Flow
```

history chart 0~100.

---

# 42. Event Dashboard

탭:

```text
실적
수주
자사주
배당
CAPEX
희석
회계위험
기술/바이오
```

Event Card:

```text
Company
Event Type
Date/Time
Materiality
Quant Score
Sector State
Key Metrics
Source Confidence
DART Original
```

---

# 43. Event Research UI

각 event type별:

```text
Signals
Avg 5D
Avg 20D
Avg 60D
Median
Win Rate
Excess Return
MFE
MAE
Sample Count
```

과거 성과가 미래 수익을 보장하지 않는다는 연구용 안내를 표시한다.

---

# 44. 손자 五事 통합

## 道

추가 evidence:

- 공시 이벤트와 회사 narrative 일치
- 실제 strategic holding
- 자사주/배당 vs shareholder narrative
- CAPEX 실행
- contract execution

Flow는 道 핵심점수보다 보조 evidence.

## 天

```text
Internal KR Sentiment
Market Pension Flow Regime
Foreign Market Flow
```

## 地

```text
Sector Pension Flow
Sector Foreign Flow
Sector Breadth
Sector Liquidity
```

## 將

- 반복 희석
- buyback 실행
- capital allocation event
- CAPEX 결과
- large contract execution

## 法

```text
Flow Source Confidence
Event Source = DART?
Estimate vs Final
Data Freshness
Minimum Sample
OOS Validation
```

---

# 45. 法 Gate 보완

새 Fail 후보:

```text
Flow source confidence too low
Estimated flow displayed as final
DART event not canonical
Event correction unresolved
Backtest sample too small but high confidence 표시
Forward-return research leakage detected
```

이런 조건은 `fa_gate_pass`에 영향을 줄 수 있다.

---

# 46. Change Events

```text
PENSION_NEW_STREAK
PENSION_STREAK_EXTENDED
PENSION_STREAK_BROKEN
PENSION_BUY_REVERSAL
PENSION_SELL_REVERSAL
PENSION_FOREIGNER_DOUBLE_BUY
PENSION_FOREIGNER_DOUBLE_SELL
PENSION_RELATIVE_ACCUMULATION
PENSION_RELATIVE_DISTRIBUTION
NPS_NEW_5PCT
NPS_STAKE_INCREASE
NPS_STAKE_DECREASE
NPS_EXIT_5PCT
NEW_EARNINGS_IMPROVEMENT
NEW_LARGE_CONTRACT
NEW_BUYBACK
NEW_CAPEX
NEW_DILUTION_RISK
EVENT_CORRECTION
EVENT_CANCELLED
SENTIMENT_STATE_CHANGE
```

---

# 47. Daily Report

새 섹션:

## Market Flow

- Pension market flow
- foreign flow
- Internal Sentiment

## Flow Candidates

- 연속 매집
- 동반 수급
- 방향전환
- relative accumulation

## DART Events

- earnings
- contract
- buyback
- dilution

## Holdings Changes

- NPS 5% events

---

# 48. Research Priority

새 giant score를 만들지 않는다.

표시:

```text
Quant Score
Sector Score
Research Score
Timing Confidence
Flow State
Event State
Sunzi
Data Confidence
```

Optional research label:

```text
QUANT_ONLY
QUANT_SECTOR
QUANT_FLOW
QUANT_EVENT
QUANT_FLOW_EVENT
FULL_CONVERGENCE
```

`FULL_CONVERGENCE`도 매수 추천이 아니다.

---

# 49. Event/Flow Backtest와 Strategy Lab 연결

공통 infra는 재사용하되 다음은 구분한다.

```text
Technical Strategy Backtest
Flow Signal Event Study
Corporate Event Study
```

Event Study는 event 발생 후 고정 horizon 성과, Strategy는 entry/exit rule의 반복 simulation이다.

---

# 50. Portfolio Lab 연결

Research Portfolio에서:

```text
Pension Flow Concentration
Foreign Flow Concentration
```

을 보여줄 수 있다.

같은 섹터 집중 시 `SECTOR_CONCENTRATION_HIGH` 경고.

---

# 51. Scheduler

기본 장마감 연구 흐름 후보:

```text
latest market/flow available check
→ KRX price update
→ market/sector/quant
→ flow aggregation
→ DART event refresh
→ daily report
```

FASTJUSIK의 16:30 갱신 시간을 그대로 hard-code하지 않는다. 실제 API 제공 가능 시점 확인 후 config로 설정한다.

DART intraday polling은 optional.

---

# 52. API Failure

```text
Flow source 실패 → Flow=N/A, Quant continues
DART event 실패 → Event unavailable/low confidence
Sentiment 일부 실패 → partial confidence
```

`optional overlay failure != quant pipeline failure` 원칙 유지.

---

# 53. Data Confidence Extensions

Flow:

```text
A = official/final + complete
B = reliable secondary + complete
C = partial / estimated
D = insufficient
```

Event:

- DART direct: 높은 confidence
- News-only: DART 확인 전 낮은 confidence

UI에 항상 `Source / As of / Confidence / Final-or-Estimate`를 표시한다.

---

# 54. Tests — Flow

- streak start/extend/break
- zero handling
- missing day
- reversal
- double-buy/double-sell
- 5/20/60 aggregation
- market-cap normalization
- estimated vs final
- KOSPI/KOSDAQ split

# 55. Tests — NPS

- new 5%
- increase/decrease
- exit
- correction
- duplicate filing
- ownership delta

# 56. Tests — Sentiment

- MA calculation
- breadth
- new high/low
- realized volatility
- trading-value participation
- foreign flow normalization
- score 0~100
- missing component

# 57. Tests — Event

- earnings parser
- contract parser
- buyback
- rights offering
- CB/BW
- correction/cancellation
- dedupe
- no fabricated values

# 58. Tests — Event Study

- no look-ahead
- next trading day
- benchmark
- MFE/MAE
- sample count
- missing future data
- suspended stock

# 59. Tests — Sunzi

- flow does not change Quant
- sentiment does not change Quant
- event does not change Quant
- source confidence affects 法
- estimated data flagged
- low sample cannot become validated edge

---

# 60. Security / Compliance

하지 않을 것:

- FASTJUSIK HTML 대량 저장
- 비공개 endpoint 역추적
- 인증 우회
- 소스코드 복제
- JS/CSS/이미지 복사
- 문구 대량 복사
- FASTJUSIK를 production scraping source로 사용

목표는 `기능 아이디어 → 독립 구현`이다.

KRX 데이터를 사용할 경우 현재 이용약관 및 필요한 출처표시를 확인해 UI/report에 반영한다.

---

# 61. 구현 우선순위

```text
Phase 0  Audit
Phase 1  Flow source discovery
Phase 2  Pension / Foreigner Flow
Phase 3  Flow UI
Phase 4  Internal Sentiment
Phase 5  DART Event Engine
Phase 6  Event Study
Phase 7  NPS Holdings
Phase 8  Rebalancing
Phase 9  Strategic Holdings
Phase 10 Sunzi Integration
Phase 11 Regression / Documentation
```

---

# 62. 가장 먼저 할 Audit

생성:

```text
docs/V1_3_FASTJUSIK_GAP_ANALYSIS.md
docs/V1_3_FASTJUSIK_IMPLEMENTATION_PLAN.md
```

Gap 상태:

```text
ALREADY_IMPLEMENTED
PARTIAL
MISSING
BLOCKED_BY_DATA
CONFLICT
```

`BLOCKED_BY_DATA`가 중요하다. 연기금 전종목 source가 없으면 fake endpoint를 만들지 않는다.

특히 확인:

```text
src/kr_quant/flow/
src/kr_quant/ingest/toss*
src/kr_quant/ingest/kis*
src/kr_quant/ingest/krx*
src/kr_quant/ingest/opendart*
src/kr_quant/web/
src/kr_quant/research/
src/kr_quant/timing/
db/
config/
```

---

# 63. DB Migration

기존 DuckDB 삭제 금지. idempotent migration으로 추가.

신규 후보:

```text
investor_flow_daily
flow_streaks_daily
flow_signals
market_flow_daily
nps_major_holdings
corporate_events
event_forward_returns
market_sentiment_daily
strategic_holdings
research_hypotheses
```

---

# 64. FastAPI Endpoint 후보

```text
GET /api/flow/pension
GET /api/flow/pension/streaks
GET /api/flow/pension/reversals
GET /api/flow/pension/period
GET /api/flow/pension/market
GET /api/flow/stock/{ticker}
GET /api/nps/holdings
GET /api/nps/holdings/{ticker}
GET /api/sentiment
GET /api/events
GET /api/events/{ticker}
GET /api/events/research
GET /api/strategic-holdings/{ticker}
```

---

# 65. Config Example

```yaml
flow:
  enabled: true
  include_in_quant_score: false
  windows: [5, 20, 60]

  reversal:
    minimum_prior_streak_days: 5

  research:
    minimum_signal_count: 30

pension:
  enabled: true
  require_final_data_for_high_confidence: true

sentiment:
  enabled: true
  include_in_quant_score: false

  weights:
    momentum: 20
    breadth: 20
    high_low: 15
    volatility: 15
    trading_value: 15
    foreign_flow: 15

events:
  enabled: true
  include_in_quant_score: false
  event_study_horizons: [1, 5, 10, 20, 60]

nps_holdings:
  enabled: true

strategic_holdings:
  enabled: true

sunzi:
  enabled: true
  used_in_quant: false

  tian:
    use_internal_sentiment_as_overlay: true

  fa:
    enforce_source_confidence: true
```

---

# 66. 완료 조건

1. 기존 Quant 결과 regression 유지
2. Flow source 계약/adapter 문서화
3. Pension 5D/20D/60D 저장 가능
4. streak 동작
5. reversal 동작
6. pension+foreigner alignment 동작
7. market pension flow 동작
8. Internal Sentiment 동작
9. DART event parser 동작
10. correction/dedupe 동작
11. event study 동작
12. NPS 5% holding 추적
13. Rebalancing page
14. Stock Detail Flow panel
15. Event page
16. Sunzi evidence 연결
17. 法 source gate
18. 모든 overlay `used_in_quant=false`
19. test suite 통과
20. secret 노출 없음
21. 주문 기능 없음
22. FASTJUSIK를 production scraper로 사용하지 않음

---

# 67. Grok Build에 전달할 최종 작업 지시문

```text
현재 프로젝트:
C:\Users\a4jud\kr_quant_research

첨부한
GROK_BUILD_KR_QUANT_V1_3_FASTJUSIK_FLOW_EVENT_ADDENDUM.md
를 기존 시스템에 대한 증분 요구사항으로 적용해라.

목표는 FASTJUSIK 사이트를 복제하는 것이 아니다.

공개 페이지에서 확인 가능한
연기금 연속수급, 동반수급, 방향전환, 기간누적,
국민연금 5% 보유지분, 리밸런싱 관점,
한국형 시장심리, DART Event 분류,
Event/Flow 사후 백테스트,
실제 해외 지분 보유 검증
이라는 연구 아이디어를 현재 Grok Build 데이터 구조에 맞게 독립 구현한다.

중요 원칙:

1. 기존 Fundamental Quant Score와 ranking을 변경하지 않는다.
2. Flow / Event / Sentiment / NPS / Strategic Holding은 used_in_quant=false다.
3. 현재 KRX / OpenDART / FastAPI 구조를 유지한다.
4. 연기금 데이터 endpoint를 추측하지 않는다.
5. 먼저 현재 Toss/KIS/KRX adapter에서 어떤 투자자별 데이터가 실제로 가능한지 확인한다.
6. source가 없으면 BLOCKED_BY_DATA로 기록하고 fake 구현을 하지 않는다.
7. FASTJUSIK 자체를 production scraping source로 만들지 않는다.
8. 사이트의 소스코드, 디자인, 이미지, 문구를 복사하지 않는다.
9. Flow 신호를 매수 추천으로 표현하지 않는다.
10. 연기금 3일 연속매수 같은 단일 신호에 점수를 부여하지 않는다.
11. 모든 Flow/Event signal은 forward-return 연구 대상으로 저장한다.
12. Event study는 no-lookahead / next-trading-day 원칙을 사용한다.
13. 표본이 부족하면 LOW_SAMPLE로 표시한다.
14. DART event는 DART 원문을 canonical source로 사용한다.
15. estimate와 final data를 반드시 구분한다.
16. 국민연금 5% DART 지분과 일별 연기금 합산 수급을 같은 데이터처럼 취급하지 않는다.
17. Internal Sentiment는 현재 Market Engine과 분리된 overlay로 시작한다.
18. Sunzi 天에는 Sentiment/Market Flow, 地에는 Sector Flow,
    道/將에는 기업 이벤트와 실제 자본배분 evidence,
    法에는 source confidence / final-vs-estimate / sample robustness를 연결한다.
19. 주문 기능을 추가하지 않는다.
20. API secret을 출력하지 않는다.

작업 순서:

STEP 1 Repository read-only audit.
STEP 2 기존 tests baseline.
STEP 3 docs/V1_3_FASTJUSIK_GAP_ANALYSIS.md 작성.
STEP 4 docs/V1_3_FASTJUSIK_IMPLEMENTATION_PLAN.md 작성.
STEP 5 Flow source discovery. Toss/KIS/KRX 현재 adapter 및 실제 계약 확인.
STEP 6 Investor Flow canonical schema 구현.
STEP 7 Pension/Foreigner streak, cumulative flow, double flow, reversal.
STEP 8 FastAPI Flow dashboard.
STEP 9 Internal Korea Sentiment.
STEP 10 DART Event Engine + dedupe/correction.
STEP 11 Flow/Event Forward Return Research.
STEP 12 NPS 5% Holdings.
STEP 13 Rebalancing Monitor.
STEP 14 Strategic Holdings / Theme Verification.
STEP 15 Sunzi Overlay evidence integration.
STEP 16 Full regression + docs.

중간 승인 대기로 작업을 멈추지 말고
기존 Quant 산식 변경, DB destructive migration,
새 외부 유료 data dependency가 필요한 경우만
DECISION REQUIRED로 기록하고 기존 기능을 유지한다.

완료 보고:

- 실제 사용한 data source
- BLOCKED_BY_DATA 항목
- 신규 DB table
- 신규 adapter
- Flow signal 정의
- Sentiment 공식
- Event parser 규칙
- Event Study assumption
- NPS holding parser
- Rebalancing logic
- Strategic holding parser
- Sunzi 연결
- 신규 FastAPI endpoint
- 신규 UI
- tests
- regression
- known limitations
- next recommendation
```

---

# 68. 참고한 공개 페이지

기능 분석 기준:

- https://fastjusik.com/pension
- https://fastjusik.com/pension/follow
- https://fastjusik.com/pension/surprise
- https://fastjusik.com/pension/rebalancing
- https://fastjusik.com/pension/portfolio
- https://fastjusik.com/pension/global
- https://fastjusik.com/feargreed

KRX 확인:

- https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp

본 프로젝트는 FASTJUSIK를 데이터 source로 의존하지 않는다.

---

# 69. 핵심 철학

FASTJUSIK에서 가장 참고할 만한 것은 단순한 `연기금 순매수 랭킹` 자체가 아니다.

핵심 연구 구조는:

```text
관측
 ↓
연속성
 ↓
누적
 ↓
다른 투자주체와 Alignment
 ↓
방향전환
 ↓
시장/섹터 Context
 ↓
공시 Event
 ↓
사후 Forward Return
 ↓
실제 Edge 검증
```

이다.

우리 프로젝트는 여기에 이미 존재하는:

```text
Fundamental Quant
Sector
Risk
Strategy Lab
AI Research
Sunzi Five Factors
```

를 결합한다.

최종 목표는 `연기금이 샀으니 사는 프로그램`이 아니다.

최종 목표는:

> **좋은 기업이 좋은 산업에 있고, 시장 및 주요 수급 주체의 환경이 어떻게 변하고 있으며, 실제 기업 이벤트가 투자논리를 강화하거나 훼손하는지, 그리고 그런 신호가 과거에 실제로 유효했는지를 매일 재현 가능한 데이터로 검증하는 한국 주식 리서치 플랫폼**

이다.
