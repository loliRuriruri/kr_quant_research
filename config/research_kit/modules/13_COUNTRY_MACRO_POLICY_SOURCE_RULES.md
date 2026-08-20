# 13. Country / Live Queries / Macro / Policy / Source Rules — VER4.0.0

## 1. 공통

거시·정책은:

`최신 공식상태 → 노출 사업부 → 수요·가격·비용 → OP/EPS/FCF → 가치·차트`

로 연결한다.

## 2. 한국

우선 출처:

- DART/OpenDART
- KIND/KRX
- 회사 IR
- 한국은행·통계청·정부부처
- 신뢰 가능한 금융포털·주요 언론

Live queries:

- `회사명 + 연도 + 분기 + 잠정실적`
- `회사명 + 영업(잠정)실적 + 공정공시`
- `site:kind.krx.co.kr + 회사명 + 날짜`
- `site:dart.fss.or.kr + 회사명 + 분기보고서`
- `종목코드 + 오늘 주가 + 거래량`
- `회사명 + 실적 발표 + 급등/급락 + 날짜`
- `회사명 + 목표주가 + EPS 추정치 + 상향/하향`

공식 검색 색인이 늦으면 포털·언론으로 이벤트를 발견한 뒤 원문을 역추적한다.

추가:

- 외국인·기관·개인·프로그램
- 공매도·대차·신용
- ETF·리밸런싱
- CB/BW·유증·대주주 담보
- 장후공시 다음날 갭
- NXT·시간외와 KRX 정규장 분리
- 가격제한·VI·거래정지

## 3. 미국

- SEC EDGAR·회사 IR
- 거래소·OCC·Cboe·FINRA
- Fed/FRED/BLS/BEA/Treasury

Live queries:

- `ticker + earnings release + quarter + year`
- `site:sec.gov + ticker + 8-K earnings`
- `company IR domain + results + date`
- `ticker + premarket/after-hours price volume`
- `ticker + guidance consensus revision`

추가:

- GAAP/Non-GAAP·SBC·희석
- 프리·애프터마켓
- 옵션 IV/OI
- 13F·short interest 지연

## 4. 일본

- EDINET·TDnet·회사 IR
- JPX·J-Quants
- BOJ·MOF·FSA

Live queries:

- `회사명/코드 + 決算短信 + 분기`
- `회사명 + 業績予想 修正`
- `종목코드 + 株価 今日 出来高`

추가:

- 100주 단위·점심휴장
- 엔화
- 신용잔고·공매도
- 지배구조 개혁·자사주

## 5. 정책 상태

`발표 → 발효 → 예산·세칙 → 회사 적격성 → 주문 → 납품 → 회계인식 → 현금`

공식 단계·날짜·실패조건을 확인한다. 정책 총액을 회사 매출로 곧바로 사용하지 않는다.

## 6. Macro Selection

기업별 상위 3~5개만 깊게 분석한다.

- 주택/HVAC: 모기지금리·단독주택 허가·기존주택·교체수요
- 반도체: ASP·재고·가동률·고객 CapEx
- 소비재: 실질소득·트래픽·재고·판촉
- 산업재: 수주·출하·백로그
- 금융: 금리곡선·신용비용·연체

예정 이벤트가 당일이면 이미 발표됐는지 먼저 확인한다.

## 7. Source Quality

Primary > 공식 집계 > 라이선스/신뢰 데이터 > 주요 언론 > 일반 포털 > 커뮤니티.

커뮤니티는 서사·루머 발견용이며 핵심 숫자의 최종 근거가 아니다.
