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

### 1. 🎯 UI/UX 전면 개선 (v2.23‑v2.32)
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
