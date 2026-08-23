# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.18.0-stable`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **최신 릴리스 태그**: **`v2.18.0-stable`** (Commit `a6f5095`)
* **테스트 상태**: 166개 단위 테스트 **100% 정상 통과 (`pytest`)**
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla Modern JS (ES6+) Frontend

---

## 2. 🌟 최근 완성 및 배포된 핵심 퀀트 기능들

### 1. 🍵 은하퀀트전설 (Legend of Galactic Quant) - 양 웬리 실전 전술 참모
* **제13함대 기함 *히페리온* 작전 회의실 UI/UX**:
  * 양 웬리 제독의 실시간 전황 브리핑 카드 (`🍵 홍차 브리핑 준비 완료 · 브랜디 한 방울`)
  * 손자 五事(道·天·地·將·法) 거시 전황 측정계 레이더 바
  * 5대 전략 태세(`🟢 ENGAGE`, `🟡 WAIT`, `🟣 OBSERVE`, `🟠 RETREAT`, `🔴 AVOID`) 원클릭 인터랙티브 필터
* **종목 맞춤형 3단 실전 전술 지시서 엔진 (`src/kr_quant/sunzi/critic.py`)**:
  * 🔭 **전황 분석 (Battlefield Assessment)**: 회사 장부(道)의 진실과 팩터 건전성 평가
  * 💡 **양 웬리의 기책 & 진입 타점 (Tactical Maneuver & Entry)**: 손자병법 전술 태세 및 분할 진입/관망 지침
  * 🚪 **퇴로 확보 & 무효화 조건 (Disengagement & Escape Route)**: 손절선, 리스크 플래그, 퇴각 기준
  * 📜 **한 줄 참모 총평 (One-line Strategic Insight)**: 위트와 혜안이 담긴 명구
  * ⚔️ **손자병법 6대 전략 뱃지** (`先勝求戰`, `以逸待勞`, `風林火山·靜`, `知彼知己`, `避實擊虛`, `全軍退路`)
* **`양 웬리 제독의 1:1 심층 작전 지시서 (Private Briefing)` 모달**:
  * 종목 클릭 시 손자 5사 정밀 점검표 및 반대 논리, 기다림의 득실 분석 팝업 연동.

### 2. 🏆 오늘의 선취매 추천 TOP 10 뷰 (`#pane-v11-pre-entry`)
* 8대 핵심 계절성 테마의 수익 기여도(%) SVG 도넛 차트 및 대형 히어로 카드.

### 3. 🚀 90일 진입 디스커버리 TOP (`#pane-v11-discovery`)
* `[☑️ 시즌 종료 제외 (진입 유효만)]` 토글 버튼 및 5대 상태 실시간 마우스 호버(Hover) 팝오버.

---

## 3. 🤖 그록(Grok) 연계 프롬프트 가이드 (복사해서 바로 사용 가능)

```text
안녕하세요 Grok! 우리는 'kr_quant_research' (한국 주식 정량 계절성 & 은하퀀트전설 시스템) 프로젝트를 진행 중입니다.

[현재 깃 저장소 상태]
• GitHub Tag: v2.18.0-stable (Commit: a6f5095)
• 테스트: 166개 단위 테스트 100% 정상 통과 완료
• 핵심 구현 기능:
  1) 🍵 은하퀀트전설 (Legend of Galactic Quant): 제13함대 히페리온 작전 회의실 HUD + 양 웬리 종목 맞춤형 3단 실전 전술 지시서(전황 분석/기책 타점/퇴로 확보) + 1:1 심층 독대 모달 연동
  2) 🏆 오늘의 선취매 TOP 10 뷰 (8대 테마 SVG 도넛 차트 + 기여도 랭킹 + 10대 리치 히어로 카드)
  3) 🚀 90일 진입 디스커버리 TOP (시즌 종료 제외 토글 + 5대 상태 마우스 호버 팝오버 + 진입/엑시트 윈도우)
  4) 🎯 종목별 맞춤형 동적 피크 일자(08~26일) 및 선취매 상세 플레이북 모달 (P50/P90/PF 산출)
  5) 📅 10대 이벤트 마스터 캘린더 (18대 연말/연초 정량 이벤트 전수 수록)

[주요 소스코드 경로]
- 전략 엔진: src/kr_quant/strategy/ 및 src/kr_quant/sunzi/ (critic.py, five.py, alignment.py)
- 웹 백엔드: src/kr_quant/web/app.py
- 프론트엔드: src/kr_quant/web/static/ (index.html, styles.css, app.js)

이 코드를 기반으로 다음 작업을 함께 이어가고자 합니다.
```
