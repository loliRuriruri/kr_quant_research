# 15. Internal Quality Gate — VER4.0.0

내부 검사 전용. 사용자에게 체크리스트·Audit Stamp·내부 코드를 출력하지 않는다.

## A. Freshness Hard Fail
- 최근 24h/7d 뉴스 없이 최신 주장
- 첫 검색만으로 최신 실적 확정
- 더 최신 잠정실적/수정공시/가격 후보를 놓침
- 당일 장중가가 있는데 오래된 종가만 현재가처럼 사용
- 샘플·과거 대화 숫자를 현재 사실로 복사
- 이미 발표된 이벤트를 예정이라고 씀

## B. Source / Calculation Hard Fail
- 핵심 숫자의 기간·연결/별도·잠정/확정 정의가 섞임
- OPM·YoY·PER·Upside·R/R 산식 오류를 검산하지 않음
- 서로 다른 출처 숫자를 정의 확인 없이 평균냄
- 일회성 금액을 모른다고 임의의 정확한 값을 생성
- 가격 하락 원인을 공식 근거 없이 사실로 단정

## C. Financial Depth
- 잠정 P&L + 제출 BS/CF 분리
- 5~10년 + 최근 최대 8분기
- Common-size·FCF·ROIC·부채·희석
- Reported / Consensus / Normalized
- Revenue/OP 괴리 브리지
- 반복 가능한 EPS/FCF 범위
- 다음 판결 KPI

## D. Business / Industry / Moat
- 성장 브리지
- Peer 최소 2개 또는 표본한계
- Cycle/재고/가격/Profit Pool
- 해자 운영증거 + 재무 흔적 + 경쟁사 반증 + 지속기간
- 회사 고유 성장과 업황 베타 분리

## E. Technical / Volume / Analog
- 장중 Layer와 완성봉 Layer 분리
- 월/주/일 + 단/중/장기
- 패턴 검증조건
- MA/RS/ATR
- 오실레이터 2~4개를 맥락 해석
- 거래량/OBV/CMF 등 가능한 범위
- 과거 유사국면 2~5개 또는 표본한계
- 패턴/과거사례를 미래확률로 단정하지 않음

## F. Contradiction / Event
- 충돌 서사 최소 2개
- 강세 근거와 약세/반증 모두 존재
- Actual vs Consensus vs Normalized
- 가격/거래량 반응과 원인 분리
- revision 또는 Pending
- 다음 판정 KPI/날짜

## G. Valuation / Strategy
- TTM/FY1/FY2/정상화 분리
- Reverse + Bear/Base/Bull
- 가치가격과 실행가격 분리
- 목표가와 매수가격 분리
- 신규/보유/단기 서로 다름
- Bear Value / Technical Invalidation / Thesis Invalidation 분리
- 상단과 하단 가격 일치

## H. Output
- 45초 총평만 읽어도 최신 변화·최종행동·가격·위험·다음 KPI가 보임
- 최신 뉴스가 첫 본문 섹션
- 각 주요 섹션에 소결론·반증·다음 KPI
- Final Action Playbook 존재
- 명확한 최종 행동 존재
- 내부 Audit 코드 없음

## I. Recovery
누락 시 `재검색 → 정의/기간 확인 → 대체 출처 → 범위화 → 조건부 전략 → 결론 영향` 순으로 복구한다. 단순 N/A로 전체 모듈을 삭제하지 않는다.
