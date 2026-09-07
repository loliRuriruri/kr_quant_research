# 과거 입력 버전 선택과 시즌 점수 연결

작업 전 저장점 `37bf6f7`. 재개 스킬로 이전 기록을 확인하고 입력 연결만 분리했다. 원천 수집, 공개 배포, 서버 재시작, 사용자 포트폴리오 및 현재 점수 배점 변경 없음.

## 이번 구현

- `research/historical_features.py`: financial_features / flow / event의 명시적 기록 중 판단 시점에 공개됐고 효력이 발생한 최신 버전을 선택한다. 동일 효력시각에서는 공개시각이 늦은 정정 버전을 선택한다. 판단 뒤의 기록은 payload를 사용하지 않는다.
- 시간대 포함 available_at/effective_at/valid_until, 출처, 데이터 해시를 요구한다. 중복 최신 버전, 만료, 결측, 잘못된 수치, 누락 입력은 BLOCKED. 최신 버전이 만료됐다고 과거 버전으로 되돌아가지 않는다.
- 제공받는 재무 특징은 quant_score/return_3m/volume_ratio, 수급은 foreign_net/institution_net이다. 누락을 0으로 채우지 않는다. 이벤트에는 common_event/secondary_event/confidence/invalidating_rules가 필요하다.
- 이전 단계의 명시적 시점 월 패턴 함수와 기존 `explain_and_score_pattern`을 연결한다. 패턴의 2개년/승률 50% 조건도 적용하고 미충족은 EXCLUDED로 남긴다.
- 기존 설명/점수 함수에 keyword-only `event_context`를 추가했다. 과거 문맥이 전달되면 현재 종목 지식베이스 및 업종 fallback을 사용하지 않는다. 정상은 `HISTORICAL_INPUT_UNVERIFIED` 설명 모드 및 `SCORED_UNVERIFIED / verified=false`다.
- 기본 운영 호출은 이전과 동일하다. 이 경로는 아직 UI 자동 후보 생성이나 전체 과거 재현에 연결하지 않았다.

## 입력 계약

기록은 ticker, kind, available_at, effective_at, valid_until, source, data, sha256을 가진다. sha256은 `pre_entry_replay.payload_hash(data)`와 같아야 한다. 각 시각은 시간대가 필요하다. source 문자열·해시가 존재한다는 것은 출처 진실성이나 실제 공개시각을 인증하지 않는다. 메타데이터 서명 검증은 별도 과제다.

`score_historical_pattern`에 기록, 종목 정보, 연도가 명시된 월별 history_records, decision_at, lookback_years를 전달한다. 성공 결과의 lineage에는 각 종류의 선택 시각·출처·해시를 남긴다. 입력 목록을 수정하지 않는다.

## 검증

- 신규 11개 포함 관련 **113 passed / 7.25초**. 미래 정정 불변성, 알려진 정정 선택, 만료 최신본의 과거 fallback 금지, 입력 누락/해시/시간대/중복/결측/이벤트 오류, 현재 지식베이스 읽기 금지, 입력 불변을 검사했다.
- 이전 커밋 설명 함수를 직접 실행해 3종목 × 2패턴 × 3현재 입력, 18개 조합에서 기본 호출 반환값 전체 일치를 확인했다. 첫 비교 명령은 PowerShell 인용 오류로 실행 실패했고, 인용을 수정한 비교 명령이 통과했다.
- 문법/공백 검사 통과. UI 파일 수정 없음. 새 모델 해시에 맞춰 기본/전체 조회 저장본을 준비했다. 수집 API 호출은 없다.

재현:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_historical_features.py tests/unit/test_pre_entry_replay.py tests/unit/test_pit_readiness.py tests/unit/test_seasonality_discovery.py tests/unit/test_season_snapshot.py tests/unit/test_season_listing.py tests/unit/test_season_holdout.py tests/unit/test_selection_tracking.py tests/unit/test_failure_observations.py -q
```

## 명확한 한계와 다음 작업

**원시 DART 공시에서 과거 Quant 점수를 생성하는 수집/계산기가 아니다.** 이미 계산된 과거 특징을 받는 어댑터다. 현재 저장본에는 수년간의 거래상태·수급·이벤트 버전이 확보되지 않아 이 검사만으로 실제 과거 후보 생성/OOS를 완료할 수 없다.

월별 가격 입력의 원천 해시·당시 공개 가능성, 피크 계산, 과거 유니버스/정지/상폐 이력, 수정주가·기업행위·체결 비용, 전체 스캔의 누락 분모 장부도 아직 별도 연결해야 한다. 현재 지식으로 빈 구간을 채운 과거 성과를 만들지 않는다.

다음은 확보 가능한 과거 원천을 이 계약으로 변환하는 읽기 전용 로더와 누락 장부를 연결하는 일이다. 공급되지 않는 과거 자료가 필요한 구간은 계속 미검증으로 남기고, 현재부터 기록되는 실제 선정 장부를 별도로 축적한다.
