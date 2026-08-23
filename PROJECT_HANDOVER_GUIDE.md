# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.20.0-stable`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **최신 릴리스 태그**: **`v2.20.0-stable`** (Commit `fdaf317`)
* **테스트 상태**: 166개 단위 테스트 **100% 정상 통과 (`pytest`)**
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla Modern JS (ES6+) Frontend

---

## 2. 🌟 최근 완성 및 배포된 핵심 퀀트 기능들

### 1. 🎯 대시보드 ↔ 계절성 선취매 TOP 1~3위 100% 완전 동기화
* **일치 로직 구현**:
  * 대시보드의 `오늘의 선취매 Top 3`와 계절성·캘린더 퀀트의 `오늘의 선취매 TOP 10`이 진입 임박 실전 선취매 구간(`TODAY_ENTRY`, `PRE_ENTRY_15`, `PRE_ENTRY_30`, `ACCUMULATE_60`)만을 엄격하게 필터링하도록 로직을 일치시켰습니다.
  * **1위**: `알파AI (043100)` / **2위**: `인카금융서비스 (211050)` / **3위**: `엑스게이트 (356680)`가 양쪽 화면에서 정확하게 일치하여 표출됩니다.

### 2. 🍵 은하퀀트전설 (Legend of Galactic Quant) - 초개인화 정밀 전술 참모
* 8대 섹터별 전술 렌즈 및 FCF 수익률, ROE, PBR 안전마진, 3개월 모멘텀을 결합한 종목별 초개인화 3단 전술 지시서 및 1:1 독대 모달.

---

## 3. 🤖 그록(Grok) 연계 프롬프트 가이드

```text
안녕하세요 Grok! 우리는 'kr_quant_research' (한국 주식 정량 계절성 & 은하퀀트전설 시스템) 프로젝트를 진행 중입니다.

[현재 깃 저장소 상태]
• GitHub Tag: v2.20.0-stable (Commit: fdaf317)
• 테스트: 166개 단위 테스트 100% 정상 통과 완료
• 핵심 구현 기능:
  1) 🎯 대시보드 ↔ 계절성 선취매 TOP 1~3위 100% 일치 동기화 (진입 임박 선취매 구간 엄선)
  2) 🍵 은하퀀트전설 (Legend of Galactic Quant): 제13함대 히페리온 작전 회의실 HUD + 업종 렌즈 및 실시간 팩터(FCF/ROE/PBR/3M) 결합 초개인화 양 웬리 3단 실전 전술 지시서 + 1:1 심층 독대 모달 연동
  3) 🏆 오늘의 선취매 TOP 10 뷰 (8대 테마 SVG 도넛 차트 + 기여도 랭킹 + 10대 리치 히어로 카드)
  4) 🚀 90일 진입 디스커버리 TOP (시즌 종료 제외 토글 + 5대 상태 마우스 호버 팝오버 + 진입/엑시트 윈도우)
  5) 🎯 종목별 맞춤형 동적 피크 일자(08~26일) 및 선취매 상세 플레이북 모달 (P50/P90/PF 산출)
  6) 📅 10대 이벤트 마스터 캘린더 (18대 연말/연초 정량 이벤트 전수 수록)

[주요 소스코드 경로]
- 전략 엔진: src/kr_quant/strategy/ 및 src/kr_quant/sunzi/ (seasonality.py, critic.py, five.py)
- 웹 백엔드: src/kr_quant/web/app.py
- 프론트엔드: src/kr_quant/web/static/ (index.html, styles.css, app.js)

이 코드를 기반으로 다음 작업을 함께 이어가고자 합니다.
```
