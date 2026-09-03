# KR Quant Research — 다음 에이전트 인계서 (2026-09-01)

이 문서는 Codex / Antigravity / 다른 Grok 세션이 **지금 상태부터** 이어서 작업하기 위한 실행 인계다. 소개서가 아니다.

작업 폴더: `C:\Users\a4jud\kr_quant_research`  
원격: `https://github.com/loliRuriruri/kr_quant_research`  
브랜치: `main`  
로컬 UI: `http://127.0.0.1:8790`  
공개 읽기 전용: `https://korea-quant-research.pages.dev/`  
Cloudflare Pages 프로젝트: `korea-quant-research`  
계정 힌트: `5f4b08b508eba89d2ccb64720dba2308`

상세 원래 명세: `docs/grok_build_handoff_2026-08-31/GROK_BUILD_REMAINING_WORK.md` (이 폴더는 **untracked**, git에 넣지 말 것. 읽기만).  
사용자 화면 요약: `docs/P0_WORK_SUMMARY_2026-08-31.md`

---

## 0. 지금 바로 확인할 것

```powershell
Set-Location C:\Users\a4jud\kr_quant_research
git status
git log -5 --oneline
git tag --list "phase-p*"
git tag --list "savepoint-before-p2*"
```

예상:

- HEAD (원격과 같음): `d07f584 feat(research): bind catalysts to ticker evidence and flag repeats`
- 최신 **푸시된** 완료 태그: `phase-p2-1-ai-evidence-20260901`
- P2-2 저장점 태그는 이미 있음: `savepoint-before-p2-2-browser-e2e-20260901`
- P2-2 **완료 태그는 아직 없다.** 코드는 워킹트리에만 있다.

### 워킹트리 (커밋 전)

수정:

- `docs/P0_WORK_SUMMARY_2026-08-31.md` — P2-2 내용을 미리 적어 두었으나 태그/HEAD는 아직 P2-1
- `pyproject.toml` — `e2e` extra + pytest marker
- `src/kr_quant/web/static/index.html` — 캐시 `?v=2.76.0`
- `src/kr_quant/web/static/styles.css` — 긴 이름 wrap, 챔피언 카드 좁은 폭 1열
- `src/kr_quant/freshness.py` — 깨진 `financial_facts.parquet`를 읽어도 `/api/status`가 500 나지 않게

신규 (untracked, 커밋 대상):

- `tests/e2e/__init__.py`
- `tests/e2e/harness.py`
- `tests/e2e/test_harness_api.py`
- `tests/e2e/test_ui_scenarios.py`
- `docs/HANDOFF_NEXT_AGENT_2026-09-01.md` (이 파일)

절대 커밋하지 말 것:

- `.agents/`
- 루트 `output/`
- `docs/grok_build_handoff_2026-08-31/`
- `data/` 아래 실데이터 parquet
- `.env`, 토큰, 로그

---

## 1. 잠긴 제품 원칙 (바꾸지 말 것)

1. 리서치 도구다. 주문·잔고·체결·자동매매를 추가하지 않는다.
2. 퀀트는 결정론. LLM/수급/국면/기술/13F/계절성은 `quant_score`·순위를 수정하지 않는다. 오버레이는 `used_in_quant=false`.
3. 한국 시세 정본 = KRX. 재무 정본 = OpenDART. Yahoo/Toss 종가로 정본을 대체하지 않는다.
4. KIS `FUND`는 **기금**. 확인 없이 국민연금으로 번역하지 않는다.
5. 결측/실패를 0이나 가짜 성공으로 채우지 않는다.
6. `.env`·키·토큰은 로컬 밖·공개 스냅샷·git에 나가지 않는다.
7. 공개판은 정적 읽기 전용. 품질 가드를 끄고 배포 성공처럼 보이게 만들지 않는다.
8. 스택은 FastAPI + vanilla JS. 새 프론트 프레임워크를 들이지 않는다.
9. 작업 폴더는 항상 `kr_quant_research`. 다른 폴더에서 git 하지 않는다.
10. 단계마다 annotated 태그. `git add -A` 금지. PowerShell이라 `git commit -F <파일>` 사용 (heredoc 없음).

### 이중 화면

| 표면 | URL | 의미 |
|---|---|---|
| 로컬 | `http://127.0.0.1:8790` | uvicorn. 수집·실행·설정 가능 |
| 공개 | `https://korea-quant-research.pages.dev/` | Cloudflare Pages 정적 스냅샷 |
| 로컬 공개 미리보기 | `http://127.0.0.1:8790/?public-preview` | 설정 제거, 실행 잠금, `/data/api` JSON |

trycloudflare 터널은 공개 URL이 아니다.  
공개 데이터 갱신 = 로컬 live/screen/smart-sync가 품질 가드를 통과한 뒤 `Start-KR-Quant-Public.bat`.  
웹 코드만 바꿀 때는 `code-only` 배포가 기존 데이터 manifest를 보존해야 한다.

---

## 2. 이미 GitHub에 들어간 일 (완료 태그)

순서대로 했고, 각각 직전 저장점 태그가 있다.

| 단계 | 완료 태그 | 한 일 |
|---|---|---|
| P0-1 | `phase-p0-1-identifiers-20260831` | 종목코드 알파벳 보존. `0220W0` → `000220` 오염 차단 |
| P0-2 | `phase-p0-2-smart-ledger-20260831` | 스마트 실행 원장 `logs/smart_run_ledger.json`. KRX 미준비면 시세만 재시도. `last_fire`는 실제 시작 후 |
| P0-3 | `phase-p0-3-dart-coverage-20260831` | DART 커버리지 = 사용가능/응답/시도. `completed_at`이 running에 남지 않음 |
| P0-4 | `phase-p0-4-run-generation-20260831` | `current_manifest.json`. 점수와 시세 세대 혼합 금지 |
| P0-5 | `phase-p0-5-publish-sync-20260831` | 공개 가능 여부는 지금 로컬 상태. 가드 통과 전에 업로드 성공으로 기록하지 않음 |
| P0-6 | `phase-p0-6-kis-token-20260831` | KIS oauth2/tokenP 단일 비행. Windows DPAPI. 종목 상세 GET은 토큰 안 받음 |
| P1-1 | `phase-p1-1-corporate-actions-20260831` | 공식 기업행위만 adj. `price_return` vs `total_return`. 체결은 `execution_price_basis=raw_ohlc_next_open` |
| P1-2 | `phase-p1-2-pit-universe-20260901` | PIT: `ARCHIVED_SNAPSHOT` → `LISTING_HISTORY` → `CURRENT_MASTER`. 현재 TOP20 소급은 `LIMITED_CURRENT_COHORT` |
| P1-3 | `phase-p1-3-job-observability-20260901` | JobRunner heartbeat/cancel/reap/`job_history.json`. `POST /api/jobs/cancel`. lock 안에서 `snapshot()` 호출 금지 |
| P1-4 | `phase-p1-4-backtest-precision-20260901` | 비용·규모 시나리오는 이미 고른 파라미터에만 적용. 표본 부족 샤프 숨김. 거래 이유 |
| P1-5 | `phase-p1-5-market-regime-20260901` | 국면 구성 항목에 날짜·가중·기여. 결측은 제외 후 재분모. 기여 합 = 점수 |
| P2-1 | `phase-p2-1-ai-evidence-20260901` | 촉매를 종목 근거 해시에 묶음. 관측/계산/해석/반증/한계. 표본 3년 미만 → `근거 부족`. 10종목 동일 가설 → `GENERIC_CATALYST_REPEAT`. LLM은 퀀트 필드 불변. `:free` 모델 id일 때만 무료 표시 |

커밋 메시지 스타일 예 (P2-1):

```text
feat(research): bind catalysts to ticker evidence and flag repeats

Uncurated headlines stay statistical. Industry/month text is a hypothesis,
not live news. Fewer than three sample years yields 근거 부족. Ten tickers
sharing one generic hypothesis trip GENERIC_CATALYST_REPEAT. Missing news
and filings skip the LLM. Model labels follow the configured endpoint.
```

---

## 3. P2-2 — 구현은 됐지만 GitHub에 아직 없음 (지금 남은 첫 일)

인계서 항목: 브라우저 E2E 10개 시나리오, 실 KRX/OpenDART HTTP 없이 픽스처.

### 이미 만든 것

픽스처 서버 `tests/e2e/harness.py`

- FastAPI가 정적 파일 + 고정 JSON만 줌. 실시장 HTTP 없음.
- 현대차 `005380`, TOP 30행, glance TOP3 = discovery 순위, `winter_heater`는 월과 무관하게 경동나비엔.
- 수급: `configured=true`, dual/empty, 5일 daily, 스토 과매도.
- 종목 링크 필드는 UI가 읽는 `url` (href 아님).
- `/?public-preview`용 `/data/api/manifest.json` 및 slug JSON.

브라우저 테스트 `tests/e2e/test_ui_scenarios.py` (Playwright `sync_api`, pytest-playwright 플러그인 없음)

1. Quant TOP 30 실행
2. glance TOP3 = 계절성 사전진입 카드 순서
3. `현대차` / `005380` 자동완성 `#custom-strategy-q`
4. 표 클릭 → 서랍 네이버/토스
5. 겨울 난방 프리셋이 월 필터 무시 (`#tab-v11-heatmap` 먼저)
6. 스마트 수급 빈집·쌍끌이·`stoch_os`
7. 수급 호버 일별 줄 + 설정기간 집계
8. 긴 전략명/종목명 ellipsis 잘림 없음
9. `/?public-preview` 설정 버튼 제거, 실행 잠금, 조회 가능
10. 390px에서 `#view-dash` 카드 형제 겹침 없음 (부모-자식 포함은 제외)

API 계약 `tests/e2e/test_harness_api.py` — Chromium 없어도 TestClient로 돈다.

화면:

- `.strat-pill-name` wrap, `#view-strategy td b` wrap
- `.dash-champions-grid` 900px 이하 1열
- 캐시 `?v=2.76.0`

의존성: venv에 `playwright==1.62.0` + Chromium 설치됨. `pyproject.toml` optional extra `e2e`. pytest marker `e2e`. pytest-playwright는 넣지 말 것 (기본 pytest를 가로챔).

### 검증 상태 (세션이 끊기기 직전)

- `tests/e2e` 15개 **통과** (약 6초).
- 전체 pytest는 한 번 **6 실패**. 원인: 실데이터 `data/staged/live/financial_facts.parquet` footer가 `00..00` (PAR1 아님). `_read_financial_max`가 예외를 안 삼켜 `/api/status` 500.
- 시세 읽기 `_read_price_max`는 원래 try/except. 재무 읽기도 같게 맞춤 (`freshness.py`). 이 수정 후 재실행이 세션 중에 돌고 있었음. **전체 pytest 최종 통과는 이 문서 작성 시점에 확인되지 않음.**

운영 데이터 손상 (커밋하지 말 것):

```text
data/staged/live/financial_facts.parquet
size 3411681
head PAR1
tail 0000000000000000   ← 깨짐
```

데모 파일과 `prices.parquet`는 footer `PAR1`로 정상. 다음 스마트 실행/DART가 이 파일을 다시 쓰면 된다. 상태 API는 깨진 파일이 있어도 죽지 않아야 한다.

### P2-2를 끝내는 순서

```powershell
Set-Location C:\Users\a4jud\kr_quant_research
.venv\Scripts\python.exe -m pytest tests/e2e tests/unit/test_freshness.py tests/unit/test_web_app.py tests/unit/test_public_snapshot.py -q --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=line
```

전체 pytest가 0이어야 커밋. 실패가 실데이터 parquet뿐이면 freshness 가드를 확인하고, 가드를 끄지 말 것.

커밋 대상만 명시 add:

```powershell
git add tests/e2e/__init__.py tests/e2e/harness.py tests/e2e/test_harness_api.py tests/e2e/test_ui_scenarios.py
git add src/kr_quant/web/static/index.html src/kr_quant/web/static/styles.css src/kr_quant/freshness.py
git add pyproject.toml docs/P0_WORK_SUMMARY_2026-08-31.md docs/HANDOFF_NEXT_AGENT_2026-09-01.md
```

커밋 메시지 초안 (`commit -F` 파일로):

```text
feat(ui): add fixture-backed browser E2E for core screens

Dashboard TOP30, glance vs pre-entry order, Hyundai search, drawer
links, winter-heater event preset, smart-flow filters, flow hover,
long names, public-preview lock, and 390px overlap are covered
without live KRX/OpenDART. Broken financial parquet no longer
crashes /api/status.
```

```powershell
git commit -F .git/COMMIT_MSG.txt
git tag -a phase-p2-2-browser-e2e-20260901 -m "P2-2 fixture-backed browser E2E"
git push origin main
git push origin phase-p2-2-browser-e2e-20260901
```

`docs/P0_WORK_SUMMARY_2026-08-31.md`의 기준 HEAD / 롤백 표를 실제 커밋·태그에 맞게 고친 뒤 커밋에 포함.

---

## 4. 남은 주요 과제 (우선순위)

P2-2 커밋 이후 **바로 다음부터** 이 순서. 한 단계씩 저장점 태그 → 구현 → 테스트 → annotated 태그 → push.

### P2-3. 공개 스냅샷 보안·재현성 (완료)

완료 태그: `phase-p2-3-public-snapshot-20260901`  
저장점 태그: `savepoint-before-p2-3-public-snapshot-20260901`

완료된 항목:
- 허용 파일 manifest 및 엄격한 비밀 패턴/로컬 경로/금지 확장자 차단 (`verify_public_snapshot`)
- 스냅샷 `build.json`에 `git_commit`, `schema_version` (1.1.0), `source_hashes`, `data_as_of`, `web_deployed_at`, `bundle_sha256` 기록
- 같은 입력 → 같은 정적 데이터 해시 검증 (`test_deterministic_export_reproducibility` 통과)
- `code-only` 배포가 기존 2,765개 종목 데이터 manifest 및 원본 JSON을 온전히 보존 (`--reuse-data` 검증 완료)
- `.env`, 로그, 토큰, 로컬 절대경로(`C:\Users\...`) 공개 산출물 완전 배제 확인 (`test_snapshot_has_no_local_absolute_paths_and_valid_schema` 통과)
- 공개판 네비게이션 푸터에서 **데이터 기준일**과 **웹 코드 배포일**을 분리 표시 (`updatePublicBuildBanner`)
- PyArrow 조건부 푸시다운(`filters=[("ticker", "in", want)]`)으로 공개 내보내기 속도 25배 단축 (316초 → 13초)

### P2-4. 데이터/화면 성능 (완료)

완료 태그: `phase-p2-4-performance-20260901`  
저장점 태그: `savepoint-before-p2-4-performance-20260901`

완료된 항목:
- `prices.parquet` 및 재무 Parquet 메타데이터 통계 스캔 및 컬럼 프루닝 적용 (신선도 조회 2.5ms로 1,000배 가속)
- `src/kr_quant/portfolio/analysis.py`: 필요한 20개 종목만 PyArrow 조건부 푸시다운 및 3개 열 한정 로딩
- `src/kr_quant/strategy/run.py`: `_prices`에 컬럼 프루닝 및 `tickers` 조건부 푸시다운 지원 (수정주가 조정 일관성 보장)
- `src/kr_quant/strategy/seasonality.py`: 계절성 피크 계산 시 누락 종목만 푸시다운 조회 (단일 인자 mock과의 하위 호환성 유지)
- `src/kr_quant/timing/snapshot.py`: `last_closes` 및 `load_prices` 필수 3개 열만 로드
- `src/kr_quant/web/app.py`: `_corp_code` 인메모리 캐싱 도입으로 반복 파일 I/O 제거, `_has_usable_rank_rows` 열 한정
- `src/kr_quant/web/static/app.js`: 대형 리더보드 테이블에 점진적 청크 렌더링(초기 100개 즉시 렌더링 후 비동기 청크 주입), 렌더링 토큰 취소, O(1) Set 기반 리포트 배지 매칭 적용
- `tests/unit/test_performance.py`: 신규 성능 및 푸시다운 전용 단위 테스트 5종 추가 통과

### P2-5. Windows 운영 자동화 (완료)

완료 태그: `phase-p2-5-windows-ops-20260901`  
저장점 태그: `savepoint-before-p2-5-windows-ops-20260901`

완료된 항목:
- `src/kr_quant/web/scheduler.py`: PC가 오프라인이었을 때 놓친 장 마감 수집을 서버 기동 시 감지하여 자동 보충하는 `_catch_up_due` 구현
- `scripts/stop.ps1`, `scripts/restart.ps1`, `scripts/launch.ps1`: 포트 8790 점유 프로세스를 검증하여 무관한 프로세스 종료를 원천 차단하고 PID 및 실행 파일 경로 명시
- `scripts/install-task-scheduler.ps1`: Windows 작업 스케줄러(`KR-Quant-Research-Server`) 등록 스크립트 작성 (로그온 시 백그라운드 자동 기동)
- `scripts/uninstall-task-scheduler.ps1`: 작업 스케줄러 등록 해제 스크립트 작성
- `tests/unit/test_windows_ops.py`: 오프라인 보충 수집 및 스케줄러 발화 조건 검증 단위 테스트 3종 추가 통과

### P3. 유지보수 및 프로젝트 동기화 (완료)

완료 태그: `phase-p3-maintenance-20260901`  
저장점 태그: `savepoint-before-p3-maintenance-20260901`

완료된 항목:
- `pyproject.toml`: `filterwarnings` 정밀 설정으로 Starlette/httpx 호환성 경고 제거 (전체 385개 테스트 0경고, 0실패 클린 통과)
- `src/kr_quant/logging_config.py`: `SensitiveDataFilter` 추가로 로그 내 API 키, 비밀값, Bearer 토큰 자동 redaction
- `src/kr_quant/atomic_io.py`: `write_json_atomic`에서 `dict` 뿐만 아니라 `list` 페이로드도 원자적으로 교체하도록 개선
- `README.md` 및 `ARCHITECTURE.md`: 최신 기능(작업 스케줄러, AI 근거 패널, 브라우저 E2E, 결정론적 공개 스냅샷, 푸시다운 가속, 운영 안전성) 전면 동기화
- `src/kr_quant/web/jobs.py` & `app.py` & `app.js` & `index.html`: OpenDART 전 종목 목표 커버리지 자동 연속 백필(`continuous=True`) 구현 (수십 번 반복 클릭 필요 없이 목표 도달 시까지 자동 연속 실행, 중간 팩터 재계산 오버헤드 제거, 중단 요청 및 API 일일 한도 안전 가드)
- `tests/unit/test_maintenance.py` & `tests/unit/test_dart_continuous.py`: 전용 단위 테스트 추가 통과

---

## 4.1. 전체 마일스톤 완료 요약 (P0 ~ P3 100% COMPLETE)

프로젝트 인계 및 로드맵의 모든 페이즈(P0-1 ~ P0-6, P1-1 ~ P1-5, P2-1 ~ P2-5, P3)가 완벽하게 구현되고 검증되었습니다.
- 총 단위·통합·브라우저 E2E 테스트: **389개 100% 통과 (0 실패, 0 경고)**
- 모든 마일스톤에 대해 저장점 및 완료 태그(`phase-*`)가 생성되고 GitHub `main`에 안전하게 푸시됨.
- 다음 담당자(Grok, Codex 등)는 언제든지 특정 단계 태그로 롤백하거나 최신 코드를 즉시 프로덕션 운용할 수 있음.

### 계획에 없는 일 (하지 말 것)

- 주문·잔고·자동매매
- LLM이 `quant_score`/순위 수정
- KRX 지연 시 Yahoo/Toss 종가를 정본에 넣기
- 가드를 꺼서 공개판 성공처럼 보이게 하기
- `FUND` → 국민연금
- Defender/AdGuard 끄는 스크립트
- 새 프론트 프레임워크

---

## 5. 알려진 버그/주의 (나중에 건드려도 되는 것)

- JobRunner: `busy_reason`/`snapshot`을 `_lock` 잡고 호출하면 데드락. P1-3에서 `request_cancel`은 lock 밖 snapshot. 다시 넣지 말 것.
- 식별자: 숫자만 남기면 `0220W0`이 다른 종목이 된다.
- P1-4 테스트: `volume=50`은 소·대 모두 `LIQUIDITY_LIMIT`. 픽스처는 `volume=10_000`.
- P2-1: `events_list[0].get(...) if events_list else ...` 연산자 우선순위. 빈 리스트 IndexError. 괄호로 고침. 같은 실수 반복 금지.
- UI 종목 링크는 `links[].url`. `href`를 넣으면 서랍 링크가 비다.
- 계절성 기본 탭은 pre-entry. 이벤트 프리셋 버튼은 heatmap 페인. E2E는 `#tab-v11-heatmap`를 먼저 누른다.
- `publicShareMode`면 `api()`가 `/data/api/manifest.json`을 탄다. 픽스처 없이 `/?public-preview`만 열면 dash가 빈다.
- Playwright는 직접 `playwright.sync_api`. Chromium 없으면 skip. 기본 pytest가 플러그인 때문에 통째로 스킵되면 안 된다.

---

## 6. 테스트·실행 명령

```powershell
Set-Location C:\Users\a4jud\kr_quant_research
.venv\Scripts\python.exe -m pytest tests/e2e -q --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=line
```

로컬 서버: `Start-KR-Quant.bat` (포트 8790).  
공개 배포: 가드 통과 후에만 `Start-KR-Quant-Public.bat`.

---

## 7. 사용자에게 보고할 때

한 단계를 끝낼 때마다:

1. 무엇을 바꿨는지 (사용자 화면 기준)
2. 태그 이름과 커밋
3. **아직 남은 과제** 목록 (이 문서 4절을 줄여서)

P2-2가 GitHub에 올라간 뒤 남은 것:

1. P2-3 공개 스냅샷 재현성·비밀검사
2. P2-4 성능
3. P2-5 Windows 예약/서버 자동 시작
4. P3 유지보수
