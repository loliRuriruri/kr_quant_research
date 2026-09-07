# KR Quant Research — Grok Build 후속 보완 상세 인계서

작성일: 2026-08-31 KST  
프로젝트: `C:\Users\a4jud\kr_quant_research`  
원격: `https://github.com/loliRuriruri/kr_quant_research`  
로컬 대시보드: `http://127.0.0.1:8790`  
공개 읽기 전용 스냅샷: `https://korea-quant-research.pages.dev/`

---

## 0. 이 문서의 역할

이 문서는 “무엇이 있어 보이는가”를 설명하는 소개서가 아니다. 다음 개발자가 현재 프로그램을 다시 뜯어고치지 않고, 남은 위험을 우선순위대로 제거하기 위한 실행 명세다.

특히 아래 세 종류를 구분한다.

1. **완료·테스트된 기능**: 코드와 테스트가 현재 저장소에 존재한다.
2. **현재 데이터로 드러난 한계**: 코드가 있어도 데이터가 불완전하거나 공급자 시점 때문에 결과가 제한된다.
3. **추가 검증이 필요한 의심 항목**: 재현 없이 버그로 단정하지 말고 먼저 코드·실데이터로 확인한다.

기존 `docs/GROK_BUILD_HANDOFF.md`는 2026-08-21 기준이라 최신 P0~P8 보강과 스마트 파이프라인을 반영하지 못한다. 이 문서를 후속 작업의 기준으로 사용한다.

---

## 1. Git 기준점과 롤백

### 현재 기준

- 브랜치: `main`
- HEAD: `cd4b197 feat(pipeline): add one-click smart daily maintenance`
- 원격: `origin/main`과 동일
- 최신 완료 태그: `smart-pipeline-20260831`
- 스마트 파이프라인 작업 전 태그: `savepoint-before-smart-pipeline-20260831`
- 6~8단계 완료 태그: `phases6-8-complete-20260831`
- 4단계/5단계 태그: `phase4-freshness-contract-20260831`, `phase5-dart-backfill-20260831`

### 중요: 현재 추적하지 말아야 할 항목

2026-08-31 확인 당시 아래 두 경로는 untracked였다. 사용자 소유로 간주한다.

- `.agents/`
- 루트 `output/`

`git add -A`로 함께 넣지 말고, 이번 작업에 필요한 파일만 명시적으로 추가한다.

### 안전한 롤백 방식

작업 전 상태를 별도 브랜치에서 확인하려면:

```powershell
git fetch origin --tags
git switch -c inspect/smart-pipeline smart-pipeline-20260831
```

현재 `main`의 특정 후속 커밋만 취소할 때는 `git reset --hard`보다 `git revert <commit>`을 우선한다.

---

## 2. 절대로 바꾸면 안 되는 제품 원칙

1. 이 프로그램은 **리서치 도구**다. 주문·잔고·체결·자동매매를 추가하지 않는다.
2. 퀀트 점수는 결정론이다. LLM, 수급, 시장 국면, 기술지표, 13F, 계절성은 `quant_score`를 수정하지 않는다.
3. 한국 주식 가격 정본은 KRX, 재무 정본은 OpenDART다.
4. KIS는 읽기 전용 수급 교차검증/보조다. `FUND`는 **기금**이며 확인 없이 국민연금으로 바꾸지 않는다.
5. Toss·네이버·Yahoo·FRED·ECOS·LLM은 보조 또는 설명 레이어다. 공식 정본을 조용히 대체하지 않는다.
6. 결측 또는 실패를 0이나 가짜 성공 데이터로 채우지 않는다.
7. `.env`, API 키, 토큰, 세션, 쿠키는 로컬 밖으로 내보내지 않는다.
8. 공개판은 정적 읽기 전용 스냅샷이다. 데이터 품질 가드를 통과하지 못하면 배포를 차단한다.
9. 안전장치를 꺼서 배포 성공처럼 보이게 만들지 않는다.
10. 과거 성과와 AI 설명을 매수·매도 지시, 목표가, 수익 보장처럼 표현하지 않는다.

---

## 3. 현재 아키텍처

```text
KRX/OpenDART/KIS/ECOS/FRED/SEC 등
          │
          ▼
로컬 수집·정규화·품질검사
  data/staged/live/*.parquet
          │
          ├─ 결정론적 Quant 계산
          │     data/output/latest_*
          │
          ├─ 수급·시장·계절성·전략 Overlay
          │     data/cache/*, 전략 캐시
          │
          ├─ FastAPI 로컬 UI (:8790)
          │
          └─ 품질/근거/비밀검사 통과 시
                dist-public 정적 스냅샷
                         │
                         ▼
                Cloudflare Pages 공개판
```

### 핵심 계층

| 계층 | 역할 | Quant 합산 |
|---|---|---:|
| Discovery | KRX+OpenDART 기반 5대 팩터, 유니버스, 순위 | 예 |
| Context | 시장 국면, 업종, 관심종목 | 아니오 |
| Flow/Timing | KIS/Toss 수급, 기술적 지표 | 아니오 |
| Seasonality/Strategy | 계절성, 이벤트, 가격 규칙 백테스트 | 아니오 |
| Research/AI | 근거를 설명하고 반증 조건을 제시 | 아니오 |
| Public | 로컬 계산 결과를 정적으로 조회 | 계산 없음 |

---

## 4. 2026-08-31까지 완료된 작업

### 데이터·안전

- KRX 거래상태 일별 스냅샷과 fail-closed 후보 차단
- 현재 거래 불가/위험 종목을 퀀트·계절성·파생 캐시에서 재필터링
- Parquet 원자적 교체
- 시세/랭킹/전략 캐시 최신성 계약
- OpenDART 전 종목 순환 백필과 체크포인트
- 가격 단절·거래량 0·OHLC 이상을 탐지하고 최근 안전 구간만 사용
- 일별 유니버스 스냅샷과 현재 TOP20 소급 연구의 생존편향 한계 표시
- 공개 스냅샷의 품질·기준일·근거 계약 배포 가드

### 전략·백테스트

- 신호 다음 거래 가능일 시가 체결
- 수수료·날짜별 매도세·슬리피지·거래대금 참여율 충격 반영
- 거래량 0 및 일봉 기준 상·하한가 잠김 프록시 미체결
- 학습/검증/최종 OOS 분리와 최종 구간 선택 누수 방지
- Walk-Forward와 현재 TOP20 소급 연구 한계 노출

### UI/기능 통합

- 메이저 수급·쌍끌이·빈집·기술 타점을 스마트 수급 작업공간으로 통합
- 수급 호버 내용을 날짜별 줄바꿈과 기간 집계로 정리
- 계절성 특수 이벤트 프리셋과 테마맵 정합성 보강
- 대시보드 TOP/계절성 데이터 일치 문제 보강
- 반복적이고 정보 가치가 낮은 `Quant 점수 미합산` 문구 정리
- 메뉴 공통 근거 계약(`sources`, `as_of`, `sample`, `calculation_state`, `limitations`) 도입
- 실행 파이프라인을 `오늘 필요한 작업 스마트 실행` 중심으로 단순화

### 운영

- `Start-KR-Quant.bat`: 기존 8790 서버 정리 후 재시작
- `Stop-KR-Quant.bat`: 로컬 서버 정지
- 평일 19:10 스마트 실행 예약과 서버가 늦게 켜진 날의 1회 보충 실행
- 예약 실행일을 `logs/scheduler_state.json`에 저장해 서버 재시작 중 중복 실행 억제
- 품질 통과 시 공개판 자동 갱신 연결

### 테스트

- 마지막 전체 회귀 확인: **285개 통과**
- 알려진 테스트 경고: Starlette `TestClient`와 `httpx` 구형 연동 deprecation 1종
- 위 숫자는 후속 작업 시작 시 반드시 다시 실행해 확인한다.

---

## 5. 실제 데이터 상태 스냅샷

아래는 2026-08-31 21:26 KST에 스마트 작업 종료 후 로컬 API와 산출물을 다시 읽어 확인한 값이다. 이후 예약/수동 실행에 따라 변할 수 있으므로 “현재값”이 아니라 “인계 당시 관측값”으로 취급한다.

| 항목 | 관측값 | 해석 |
|---|---:|---|
| KRX 기대 기준일 | 2026-08-31 | 거래 캘린더 기준 |
| KRX 실제 최대 일자 | 2026-08-28 | 1거래일 지연 상태 |
| Quant 랭킹 기준일 | 2026-08-28 | 보유 가격과 일치 |
| DART 재무 사용 가능 종목 | 513 / 2,544 | 20.2%, 전체 커버리지 미완 |
| DART 체크포인트 | cursor 100 | 이번 50종목 배치 성공 |
| Quant 적격 종목 | 336 | 재무 커버리지가 늘며 307에서 증가 |
| 가격 품질 이슈 | 32,656 | 대부분 무거래 행 제거 30,668건 |
| 중요 가격 이슈 | 77 | 미설명 가격 단절 76 + 비양수 OHLC 1 |
| 기업행위 공식 확정 | false | 보수적 구간 분리만 적용 |
| 상장일 커버리지 | 100% | 현재 마스터 기준 |
| 상장폐지일 커버리지 | 0% | 과거 시장 전체 생존편향 통제 불가 |
| 전략 연구 등급 | `LIMITED_CURRENT_COHORT` | 현재 TOP20의 과거 소급 연구 |
| 근거 레지스트리 | valid | 필수 메뉴 계약 유효 |
| 스케줄러 | enabled/running | 다음 2026-09-01 19:10 KST |

### 인계 시점의 실행 결과

- 시작: 2026-08-31 21:13:10 KST
- 종료: 2026-08-31 21:23:13 KST
- 최종 상태: `partial`
- KRX: 2026-08-31 자료 미준비, 2026-08-28 유지
- DART: 50종목 처리, 513/2,544종목(20.2%)
- KIS: 33종목 시도, 2,970행 저장
- 공개판: `PRICE_DATA_STALE`, `AS_OF_DATE_MISMATCH`로 안전 차단
- 작업 초반 약 10분 동안 API 로그에는 `[1/4]`만 보여 장시간 단계의 실제 세부 진행률은 확인하기 어려웠다.
- 작업의 `result.freshness`에는 순간적으로 `quant_ranking=missing`이 기록됐지만, 종료 후 `/api/status` 재조회에서는 2026-08-28 `fresh`로 확인됐다. 여러 최신 산출물을 한 세대로 읽지 못하는 순간 불일치 가능성을 별도 P0로 다룬다.

---

## 6. 가장 먼저 해결할 P0

P0는 새 메뉴나 디자인보다 먼저 처리한다. 데이터 식별자, 실행 상태, 배포 기준일이 틀리면 보기 좋은 화면도 신뢰할 수 없다.

### P0-1. 종목 식별자 계약 통일

#### 현재 관측

KRX 마스터와 DART 백필 순서에는 `0220W0`, `0120G0`, `0011T0` 같은 알파벳 포함 6자리 단축코드가 존재한다. 이것을 무조건 오류라고 단정하면 안 된다. 다만 공급자별 코드 지원 범위가 다르므로 현재의 산발적인 정규화는 위험하다.

특히 `src/kr_quant/ingest/kis.py`는 KIS 요청 전 다음과 같이 숫자만 남긴다.

```python
code = "".join(ch for ch in str(ticker) if ch.isdigit()).zfill(6)
```

예를 들어 `0220W0`을 숫자만 남기면 다른 코드 `000220`처럼 변형될 수 있다. 이는 잘못된 종목의 수급을 원래 종목에 붙이는 심각한 데이터 오염 가능성이다.

#### 요구 구현

1. `canonical_ticker`, `source_ticker`, `security_type`, `market`, `provider_support`를 다루는 중앙 식별자 모듈을 만든다.
2. KRX 코드는 원문 6자리를 보존한다. 숫자 강제 삭제를 하지 않는다.
3. 공급자가 알파벳 코드를 지원하지 않으면 호출하지 않고 `UNSUPPORTED_TICKER_FORMAT`으로 기록한다.
4. OpenDART는 `corp_code`와 `stock_code` 매핑이 실제 존재할 때만 수집한다.
5. Toss/KIS/네이버 링크 등 공급자별 변환을 각 어댑터에서 임의 구현하지 말고 공통 계약을 사용한다.
6. 캐시·DuckDB·Parquet join에서 앞자리 0과 알파벳이 보존되는지 검사한다.
7. 잘못 변환된 과거 캐시가 있으면 삭제보다 마이그레이션/격리 보고서를 우선한다.

#### 완료 조건

- `0220W0` 같은 코드가 `000220`으로 바뀌지 않는 테스트
- 숫자형 `005930`이 모든 기존 API에서 그대로 동작하는 테스트
- 지원하지 않는 공급자에는 네트워크 호출이 발생하지 않는 테스트
- 종목 A의 수급/가격/재무가 종목 B에 붙지 않는 join 무결성 테스트
- UI에는 “해당 공급자 코드 미지원”을 0건 수급으로 표시하지 않음

#### 주요 파일

- `src/kr_quant/ingest/kis.py`
- `src/kr_quant/ingest/tossinvest.py`
- `src/kr_quant/ingest/live.py`
- `src/kr_quant/flow/official.py`
- `src/kr_quant/universe/`
- 관련 캐시/API 직렬화 코드와 테스트

---

### P0-2. 스마트 실행을 단계 상태 머신으로 변경

#### 현재 문제

현재 `job_smart_sync()`는 시세가 오래되면 `job_live()`를 호출한다. 공급자에서 당일 KRX 자료가 아직 준비되지 않았으면 가장 최근 거래일로 후퇴해 실행은 끝나지만, `expected_price_date`와 `price_max_date`가 계속 다를 수 있다.

또한 스케줄러는 `_fire()` 시작 시점에 `last_fire`를 먼저 저장한다. 다음 문제가 생길 수 있다.

- 19:10 자료 미준비 상태에서 실행한 뒤 그날 성공한 것으로 간주
- 다른 작업이 실행 중이라 실제로 시작하지 못했는데도 당일 슬롯 소비
- 시세만 재시도하면 되는데 DART/KIS/퀀트 전체를 다시 실행
- 실패/부분 완료/차단 상태가 다음 재시작에서 충분히 복구되지 않음

#### 요구 구현

단일 `last_fire` 대신 날짜별·단계별 실행 원장을 둔다.

권장 필드:

```json
{
  "run_date": "2026-08-31",
  "run_id": "...",
  "expected_price_date": "2026-08-31",
  "started_at": "...",
  "heartbeat_at": "...",
  "finished_at": null,
  "overall_status": "running|success|partial|failed|blocked",
  "steps": {
    "krx": {"status": "source_not_ready", "attempt": 1, "retry_at": "..."},
    "dart": {"status": "success", "batch_id": "..."},
    "quant": {"status": "blocked_dependency"},
    "kis": {"status": "success"},
    "publish": {"status": "blocked_stale"}
  }
}
```

동작 원칙:

1. KRX가 당일 자료를 주지 않으면 `SOURCE_NOT_READY`로 분리한다.
2. 20~30분 뒤 시세 단계만 제한 횟수 재시도한다.
3. 이미 성공한 DART 배치와 KIS 수급은 같은 날 재실행하지 않는다.
4. 다른 작업 때문에 시작하지 못했으면 `last_success`를 쓰지 않는다.
5. 서버 재시작 후 `running`이 남아 있으면 heartbeat와 실제 프로세스를 비교해 `interrupted`로 복구한다.
6. 모든 의존 단계가 최신일 때만 Quant/파생 캐시/배포를 이어간다.
7. 수동 스마트 실행과 예약 실행이 같은 상태 머신을 사용한다.

#### 완료 조건

- KRX 미준비 → 시세 단계만 재시도 → 당일 자료 수신 → Quant 재계산 → 배포 성공 테스트
- 이미 성공한 DART/KIS가 KRX 재시도 때 다시 호출되지 않는 테스트
- `RUNNER`가 바쁜 경우 실행 슬롯이 성공 처리되지 않는 테스트
- 서버 강제 종료 후 `running` 체크포인트가 `interrupted`로 복구되는 테스트
- UI에서 현재 단계, 경과 시간, 다음 재시도 시각, 차단 의존성을 확인 가능

#### 주요 파일

- `src/kr_quant/web/jobs.py`
- `src/kr_quant/web/scheduler.py`
- `src/kr_quant/freshness.py`
- `config/scheduler.yaml`
- `tests/unit/test_smart_sync.py`
- `tests/unit/test_freshness.py`

---

### P0-3. DART 백필 상태와 커버리지 의미 바로잡기

#### 현재 문제

1. 백필을 시작할 때 이전 상태를 펼쳐 넣기 때문에 새 상태가 `running`인데 이전 `completed_at`이 남을 수 있다.
2. 현재 커버리지는 “재무 fact가 하나라도 저장된 ticker / 대상 ticker”다. 보고서가 원래 없거나 공급자 미지원인 종목은 계속 미커버로 남아 목표 90%가 영원히 어려울 수 있다.
3. `cursor`는 진행하지만 종목별 결과가 성공/보고서 없음/매핑 없음/재시도 가능 오류로 분리되지 않는다.
4. 첫 스마트 갱신에서 우선 400종목 수집 후 별도 50종목 백필도 실행될 수 있어, 사용자가 예상한 시간보다 무거워질 수 있다.

#### 요구 구현

- 실행 시작 시 이전 `completed_at`, `error`, terminal status를 명시적으로 비운다.
- 종목별 상태를 저장한다.
  - `usable_facts`
  - `no_filing_for_period`
  - `no_corp_mapping`
  - `unsupported_security`
  - `rate_limited`
  - `transient_error`
  - `permanent_error`
- 커버리지를 최소 3개로 나눈다.
  - 시도 커버리지
  - 정상 응답 커버리지
  - 퀀트 사용 가능 재무 커버리지
- 전체 순환 완료와 90% 사용 가능 커버리지를 별도 상태로 둔다.
- 예상 남은 배치 수와 대략적인 완료 예정일을 UI에 표시한다.
- 같은 종목의 무한 재시도를 막되 공시 갱신 주기에 맞춘 재수집은 허용한다.
- 스마트 일일 작업의 `max_corps=400` 우선 수집과 50종목 백필의 중복을 제거하거나 의도를 명확히 분리한다.

#### 완료 조건

- 중단 후 재시작해도 cursor와 종목별 결과가 정확히 복구
- `status=running`에 과거 `completed_at`이 남지 않음
- 보고서 없음과 API 실패가 구분됨
- 같은 날 같은 배치가 중복 수집되지 않음
- 90% 목표가 어떤 분모/분자로 계산되는지 UI와 API에 동일하게 표시

#### 주요 파일

- `src/kr_quant/ingest/live.py`
- `src/kr_quant/freshness.py`
- `src/kr_quant/web/jobs.py`
- `data/staged/live/dart_backfill_state.json` 스키마
- `tests/unit/test_dart_backfill.py`

---

### P0-4. 여러 산출물을 하나의 실행 세대로 원자 공개

#### 현재 관측

2026-08-31 21:23 스마트 작업의 반환값에는 최종 `quant_ranking.observed_date=null`, `state=missing`이 저장됐다. 그러나 몇 초 뒤 같은 서버의 `/api/status`는 `observed_date=2026-08-28`, `state=fresh`를 반환했다.

개별 Parquet/JSON은 원자 교체되지만 다음 파일 전체가 하나의 트랜잭션으로 전환되는 것은 아니다.

- `latest_all_stocks.parquet`
- `latest_top20.csv`, `latest_top100.csv`
- `data_quality_report.json`
- `universe_evidence.json`
- 파생 전략 캐시와 근거 레지스트리

따라서 실행 도중 API가 이전 세대 파일과 새 세대 파일을 섞어 읽을 수 있고, 최종 job result도 그 순간 상태를 영구 기록할 수 있다.

#### 요구 구현

1. 모든 실행 산출물을 `run_id`별 임시/버전 디렉터리에 완성한다.
2. 스키마·행 수·해시·기준일 검증을 끝낸 뒤 `current_manifest.json` 포인터 하나만 원자 교체한다.
3. API와 공개 빌드는 항상 같은 manifest가 가리키는 세트만 읽는다.
4. 실행 중에는 직전 정상 세트를 계속 제공하고 별도 `updating=true`만 표시한다.
5. 파생 캐시가 새 가격/랭킹 세대와 맞지 않으면 새 manifest에 포함하지 않는다.
6. job result의 최종 freshness는 commit된 manifest를 다시 읽어 기록한다.

#### 완료 조건

- 출력 파일 사이에 의도적으로 지연을 넣어도 API가 혼합 세대를 보지 않음
- 실행 실패 시 직전 manifest와 데이터가 그대로 유지됨
- job result와 즉시 재조회한 `/api/status`의 기준일/상태가 일치
- 공개 빌드가 단일 run_id/source hash 세트만 사용

#### 주요 파일

- `src/kr_quant/orchestration/run.py`
- `src/kr_quant/freshness.py`
- `src/kr_quant/web/jobs.py`
- `src/kr_quant/web/evidence.py`
- `src/kr_quant/web/publish.py`
- 원자적 I/O 유틸리티와 통합 테스트

---

### P0-5. 공개판 상태를 “마지막 성공”과 “현재 동기화”로 분리

#### 현재 관측

인계 당시 `/api/publish/status`는 과거 배포 성공을 보여 주지만, 현재 로컬 시세는 기대일보다 늦어 품질 계약이 차단 상태였다. “마지막 배포 성공”과 “현재 데이터를 지금 배포할 수 있음”은 다른 사실이다.

또한 `_maybe_publish()`는 품질 가드 검사 전에 “Cloudflare Pages에 올리는 중” 로그를 먼저 남겨, 실제로는 가드에서 막힌 상태가 업로드 실패처럼 보일 수 있다.

#### 요구 구현

공개판 상태를 다음처럼 분리한다.

- `last_successful_deploy_at`
- `published_as_of`
- `current_local_as_of`
- `current_expected_as_of`
- `in_sync`
- `current_publish_readiness`
- `blocking_reasons`
- `deployment_url`

로그 단계도 다음처럼 바꾼다.

1. 공개판 갱신 가능 여부 검사
2. 차단이면 “안전 차단”과 원인 표시
3. 통과한 경우에만 빌드/업로드 중 표시

#### 완료 조건

- 과거 성공 배포가 있어도 현재 로컬과 날짜가 다르면 `in_sync=false`
- stale/as-of mismatch는 실패가 아니라 안전 차단으로 명확히 표시
- 코드만 배포와 데이터 배포를 UI에서 구분
- 공개판에 올라간 실제 `as_of`를 스냅샷 manifest로 검증

#### 주요 파일

- `src/kr_quant/web/publish.py`
- `scripts/build-public.mjs`
- `scripts/export_public_snapshot.py`
- `src/kr_quant/web/static/app.js`
- `tests/unit/test_public_publish.py`
- `tests/unit/test_public_snapshot.py`

---

### P0-6. KIS 토큰 중복 발급 방지

#### 배경

사용자는 작업 중 한국투자증권 OpenAPI 토큰 발급 알림톡을 여러 번 받았다. 현재 KIS 토큰 캐시는 프로세스 메모리 전역 변수라 서버를 재시작하면 사라진다. 연결 테스트나 수급 작업이 새 프로세스에서 토큰을 다시 요청할 수 있다.

#### 요구 구현

1. 한 프로세스 안에서는 lock/single-flight로 동시에 토큰을 한 번만 발급한다.
2. 자동 화면 로딩 또는 상태 조회가 토큰 발급 API를 호출하지 않게 한다.
3. 연결 테스트는 사용자가 명시적으로 눌렀을 때만 발급한다.
4. 프로세스 재시작 간 캐시가 꼭 필요하면 Windows DPAPI 등 로컬 보안 저장소를 사용한다.
5. 평문 토큰 파일, Git 추적 파일, 로그, API 응답에 토큰을 남기지 않는다.
6. 발급 시각·만료 시각·발급 원인만 비밀 없는 운영 로그에 남긴다.
7. 공급자 발급 제한을 만나면 재발급 루프 대신 다음 가능 시각을 보여 준다.

#### 완료 조건

- 동시 20개 종목 수집에서도 발급 호출 1회
- 서버 재시작 직후 자동 상태 조회만으로 발급 알림이 오지 않음
- 토큰 또는 appsecret이 테스트 출력·로그·공개판에 없음
- 401 발생 시 한 번만 갱신 후 재시도하고, 반복 401은 중단

#### 주요 파일

- `src/kr_quant/ingest/kis.py`
- `src/kr_quant/flow/official.py`
- `src/kr_quant/web/app.py`의 연결 테스트
- 비밀 패턴 검사 테스트

---

## 7. P1 — 연구 신뢰도를 높이는 핵심 과제

### P1-1. 공식 기업행위와 수정 가격

현재 가격 품질 게이트는 큰 단절을 발견하면 이전 구간을 버리는 보수적 정책이다. 이는 오염 방지에는 유효하지만 액면분할, 병합, 감자, 권리락, 합병, 무상증자, 배당을 확정하지 않는다.

해야 할 일:

- 공식 기업행위 원천과 event date, ratio, ex-date를 저장
- 원시 OHLC와 조정계수/조정 OHLC를 함께 보존
- 가격 단절 76건을 공식 이벤트와 대조
- 설명되지 않은 단절은 계속 격리
- 가격 수익률과 배당 포함 총수익률을 혼동하지 않도록 필드 분리
- 전략 결과에 raw/adjusted/total-return 중 무엇을 썼는지 명시

완료 조건:

- 알려진 분할/권리락 표본의 조정 전후 회귀 테스트
- 공식 이벤트가 없는 큰 단절은 자동 연결하지 않음
- 거래 수·수익률·MDD 변화 감사표 제공

주요 파일:

- `src/kr_quant/quality/price_integrity.py`
- `src/kr_quant/ingest/krx.py`
- `src/kr_quant/strategy/engine.py`
- `src/kr_quant/factors/momentum.py` 또는 실제 모멘텀 구현부

---

### P1-2. 진짜 Point-in-Time 시장 유니버스

현재 일별 `universe_snapshot.parquet` 적재는 앞으로의 재현에는 도움이 된다. 그러나 과거 상장폐지일 커버리지는 0%이고 전략은 현재 TOP20을 과거로 소급한 연구다.

해야 할 일:

- 과거 날짜별 상장·상장폐지·거래정지·시장 이전 이력 수집
- 당시 존재한 종목만으로 횡단면 랭킹 재구성
- 재무도 당시 `available_date <= selection_date`만 사용
- 일별/월별 리밸런싱 규칙과 종목 교체 비용 반영
- 현재 소급 연구와 PIT 포트폴리오 연구를 별도 메뉴/등급으로 유지

완료 조건:

- 3개 이상의 과거 기준일에서 당시 유니버스 표본을 독립 검증
- 이후 상장 종목이 과거 후보에 들어가지 않음
- 당시 상장폐지 종목이 원천에 있으면 누락되지 않음
- PIT 원천이 없으면 `survivorship_bias_controlled=true`를 표시하지 않음

주요 파일:

- `src/kr_quant/universe/point_in_time.py`
- `src/kr_quant/orchestration/run.py`
- `src/kr_quant/strategy/run.py`
- `tests/unit/test_point_in_time_universe.py`

---

### P1-3. 스마트 작업의 관측성·중단 복구

인계 당시 장시간 작업은 실제 파일을 갱신하고 있어도 화면 로그가 첫 단계에서 오래 멈췄다.

해야 할 일:

- 현재 단계/대상 수/완료 수/실패 수/경과 시간/heartbeat 표시
- 네트워크 공급자별 timeout과 제한된 재시도
- 단계 경계에서 안전 취소, 강제 종료 후 체크포인트 복구
- 최근 N회 실행 이력과 단계별 소요 시간 저장
- job process/thread가 사라진 `running` 상태 자동 정리
- 무거운 DART/전략 작업 중 같은 작업 재클릭 차단 이유 표시

완료 조건:

- 60초 이상 작업에서 heartbeat가 계속 변함
- 중단 후 정상 데이터 파일이 손상되지 않음
- 마지막 성공, 마지막 부분 완료, 마지막 실패를 각각 조회 가능

---

### P1-4. 백테스트 정밀도 2차 보강

6단계에서 비용·일봉 체결 프록시는 구현됐다. 남은 과제는 결과의 적용 범위를 더 정확히 만드는 것이다.

해야 할 일:

- 설정별 비용 민감도(낮음/기본/보수적) 동시 비교
- 종목 거래대금 대비 포지션 규모 민감도
- 기업행위/PIT 유니버스 연결
- 벤치마크와 같은 기간·거래일 정렬
- 배당 제외 가격수익률과 총수익률 분리
- 거래 1~2회의 샤프·연환산 수익률을 대표 지표처럼 보이지 않게 신뢰구간/표본 경고 강화
- 전략별 왜 진입/청산했는지 거래 로그에서 재현

하지 말 것:

- 일봉만으로 실제 호가 잔량을 재현했다고 표현
- 현재 TOP20 소급 결과를 시장 전체 포트폴리오 성과라고 표현
- OOS 결과를 보고 다시 파라미터를 고른 뒤 OOS라고 부르기

---

### P1-5. 시장 국면의 구성요소별 날짜와 설명

현재 근거 계약에서 시장 메뉴는 `ECOS/FRED/Yahoo/KRX` 혼합, `observed_at=null`, 표본 수 미상으로 남는다. 화면이 수치를 보여도 어느 날짜의 금리·환율·변동성인지 판단하기 어렵다.

해야 할 일:

- 추세, breadth, 유동성, 변동성, 금리, 환율, 모멘텀을 개별 카드/차트로 표시
- 각 구성요소의 원천, 실제 관측일, 최근값, 전일/1개월 변화, 점수 기여도 표시
- VIX, 미국 2Y/10Y, 장단기 금리차, 원/달러, 원자재 등을 쓰면 실제 원천과 시차를 명시
- 누락 지표를 0점으로 조용히 처리하지 말고 가중치 재분배 여부를 공개
- “중립 44.2”가 어떤 계산으로 나왔는지 합계가 재현되게 함
- 모델 의견과 관측 사실을 구분하고 반증 조건을 제시

완료 조건:

- 화면 숫자 합으로 최종 국면 점수를 재현 가능
- 각 지표에 `as_of`와 stale 상태가 있음
- 지표 일부 실패 시 국면 신뢰도가 낮아짐
- 근거 계약의 `observed_at`, `sample.count`가 실제 값으로 채워짐

주요 파일:

- `src/kr_quant/context/market_sentiment.py`
- `src/kr_quant/web/evidence.py`
- 시장 API 및 `src/kr_quant/web/static/app.js`

---

## 8. P2 — UI·AI·운영 품질

### P2-1. AI 설명을 종목별 근거에 묶기

과거 화면에서 여러 종목의 “AI 핵심 투자 촉매”가 월만 바꾼 동일 문장으로 표시된 문제가 있었다. 공급자 실패 시 일반 문구를 종목 분석처럼 보여 주면 안 된다.

요구사항:

- 입력 근거 해시로 AI 캐시 키 구성
- 종목명, 업종, 실제 계절성 구간, 연도별 수익률, 공시/실적, 수급 등 제공된 근거만 사용
- `관측 사실 / 계산 결과 / AI 해석 / 반증 조건 / 데이터 한계`를 구조화
- 근거가 부족하면 종목별 촉매를 생성하지 않고 “근거 부족” 표시
- Tier1 실패는 결정론적 요약으로 대체하되 가짜 뉴스·실적·목표가를 만들지 않음
- 같은 문장이 여러 종목에 반복되는 비율을 회귀 테스트 또는 품질 검사로 감지
- 모델 이름·비용·무료 여부를 하드코딩한 홍보 문구는 실제 공급자 응답과 설정 기준으로 관리

완료 조건:

- 서로 다른 종목 10개에서 동일 일반 문구 반복이 품질 검사에 걸림
- 원천 데이터가 없는 경우 구체적인 촉매/가격/확률을 만들지 않음
- LLM 응답이 퀀트 필드에 쓰이지 않음

---

### P2-2. 사용자 회귀 시나리오를 브라우저 E2E로 고정

이 프로젝트는 기능이 많아 한 메뉴 수정이 다른 메뉴의 빈 표, 순위 불일치, 자동완성 누락으로 이어진 적이 있다. 단위 테스트만으로 화면 회귀를 충분히 잡기 어렵다.

최소 E2E 시나리오:

1. 대시보드 Quant TOP 30에 실제 행이 표시됨
2. 대시보드 시즌 TOP3와 시즌 메뉴 동일 조건 순위가 일치함
3. `현대차`와 `005380` 검색 및 자동완성 성공
4. 표 행 클릭/더블클릭 시 종목 상세가 열리고 네이버/토스 링크가 올바름
5. 특수 이벤트 프리셋은 월 선택과 독립적으로 해당 유니버스를 표시
6. 스마트 수급 메뉴에서 빈집·쌍끌이·기술 필터가 함께 동작
7. 수급 호버가 날짜별 줄바꿈과 설정기간 합계를 표시
8. 전략 최고명, 긴 종목명, 긴 오류 문구가 잘리지 않음
9. 공개판에서는 설정/실행 변경이 잠기고 조회는 가능
10. 모바일 폭에서 핵심 카드와 표가 겹치지 않음

테스트 데이터는 네트워크 결과에 직접 의존하지 말고 고정 fixture를 사용한다. 실데이터 smoke test는 별도로 둔다.

---

### P2-3. 공개 스냅샷 보안·재현성

- 허용 파일 manifest 기반으로 `dist-public` 생성
- 비밀 패턴 검사와 알려진 민감 파일 차단
- 스냅샷에 코드 commit, schema version, source hashes, generated_at, as_of 기록
- 같은 입력으로 같은 정적 데이터가 만들어지는지 해시 검증
- 오래된 공개 캐시와 브라우저 캐시를 구분하는 버전 표시
- `code-only` 배포가 기존 데이터 manifest를 실제로 보존하는지 테스트

완료 조건:

- `.env`, 로그, 토큰, 로컬 절대경로가 공개 산출물에 없음
- 배포된 manifest와 로컬 build manifest가 일치
- 공개판에서 데이터 기준일과 웹 코드 배포일을 각각 확인 가능

---

### P2-4. 데이터/화면 성능

가격 파일은 장기 이력 확장으로 커질 수 있다. 모든 메뉴에서 전체 Parquet를 매 요청마다 읽으면 서버와 공개 스냅샷이 느려진다.

측정 후 개선할 것:

- API별 p50/p95 응답 시간과 메모리
- `prices.parquet` 읽기 횟수와 필요한 열/종목 predicate pushdown
- 계절성·전략·수급 캐시 크기와 생성 시간
- 표 pagination/virtualization
- 공개 JSON 분할과 압축
- 캐시 key에 기준일·코드 버전·source hash 포함

성능 최적화가 데이터 신선성 또는 품질 가드를 우회하면 안 된다.

---

### P2-5. Windows 운영 자동화

현재 예약은 로컬 FastAPI 프로세스가 켜져 있을 때만 동작한다. PC가 꺼져 있거나 서버가 중단되면 다음 실행 때 보충한다.

선택 보강:

- Windows 작업 스케줄러로 로그인/부팅 후 서버 시작
- 평일 예약 시각에 서버가 꺼져 있으면 시작 후 스마트 작업
- 실행 계정과 작업 폴더를 명시
- Defender/AdGuard를 끄거나 예외를 광범위하게 추가하지 않음
- 8790 포트 충돌 시 소유 PID와 실행 파일을 보여 주고 무관한 프로세스를 종료하지 않음

완료 조건:

- 재부팅 후 백신/AdGuard 상태를 건드리지 않음
- 같은 서버가 중복 실행되지 않음
- 실패 로그가 한글 UTF-8로 읽힘
- 시작/정지는 `Start-KR-Quant.bat`, `Stop-KR-Quant.bat` 두 파일로 일상 운영 가능

---

## 9. P3 — 유지보수 과제

- Starlette `TestClient`/`httpx` deprecation 정리
- `README.md`, `ARCHITECTURE.md`, 기존 오래된 `docs/GROK_BUILD_HANDOFF.md` 상태 동기화
- JSON/CSV도 Parquet와 같은 원자적 교체 정책으로 통일
- 캐시 스키마 버전과 마이그레이션 도구
- 로그 보존 기간과 민감정보 redaction
- 네트워크 어댑터 공통 retry/backoff/rate-limit 계약
- 공급자별 time zone/장 마감 기준 통일
- 정적 타입 검사와 JavaScript lint/format 도입 여부 검토

---

## 10. 수정 대상 파일 지도

| 영역 | 주요 파일 |
|---|---|
| 스마트 실행 | `src/kr_quant/web/jobs.py` |
| 예약·보충 실행 | `src/kr_quant/web/scheduler.py`, `config/scheduler.yaml` |
| 최신성 계약 | `src/kr_quant/freshness.py` |
| KRX/OpenDART 수집·백필 | `src/kr_quant/ingest/live.py`, `src/kr_quant/ingest/krx.py` |
| KIS 수급 | `src/kr_quant/ingest/kis.py`, `src/kr_quant/flow/official.py` |
| 가격 무결성 | `src/kr_quant/quality/price_integrity.py` |
| PIT 유니버스 | `src/kr_quant/universe/point_in_time.py` |
| 퀀트 실행 | `src/kr_quant/orchestration/run.py` |
| 전략 체결·결과 | `src/kr_quant/strategy/engine.py`, `src/kr_quant/strategy/run.py` |
| 공개 배포 | `src/kr_quant/web/publish.py`, `scripts/build-public.mjs`, `scripts/export_public_snapshot.py` |
| 근거 계약 | `src/kr_quant/web/evidence.py` |
| HTTP API | `src/kr_quant/web/app.py` |
| UI | `src/kr_quant/web/static/index.html`, `app.js`, `styles.css` |
| 실행 스크립트 | `Start-KR-Quant.bat`, `Stop-KR-Quant.bat`, `scripts/restart.ps1` |
| 회귀 테스트 | `tests/unit/`, `tests/integration/` |

---

## 11. 권장 실행 순서와 커밋 단위

### 단계 A — 식별자 오염 차단

권장 커밋:

```text
fix(data): preserve provider-safe Korean security identifiers
```

범위: P0-1만. 캐시 마이그레이션 영향 보고 포함.

### 단계 B — 실행 상태/재시도 상태 머신

권장 커밋:

```text
fix(pipeline): persist step outcomes and retry source-not-ready prices
```

범위: P0-2와 실행 원장 최소 구현.

### 단계 C — DART 백필 계약

권장 커밋:

```text
fix(dart): track terminal outcomes and truthful coverage
```

범위: P0-3. 종목별 결과, 모순 상태 제거, 중복 수집 방지.

### 단계 D — 산출물 세대 원자 전환

권장 커밋:

```text
fix(outputs): publish one coherent run generation atomically
```

범위: P0-4. API와 job result의 혼합 세대 제거.

### 단계 E — 배포 동기화 상태

권장 커밋:

```text
fix(publish): separate last deployment from current readiness
```

범위: P0-5. 품질 가드는 유지.

### 단계 F — KIS 토큰 수명주기

권장 커밋:

```text
fix(kis): prevent duplicate token issuance across flow jobs
```

범위: P0-6. 비밀 저장 보안 검토 필수.

### 단계 G 이후

1. 공식 기업행위/수정 가격
2. 역사적 PIT 유니버스
3. 시장 국면 구성요소 근거
4. AI 설명 근거화
5. 브라우저 E2E
6. 성능·운영·의존성 정리

한 단계에서 여러 P0/P1을 한꺼번에 바꾸지 않는다. 수집, 스코어링, UI, 배포를 동시에 크게 고치면 회귀 원인을 찾기 어렵다.

---

## 12. 단계별 표준 검증 절차

### 1) 작업 전

```powershell
cd C:\Users\a4jud\kr_quant_research
git status --short
git diff
git log -10 --oneline --decorate
```

annotated tag 예시:

```powershell
git tag -a savepoint-before-<phase>-20260901 -m "<무엇을 시작하기 직전인지, 현재 데이터 기준일과 알려진 한계를 자세히 기록>"
git push origin savepoint-before-<phase>-20260901
```

### 2) 코드 검증

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\<관련테스트>.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

JavaScript를 수정했다면:

```powershell
node --check src\kr_quant\web\static\app.js
```

### 3) 로컬 런타임 검증

```powershell
.\Start-KR-Quant.bat
```

확인 API:

- `GET http://127.0.0.1:8790/api/status`
- `GET http://127.0.0.1:8790/api/jobs`
- `GET http://127.0.0.1:8790/api/scheduler`
- `GET http://127.0.0.1:8790/api/publish/status`
- `GET http://127.0.0.1:8790/api/system/spec`

### 4) 실데이터 검증

- 기대 KRX 거래일과 실제 최대 거래일 비교
- 거래상태 스냅샷 기준일 일치
- DART 분자/분모/상태 합계 재현
- 퀀트 랭킹 기준일 일치
- 위험/거래불가 종목이 후보에 없는지 확인
- 수정 전후 적격 종목 수와 제외 이유 diff 저장
- 공개 배포 readiness만 확인한 뒤 통과 시에만 배포

### 5) Git 마감

```powershell
git diff --check
git status --short
git add <이번 단계 파일만 명시>
git commit -m "<단계별 상세 메시지>"
git push origin main
```

완료 태그에도 구현 내용, 테스트 수, 실데이터 기준일, 남은 한계를 상세히 기록한다.

---

## 13. 전 메뉴 회귀 체크리스트

### Quant

- TOP20/30/50/100 표가 빈 화면 없이 동일 데이터 계약 사용
- 점수 구성은 항목별 기여도와 결측을 이해할 수 있게 표시
- 종목명/코드 검색과 자동완성, 마우스 선택이 동작
- 상세 서랍의 회사·가격·재무·기술 자료 기준일 일치

### 시장·업종

- 시장 국면 최종 점수가 구성요소 합으로 재현
- 업종·섹터 데이터 표본과 미분류 비중 표시
- 각 차트에 source/as_of/observed_at/limitation 존재

### 스마트 수급·타점

- 메이저 수급·쌍끌이·빈집·기술 필터 통합 동작
- KIS와 Toss 분류를 혼동하지 않음
- 기금과 국민연금을 혼동하지 않음
- 호버 날짜별 행과 설정기간 합계가 읽기 쉬움
- 공급자 미지원 종목을 다른 코드로 변환하지 않음

### 시즌 모멘텀·캘린더

- 대시보드 TOP3와 같은 조건의 메뉴 순위 일치
- “오늘”과 과거 진입창을 혼동하지 않음
- 현재가→과거 분포상 피크까지의 기대치는 P50/P90 등 통계로 표시
- 특수 이벤트 프리셋은 월 필터와 독립적으로 동작
- AI 코멘트는 종목별 실제 근거가 다름

### 전략·백테스트

- 긴 전략명이 잘리지 않음
- 전략 규칙, 검증 구간, 비용, 거래 수, MDD, 샤프를 풀어서 설명
- 거래 수 부족/낮은 신뢰도는 결론 보류
- 현재 TOP20 소급 연구 한계를 표시

### 실행·배포

- 사용자는 기본적으로 스마트 실행 하나만 누르면 됨
- 필요한 작업이 없으면 실제로 아무 수집도 하지 않음
- 부분 완료와 실패와 안전 차단을 구분
- 공개판과 로컬판 기준일 불일치를 명확히 표시

---

## 14. 하지 말아야 할 구현

- `git reset --hard`, 광범위한 사용자 파일 삭제
- `.agents/`, 루트 `output/`, `.env` 커밋
- KRX가 늦다는 이유로 Yahoo/Toss 종가를 Quant 정본에 넣기
- 배포 차단을 해제해 stale/partial 데이터를 최신이라고 공개
- alphanumeric 코드를 숫자로 강제 치환
- 가격 점프를 근거 없이 분할/배당으로 확정
- 현재 상장 종목만으로 만든 과거 결과를 생존편향 통제 완료라고 표시
- API 실패를 가짜 데이터/0/일반 AI 문구로 채우기
- `FUND`를 국민연금으로 번역
- LLM이 Quant 점수 또는 순위를 수정
- Windows Defender나 AdGuard를 끄는 설치/실행 스크립트
- KIS 토큰을 로그·파일·응답에 평문 저장
- 자동 주문 기능 추가

---

## 15. 전체 완료 정의

후속 보완이 “완료”라고 말하려면 최소 아래를 만족해야 한다.

1. 종목 식별자가 공급자 사이에서 오염되지 않는다.
2. 스마트 실행은 필요한 단계만 실행하고 중단 후 이어진다.
3. KRX 자료 미준비는 실패나 성공으로 뭉개지지 않고 제한 재시도된다.
4. DART 진행률이 시도/응답/사용 가능 재무를 구분한다.
5. 마지막 공개 성공과 현재 로컬 동기화 상태가 구분된다.
6. 같은 실행의 최신 산출물을 API가 한 세대로 일관되게 읽는다.
7. KIS 토큰이 사용자 동작 없이 반복 발급되지 않는다.
8. 공식 기업행위가 없으면 가격 단절을 계속 보수적으로 격리한다.
9. PIT 원천이 없으면 생존편향 통제를 주장하지 않는다.
10. 시장·수급·계절성·AI 설명은 출처·날짜·표본·한계를 가진다.
11. 전 메뉴 핵심 E2E와 전체 pytest가 통과한다.
12. 공개 산출물에 비밀정보가 없다.
13. 단계별 커밋·태그·실데이터 검증 기록으로 롤백 가능하다.

---

## 16. 첫 작업 권고

Grok Build가 처음부터 모든 P0를 동시에 구현하지 않도록 한다.

첫 회차는 아래 두 질문에 대한 증거 수집과 P0-1만 처리하는 것이 안전하다.

1. 알파벳 포함 KRX 단축코드가 실제로 어느 `security_type`에 속하며 OpenDART/KIS/Toss가 각각 지원하는가?
2. 현재 코드가 그 식별자를 어떤 경로에서 숫자 코드로 오염시키는가?

그 결과를 표로 남긴 뒤 중앙 식별자 계약과 테스트를 구현한다. 다음 회차에 P0-2 상태 머신으로 넘어간다.

이 순서가 중요한 이유는 실행 자동화를 더 강화하기 전에 잘못된 종목 코드로 수급·재무를 자동 적재할 가능성을 먼저 제거해야 하기 때문이다.
