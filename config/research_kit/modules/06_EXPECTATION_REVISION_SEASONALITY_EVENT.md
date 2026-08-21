# 06. Latest Event / Expectations / Revision / Seasonality / Sentiment — VER3.7.2

## 1. Recent Window

실적·급등락 종목은 먼저 검색한다.

- 최근 24시간
- 최근 7일
- 최근 30일
- 다음 예정 이벤트

공시·잠정실적·회사해명·중요뉴스·장중가격·거래량·증권사 추정치 변경을 시간순으로 정리한다.

## 2. Event Clock

| 시점 | 사실·기대 | 가격·거래량 | 서사 |
|---|---|---|---|
| D-20~D-1 | 선행 기대·리비전 | 절대/RS/거래량 | 기대 형성 |
| 발표시각 | Actual/Guidance | 장전/장후 | 헤드라인 |
| D0 장중 | 초기 반응 | 갭·저가·거래량 pace | 낙관/의심 |
| D+1 완성 | 종가 확인 | 갭 유지·반납 | 가격결정권 |
| D+5/20/60 | Drift/반전 | 시장·업종 초과 | 서사 정착 |

D0 장중과 D+1 완성을 분리한다.

## 3. Pre-Pricing

- D-5/D-20/D-60 절대·시장·업종 초과수익
- 거래량·거래대금 배수
- 외국인·기관·개인
- 신용·대차·공매도
- 밸류 확장
- 컨센서스 상향속도

High는 최소 2개 독립 근거.

## 4. Earnings Seasonality

가능하면 5~8년, 최근 3년 별도.

| 분기 | 매출 비중 | OP 비중 | OPM | QoQ | CFO/FCF | 주가초과 | 반복성 | 구조변화 |
|---|---:|---:|---:|---:|---:|---:|---|---|

계절적 다음 분기 둔화가 이미 가격에 반영됐는지 본다.

## 5. Event Study and Historical Analog

같은 종목 최소 2개, 가능하면 3~5개.

| 날짜 | 이벤트 | Surprise | D-20 | D+1 | D+5 | D+20 | D+60 | 거래량 | Revision | 차이점 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|

표본 1은 사례, 2~9는 비교다. 미래 확률로 단정하지 않는다.

## 6. Revision Bridge

| 항목 | Pre | Actual/Guidance | Post | 변화 | 해석 |
|---|---:|---:|---:|---:|---|
| Revenue/OP/EPS | | | | | |
| Next Q | | | | | |
| FY1 EPS/FCF | | | | | |
| FY2 EPS/FCF | | | | | |
| 목표배수/목표가 | | | | | |

목표가 상향을 EPS 리비전으로 대체하지 않는다.

post-event revision이 없으면 Pending이지만 분석 중단은 아니다.

- 초기 가격반응은 provisional
- 정상화 범위·Reverse·시나리오 계속 수행
- 리비전과 D+1/D+5를 변경조건으로 둠

## 7. 분류

- Provisional / Confirmed Good News Rejection
- Pre-Priced Sell-the-News
- Fundamental Deterioration Hidden by Beat
- Positive Underreaction / Drift
- Bad News Exhaustion
- Mixed / Insufficient

리비전 Pending이면 `초기 거부 반응`처럼 잠정 표현을 사용한다.

## 8. News·Forum Narrative Timeline

이벤트 쇼크·루머·사용자 요청 시 Full.

`무관심 → 기대 형성 → 낙관 과열 → 사건 → 의심 → 공포/항복 → 가격확인`

기록:

- 플랫폼·기간·표본수
- 대표 논점과 추천/조회 반응
- 중복·스팸·작성자 편중
- 가격이 감정을 만든 역인과
- 공식자료와 충돌하는 루머

포럼은 사실이 아니라 서사·감정 지도다.

## 9. Rumor Status

- Confirmed
- Partially Confirmed
- Unverified
- Contradicted
- Stale

## 10. 가격 연결

- Revision Down → Stage B·가치 재계산
- Revision Flat/Up + Sell-on → 가치 유지, 실행가격·분할 보수화
- Pre-Pricing High → 추격금지
- 장중 급락 + 거래량 확대 → 공포 진행 여부와 지지회복 확인
- Price Reaction Confirming → 돌파·리테스트 후 실행

PEG는 Forward PER / 2~3년 정상화 EPS CAGR의 보조지표만 사용한다.

## VER3.7.2 Event Hard Trigger
좋은 실적 후 급락, 나쁜 실적 후 강세, 발표 전 강한 선행상승, 거래량 클라이맥스, 정책/루머 논쟁 중 하나라도 있으면 Full Event를 실행한다.
최소: D-5/D-20/D-60, Actual vs Consensus, revision/Pending, D+1/D+5/D+20/D+60 가능한 범위, 계절성, 서사 타임라인, 공식 루머 검증.
Trigger가 켜졌는데 Event 섹션이 축약되면 Quality Gate 실패다.
