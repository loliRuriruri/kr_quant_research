# 01. Router / Entity / Freshness — VER4.0.0

## 1. Entity Lock

내부 객체:

`requested_name, canonical_company, ticker, exchange, currency, security_type, fiscal_year_end`

가격·공시·재무·컨센서스·차트가 같은 증권을 가리키는지 확인한다. 현재 메시지의 새 종목이 과거 대화보다 우선한다.

## 2. 분석 모드

- Fundamental Only
- Technical Focus
- Earnings/Event Update
- Position-Aware
- Portfolio
- Auto Hybrid Deep Research

사용자가 짧게 물으면 Auto Hybrid가 기본이다.

## 3. Live-First Routing

다른 분석보다 먼저:

1. 사용자 현지시각과 시장 현지시각
2. 최근 24시간·7일·30일 뉴스·공시
3. 최신 잠정실적·실적발표
4. 마지막 제출 재무
5. 장중가격 또는 최신 종가
6. pre/post 컨센서스
7. OHLCV와 수급

을 확인한다.

스킬·프로젝트의 과거 예시와 샘플은 현재 사실의 출처가 아니다.

## 4. Freshness Clock

별도 기록:

- 분석시각
- 시장세션
- 장중가격 시각
- 마지막 완성 종가 시각
- 최신 뉴스·공시 발표시각
- 최신 잠정실적 발표시각
- 마지막 제출 보고서 접수시각
- 컨센서스 기준일
- 다음 예정 이벤트

장후 발표면 발표 전 종가와 다음 세션을 분리한다. 장중이면 현재 틱과 완성봉을 섞지 않는다.

## 5. Candidate Selection

뉴스·실적·가격 후보를 시간순으로 비교한다.

- 더 최신 유효 후보가 있으면 과거 선택을 폐기
- 수정공시는 원공시보다 우선
- 잠정실적은 최신 P&L 이벤트
- 제출 보고서는 BS·CF·주석용
- 장중가는 이벤트 반응, 완성봉은 추세 계산용

## 6. 기본 보고서 순서

`최신 뉴스 → 재무 → 밸류 → 성장·해자·업계 → 정책·테마 → 기술·유사국면 → 리스크 → 목표가·가격지도 → 신규·보유·단기 전략`

## 7. 출력

첫 줄:

`기준: [분석시각] / 시장: [세션] / 가격: [장중·전일종가] / 최신실적: [기간·잠정/확정·발표일] / 다음 이벤트: [날짜]`

내부 라우팅·Readiness·PASS/FAIL 표는 출력하지 않는다.
