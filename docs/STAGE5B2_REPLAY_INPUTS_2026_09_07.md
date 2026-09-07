# 5B-2: 명시적 시점과 공통 순위 함수 연결

작업 전 저장점: `4d0a881`. 이번 작업은 **준비된 과거 입력의 순위 재현 기반**이며 실제 선취매 전체 OOS 완료가 아니다.

## 구현

1. `discovery_engine.pattern_from_month_stat`에 이미 있던 `as_of_date`를 실제로 사용한다. 명시적으로 지정한 경우 PC 현재 연도가 아니라 해당 한국 날짜를 기준으로 계산한다. 해당 월의 달력상 말일이 기준일보다 이전인 관측만 남긴 뒤 lookback을 적용한다. 같은 달 말일도 공개시각이 불명확하므로 보수적으로 제외한다.
2. 과거 경로에서는 연도 없는 `history` 배열에 연도를 임의 배정하지 않고 오류로 반환한다. 중복 연도와 비유한/결측 수익률도 거절한다. 미래 연도의 수익률을 바꾸거나 추가해도 기존 과거 결과는 같아야 한다. 이는 가격 관측 월 필터이며 공시 공개시각·거래일 검증은 별개다.
3. 기존 선취매 순위 로직을 `strategy/pre_entry_ranking.py`의 입력 전용 함수로 그대로 분리했다. 생산 `rank_pre_entry_candidates`는 기존 최신 시세/적격 자료를 읽은 다음 이 함수를 호출한다. 단계 가중치·점수·피크 중앙값·종목/패턴 ID 정렬, 1,000원 미만 제외, 피크 미확보 제외 규칙을 변경하지 않았다.
4. `research/pre_entry_replay.replay_prepared_ranking`은 후보·적격 여부·시세의 3개 스냅샷을 명시적으로 전달받는다. 최신 파일 fallback이 없다. 5B-1 계약에 연결하여 미래 시각·출처 누락 등을 차단하고 실제 JSON payload 해시도 대조한다. 모델 ID, 판단시각, 시장 기준일, 종목별 자료 누락/중복, 피크 기준일을 검사한다.
5. 과거 재현 어댑터는 판단일보다 이전 시장 기준일만 허용한다. 장중/같은 날 종가 재현은 지원하지 않는다. 정상도 `PREPARED_INPUT_RANK_REPLAY / RANKED_UNVERIFIED / verified=false`로 반환한다. 메타데이터 자체의 진실성이나 제공된 유니버스의 역사적 완전성은 자동 인증하지 않는다.

## 검증

- 관련 테스트 **102 passed / 19.94초**. 신규 시점/재현 검사는 미래 자료 변경 불변성, 월말/연말, 날짜 없는 자료, 중복·결측·출처·해시·기준일 불일치, 정지 종목 제외, 현재 자료 읽기 금지, 생산 어댑터 일치 등을 검사한다.
- `4d0a881`의 이전 순위 함수 AST를 직접 불러왔다. 같은 실제 원천과 저장된 전체 4,451패턴을 이전/새 함수에 전달했을 때 **218개 후보의 반환값 전체 일치**, 입력 자료 불변 확인.
- 동일 데이터에 대한 리팩터링 동등성이지 투자 성과의 통계적 인증은 아니다. 과거 유니버스/정정 공시 완전성은 5B-1에서 확인한 제한이 남아 있다.
- JS/UI 수정 없음. 현재 점수·등급 배점·매매 규칙·사용자 포트폴리오 변경 없음. 원천 수집 API/키 발급/주문 호출 없음.
- 모델 코드 해시에 새 공통 순위 모듈이 자동 포함된다. 코드 변경으로 달라진 세대에 맞춰 기본 5년 및 전체 기간 조회 저장본을 준비했다. 세대 ID는 HANDOFF에 기록한다. 운영 서버 재시작·push·공개 배포는 하지 않았다.

## 입력 형식

각 스냅샷은 `metadata`와 `payload` 객체로 구성한다.

- metadata: input(candidates/eligibility/quotes), partition_id, available_at, effective_end, provenance_ref, sha256.
- payload: decision_at(시간대 포함), market_date(YYYY-MM-DD), rows. candidates에는 model_id가 추가로 필요하다.
- metadata.sha256은 `payload_hash(payload)` 결과여야 한다. 출처와 해시를 임의로 채운다고 실제 PIT 증거가 되는 것은 아니다.
- candidates.rows: 기존 생산 후보 필드(ticker, pattern_id, entry_stage, seasonality_score, remaining_peak).
- eligibility.rows: ticker, eligible(bool). 미확인은 false로 임의 변환하지 않고 거절한다.
- quotes.rows: ticker, last_close, as_of, 선택 chg_pct. 후보마다 해당 기준일 자료를 요구한다.

검사 재현:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_pre_entry_replay.py tests/unit/test_pit_readiness.py tests/unit/test_seasonality_discovery.py tests/unit/test_season_snapshot.py tests/unit/test_season_listing.py tests/unit/test_season_holdout.py tests/unit/test_selection_tracking.py tests/unit/test_failure_observations.py -q
```

## 아직 안 된 것 / 다음 작업

이번 연결은 **후보 생성 전체가 아니라 시점별 월 패턴 필터와 준비된 후보의 최종 순위**에 한정된다. 당시 재무 점수·수급·이벤트 지식·피크를 생산 코드로 생성하는 전체 과거 입력 어댑터는 아직 없다. 이것 없이 5B-3 전체 OOS 완료로 넘어가면 안 된다.

다음은 확보된 원천의 기간을 바탕으로 과거 입력 생성기를 연결하고, 없는 입력은 명시적으로 차단하는 일이다. 이벤트 신뢰도가 시즌 점수에 들어가므로 당시 지식 버전이 없을 때 현재 지식으로 대체하지 않는다. 수정주가/기업행위·정지/상폐 이력·비용 증거와 실제 관측 장부도 별도로 필요하다.

큰 잔여 묶음은 여전히 ① 선정 신뢰성 ② 성능·실시간 ③ 최종 연동·복구·배포 검사다. 다음 작업이 단순 UI 수정만 남았다는 의미는 아니다.
