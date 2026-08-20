# KR Quant Research — 현황 브리프 (GPT 검증용)

작성일: 2026-08-20  
대상 폴더: `C:\Users\a4jud\kr_quant_research`  
대시보드: `http://127.0.0.1:8790`  
모델: `kr_equity_quant` / `1.1.0-share-adj-momentum`

이 문서는 **현재 구현된 기능·설정·한도·하지 않는 일**을 한곳에 모은 검증용 브리프다.  
GPT Pro 등 외부 모델에 붙여 넣고 **보완 작업·추가 기능이 타당한지** 검토할 때 쓴다. 키·토큰·세션 값은 넣지 않았다.

---

## 1. 제품이 무엇인가

한국 주식 **조사 후보를 매일 같은 공식으로 뽑는 리서치 프로그램**이다. 자동매매 앱이 아니다.

출발점:

| 기존 | 경로 | 가져간 것 |
|---|---|---|
| 재무 스크리너 | `C:\Users\a4jud\stock_screener` (:8787) | OpenDART TTM, PIT, Quant 점수, DuckDB |
| Codex 디스커버리 | `C:\TEST\korea-quant-discovery-engine-v2` (:8501) | 시장 국면·관심종목 아이디어 (점수는 합치지 않음) |

새 제품은 둘을 이어붙이지 않고 **역할을 나눈 재설계**다.

### 1.1 절대 제약 (깨면 안 됨)

1. **주문·잔고·체결·자동매매 없음.** 키움/한투 키가 있어도 시세·조회만. 주문 API는 쓰지 않는다.
2. **Quant 점수는 결정론.** LLM이 점수·팩터·랭킹을 수정하지 않는다. AI 리포트는 버튼으로만 호출.
3. **시장·수급·13F·기술적 지표는 overlay.** `used_in_quant: false`. 합산 금지.
4. **한국 공식 시세는 KRX Open API.** yfinance/Yahoo는 비교·연구용.
5. **재무는 OpenDART PIT/TTM.** 당기 공시만 쓰고, CFS와 OFS를 한 TTM 안에서 섞지 않는다.
6. **비밀은 `.env`에만.** 로그·리포트·채팅에 키를 찍지 않는다.

### 1.2 사용자 의도 (대화에서 고정된 것)

- 재무 Quant 후보 + 그 밖의 **수급/트레이딩/미국 13F** 조사를 한 대시보드에서 본다.
- 기관·외인 **쌍끌이**, **사모펀드 매집**, **빈집(쌍매도·낮은 외인 지분)**, 이후 수익률 **연구**.
- 퀀트 TOP100 밖 종목도 거래대금·토스 랭킹에서 찾는다.
- 기술적 분석(스토캐스틱·일목)은 트레이딩 탭에만.
- 미국은 13F 기관 보유만 (WhaleWisdom 스크랩 금지, SEC EDGAR 원문).

---

## 2. 실행·레이어

### 2.1 실행

```text
C:\Users\a4jud\kr_quant_research
.\.venv\Scripts\python.exe -m kr_quant.cli doctor
.\.venv\Scripts\python.exe -m kr_quant.cli demo
.\Start-KR-Quant.bat          # 대시보드 :8790
.\.venv\Scripts\python.exe -m pytest -q
```

대시보드 작업:

- 데모 실행
- 재계산만 (이미 받은 parquet)
- 실데이터 재계산 (수집 스킵)
- 실데이터 수집+계산 (OpenDART 한도 때문에 수십 분)

CLI: `doctor`, `demo`, `screen`.

### 2.2 계층

| 계층 | 하는 일 | Quant 합산 |
|---|---|---|
| Discovery | KRX+DART TTM, 유니버스, 팩터, 리스크 페널티, TOP100/20 | 예 |
| Context | 시장 국면, 관심종목, “왜 나왔는가” | 아니오 |
| Research | AI 분석 리포트 (VER4 키트), 네이버/Toss/FRED | 아니오 |
| Flow / Trading | 쌍끌이·사모·빈집·스토캐/일목 | 아니오 |
| US 13F | SEC 기관 보유 분기 스냅샷 | 아니오 |
| Timing | 지표는 트레이딩 overlay로 일부 구현. 전략 백테스트 랩은 자리만 | 아니오 |

`ARCHITECTURE.md`의 “모멘텀 disabled”는 **구버전**이다. 현재 `quant_v1.yaml`은 모멘텀 `enabled: true` + 상장주식수 보정.

---

## 3. Quant Discovery (점수)

설정 파일: `config/quant_v1.yaml`, `universe_rules.yaml`, `risk_rules.yaml`, `account_map_ifrs.yaml`.

### 3.1 점수 구성 (100점)

| 팩터 | 배점 | 내용 |
|---|---|---|
| Value | 30 | EV/EBIT, FCF yield, earnings yield, PBR (피어 백분위) |
| Quality | 25 | ROIC, 영업이익률, ROE, CFO/NI, 마진 안정성 8Q |
| Growth | 25 | 매출·영업 YoY TTM, 3Y CAGR, EPS YoY |
| Momentum | 10 | 3m/6m/12m, 시장대비 6m, 52주 고점 거리 |
| Stability | 10 | 순부채/자산, 부채비율, 이자보상, CFO/자산, 유동비율 |
| 소프트 페널티 | 최대 −15 | 매출·영업 연속 악화, 레버리지, 희석, CB/BW 등 |

피어: 업종 n≥20 → 섹터 n≥40 → 시장. 윈저라이즈. 결측 팩터를 재정규화해서 다른 팩터를 부풀리지 않음.

### 3.2 모멘텀 보정

KRX에 공식 수정주가가 없다.

- `listed_shares_adjustment: true`
- 레벨 = `시가총액` 우선, 없으면 `종가 × 상장주식수`
- **액면분할만** 흡수. **배당 재투자(TR) 아님.** yfinance adj close 사용 안 함.

### 3.3 유니버스 게이트

- 시장: KOSPI, KOSDAQ 보통주
- 제외: 금융 KSIC, 리츠, 인프라펀드, 스팩, 우선주, ETF/ETN/ELW
- 시총 ≥ 300억, 60일 중위 거래대금 ≥ 3억, 63거래일 중 관측 ≥ 45
- 음(-)의 자본 제외
- TOP100: 가중 커버리지 ≥ 80%, 데이터 신뢰도 ≥ 70
- TOP20: 커버리지 ≥ 90%, 신뢰도 ≥ 80, 영업이익·지배주주순이익·CFO TTM 모두 양수

### 3.4 PIT / TTM

- 공시 접수일 이후만 사용 (`action_date: NEXT_TRADING_DAY`)
- TTM 길이 330–400일
- 재무 신선도 270일
- CFS 우선, 같은 TTM에 CFS/OFS 혼합 금지
- 계정 매핑: `account_map_ifrs.yaml`

### 3.5 산출물

- `data/output/latest_top20.csv`, `latest_top100.csv`, `latest_all_stocks.parquet`
- 일자별 `data/output/as_of_date=YYYY-MM-DD/`
- DuckDB `db/screener.duckdb` (일별 히스토리·순위 변화)
- 최근 실데이터 기준일: **2026-08-19** (약 2763종목 마스터)

---

## 4. 대시보드 탭

그룹: Quant / 시장·수급 / 리서치 / 시스템.

### 4.1 대시보드

- TOP20, 데이터 품질, 보관 리포트
- 토스 실시간 랭킹: 급상승·급하락·거래대금·토스 거래대금 (이름 보정)
- FRED + Yahoo 지수 (점수 미포함)

### 4.2 랭킹

적격 유니버스 전체 점수순. 검색. 종목 클릭 시 상세 서랍.

### 4.3 시장 국면

**매일 cron 없음.** 탭을 열면 `/api/market`이 그 자리에서 계산.

| 구성 | 소스 | 갱신 |
|---|---|---|
| 한국/미국 공포·탐욕 | feargreed.co.kr API (`feargree-api.vercel.app`), CNN 폴백 | 프로세스 메모리 **10분** 캐시 |
| 내부 국면 점수 | KRX `prices.parquet` 추세·폭·유동성·변동성·모멘텀 | **시세 파일을 다시 수집해야** 날짜가 바뀜 |
| ECOS | 한은 (데모 키면 호출당 10행) | 열 때 조회 |
| FRED | DGS2, DGS10, T10Y2Y, DEXKOUS | 열 때 조회 |

국면 가중 (`config/market.yaml`): trend 20, breadth 20, liquidity 15, volatility 15, rates 10, fx 10, momentum 10.  
70↑ 위험선호, 40↑ 중립, 그 미만 위험회피. **Quant 미합산.**

### 4.4 수급

토스 `GET /api/v1/stocks/{code}/investor-trading`.

- 창: 5/10/20거래일 (토스 레코드는 보통 10일, 페이지네이션 미구현)
- **쌍끌이**: 외인 순매수 > 0 **그리고** 기관 순매수 > 0
- **사모**: `institution.breakdown.privateEquityFund`
- 순매수는 **주수**. 추정금액 = 주수 × 최근 종가
- 이후 5일·20일 수익률은 연구용. 가격 이력이 짧으면 5일과 20일이 같아 보일 수 있음
- GET은 캐시, POST는 강제 스캔. 캐시 `data/cache/investor_flow.json`, 스키마 3, TTL 30분

### 4.5 빈집

같은 스캔 데이터.

- 쌍매도: 외인<0 **그리고** 기관<0
- 외인 지분 낮음: 토스 `foreignerHolding.holdingRate` (0–1). 기관 **보유비율 API 없음** → 기관은 순매도로만
- 복귀 조짐: 앞선 날은 쌍매도, 최근 1–2일은 쌍끌이
- 개인만 받음: 쌍매도 + 개인 순매수
- 금액·지분 상한 필터는 캐시에서 즉시

### 4.6 트레이딩

Quant TOP100이 **기본 제외**. 유니버스 우선순위:

1. 토스 급등락·거래대금 (종목당 최대 25)
2. 당일 KRX `trading_value` 상위 60
3. 관심종목
4. Quant TOP100으로 채움  
한도 **160종목**. 토스 종목당 호출 + 0.05s sleep.

셋업: 쌍끌이 / 사모 순매수 / 사모매집(2일 이상 연속) / 빈집 / 복귀 / 쌍끌이+사모.

기술적 overlay (KRX OHLC, ~80거래일):

- 스토캐스틱 슬로우 **5,3,3** (한국에서 흔한 설정): 과매도<20, 과매수>80, 골든/데드
- 일목 **9-26-52**, 선행 26: 구름 위/안/아래, 전환↔기준
- 필터: 스토 과매도·골든, 구름 위/아래, 전환>기준, 기술 강세, **수급+기술**
- Quant 미합산. 차트 그림은 없음 (숫자·태그)

**ETF 이름:** 주식 마스터에 ETF가 없어 코드만 나오던 문제. `KNOWN_ETF` + 토스 `get_stocks`로 KODEX/TIGER 등 이름·`security_type=ETF` 표시. 예: `069500` KODEX 200, `114800` KODEX 인버스, `252710` TIGER 200선물인버스2X.

### 4.7 관심종목

로컬 `data/watchlist.json`. 점수와 무관.

### 4.8 미국 13F

공식: SEC EDGAR `data.sec.gov/submissions` + Archives infotable XML.  
WhaleWisdom은 **참고 링크만**. 스크랩 안 함.

추적 펀드 12곳 (`config/us_13f_filers.yaml`): 버크셔, 브리지워터, 르네상스, 시타델, 퍼싱 스퀘어, 타이거, 코튜, 듀케인, 사이언(버리), ARK, 소로스, 바우포스트.

분류:

- 신규 매수 / 규모 확대 / 매도·청산 (직전 분기 대비 CUSIP)
- 공통 매수 (2곳 이상)
- 트렌드 점수 = (신규+확대) − (축소+청산)
- 펀드별 상위 비중
- 한글 펀드명·운용자, CUSIP→티커(OpenFIGI), 한글 종목 설명 (`us13f/names.py`)
- 비상장 성격(스페이스X 등)은 티커를 비울 수 있음

캐시: `data/cache/us13f.json`, CUSIP 맵 `data/cache/cusip_map.json`.  
13F는 분기 말 + 최대 45일 시차. 펀드마다 최신 `report_date`가 다를 수 있음 (예: 퍼싱 2026-03-31, 버리 2025-09-30, 다수는 2026-06-30).

SEC 접근: `User-Agent`에 이름+이메일 필요. `SEC_USER_AGENT` 환경변수. 공정 이용(초당 요청 제한) 준수, 호출 사이 sleep.

### 4.9 AI 리포트

- 버튼으로만 LLM 호출. 기본 제공자 Grok (xAI), DeepSeek/OpenRouter/커스텀 가능
- 연구 키트 VER4 (`config/research_kit/`)
- 보관: `data/output/research/as_of=.../*.report.json`
- 종목 상세: FnGuide Snapshot `wcomp.fnguide.com/CompanyInfo/Snapshot?gicode=A{code}`, KIND `disclosureSimpleSearch`

### 4.10 실행 / API 설정

키는 `.env` upsert. 빈 칸 저장은 유지, `CLEAR`로 삭제.  
연결 테스트, 텔레그램 테스트(채팅 ID 필요).

---

## 5. 데이터 소스 목록

| 소스 | 용도 | Quant | 비고 |
|---|---|---|---|
| KRX Open API `data-dbg.krx.co.kr/svc/apis` | 일봉, 마스터 | 예 (가격) | `sto/stk_bydd_trd`, `ksq_bydd_trd`, `*_isu_base_info` |
| OpenDART | 재무제표 TTM | 예 | 호출 한도, sleep 기본 0.15s |
| 토스 Open API `openapi.tossinvest.com` | 랭킹, 수급, 종목명, 외인 지분율 | 아니오 | 종목별 investor-trading |
| 네이버 검색/지도 | 뉴스, 백과, 본사 지도 | 아니오 | |
| FRED | 금리·환율 맥락 | 아니오 | |
| Yahoo/yfinance | 지수·종목 비교 | 아니오 | KRX 대체 금지 |
| 한은 ECOS | 기준금리 등 | 아니오 | 공개 샘플 키 10행 |
| feargreed.co.kr | 공포·탐욕 | 아니오 | |
| SEC EDGAR | 미국 13F | 아니오 | |
| OpenFIGI | CUSIP→티커 | 아니오 | 키 없이 배치 매핑 |
| 텔레그램 | 알림 테스트 | 아니오 | chat_id 없으면 미완 |
| 키움/한투(KIS) | 설정만 존재 | — | **주문 미사용**, 일괄 수급도 미구현 |

---

## 6. 환경 변수 (이름만)

`.env` — 값은 이 문서에 없음.

```
OPENDART_API_KEY
KRX_API_KEY
XAI_API_KEY / GROK_API_KEY
DEEPSEEK_API_KEY
OPENROUTER_API_KEY
LLM_PROVIDER, LLM_MODEL
CUSTOM_LLM_BASE_URL, CUSTOM_LLM_API_KEY
KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE_URL
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
NAVER_MAP_CLIENT_ID, NAVER_MAP_CLIENT_SECRET
TOSS_CLIENT_ID / TOSS_API_KEY
TOSS_CLIENT_SECRET / TOSS_SECRET_KEY
FRED_API_KEY
BOK_ECOS_API_KEY
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
OPENDART_SLEEP_SEC
SEC_USER_AGENT
KR_QUANT_HOME
```

대시보드 설정 화면에서 저장 가능. 텔레그램 chat_id는 봇에 먼저 말을 건 뒤 채팅 목록에서 넣어야 한다.

---

## 7. 주요 HTTP API

로컬 FastAPI.

- `GET /` 정적 대시보드
- `GET/POST /api/settings`, `POST /api/settings/test`
- `GET /api/status`, `/api/results/top`, `/api/results/all`, `/api/results/stock/{ticker}`
- `GET /api/market`, `/api/macro`, `/api/toss/rankings`
- `GET/POST /api/flow` body `{days}`
- `GET/POST /api/us13f` body `{force}`
- `GET/POST/DELETE /api/watchlist`
- `GET/POST /api/research`, `/api/research/report`
- `GET/POST /api/jobs` (demo|screen|live)
- LLM: `/api/llm/connections`, `/api/llm/grok/connect`

---

## 8. 알려진 한도 (버그가 아니라 설계 한계)

1. **시세 일일 갱신:** 대시보드가 떠 있으면 평일 18:30 KST에 KRX 일봉만 받는다 (`config/scheduler.yaml`). OpenDART 전체 수집은 하지 않는다. 시세·점수 날짜는 헤더 칩과 `GET /api/system/spec`의 `freshness`에 표시한다.
2. **수급 전 종목 스캔 없음.** 거래 많은 ~160종목. 소형 빈집은 빠질 수 있음.
3. **기관 지분율 없음.** 토스에 외인 `holdingRate`만. 기관은 순매수 주수.
4. **순매수 KRW는 추정.** 주수×최근 종가. 당일 평균단가 아님.
5. **토스 수급 히스토리 ~10거래일.** 20일 창은 잘려 나옴. `nextUntil` 페이지네이션 미구현.
6. **이후 20일 수익률**은 가격 윈도가 짧으면 5일과 동일.
7. **ETF는 Quant 유니버스에서 제외**되지만 토스 랭킹에는 들어옴. 이름 맵+토스로 보완함. ETF 일봉은 주식 prices에 없을 수 있어 기술적 지표·선도수익이 비는 경우 있음.
8. **13F 시차 45일**, 일부 펀드 금액 필드 0, 풋/콜·복수 CUSIP.
9. **한글 종목 설명**은 주요 티커 사전 + 폴백(“미국 상장 증권”). 전 종목 한국어 리서치 아님.
10. **OpenDART 커버리지**가 약하면 Codex 시절처럼 점수 구멍(커버리지 부족)이 남음.
11. **텔레그램 chat_id** 미설정 시 알림 불가.
12. **백테스트 랩·포트폴리오·포지션 사이징 없음.**
13. README의 모멘텀 설명 / `ARCHITECTURE.md` 일부가 코드보다 오래됨.

---

## 9. 테스트

`tests/unit/` 대략: 계정맵, ECOS, env, fear-greed, flow/빈집/트레이딩 필터, 공식, FRED/Yahoo/텔레그램, 가이드 URL, LLM, 시장·관심, 네이버, 피어·리스크·TTM, 리서치 키트, 주식수 보정, 스토캐/일목, 토스 랭킹, 13F 파싱, 웹 HTML 훅.  
통합: `tests/integration/test_demo_pipeline.py`.

---

## 10. 대화에서 나온·아직 안 한 것

우선 후보 (제약 1–3을 지키는 전제):

- 장 마감 후 **KRX 일봉만** 받는 스케줄 (시장 국면 날짜 갱신)
- 수급 유니버스 확대 (키움/한투 일괄 투자자별 매매, 주문 없이)
- 토스 investor-trading 페이지네이션으로 20·60일
- 빈집·쌍끌이 **복귀 이후** 구간 히트율만 따로
- RSI·이동평균·볼린저, 간단 차트
- 13F 종목 역검색 (NVDA를 누가 늘렸나), 펀드 추가
- 텔레그램: 일일 TOP20 / 쌍끌이 / 13F 신규 요약 (주문 아님)
- DART 커버리지 확대, 상태 CSV 자동화
- 전략 백테스트 랩 (Timing, 점수와 분리)
- README/`ARCHITECTURE.md`를 코드와 동기화

하지 말 것: 자동주문, LLM을 점수에 넣기, WhaleWisdom 스크랩, yfinance를 KRX 가격 정본으로.

---

## 11. GPT Pro에 부탁할 검증 질문

아래를 그대로 질문으로 써도 된다.

1. 계층 분리(Discovery vs overlay)가 유지되는가. 수급·13F·스토캐를 점수에 넣자는 제안이 나오면 **거부**하는 게 맞는지.
2. 모멘텀을 시총/주식수로 보정하는 방식이 분할에는 타당한지. 배당 TR을 넣지 않은 선택이 스크리너 목적에 맞는지.
3. 토스 수급 160종목 한도가 연구용으로 충분한지, 전 시장을 넣으면 어떤 치우침이 줄어드는지.
4. “빈집”을 쌍매도+외인 지분으로 정의한 것이 한국 개인 투자 용어와 맞는지. 기관 지분율 없이 쓸 때의 함정.
5. 스토캐 5,3,3 + 일목 9-26-52를 overlay로 두는 것이 과적합한지. 수급+기술 필터의 표본 편향.
6. 13F를 트레이딩 신호가 아니라 분기 스냅샷으로 쓰는 설명이 충분한지. 시타델 수천 종목을 공통 보유에 넣으면 대형주 편향이 커지는지.
7. 일일 자동 갱신을 넣는다면 **최소 파이프라인**은 무엇인지 (KRX 일봉만 vs DART 전체).
8. 지금 빠진 기능 중 **조사 프로그램**으로서 ROI가 큰 3가지.
9. 보안: 로컬 `.env`, SEC User-Agent, 토스/DART 한도. 추가로 막을 것.
10. README와 `ARCHITECTURE.md`를 고칠 때 우선 문장.

---

## 12. 디렉터리 지도 (요약)

```
kr_quant_research/
  config/          quant_v1.yaml, universe_rules, risk_rules, market.yaml,
                   research_v1.yaml, us_13f_filers.yaml, research_kit/
  src/kr_quant/
    orchestration/  일일 스크리닝
    scoring/ universe/ financials/ pit/ factors/  Quant
    ingest/         krx, opendart, toss, fred, ecos, yahoo, naver, telegram, fear_greed
    flow/           수급·빈집·트레이딩 유니버스
    timing/         스토캐·일목
    us13f/          EDGAR 13F
    research/       AI 리포트
    web/            FastAPI + static
  data/staged/live/ prices, master, financial_facts
  data/output/      latest_top20/100, all_stocks, research/
  data/cache/       investor_flow.json, us13f.json, cusip_map.json
  tests/
```

이 브리프만으로 코드를 다시 짜지 말고, **제약 준수 + 한도 인정 + 보완 우선순위**를 검증하는 데 쓴다.
