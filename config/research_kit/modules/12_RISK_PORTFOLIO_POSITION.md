# 12. Risk / Position / Portfolio — VER4.0.0

## 1. 자동 실행
평단·수량·비중·손익·총자산·포트폴리오 중 하나라도 있으면 실행한다.

## 2. 가능한 계산
- 평가금액·손익률
- 추가매수 후 새 평단
- 목표가별 손익
- 기술 무효화·Bear Value 손실
- 이벤트 갭 스트레스
- 종목·산업·국가·통화 집중도

## 3. Position Sizing
총자산과 허용손실률이 있을 때:
`허용손실액 / 주당 위험 = 최대수량`

갭 종목은 정상 손절보다 보수적인 gap stress를 사용한다.

## 4. Risk Layers
- Fundamental downside
- Technical downside
- Event gap
- Liquidity/slippage
- Currency
- Portfolio factor concentration

## 5. 기존 보유자 우선 질문
- 투자논문이 유지되는가?
- 현재 가격이 가치보다 위인가 아래인가?
- 추가매수는 평균단가를 낮추는가, 위험을 키우는가?
- 같은 팩터에 이미 과도하게 노출됐는가?

총자산이 없으면 최대수량을 확정하지 않지만, 손익·새 평단 등 계산 가능한 것은 먼저 한다.
