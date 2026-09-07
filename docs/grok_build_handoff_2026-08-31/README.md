# Grok Build 후속 작업 인계 패키지

작성 기준: 2026-08-31 KST  
대상 저장소: `C:\Users\a4jud\kr_quant_research`  
원격 저장소: `https://github.com/loliRuriruri/kr_quant_research`

이 폴더는 2026-08-31까지 Codex에서 진행한 데이터 무결성·백테스트·근거 계약·스마트 실행 파이프라인 작업 이후, Grok Build가 안전하게 이어서 보완하기 위한 최신 인계 패키지다.

## 읽는 순서

1. `GROK_BUILD_REMAINING_WORK.md`
   - 현재 구현과 실제 데이터 상태
   - 남은 결함과 위험도
   - P0~P3 구현 순서
   - 수정 대상 파일과 완료 조건
   - 회귀 테스트·배포·롤백 원칙
2. `GROK_BUILD_START_PROMPT.md`
   - Grok Build 대화에 그대로 붙여 넣을 시작 지시문

## 중요

- 기존 `docs/GROK_BUILD_HANDOFF.md`는 2026-08-21 시점의 문서라 테스트 수와 구현 상태가 오래되었다.
- 이 폴더의 문서가 **2026-08-31 이후 후속 작업의 우선 기준**이다.
- 이 문서는 자동매매 또는 매수·매도 추천 기능을 요구하지 않는다.
- `.env`, 토큰, API 키 원문은 어떤 문서·로그·공개 스냅샷에도 넣지 않는다.

