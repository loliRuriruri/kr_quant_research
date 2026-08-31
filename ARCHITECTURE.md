# 설계

두 제품을 이어붙이지 않고 역할을 나눴다.

## 점수

- Value 30 / Quality 25 / Growth 25 / Stability 10
- Momentum 10은 `enabled: true` (상장주식수·시총으로 분할만 보정, 배당 TR 아님)
- 런타임 설정은 `GET /api/system/spec` 이 설정 파일을 직접 읽는다
- TOP100 커버리지 80%, TOP20 90% + 영업이익·순이익·CFO 양수
- 재무 신선도 270일, CFS/OFS 혼합 금지
- 시장 국면·FRED·Yahoo·전략 샤프는 `used_in_quant: false`

## 데이터

- 가격 정본: KRX Open API
- 재무: OpenDART TTM
- 보조: Toss 시세, 네이버 뉴스, FRED 거시, Yahoo 비교
- 매 실행일의 구성종목은 `universe_snapshot.parquet`와 `universe_evidence.json`으로 보존한다
- 상장일 이후·확인된 상장폐지일 이전만 PIT 적격으로 보되, 날짜가 없는 종목은 임의 제거하지 않고 커버리지 한계를 남긴다
- 현재 TOP20을 과거로 소급한 전략 결과는 횡단면 PIT 백테스트가 아니며 `LIMITED_CURRENT_COHORT`로 표시한다

## 전략 체결 연구

- 종가 신호는 다음 체결 가능한 거래일 시가에 실행한다
- 수수료·날짜별 매도세·슬리피지·거래대금 참여율 시장충격을 차감한다
- 거래량 0과 일봉상 상·하한가 한 가격 잠김은 미체결 처리한다
- 실시간 호가·잔량 재현이 아닌 일봉 프록시이며 주문 기능은 없다

## 메뉴 근거 계약

- 모든 주요 메뉴는 `contract_version`, `sources`, `as_of`, `observed_at`, `sample`, `calculation_state`, `used_in_quant`, `limitations`를 공통 형식으로 공개한다
- 로컬 `/api/status`와 공개 정적 스냅샷이 같은 근거 레지스트리를 사용한다
- 공개 배포는 대시보드·랭킹·스크리너의 핵심 근거 계약이 누락되거나 무효면 실패 폐쇄한다
- API 설정 계약은 로컬 전용이며 공개 스냅샷에서 제거한다

## 하지 않는 것

- 주문·잔고·체결
- LLM이 Quant 필드를 수정
- 결측 Factor 재정규화로 한 팩터 고점
- 원주가 모멘텀을 순위에 합산
