# 15. Internal Quality Gate — VER3.7.2 HARD GATE

이 파일은 내부 검사 전용이다. 체크리스트·Audit Stamp·내부 코드를 사용자에게 출력하지 않는다.

## 0. Final Response Prohibition

Auto Hybrid Deep Research에서는 이 Gate를 실행하기 전 Final Action을 확정하지 않는다.
Mandatory 항목이 빠졌고 공개자료로 추가 확인 가능성이 있으면 **재검색·재계산 후 다시 Gate**한다.
사용자가 특정 모듈을 명시적으로 제외한 경우에만 해당 항목을 Gate에서 제외한다.

## A. Freshness / Finality Hard Fail
- 최근 24h/7d 뉴스·공시 잠금 없이 최신이라고 주장
- 더 최신 잠정실적/보고서/가격 후보가 있는데 과거값 선택
- 잠정 P&L과 제출 BS/CF를 같은 확정성으로 혼합
- 현재가격을 완료봉 지표에 사용하거나 미완성봉으로 장기 MA 계산
- 장중 외인/기관/프로그램 수치를 검증 없이 생성
- data-stock EOD snapshot을 실시간으로 표현
- 프로젝트 예시·과거 분석 숫자를 현재 사실로 재사용

## B. Source Escalation Hard Fail
최신 제출 보고서 존재가 확인됐는데 한 번의 endpoint 실패만으로 이전 분기 BS/CF에 후퇴하면 실패.
최소 공식 재검색 + 대체 공식경로 + 보조경로를 거친 뒤에만 이전 검증값 사용 가능.

## C. Financial Mandatory
자료가 존재하는 범위에서:
- 최신 P&L + 마지막 제출 BS/CF/주석
- 5~10년 또는 가능한 최대 장기
- 최근 최대 8개 단독분기
- Gross/OP/Net/FCF margin
- CFO/NI, FCF/NI, CapEx/CFO
- 운전자본·재고·채권
- 순현금/순차입·이자
- ROIC/증분 ROIC 가능한 범위
- 희석/SBC/CB/BW/자사주
- 일회성·정상화 EPS/FCF

빠진 항목은 `자료 미확인`으로 끝내기 전에 최소 1회 대체소스/대체계산을 시도한다.

## D. Valuation Mandatory
- TTM/FY1/FY2/Normalized
- 역사/Peer
- Reverse Valuation
- Bear/Base/Bull
- 10%·12%·15% 요구수익률 매수상한
- Fundamental R/R 1.5x·2.0x 상한 가능한 범위
- 가치가격 ≠ 목표가 ≠ 실제 진입가격
- 상단/하단 숫자 일치

12% 한 개만 계산하면 실패.

## E. Moat / Industry / Macro Mandatory
- 해자: 운영 증거→재무 흔적→경쟁사 반증→지속기간
- 산업: 수요·공급·가격·재고·점유율·Cycle Stage·선행지표
- 거시: 회사에 중요한 3~5개를 실적/FCF 경로와 연결
- 정책 관련성이 있으면 전달경로와 실패조건

## F. Technical / Flow Mandatory
자료가 존재하면:
- 월/주/일
- 5/10/20/50/60/120/200D + 40W 가능한 범위
- 구조/Stage
- 20/60/120D RS
- ATR + MDD/변동성
- 주요 패턴·지지·저항
- 필요한 오실레이터 2~4개
- 거래량 + EOD 수급 + 공매도/신용/대차 가능한 범위
- 장중 수급은 Optional

5/10/20D + RSI만으로 Full Technical을 끝내면 실패.

## G. Event / Analog Mandatory
Trigger가 있으면:
- D-5/D-20/D-60
- Actual vs Consensus
- Revision 또는 Pending
- D+1/D+5/D+20/D+60 가능한 범위
- 계절성/서사
- 같은 종목 Analog 최소 2개, 가능하면 3~5개

동일종목 사례를 검색했지만 부족한 경우에만 부족 사유 + Peer analog로 대체 가능.

## H. Position / Strategy Mandatory
- 신규 / 보유 / 단기 분리
- 1·2·3차 / 돌파 / 추격금지 / 목표 / 무효화
- 포지션이 있으면 현재 대화와 Position Context 확인
- 평단·수량이 있으면 평가손익과 계산 가능한 추가매수/목표가 시나리오
- Bear Value, Technical Invalidation, Thesis Invalidation 분리

포지션 정보가 있는데 `평단을 모른다`고 쓰면 실패.

## I. Recovery Loop
실패 항목마다:
1. 쿼리·날짜·언어·공시유형 변경
2. 공식 원문 직접 검색
3. 다른 공식/신뢰 보조 소스
4. 사용 가능한 외부 Skill 보조
5. 직접 계산/범위 추정
6. 그래도 불가하면 마지막 검증 데이터 + 기준일 + 정밀도 영향

## J. Exit Condition
모든 Mandatory 항목이 `충족`, `사용자 제외`, 또는 `재탐색 후 미확인 + 영향 명시` 중 하나가 되어야 Final Action을 확정한다.
