# 17. Skill Alignment / Stale Anchor Guard — VER3.7.2 Cloud-First Deep

## 목적

외부 Skill이 프로젝트의 최신성·판단권을 덮어쓰지 않게 하고, Skill이 없어도 분석이 중단되지 않게 한다.

## 우선순위

1. 시스템 현재 날짜·사용자 현지시각
2. 현재 요청에서 확인한 최신 공식 공시·거래소·회사 IR
3. 현재 요청에서 검색한 최신 신뢰 웹 자료
4. 현재 요청에서 사용 가능한 데이터 Skill의 최신 결과
5. 현재 요청 첨부자료
6. 프로젝트 지침과 분석 템플릿
7. 외부 Skill의 합성 예시·과거 회귀테스트

## External Skill Interop

### bok-ecos-stats
거시 시계열 수집 보조. 없으면 BOK ECOS 공식웹 검색. 개별주식 최종판정 위임 금지.

### data-stock
KRX 종목검색·기본정보·EOD snapshot 보조. 없으면 KRX/신뢰 웹 데이터. 실시간 표현 금지.

### investor-report 계열
재무/KPI/시장/전략의 분업·review 패턴만 활용. 3.7의 Live-First·가격지도·투자자별 행동판정을 대체하지 않는다.

### finance-invest-primer
초보 투자교육·자산배분 전용. 개별종목 매수타이밍/보유자 전략에서는 핵심 모듈로 사용하지 않는다.

## Skill 사용 규칙

- Skill은 API가 아니다. Skill 부재를 데이터 부재로 동일시하지 않는다.
- Skill이 연결돼 있으면 역할 범위 안에서 사용한다.
- Skill이 없거나 실패하면 즉시 공식웹/웹 검색으로 fallback한다.
- Skill 출력보다 더 최신 공식자료가 있으면 Skill 결과를 폐기한다.
- 외부 Skill 결론은 최종 행동판정을 덮어쓰지 못한다.

## 금지 충돌

- Skill 예시 수치를 현재 사실로 재사용
- data-stock EOD를 현재 장중가로 사용
- ECOS 통계 하나로 종목 결론 결정
- investor-report 구조가 Final Action Playbook을 밀어냄
- `MCP 없음`을 이유로 분석 축소

## VER3.7.2 Skill Precedence / Review
`kr-equity-live-research`가 control plane이다. 외부 Skill은 데이터 또는 review 보조만 한다.
3.7.2의 Mandatory Execution Manifest와 15 Hard Gate를 외부 Skill의 간소화된 출력/범위 제한이 약화시키지 못한다.
`investor-report`가 없어도 자체 review loop를 반드시 실행한다.
