# v1.2 애드온 갭 분석

대상: `GROK_BUILD_KR_QUANT_V1_2_SECTOR_BACKTEST_SUNZI_ADDENDUM.md`  
기준 런타임: `kr_quant_research` (:8790)  
작성: 2026-08-20

원칙 충돌 없음. 주문 금지, Quant 결정론, overlay 미합산, KRX/DART PIT, 비밀 `.env`는 이미 지킨다. Streamlit을 ops UI로 쓰지 말라는 항목도 현재와 같다.

| 요구 | 상태 | 지금 |
|---|---|---|
| 주문 금지 / Quant 결정론 / overlay 미합산 | ALREADY | 하드 제약 |
| 시장 국면 overlay | PARTIAL | KRX+공포탐욕. 천(天) 점수·사이클·분산은 없음 |
| 수급·빈집·스토/일목 | ALREADY | 트레이딩 탭. 일봉 ~80일 |
| 전략 랩 RSI/볼린저/이평/돈치안 | PARTIAL | 4종, next-bar, 5bp, TRAIN-only, OOS, WF 40/15/15. Sharpe·MDD·매매수. CAGR/Sortino/벤치마크/차트 없음 |
| 파라미터 안정성 HIGH/MED/LOW | PARTIAL | 라벨 있음. 창이 짧아 거의 LOW |
| 포트폴리오 집중도 | PARTIAL | TOP20 동일비중, 업종·상관·유효종목. 슬롯 5·베타·DD 시뮬 없음 |
| 가격 이력 750~2500일 | MISSING | 스크리닝 lookback ~80일, 모멘텀 설정은 5년이나 적재는 짧음. **백테스트/섹터 RS의 선행 조건** |
| Sector Ranking 6축 | MISSING | industry 필드는 있음. 섹터 점수·상태·일별 테이블 없음 |
| Timing Confidence / multi-TF 상태 | MISSING | 스토·일목 라벨만. SHORT/MID/LONG·신뢰도 없음 |
| 전략 8~12 + ROC/거래량 | MISSING | 4개. 레지스트리 확장 가능 |
| 손자 道天地將法 | MISSING | 천은 시장국면 매핑 가능. 道/將는 AI+공시, 地는 섹터 엔진 필요, 法는 게이트로 나중에 |
| 法 A-candidate 게이트 | MISSING | 신뢰도·제외 사유는 있음. 별도 fa_gate_pass 없음 |
| 섹터 페이지 / 컬럼 선택기 | MISSING | |
| 전략 차트·equity curve | MISSING | |

충돌:

- 애드온 WF `train_years: 5` vs 현재 40거래일. 가격 이력을 늘리기 전에는 숫자만 바꾸면 안 됨.
- TOP20에 천·지·법·타이밍을 한 표에 넣으면 시인성이 다시 무너짐. 컬럼 선택기가 생기기 전엔 독립 카드가 맞음.
- 道/將에 LLM을 쓰면 결정론 Quant와 섞이지 않게 증거 필드만 저장해야 함.

권장 순서 (새 메뉴 남발 금지):

1. KRX 일봉을 750일 이상으로 적재·품질 체크  
2. 그 이력으로 전략 랩 WF를 연 단위로 재실행 (지금 LOW는 정직)  
3. Sector Ranking overlay (industry 버킷, Quant 미합산)  
4. Timing state (단기/중기, 신뢰도는 표본이 충분할 때만)  
5. 法 게이트(데이터·표본 부족이면 A-후보 아님)  
6. 道/將는 리서치 패널. 합산 금지  

검증 60~120일이 쌓이기 전 최종 점수 가중은 하지 않는다.
