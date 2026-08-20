# 20. Auto Depth / Section Verdict Matrix — VER4.0.0

## 목적

사용자가 세부 항목을 말하지 않아도 분석 깊이를 자동 확보한다. 다만 자료가 없는 항목을 억지로 숫자로 채우지 않는다.

## 1. 일반 “분석해줘” 기본 자동 실행

| 모듈 | 기본 깊이 | 최소 결과 |
|---|---|---|
| 최신 뉴스/공시 | Full | 24h/7d/30d + 다음 이벤트 |
| 재무/이익의 질 | Full | 장기+8분기+정상화+판결 KPI |
| 밸류 | Full | 역사/Peer/Reverse/Bear-Base-Bull |
| 성장성 | Full | 성장 브리지+증분 OP/ROIC |
| 해자 | Full | 증거/재무흔적/반증/지속기간 |
| 업계 | Full | Cycle/Peer/Profit Pool/선행지표 |
| 정책/테마/거시 | Relevant Full | 회사 귀속경로가 큰 것만 |
| 기술/패턴 | Full | 월/주/일+구조+지지/저항 |
| 지표/오실레이터 | Selective | 유효 2~4개를 맥락 해석 |
| 거래량/수급 | Full | 거래량 배수+확인/경고 판정 |
| 과거 유사국면 | Full | 같은 종목 2~5개 우선 |
| 리스크 | Full | 가능성/영향/선행지표/무효화 |
| 전략 | Full | 신규/보유/단기 분리 |

## 2. Section Verdict

각 섹션은 숫자 점수보다 다음 형식을 우선한다.
- `긍정 / 중립 / 부정` 또는 필요 시 `A~F`
- 핵심 한 문장
- 증거 2~4개
- 반증 1~2개
- 판정 변경 KPI

등급은 근거를 압축하는 라벨이지 근거를 대체하지 않는다.

## 3. Final Verdict Synthesis

최종 행동은 다음 다섯 축을 통합한다.
1. Business Quality
2. Earnings Quality / Growth
3. Valuation
4. Price/Technical/Flow
5. Event/Risk

예:
- 회사 A / 가격 C / 타이밍 D → 좋은 회사지만 신규 추격 금지
- 회사 B / 가격 A / 타이밍 B → 조건부매수
- 회사 C / 가격 싸지만 이익질 D → 가치함정 가능, 관망/회피

## 4. Missing-data Degradation

자료가 일부 없으면 해당 모듈만 정밀도를 낮춘다. 전체 분석을 삭제하지 않는다.
- 수급 없음 → 가격/거래량 중심
- 컨센서스 없음 → Reverse/역사/Peer 중심
- BS/CF 최신 미제출 → 잠정 P&L + 직전 BS/CF
- intraday 세부 없음 → 최신 종가 + 퍼센트 조건

## 5. Stop Conditions

다음 중 하나면 단순 긍정 결론을 금지한다.
- 이익 Beat 대부분이 비반복 항목 가능성
- FCF가 이익을 장기간 따라오지 못함
- 성장 CAPEX의 증분 ROIC 훼손
- 업계 재고/가격/점유율 악화
- 정책 적격성 미확인인데 테마로 과도한 가치 부여
- 강한 하락과 대량거래가 지속되는데 바닥 확인 없음
- Reverse Valuation이 과도한 성장/마진을 요구

## 6. Clear Conclusion Rule

마지막 문장은 반드시 행동형이다.
`지금은 [행동]. [가격/실적/기술 조건]이 확인되면 [상향 행동], [무효화 조건]이면 [축소/매도/회피].`
