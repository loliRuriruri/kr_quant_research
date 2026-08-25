# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.32.0-stable`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **최신 릴리스 태그**: **`v2.32.0-stable`**
* **공개 웹**: `https://korea-quant-research.pages.dev/` (Cloudflare Pages 읽기 전용 스냅샷. PC 꺼져 있어도 접속)
* **로컬 대시보드**: `Start-KR-Quant.bat` → `http://127.0.0.1:8790` (수집·백테스트·API 설정)
* **공개 웹 갱신**: `Start-KR-Quant-Public.bat` (로컬 계산본만 업로드, 키 미포함)
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla JS, Cloudflare Pages static snapshot

---

## 2. 🌟 최근 완성 및 배포된 핵심 퀀트 기능들

### 1. 🎯 UI/UX 전면 개선 (v2.23‑v2.38)
* **OpenRouter DeepSeek 모델 ID 정상화 및 AI 퀵 스위처 모달 연동**:
  - OpenRouter 공식 모델 ID (deepseek/deepseek-v4-flash-0731) 및 별칭 자동 변환 매핑 적용으로 리포트 생성 시 HTTP 400 에러 해결
  - 상단 우측 🤖 AI: ... 뱃지 및 리포트 작성 화면에서 바로 열리는 **AI 분석 모델 빠른 변경 팝업 모달 (#modal-llm-quick-switch)** 신설 (Google Antigravity / OpenRouter / DeepSeek / Grok 원클릭 전환)
* **API 연결 테스트 종합 결과 패널 UI 전면 개편 및 오류 정상화**:
  - 상단 즉시 표시 패널 #test-box-top 신설로 버튼 클릭 시 스크롤 없이 즉시 상태 확인 가능
  - KIS 1분당 토큰 발급 제한(EGW00133) 정상 처리, Grok AUTH 세션 인증 연동, Google Antigravity CLI 세션 인증 연동, 네이버 지도/텔레그램 선택 항목 완벽 대응
* **Google Antigravity CLI (gy) 세션 AUTH 신규 연동**: API 키 없이 Windows 터미널 gy 1회 로그인 세션(Windows Credential Manager 캐시)을 Python subprocess로 안전 호출하여 AI 심층 분석 실행. Grok AUTH 형태의 전용 카드 UI 제공.
* **OpenRouter 및 DeepSeek 최신 모델 라인업 전면 개편**: DeepSeek-V3, DeepSeek-R1, DeepSeek-Chat-0731, DeepSeek-VL2(비전), Qwen-2.5-VL-72B, Claude-3.7-Sonnet, Grok-2-Vision-1212 등 최신 비전·추론 모델 목록 최신화
* **글로벌 매크로 전 항목 실시간 동기화 & 원클릭 새로고침 완비**: ECOS 핵심 지표, 엔 캐리 모니터(USD/JPY 심볼 매칭 정상화 포함), 글로벌 바로미터 16대 자산군, ECOS·FRED 거시 펀더멘털 카드에 각각 [🔄 실시간 새로고침] 버튼 및 실시간 동기화 타임스탬프(HUD) 연동
* **종목 심층분석 팝업 전략 백테스트 연동 복구**: 종목 상세 모달 내 [🧪 전략 백테스트] 버튼 클릭 시 모달이 닫히고 4대 전략 백테스트 탭으로 부드럽게 이동하여 즉시 백테스트 실행
* **손자병법 오사(道·天·地·將·法) UI/UX 완성**: 5번째 카드 法 한자 및 아이콘(🛡️/⚠️) 통일, 주의/경고/탈락 시 빨간/주황색 하이라이트 발광 테두리 및 텍스트 강조, 중복 면책 문구(Quant에 넣지 않습니다 등) 전면 제거
* **전략검토 참모 다른 보기 정리**: NO_CLEAR_VARIANT_VIEW 코드 노출 제거 및 자연스러운 한글 대응 문구 적용
* **API 설정 원클릭 공개판 갱신·배포**: API 설정 화면에서 \Start-KR-Quant-Public.bat\ 실행기 없이 바로 [다시 갱신·배포] 버튼 클릭으로 백그라운드 스냅샷 빌드 및 Cloudflare Pages 배포, 실시간 진행 상태 HUD 및 [공개 사이트 열기] 버튼 제공
* **쌍끌이 수급 (view‑flow)** – 실시간 검색, KPI HUD 카드, 통합 툴바, 테이블 개선
* **메이저 수급 & 지분 (view‑investor)** – 카드 헤더, 칩 배지, 필터 컨트롤統一
* **빈집 발굴 (view‑empty)** – 검색·필터 레이아웃統一, KPI 카드, 컬러‑태그
* **트레이딩랩 (view‑trade)** – 레이아웃 및 툴바 일관성
* **호버 오버레이 툴팁 복구** – 모든 뷰와 KPI, 라벨에 `data‑tip` 적용, z‑index 상승
* **기술 신호 팝업 및 배지 아이콘統一** – `renderTechnicalChip` 도입, 아이콘·색상 일관성 확보
* **화면 폭 축소 시 클리핑 완화** – `white-space: nowrap` 및 flex 레이아웃 적용

### 2. 🛠️ 핵심 백엔드·전략 기능
* 대시보드 ↔ 계절성 선취매 TOP 1~3위 100% 동기화
* 은하퀀트전설 – 8대 섹터별 전술 렌즈 및 정밀 전술 지시서
* 오늘의 선취매 TOP 10 뷰, 90일 진입 디스커버리 TOP 등

---

## 3. 🤖 그록(Grok) 연계 프롬프트 가이드
```
안녕하세요 Grok! 우리는 'kr_quant_research' (한국 주식 정량 계절성 & 은하퀀트전설 시스템) 프로젝트를 진행 중입니다.

[현재 깃 저장소 상태]
• GitHub Tag: v2.32.0-stable
• 공개 웹: https://korea-quant-research.pages.dev/ (스냅샷, PC 오프라인 유지)
• 로컬: Start-KR-Quant.bat / 공개 갱신: Start-KR-Quant-Public.bat
• 핵심 구현 기능:
  1) Cloudflare Pages 읽기 전용 공개 스냅샷 (키·설정 UI 없음)
  2) 로컬 live/screen 후 공개 웹 자동/수동 배포
  3) 종목명 검색 자동완성, 전략 백테스트 확인창·로딩
  4) 기존 핵심 퀀트 로직 유지 (대시보드·선취매·전략 엔진)

[주요 소스코드 경로]
- 전략 엔진: src/kr_quant/strategy/ 및 src/kr_quant/sunzi/ (seasonality.py, critic.py, five.py)
- 웹 백엔드: src/kr_quant/web/app.py
- 프론트엔드: src/kr_quant/web/static/ (index.html, styles.css, app.js)
```
