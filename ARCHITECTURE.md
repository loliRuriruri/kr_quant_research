# 설계

두 제품을 이어붙이지 않고 역할을 나눴다.

## 점수 (Quant Scoring)

- Value 30 / Quality 25 / Growth 25 / Stability 10
- Momentum 10은 `enabled: true` (상장주식수·시총으로 분할만 보정, 배당 TR 아님)
- 런타임 설정은 `GET /api/system/spec` 이 설정 파일을 직접 읽는다
- TOP100 커버리지 80%, TOP20 90% + 영업이익·순이익·CFO 양수
- 재무 신선도 270일, CFS/OFS 혼합 금지
- 시장 국면·FRED·Yahoo·전략 샤프는 `used_in_quant: false`

## 데이터 및 정합성 계층 (Data & Integrity)

- 가격 정본: KRX Open API
- 재무: OpenDART TTM (`available_date <= run_date`)
- 공식 이벤트(`corporate_actions.parquet`)가 확정 행을 줄 때만 수정주가 산출 (설명되지 않은 가격 단절은 연결하지 않음)
- 거래정지/정리매매 필터: `krx_status.csv` 매칭 (`TRADING_HALTED` 등 적격성 제외)
- 보조: Toss 시세, 네이버 뉴스, FRED 거시, Yahoo 비교
- 매 실행일의 구성종목은 `universe_snapshot.parquet`와 `universe_evidence.json`으로 보존한다
- 상장일 이후·확인된 상장폐지일 이전만 PIT 적격으로 보되, 날짜가 없는 종목은 임의 제거하지 않고 커버리지 한계를 남긴다
- 현재 TOP20을 과거로 소급한 전략 결과는 횡단면 PIT 백테스트가 아니며 `LIMITED_CURRENT_COHORT`로 표시한다
- 데이터 저장은 원자적 교체(`atomic_io.py`: 임시 파일 작성 후 `os.replace`)를 통해 전원 꺼짐 시 파일 손상 방지

## 장시간 비동기 작업 관리 (Job Runner & Resilience)

- `JobRunner`: 단계별 진행률, 심장박동(Heartbeat), 경과 시간, 원자적 상태 파일(`job_history.json`)
- 사용자 요청 시 다음 단계 경계에서 안전하게 멈추는 Graceful Cancel 지원
- 비정상 종료된 프로세스는 다음 서버 실행 시 `dead_thread`로 자동 전환되어 영구 대기 상태 해소

## AI 리포트 근거 출처 계약 (Evidence Panel)

- LLM은 사실 설명을 돕는 역할만 수행하며 점수·순위·스크리너 필드를 일체 변경할 수 없음
- 생성된 텍스트의 각 문장은 인라인 인용 칩(`[1]`, `[2]`)과 연동
- 우측 슬라이드 인 근거 패널(Evidence Drawer)에서 해당 주장의 근거 지표값, 출처, 수집일시, 원천 텍스트 스니펫을 투명하게 제공

## 공개 정적 스냅샷 및 보안 (Public Snapshot & Reproducibility)

- 배포 전 이중 보안 가드(`verify_public_snapshot`): `.env`, 로그, 토큰, `.bat`, `.py` 등 금지 확장자 및 로컬 절대 경로(`C:\Users\...`) 스크러빙 검증
- 결정론적 JSON 내보내기(`sort_keys=True`): 동일 데이터셋에 대해 비트 단위 동일 SHA-256 해시 재현성 입증
- 메타데이터 분리: `build.json`에 `data_as_of`(데이터 기준일)와 `web_deployed_at`(웹 배포 시점)을 분리 표시

## 성능 가속 아키텍처 (Performance Optimization)

- Parquet 메타데이터 통계 스캔: `_read_price_max`에서 파일 본문 압축 해제 없이 푸터 통계로 신선도 2.5ms 판정
- Predicate Pushdown & Column Pruning: 600만 행 가격 테이블 로딩 시 필요한 종목(`tickers`)과 필수 열(`ticker, trade_date, close`)만 메모리에 적재
- 대형 테이블 점진적 청크 렌더링: 초기 100행 즉시 동기 주입 후 `requestIdleCallback` 비동기 스트리밍 (60fps 보장 및 토큰 기반 취소)

## 운영 자동화 및 프로세스 안전 (Windows Operations)

- 오프라인 누락 보충 (`_catch_up_due`): PC가 오프라인이어서 놓친 장 마감 수집을 서버 기동 시 감지하여 1회 자동 보충
- 포트 8790 소유권 검사: 무관한 프로세스를 강제 종료하지 않고 오직 `kr_quant` 프로세스만 안전하게 제어
- Windows 작업 스케줄러 스크립트(`install-task-scheduler.ps1`) 제공

## 전략 체결 연구

- 종가 신호는 다음 체결 가능한 거래일 시가에 실행한다
- 수수료·날짜별 매도세·슬리피지·거래대금 참여율 시장충격을 차감한다
- 거래량 0과 일봉상 상·하한가 한 가격 잠김은 미체결 처리한다
- 실시간 호가·잔량 재현이 아닌 일봉 프록시이며 주문 기능은 없다

## 메뉴 근거 계약

- 모든 주요 메뉴는 `contract_version`, `sources`, `as_of`, `observed_at`, `sample`, `calculation_state`, `used_in_quant`, `limitations`를 공통 형식으로 공개한다
- 로컬 `/api/status`와 공개 정적 스냅샷이 같은 근거 레지스트리를 사용한다
- 공개 배포는 대시보드·랭킹·스크리너의 핵심 근거 계약이 누락되거나 무효면 실패 폐쇄한다
- API 설정 계약은 로컬 전용이며 공개 스냅샷에서 제거한다

## 하지 않는 것

- 주문·잔고·체결
- LLM이 Quant 필드를 수정
- 결측 Factor 재정규화로 한 팩터 고점
- 원주가 모멘텀을 순위에 합산
- KRX 지연 시 비정규 출처 가격을 정본으로 교체
- 무관한 외부 프로세스 강제 종료
