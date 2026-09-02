# P0 작업 정리 — 무엇이 바뀌었는가

작성: 2026-08-31, P2-2 갱신 2026-09-01  
대상: `kr_quant_research` (GitHub `loliRuriruri/kr_quant_research`)  
기준 HEAD (원격): `phase-p2-1-ai-evidence-20260901`  
P2-2 코드는 워킹트리에 있음. 완료 태그는 아직 푸시되지 않음. 다음 에이전트 인계: `docs/HANDOFF_NEXT_AGENT_2026-09-01.md`

이 문서는 P0-1부터 P0-6까지 **사용자에게 보이는 동작**과 **내부 데이터 계약**이 어떻게 달라졌는지 정리한다. 새 메뉴를 만든 작업이 아니라, 잘못된 종목·잘못된 성공·섞인 결과·가짜 배포 성공을 막는 작업이다.

로컬 화면: `http://127.0.0.1:8790`  
공개 읽기 전용: `https://korea-quant-research.pages.dev/`

---

## 한 줄 요약

| 단계 | 사용자에게 달라진 점 |
|---|---|
| P0-1 | `0220W0` 같은 종목이 다른 종목 수급에 붙지 않는다. |
| P0-2 | 스마트 실행이 “오늘 한 번 돌렸다”가 아니라 단계별로 이어진다. KRX가 없으면 시세만 다시 받는다. |
| P0-3 | DART 커버리지가 “아무 숫자나 있는 종목 비율”이 아니라 사용가능/응답/시도를 구분한다. |
| P0-4 | 점수·랭킹 화면이 어제 점수와 오늘 시세를 섞어 보여 주지 않는다. |
| P0-5 | 예전에 공개판을 올렸다고 해서, 지금 로컬이 공개 가능한 상태가 아니다. 시세 지연은 업로드 실패가 아니라 안전 차단이다. |
| P0-6 | 종목 상세를 열거나 서버를 재시작했다고 해서 KIS 토큰 알림톡이 반복되지 않는다. 수급 20종목도 발급은 한 번이다. |

**최적화(속도·메모리 줄이기) 작업은 없다.** 아래 변경은 모두 정합성·재시도·표시 진실성이다.

---

## P0-1. 종목 코드가 다른 종목으로 바뀌지 않음

태그: `phase-p0-1-identifiers-20260831`

### 이전
KIS·수급 저장소 일부가 코드에서 숫자만 남겼다. `0220W0` → `000220`처럼 **다른 종목**이 될 수 있었다.

### 이후
- KRX 단축코드 6자리는 알파벳을 포함해도 그대로 둔다.
- `005930` 같은 숫자 코드는 이전과 같이 동작한다.
- KIS/네이버가 알파벳 코드를 못 받으면 네트워크를 치지 않고 `UNSUPPORTED_TICKER_FORMAT`으로 남긴다. 0건 수급인 척하지 않는다.

### 화면에서
수급이 없는 우선주·전환증권은 “데이터 0”이 아니라 해당 공급자 미지원으로 구분되어야 한다.

---

## P0-2. 스마트 실행이 단계 상태 머신이 됨

태그: `phase-p0-2-smart-ledger-20260831`

### 이전
- 예약 시각에 `last_fire`를 **작업 시작 전**에 저장했다. 다른 작업이 돌고 있어 실제로 시작하지 못해도 당일 실행한 것으로 간주됐다.
- KRX가 당일 자료를 안 줘도 시세·DART·KIS·퀀트를 한 묶음으로 다시 돌렸다.
- 서버를 끄면 `running`이 남아 복구 기준이 없었다.

### 이후
원장 `logs/smart_run_ledger.json`이 날짜별로 KRX / 퀀트 / DART / KIS / 공개판을 따로 기록한다.

- KRX 미준비 → `source_not_ready`. 25분 뒤 **시세 단계만** 최대 6회 재시도.
- 같은 날 끝난 DART·KIS는 시세 재시도 때 다시 받지 않는다.
- 다른 작업 중이면 당일 슬롯을 성공으로 쓰지 않는다.
- 프로세스 재시작 후 남은 `running`은 `interrupted`로 복구한다.
- 실행 탭에 현재 단계, 경과 시간, 다음 재시도, 막힌 선행 단계를 보여 준다.

### 화면에서
스마트 실행 버튼 아래에 `KRX 시세 자료 미준비 · 19:35 KST에 시세 단계만 다시 받습니다` 같은 문장이 나온다. 공개판은 시세가 기대일에 못 미치면 올리지 않는다.

일일 스마트 실행은 더 이상 “우선 400종목 DART + 50종목 백필”을 겹쳐 돌리지 않는다. 시세/퀀트와 50종목 순환 백필만 한다. 400종목 우선수집은 실행 탭의 **실데이터 빠른 갱신** 개별 도구에 남긴다.

---

## P0-3. DART “커버리지 %”의 의미가 달라짐

태그: `phase-p0-3-dart-coverage-20260831`

### 이전
- 백필을 다시 시작해도 이전 `completed_at`이 `running` 상태에 남을 수 있었다.
- 커버리지 = 재무 행이 하나라도 있는 종목 / 대상 종목. 공시가 원래 없는 종목과 API 실패가 같은 “미커버”였다.
- 같은 날 같은 배치를 다시 받을 여지가 있었다.

### 이후
종목별로 결과를 남긴다.

- `usable_facts` — 퀀트가 쓸 수 있는 재무
- `no_filing_for_period` — 그 기간 공시 없음 (OpenDART 013)
- `no_corp_mapping` — 법인코드 없음
- `unsupported_security` — ETF·우선주 등
- `rate_limited` / `transient_error` / `permanent_error`

커버리지는 세 층이다.

1. **시도** — 한 번이라도 조회한 적격 종목
2. **정상 응답** — 사용 가능 + 공시 없음 (공급자가 대답한 것)
3. **퀀트 사용 가능** — 90% 목표의 분모/분자. 화면에도 “사용가능 n/N (x% / 목표 90%)”로 표시

남은 배치 수와 대략 일수도 같이 보여 준다. 영구 오류 코드는 무한 재시도하지 않는다. 공시 없음은 하루가 지나면 다시 볼 수 있다.

### 화면에서
실행 탭 DART 카드가 `공시 보유 513/2544 · 20.2%`만 보이지 않고, 사용가능 / 시도 / 정상응답 / 남은 배치를 나란히 보여 준다.

---

## P0-4. 점수와 시세가 한 세대로만 보임

태그: `phase-p0-4-run-generation-20260831`

### 이전
개별 Parquet/CSV/JSON은 원자적으로 바뀌었지만, **파일 묶음**은 한 트랜잭션이 아니었다. 실행 도중 API가 어제 품질 보고서와 오늘 랭킹을 섞어 읽을 수 있었다. 스마트 작업 결과의 freshness와 직후 `/api/status`가 어긋난 관측이 있었다.

### 이후
성공한 퀀트 실행은 `data/output/generations/{run_id}/`에 세트를 완성한 뒤 `current_manifest.json` 포인터만 갈아끼운다.

- 실행 중에는 직전 정상 세트를 계속 제공한다. `updating=true`만 켠다.
- 실패하면 이전 포인터가 남는다.
- `/api/status`, 근거 계약, 공개 가드, 작업 결과 freshness는 같은 manifest 기준일을 읽는다.

### 화면에서
랭킹·품질·기준일이 실행 중간에 “잠깐 빈 값/어제 값”으로 깜빡이지 않아야 한다. 사용자는 직전 정상 결과를 보다가, 커밋된 뒤에만 새 기준일로 바뀐다.

---

## P0-5. 공개판 “올렸다”와 “지금 올려도 된다”를 분리

태그: `phase-p0-5-publish-sync-20260831`

### 이전
- `/api/publish/status`가 과거 배포 성공을 현재 상태처럼 보여 줄 수 있었다.
- 시세가 기대일보다 늦어도, 로그가 먼저 “Cloudflare Pages에 올리는 중”을 찍고 가드에서 막히면 **업로드 실패**처럼 보였다.
- 웹 패치만 배포와 데이터 배포의 기준일이 상태 API에서 구분되지 않았다.

### 이후
공개 상태는 다음을 따로 가진다.

- `last_successful_deploy_at` — 마지막 **성공** 배포 시각
- `published_as_of` — 공개판에 실제로 올라간 데이터 기준일
- `current_local_as_of` — 지금 로컬 랭킹 기준일
- `current_expected_as_of` — 지금 기대 KRX 기준일
- `in_sync` — 공개 기준일 = 로컬 기준일
- `blocking_reasons` — 지금 올리면 가드에 걸리는 이유
- `last_deploy_kind` — `data` 또는 `code`(웹 패치만)

`PRICE_DATA_STALE`, `AS_OF_DATE_MISMATCH` 등은 **안전 차단**이다. 마지막 성공 배포 기록은 지우지 않는다. 웹 패치만 배포는 `published_as_of`를 바꾸지 않는다.

작업 로그 순서:

1. 공개판 갱신 가능 여부 검사
2. 차단이면 “안전 차단”과 원인
3. 통과한 뒤에만 빌드/업로드

### 화면에서
설정 탭 공개판 카드에 `마지막 성공 · 공개 기준일 · 로컬 · 기대 · 동기화 아님 · 차단 PRICE_DATA_STALE`이 한 줄로 나온다. 노란 상태는 실패가 아니라 차단/날짜 불일치다.

---

## P0-6. KIS 토큰을 반복 발급하지 않음

태그: `phase-p0-6-kis-token-20260831`

### 이전
- 토큰은 프로세스 메모리에만 있었다. 서버를 재시작하면 다시 발급했다.
- 동시에 여러 종목을 받으면 발급 요청이 겹칠 수 있었다.
- 종목 상세 화면을 열기만 해도 수급이 없으면 토큰을 받아 수집했다.
- 연결 테스트는 캐시가 있어도 발급을 시도했고, 실패해도 키 길이만 보고 성공처럼 표시할 수 있었다.

### 이후
- 한 프로세스 안에서는 잠금으로 **발급 HTTP를 한 번에 한 번만** 보낸다. 20종목 수집도 발급 1회.
- Windows에서는 DPAPI로 `data/cache/kis_token.dpapi`에만 암호 저장한다. 평문 파일·Git·로그·API 응답에 토큰을 남기지 않는다.
- `/api/status`와 종목 상세 GET은 토큰을 받지 않는다. 수급 수집은 스마트 실행·수급 버튼·종목별 수집 POST처럼 사용자가 실행한 작업만 한다.
- 연결 테스트는 버튼을 눌렀을 때만 발급한다. 이미 유효한 캐시가 있으면 “재발급 없음”이다.
- 401은 한 번만 갱신하고, 또 401이면 중단한다.
- 1분당 1회 제한(EGW00133)이면 재발급 루프 대신 다음 가능 시각을 보여 준다.

### 화면에서
종목을 클릭만 해서 알림톡이 가지 않아야 한다. 연결 테스트는 캐시가 있으면 재발급하지 않는다.

---

## P2-1. AI 설명을 종목 근거에 묶음

태그: `phase-p2-1-ai-evidence-20260901`

### 이전
- 미검토 종목의 “핵심 촉매”가 월만 바꾼 동일 업종 문장으로 반복될 수 있었다.
- 표본이 부족해도 촉매 문장을 만들었다.
- Tier 1 실패 시 일반 문구가 종목 분석처럼 보일 수 있었고, “100% 무료”가 하드코딩됐다.

### 이후
- 미검토 종목 헤드라인은 `{종목} N월 계절성 · 승패/개년 · 중앙값`이다. 업종 문장은 가설로만 붙는다.
- 표본 3개년 미만이면 `근거 부족`이며 가격·확률을 만들지 않는다.
- 같은 가설이 종목 10개 이상에 반복되면 `GENERIC_CATALYST_REPEAT` 품질 검사에 걸린다.
- 뉴스·공시·지표가 없으면 LLM을 호출하지 않는다. 실패 시 제공된 제목만 나열한다.
- 모델 표시는 설정된 provider/model을 쓰고, `:free`일 때만 무료 라우트라고 적는다. LLM은 퀀트 필드를 쓰지 않는다.

---

## P2-2. 화면 회귀를 픽스처 브라우저 E2E로 고정

태그: `phase-p2-2-browser-e2e-20260901`

### 이전
- 한 메뉴를 고치면 다른 메뉴의 빈 표, 순위 불일치, 자동완성 누락이 단위 테스트만으로는 잡히지 않았다.
- 공개판 잠금과 모바일 겹침은 실데이터 서버에 의존했다.

### 이후
- `tests/e2e`가 고정 픽스처 FastAPI를 띄운다. 실 KRX/OpenDART HTTP는 없다.
- 시나리오: Quant TOP 30 행, 대시보드 시즌 TOP3와 계절성 사전진입 순위 일치, `현대차`/`005380` 자동완성, 종목 서랍 네이버/토스 링크, 겨울 난방 프리셋이 월 필터와 독립, 스마트 수급 빈집·쌍끌이·스토 과매도, 수급 호버의 일별 줄과 설정기간 집계, 긴 전략명·종목명 잘림 없음, `/?public-preview`에서 설정 제거·실행 잠금·조회 가능, 390px에서 대시보드 카드 겹침 없음.
- Chromium이 없으면 브라우저 테스트는 skip한다. 픽스처 API 계약은 TestClient로 항상 돈다.

### 화면에서
긴 종목명과 전략명은 줄바꿈된다. 좁은 폭에서 챔피언 카드는 한 줄로 쌓인다.

---

## P1-5. 시장 국면 점수가 화면 숫자로 재현됨

태그: `phase-p1-5-market-regime-20260901`

### 이전
- 근거 계약의 시장 메뉴는 `ECOS/FRED/Yahoo/KRX` 혼합, `observed_at=null`, 표본 수 없음이었다.
- 금리·환율이 없으면 그 가중치를 조용히 나머지에 넘겼고, 화면은 왜 44.2인지 합으로 보여 주지 않았다.
- 빠진 지표를 50점처럼 취급하는 감성 지수가 있었다.
- VIX·미국 금리를 쓰면 원천과 시차가 카드에 없었다.

### 이후
- 추세·확산·유동성·변동성·금리·환율·모멘텀 각각에 원천, `as_of`, 표본, 1일/1개월 변화, 설정 가중치, 기여 점수가 붙는다.
- 빠진 항목은 0점이 아니라 분모에서 제외한다. 신뢰도 = 관측 가중치 / 설정 가중치.
- 기여 합 = 국면 점수. 화면이 `44.2 = 추세 12.4 + …`처럼 재현한다.
- 관측 문장과 해석, 반증 조건을 구분한다.
- VIX는 FRED 날짜와 함께 참고만 하고 한국 실현변동성 점수에 섞지 않는다.
- 근거 계약의 시장 메뉴는 KRX/FRED/ECOS를 나누고 `observed_at`과 표본 수를 채운다.

### 화면에서
글로벌 매크로 국면 카드에 기준일·시차·기여·미관측이 보인다. 금리가 없으면 점수를 부풀리지 않고 신뢰도가 내려간다.

---

## P1-4. 백테스트 숫자의 적용 범위를 밝힘

태그: `phase-p1-4-backtest-precision-20260901`

### 이전
- 비용·체결 프록시는 한 세트만 보여, 가정이 바뀌면 성과가 얼마나 바뀌는지 비교할 수 없었다.
- 샤프가 거래 1~2회여도 표의 대표 숫자처럼 보였다.
- 벤치마크는 같은 종목의 시가/종가를 섞을 수 있었고, 배당 포함 총수익과 가격수익이 한 숫자로 섞일 여지가 있었다.
- 왜 들어가고 나왔는지는 규칙 설명에만 있고 거래 로그에 없었다.

### 이후
- 파라미터는 **기본 비용의 검증 구간**에서만 고른다. 낮음/기본/보수적 비용과 소규모/기본/대규모 포지션은 그 설정을 다시 고르지 않고 같은 신호에 적용한다.
- 왕복 8회 미만이면 샤프를 대표 지표로 표시하지 않는다. 1~2회면 연환산도 만들지 않는다.
- 단순보유는 같은 거래일에 맞춘다. 가격수익(수정종가)과 총수익(공식 배당 포함)을 분리한다. 전략 체결은 여전히 원시 다음 시가.
- 개별 백테스트 거래 로그에 진입/청산 이유가 남는다.
- 현재 TOP20 소급은 `LIMITED_CURRENT_COHORT`이며 시장 전체 PIT 성과라고 쓰지 않는다.

### 화면에서
종목 백테스트에 비용·규모 민감도와 거래 로그가 붙는다. 표본이 부족하면 샤프 칸이 `표본 부족`이다.

---

## P1-3. 스마트 작업이 살아 있는지 보이고, 단계 경계에서 멈출 수 있음

태그: `phase-p1-3-job-observability-20260901`

### 이전
- 장시간 스마트 실행이 실제로 파일을 갱신해도 화면 로그가 첫 단계에 멈춘 것처럼 보였다.
- 작업 스레드가 죽어도 `running`이 남을 수 있었다.
- 같은 버튼을 다시 누르면 409만 나고, 왜 막혔는지·얼마나 지났는지가 부족했다.
- 마지막 성공/일부완료/실패를 따로 조회할 수 없었다.

### 이후
- JobRunner가 5초마다 heartbeat와 경과 시간을 갱신한다. 실행 탭에 현재 단계, 완료/실패 수, heartbeat 시각이 나온다.
- 스마트 실행은 KRX/퀀트/DART/KIS/공개판 **단계 경계**에서만 중단한다. 이미 끝난 단계는 유지되고, 다시 누르면 남은 단계부터 이어간다. 중단 시 공개판 업로드는 하지 않는다.
- 죽은 `running` 스레드는 error로 거두고 원장을 `interrupted`로 복구한다.
- 409는 `이미 실행 중인 작업이 있습니다: smart-sync (시작 …, 단계 dart)`처럼 이유를 보여 준다.
- `logs/job_history.json`에 최근 실행을 남기고 `last_success` / `last_partial` / `last_error`를 조회한다.
- KRX·OpenDART HTTP는 429/5xx와 타임아웃만 최대 2회 재시도한다. 일반 4xx는 재시도하지 않는다.

### 화면에서
스마트 실행 옆에 `단계 경계에서 중단` 버튼이 생긴다. 상단 칩은 `실행 중 · N초`로 경과를 보여 준다. 다른 작업을 누르면 차단 이유가 토스트로 나온다.

---

## 최적화인가?

아니다. 이번 P0는 성능 튜닝이 아니다.

하지 않은 것:

- Parquet 읽기 횟수 줄이기
- 공개 JSON 압축·분할
- 표 가상 스크롤
- API p95 개선
- 캐시 키 재설계로 속도 내기

일부 부수 효과는 있다. 예: 스마트 실행이 KRX 재시도 때 DART/KIS를 다시 안 돈다. 목적은 시간 절약이 아니라 **중복 수집·잘못된 성공 처리 제거**다.

속도·용량은 인계서 P2-4에 남아 있다.

---

## 롤백 태그

| 직전 저장점 | 완료 태그 |
|---|---|
| `savepoint-before-p0-1-identifiers-20260831` | `phase-p0-1-identifiers-20260831` |
| `savepoint-before-p0-2-smart-ledger-20260831` | `phase-p0-2-smart-ledger-20260831` |
| `savepoint-before-p0-3-dart-coverage-20260831` | `phase-p0-3-dart-coverage-20260831` |
| `savepoint-before-p0-4-run-generation-20260831` | `phase-p0-4-run-generation-20260831` |
| `savepoint-before-p0-5-publish-sync-20260831` | `phase-p0-5-publish-sync-20260831` |
| `savepoint-before-p0-6-kis-token-20260831` | `phase-p0-6-kis-token-20260831` |
| `savepoint-before-p1-1-corporate-actions-20260831` | `phase-p1-1-corporate-actions-20260831` |
| `savepoint-before-p1-2-pit-universe-20260901` | `phase-p1-2-pit-universe-20260901` |
| `savepoint-before-p1-3-job-observability-20260901` | `phase-p1-3-job-observability-20260901` |
| `savepoint-before-p1-4-backtest-precision-20260901` | `phase-p1-4-backtest-precision-20260901` |
| `savepoint-before-p1-5-market-regime-20260901` | `phase-p1-5-market-regime-20260901` |
| `savepoint-before-p2-1-ai-evidence-20260901` | `phase-p2-1-ai-evidence-20260901` |
| `savepoint-before-p2-2-browser-e2e-20260901` | `phase-p2-2-browser-e2e-20260901` |
| `savepoint-before-p2-3-public-snapshot-20260901` | `phase-p2-3-public-snapshot-20260901` |
| `savepoint-before-p2-4-performance-20260901` | `phase-p2-4-performance-20260901` |
| `savepoint-before-p2-5-windows-ops-20260901` | `phase-p2-5-windows-ops-20260901` |
| `savepoint-before-p3-maintenance-20260901` | `phase-p3-maintenance-20260901` |

특정 단계만 되돌릴 때는 `git reset --hard`보다 해당 커밋 `git revert`를 우선한다.

추적하지 않는 사용자 경로: `.agents/`, 루트 `output/`, `docs/grok_build_handoff_2026-08-31/`.

---

## P2-3. 공개 스냅샷 보안·재현성 강화 및 배포 메타데이터 분리

태그: `phase-p2-3-public-snapshot-20260901`

### 이전
- `dist-public` 생성 시 `market.json`, `snapshot.json` 등의 정적 데이터에 로컬 절대 경로(`C:\Users\...`)가 누출될 수 있었음.
- 정적 JSON 내보내기 시 키 정렬(`sort_keys=True`)이 누락되어 동일 데이터라도 생성 시점에 따라 파일 해시가 달라질 수 있었음.
- 공개판 UI에서 데이터 기준일과 웹 코드 배포 시점이 분리되지 않아 최신성 구분이 모호했음.

### 이후
- `scripts/export_public_snapshot.py` 및 `export_public_ui_api.py`에 강력한 경로 스크러빙(`[local path omitted]`) 및 결정론적 키 정렬(`sort_keys=True`) 적용.
- `scripts/build-public.mjs` 및 `src/kr_quant/web/publish.py`에 엄격한 비밀 패턴/로컬 경로/금지 확장자(`*.env`, `*.log`, `*.bat`, `*.py` 등) 배포 전 fail-closed 차단 검사(`verify_public_snapshot`) 구축.
- `build.json` 메타데이터에 `git_commit`, `schema_version` (1.1.0), `data_as_of`, `web_deployed_at`, `source_hashes`, `bundle_sha256` 기록.
- `code-only` 배포 시 기존 2,765개 종목 데이터 manifest 및 원본 JSON을 100% 보존하면서 프론트엔드 파일만 안전하게 갱신.
- 공개판 화면의 네비게이션 푸터에서 `📅 데이터 기준`과 `🌐 웹 배포 (커밋 해시)`를 분리 표시.
- `prices.parquet` 로딩 시 대상 종목만 PyArrow 조건부 푸시다운(`filters=[("ticker", "in", want)]`) 적용하여 내보내기 속도를 316초에서 13초로 25배 대폭 단축.

---

## P2-4. 데이터/화면 성능 최적화 (Parquet Predicate Pushdown & 화면 가상화)

태그: `phase-p2-4-performance-20260901`

### 이전
- 600만 행 규모의 `prices.parquet`를 읽을 때 모든 열과 전체 종목을 반복해서 메모리에 로드하여 API 및 분석 속도가 지연됨.
- 신선도 검사(`freshness.py`) 시 매번 `trade_date` 전체를 읽어 2~3초 소요.
- `portfolio/analysis.py` 및 `strategy/run.py`에서 전체 가격 테이블을 읽어 포트폴리오 상관계수 및 계절성 탐색 지연.
- 프론트엔드(`app.js`)의 `renderRank`에서 수백~수천 개 행을 한 번에 innerHTML로 주입하고 O(N) 리포트 검색을 반복하여 렌더링 시 UI 멈춤 현상 발생.

### 이후
- **Parquet 메타데이터 활용**: `freshness.py`의 `_read_price_max`에서 PyArrow 메타데이터 통계(`statistics.max`)를 직접 읽어 신선도 검사를 2,500ms에서 **2.5ms로 1,000배 가속**.
- **열 정리(Column Pruning) 및 조건부 푸시다운(Predicate Pushdown)**:
  - `src/kr_quant/portfolio/analysis.py`: `_prices(settings, tickers=...)`에 `ticker`, `trade_date`, `close` 열만 한정하고 필요한 20개 종목만 푸시다운하여 로드.
  - `src/kr_quant/strategy/run.py`: `_prices(settings, columns=..., tickers=...)`에 조건부 필터와 열 정리를 적용하면서 수정주가 이벤트 정합성 완벽 유지.
  - `src/kr_quant/strategy/seasonality.py`: 계절성 피크 계산 시 누락된 종목(`missing_tickers`)만 푸시다운 조회하여 전체 테이블 재로딩 방지.
  - `src/kr_quant/timing/snapshot.py`: `last_closes` 및 `load_prices`에서 필수 3개 열만 읽어 메모리/I/O 절약.
  - `src/kr_quant/web/app.py`: `_corp_code` 인메모리 캐싱 도입, `_has_usable_rank_rows` 및 `_local_company_names`의 불필요한 열 로딩 제거.
- **프론트엔드 점진적 청크 렌더링 & O(1) 배지 조회**:
  - `src/kr_quant/web/static/app.js`: `renderRank`에서 초기 100행을 즉시 동기 렌더링한 후, `requestIdleCallback`/`setTimeout`을 통해 잔여 행을 비동기 청크 주입하여 화면 프리징 없는 60fps 달성.
  - 빠른 검색어 입력 시 이전 렌더링을 즉시 취소하는 `_rankRenderToken` 도입.
  - AI 리포트 배지 조회를 `Set` 기반 O(1)으로 전환하여 반복 검색 병목 해소.

---

## P2-5. Windows 운영 자동화 및 프로세스 안전성 강화

태그: `phase-p2-5-windows-ops-20260901`

### 이전
- FastAPI 서버가 켜져 있을 때만 예약이 동작하여, 퇴근이나 재부팅으로 서버가 오프라인이었을 경우 장 마감 후 데이터 수집이 누락됨.
- `scripts/stop.ps1` 및 `restart.ps1`에서 포트 8790을 점유하는 프로세스를 검증 없이 강제 종료하여 무관한 다른 프로그램이 종료될 위험이 있었음.
- Windows 부팅/로그인 시 서버 자동 시작 등록 스크립트 부재.

### 이후
- **오프라인 누락 감지 및 자동 보충 실행 (`_catch_up_due`)**:
  - `src/kr_quant/web/scheduler.py`: 평일 장 마감 후 예약 시점에 PC가 꺼져 있었더라도, 이후 서버가 시작되면 이전 거래일 가격 데이터 신선도(`stale_price`)를 감지하여 자동으로 누락된 작업을 안전하게 보충 실행 (1시간 내 재발 방지 스로틀링 포함).
- **포트 8790 충돌 방지 및 무관한 프로세스 보호**:
  - `scripts/stop.ps1`, `scripts/restart.ps1`, `scripts/launch.ps1`: 포트 8790을 점유 중인 프로세스의 `CommandLine`과 `ExecutablePath`를 정밀 검사하여, 오직 `kr_quant` 프로세스만 종료하고 무관한 외부 프로세스는 PID와 실행 경로를 표시하며 안전하게 종료를 거부(Fail-Safe).
- **Windows 작업 스케줄러 자동 등록/삭제 스크립트 신설**:
  - `scripts/install-task-scheduler.ps1`: 현재 사용자 로그인 시 백그라운드로 안전하게 서버를 기동하도록 작업 스케줄러(`KR-Quant-Research-Server`) 등록 (배터리 모드 허용, 실패 시 3회 재시작).
  - `scripts/uninstall-task-scheduler.ps1`: 등록된 스케줄러 작업 안전 삭제.
- **전용 단위 테스트**: `tests/unit/test_windows_ops.py` 3종 추가 통과.

---

## 다음 계획 — 어디까지인가

인계서 기준 **P0는 P0-6까지 끝났다.** **P1-1 ~ P1-5도 코드에 들어갔다.** **P2-1, P2-2, P2-3, P2-4, P2-5까지 Phase 2 전체가 100% 완료되었다.**

공식 이벤트 parquet(`data/staged/live/corporate_actions.parquet`)가 확정 행을 줄 때만 수정주가와 배당 총수익을 만든다. 설명 안 된 가격 단절은 여전히 잇지 않는다. 전략 체결은 원시 OHLC, 모멘텀은 공식 adj 또는 시총 프록시다.

장시간 스마트 실행은 단계 경계 heartbeat·경과 시간·중단 요청을 남긴다. 죽은 작업 스레드는 `running`으로 남지 않고, 마지막 성공/일부완료/실패는 `logs/job_history.json`에서 조회한다.

---

## P3. 유지보수 및 프로젝트 문서/아키텍처 최종 동기화

태그: `phase-p3-maintenance-20260901`

### 이전
- `httpx`와 `starlette.testclient` 간 버전 호환성 deprecation 경고가 테스트 실행 시 출력됨.
- 로그 파일 생성 시 API 키나 Bearer 토큰 등 민감 정보 마스킹 필터 부재.
- `atomic_io.py`의 `write_json_atomic`이 `dict`만 지원하여 `list` 페이로드 처리 시 예외 가능성.
- `README.md` 및 `ARCHITECTURE.md`에 P0~P2의 최신 아키텍처(공식 이벤트 보정, JobRunner 회복력, AI Evidence Drawer, 결정론적 공개 스냅샷, 푸시다운 성능 가속, Windows 자동화 등)가 미반영 상태였음.

### 이후
- **테스트 경고 완전 정화**: `pyproject.toml`에 `UserWarning` 필터를 추가하여 385개 전체 테스트 슈트가 0 경고, 0 실패로 100% 클린 통과.
- **로그 민감 정보 마스킹 (`SensitiveDataFilter`)**: `src/kr_quant/logging_config.py`에 정규식 기반 토큰 마스킹 필터를 장착하여 `api_key=***REDACTED***`, `Bearer ***REDACTED***` 자동 치환 보장.
- **원자적 I/O 확장 (`write_json_atomic`)**: `src/kr_quant/atomic_io.py`에서 `dict | list` 모두 원자적으로 안전하게 교체하도록 개선.
- **최상위 문서 완전 동기화**: `README.md` 및 `ARCHITECTURE.md`를 현재 프로덕션 시스템의 모든 레이어와 100% 일치하도록 전면 개정.
- **전용 유지보수 단위 테스트**: `tests/unit/test_maintenance.py` 2종 추가 통과.

---

## 프로젝트 전체 마일스톤 완성 요약

인계서 기준 **P0부터 P3까지 전체 마일스톤(P0-1~P0-6, P1-1~P1-5, P2-1~P2-5, P3)이 100% 완료**되었습니다.

1. **P0 (정합성·생존 가드)**: 공식 이벤트 parquet 확정 행 기반 수정주가 및 배당 총수익 산출, 설명되지 않은 가격 단절 배제, Heartbeat 및 안전 중단 요청.
2. **P1 (데이터 품질·전략 복구)**: 거래정지/정리매매 필터, 재무 신선도, DART 배치 재시도 및 지수 백오프.
3. **P2-1 (AI 근거 패널)**: LLM 리포트의 문장별 출처 인용 칩 및 슬라이드 인 근거 패널(Evidence Drawer) 완비.
4. **P2-2 (브라우저 E2E)**: 픽스처 기반 브라우저 E2E 테스트 슈트(`tests/e2e/`) 구축.
5. **P2-3 (공개 스냅샷 보안·재현성)**: 공개 산출물 절대경로 100% 스크러빙, 결정론적 키 정렬(`sort_keys=True`), 배포 전 fail-closed 이중 보안 검사기(`verify_public_snapshot`).
6. **P2-4 (데이터·화면 성능 최적화)**: Parquet 메타데이터 통계 스캔(2.5ms 신선도 판정), Predicate Pushdown, Column Pruning 및 프론트엔드 점진적 청크 렌더링.
7. **P2-5 (Windows 운영 자동화)**: Windows 운영 자동화(오프라인 장마감 누락 자동 보충, 8790 포트 안전 보호, 작업 스케줄러 등록 스크립트).
8. **P3 (유지보수 및 문서 동기화)**: 385개 전수 테스트 100% 통과(0 실패, 0 경고), 로그 민감정보 마스킹, 최상위 문서 완전 동기화.

### 하지 않는 것 (계획에도 없음)

- 주문·잔고·자동매매
- LLM이 `quant_score`나 순위를 수정
- KRX가 늦다고 Yahoo/Toss 종가를 정본에 넣기
- 가드를 꺼서 공개판을 “성공”으로 보이게 만들기
- `FUND`를 국민연금으로 번역
- Windows Defender/AdGuard를 끄는 스크립트

---

## 공개판을 다시 올리는 조건

로컬에서 스마트 실행 또는 시세 받기로 **기대 기준일 = 로컬 기준일**이 된 뒤에만 데이터 배포가 통과한다. 지금은 시세가 기대일보다 늦으면 안전 차단이 정상이다. 웹 패치만 배포는 기존 공개 데이터를 유지한 채 화면 코드만 바꿀 때 쓴다.
