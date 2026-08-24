# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.30.0-stable`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **최신 릴리스 태그**: **`v2.30.0-stable`** (Commit will be created by this save)
* **테스트 상태**: 166개 단위 테스트 **100% 정상 통과 (`pytest`)**
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla Modern JS (ES6+) Frontend

---

## 2. 🌟 최근 완성 및 배포된 핵심 퀀트 기능들

### 1. 🎯 UI/UX 전면 개선 (v2.23‑v2.29)
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
• GitHub Tag: v2.30.0-stable (Commit: <to‑be‑filled>)
• 테스트: 166개 단위 테스트 100% 정상 통과 완료
• 핵심 구현 기능:
  1) UI/UX 전면 개선 (flow, investor, empty, trade, 툴팁, 기술 배지)
  2) 호버 오버레이 툴팁 복구 및 기술 신호 팝업 정상화
  3) 화면 폭 축소 시 UI 클리핑 완화
  4) 기존 핵심 퀀트 로직 유지 (대시보드·선취매·전략 엔진)

[주요 소스코드 경로]
- 전략 엔진: src/kr_quant/strategy/ 및 src/kr_quant/sunzi/ (seasonality.py, critic.py, five.py)
- 웹 백엔드: src/kr_quant/web/app.py
- 프론트엔드: src/kr_quant/web/static/ (index.html, styles.css, app.js)
```
