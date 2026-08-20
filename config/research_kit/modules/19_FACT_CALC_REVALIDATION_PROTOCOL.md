# 19. Fact / Calculation / Revalidation Protocol — VER4.0.0

## 1. 핵심 원칙

정확성은 출처만 붙인다고 확보되지 않는다. **출처 일치 + 기간 일치 + 정의 일치 + 산식 검산**까지 한다.

## 2. Fact Triangle

중요 사실은 가능한 범위에서 다음 중 2개 이상을 맞춘다.
- Primary: 공시·IR·거래소·정부
- Independent: Peer·협회·공식 통계
- Market: 가격·거래량·컨센서스

Primary 하나가 명확하면 같은 숫자를 기사 3개로 반복 확인할 필요는 없다. 대신 정의와 기간을 검증한다.

## 3. Arithmetic Sanity Checks

가능하면 자동 재계산:
- OPM = OP / Revenue
- Net margin = NI / Revenue
- YoY/QoQ = 현재 / 비교기간 - 1
- EPS × 희석주식수 ≈ NI(스코프 차이 주의)
- CFO/NI, FCF = CFO - 정상 CapEx
- PER = Price / EPS
- PBR = Price / BPS
- EV = Market Cap + Net Debt ± 기타 조정
- Surprise = Actual / Consensus - 1
- 목표가 Upside/Downside
- R/R = Base upside / Bear downside

오차가 크면 연결/별도, 평균/기말주식수, NCI, 지속/중단사업, 통화·단위 차이를 확인한다.

## 4. Period / Scope Lock

표마다 다음을 혼동하지 않는다.
- 누적 vs 단독분기
- 연결 vs 별도
- GAAP/IFRS vs 조정치
- Reported vs Constant Currency
- 잠정 vs 확정
- TTM vs FY1 vs FY2
- 장중 vs 종가
- 수정주가 vs 비수정주가

## 5. Cross-source Conflict

숫자가 다르면 평균내지 않는다.
1. 정의
2. 기준시각
3. 수정/정정 여부
4. 통화/단위
5. 연결범위
6. 주식수/기업행동 조정
순으로 차이를 설명하고 가장 적합한 값을 선택한다.

## 6. False Precision Guard

정확한 일회성 금액·컨센서스·수급·VWAP·Volume Profile 등을 확보하지 못했으면 추정치를 사실처럼 쓰지 않는다. 범위/조건/미확인으로 낮추고 결론의 정밀도만 조정한다.

## 7. Causality Guard

`주가가 떨어졌기 때문에 X가 원인이다`라고 쓰지 않는다.
- 사실: 무엇이 발표됐는가
- 반응: 가격/거래량이 어떻게 움직였는가
- 추론: 시장이 무엇을 우려했을 가능성이 있는가
- 검증: 공시·콜·리비전·다음 가격반응이 확인하는가
를 분리한다.

## 8. Final Consistency Pass

출력 직전:
- 상단/본문/Playbook 가격 일치
- 최신 실적 기간 일치
- 목표가 산식 일치
- 신규/보유 전략 논리 일치
- Bear Value와 기술 손절 혼동 없음
- 다음 이벤트가 이미 지난 날짜가 아님
을 다시 확인한다.
