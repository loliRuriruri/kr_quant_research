# 00. Position Context — Optional Project Memory

이 파일은 새 프로젝트에서 보유종목 정보를 잃지 않기 위한 선택 파일이다. 실제 보유현황이 바뀌면 사용자가 갱신한다.

| Ticker | Company | Market | Avg Price | Quantity | Portfolio Weight | Last Updated | Notes |
|---|---|---|---:|---:|---:|---|---|
|  |  |  |  |  |  |  |  |

## Rules
- 현재 사용자 메시지의 포지션 정보가 이 파일보다 우선한다.
- 동일 종목이 있으면 Position-Aware Mode를 자동 적용한다.
- 평단·수량이 있으면 최소 평가손익과 목표가/무효화 가격의 손익을 계산한다.
- 총자산/비중이 없으면 최대 포지션 크기를 임의로 확정하지 않는다.
