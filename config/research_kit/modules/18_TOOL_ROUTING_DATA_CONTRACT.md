# 18. Cloud-First Tool Routing / Data Contract — VER3.7.2

## 1. 목적

PC·Docker·MCP 없이도 기본 분석을 완주하는 Cloud Router를 정의한다. 연결형 데이터는 선택적 보강재이며 **분석 깊이 축소의 이유가 될 수 없다**.

`Cloud/Official/Optional Skill → Observation → Freshness/Finality → Analysis Modules → Hard Quality Gate → Final Action`

## 2. Source Router

### 한국주식
| 데이터 | 1순위 | 2순위 | 3순위 |
|---|---|---|---|
| 공시·실적 | DART/OpenDART/KIND/회사 IR | 보고서 PDF/거래소 | 주요 언론 |
| 최신 가격 | 거래소/신뢰 최신 시세 | 금융포털 교차검증 | 주요 언론 |
| EOD OHLCV | KRX | data-stock(있으면) | 신뢰 차트포털 |
| EOD 투자자 수급 | KRX/공식시장자료 | 금융포털/증권사 | 주요 언론 |
| 공매도 | KRX/공식시장자료 | 금융포털 | 미확인 |
| 대차·신용 | 공식시장자료/증권사 | 금융포털 | 미확인 |
| 거시 | BOK ECOS/정부 | bok-ecos-stats(있으면) | 주요 언론 |
| 컨센서스 | provider/증권사 | 금융포털 | 주요 언론 |

미국: SEC/회사 IR/Fed·FRED·BEA·BLS + 신뢰 시장자료.
일본: EDINET/TDnet/JPX/J-Quants/BOJ/MOF + 신뢰 시장자료.

## 3. External Skill Contract
- `data-stock`: KRX EOD/basic helper. 실시간으로 표현 금지.
- `bok-ecos-stats`: BOK macro helper.
- `investor-report`: review/counterevidence pattern only.
- `finance-invest-primer`: single-stock action core에서 제외.
- 외부 Skill이 없어도 동일한 분석 구조를 유지한다.

## 4. Optional Connected Layer
KIS/broker MCP가 실제 연결된 경우 장중 현재가·외인/기관 추정·프로그램 등을 보강할 수 있다. 연결되지 않아도 3.7.2는 완주한다.

## 5. Finality
- 현재가격: 관측시각 포함
- 기술지표: 마지막 완료봉
- EOD 수급: 거래일 명시
- 장중 수급: 검증 공급자 있을 때만 `장중 추정`
- 잠정실적: 최신 P&L
- 제출재무: BS/CF/주석
- 컨센서스: provider as-of

## 6. Missing Intraday Flow
장중 외인·기관·프로그램이 없으면 EOD 3D/5D/20D 누적, 거래량/거래대금, 가격구조, 시장·업종 RS, 공매도·신용·대차 최신 공개치로 대체한다. 수치를 만들어내지 않는다.

## 7. Filed Report Recovery
최신 제출 보고서 존재가 확인됐으면 해당 보고서의 BS/CF/주석을 우선 추출한다. 한 경로가 실패하면 02의 Recovery Ladder를 실행한다. 이전 분기 사용은 마지막 수단이다.

## 8. No-PC Contract
기본 3.7.2는 Docker, 로컬 MCP, Secure Tunnel, 상시 켜진 PC, KIS Secret을 요구하지 않는다.
