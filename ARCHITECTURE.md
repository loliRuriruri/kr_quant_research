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

## 하지 않는 것

- 주문·잔고·체결
- LLM이 Quant 필드를 수정
- 결측 Factor 재정규화로 한 팩터 고점
- 원주가 모멘텀을 순위에 합산
