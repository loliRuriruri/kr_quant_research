# 13. Country / Live Queries / Macro / Policy / Source Rules — VER3.7.2 Cloud-First Deep

## 1. 공통

거시·정책은 `최신 공식상태 → 노출 사업부 → 수요·가격·비용 → OP/EPS/FCF → 가치·차트`로 연결한다.

## 2. 한국 — Cloud Priority

우선 출처:

1. DART/OpenDART
2. KIND/KRX
3. 회사 IR
4. KRX Data Marketplace/공식 웹 — 완료 거래일 가격·수급·공매도·통계
5. 한국은행 ECOS — 금리·환율·물가·통화·채권
6. 정부부처·통계청·협회
7. 신뢰 가능한 금융포털·주요 언론
8. 사용 가능한 경우 `data-stock`, `bok-ecos-stats`
9. KIS/broker MCP는 연결돼 있을 때만 장중 보강

`data-stock`은 종목검색·기본정보·완료 거래일 종가/거래량 fallback으로만 사용한다. `bok-ecos-stats`는 거시 시계열 수집 모듈로 사용한다.

Live queries:

- `회사명 + 연도 + 분기 + 잠정실적`
- `회사명 + 영업(잠정)실적 + 공정공시`
- `site:kind.krx.co.kr + 회사명 + 날짜`
- `site:dart.fss.or.kr + 회사명 + 분기보고서`
- `종목코드 + 오늘 주가 + 거래량`
- `회사명 + 외국인 기관 순매수 + 날짜`
- `회사명 + 실적 발표 + 급등/급락 + 날짜`
- `회사명 + 목표주가 + EPS 추정치 + 상향/하향`

## 3. 미국

- SEC EDGAR·회사 IR
- 거래소·OCC·Cboe·FINRA
- Fed/FRED/BLS/BEA/Treasury
- 신뢰 시장데이터/주요 금융언론

## 4. 일본

- EDINET·TDnet·회사 IR
- JPX·J-Quants
- BOJ·MOF·FSA
- 신뢰 시장데이터/주요 금융언론

## 5. 정책 상태

`발표 → 발효 → 예산·세칙 → 회사 적격성 → 주문 → 납품 → 회계인식 → 현금`

공식 단계·날짜·실패조건을 확인한다. 정책 총액을 회사 매출로 곧바로 사용하지 않는다.

## 6. Macro Selection

기업별 상위 3~5개만 깊게 분석한다. 한국 기업 환율 민감도가 중요하면 ECOS 또는 `bok-ecos-stats`의 원/달러와 회사 환노출/헤지를 연결한다.

## 7. Source Quality

`Primary filing/exchange > official statistics > trustworthy market-data/provider > major financial news > general portal > community`

사용 가능한 Skill은 **공식 원천의 조회 보조층**으로 취급한다. Skill 출력이 공식 원문보다 오래되면 폐기한다.

## VER3.7.2 Macro Minimum Pack
일반 종목도 실적·현금흐름에 영향을 주는 핵심 거시 3~5개를 선정한다. 단순 지표 나열이 아니라 `거시 변화 → 수요/가격/마진/자본비용/FCF → 기업 영향`으로 연결한다.
정책 관련성이 있으면 발표→법적 발효→예산/규칙→회사 적격성→주문→납품→회계→현금회수의 전달경로를 최소 한 번 검증한다.
