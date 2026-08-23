# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.17.0`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **작업 폴더**: `C:\Users\a4jud\kr_quant_research`
* **기준 태그**: **`v2.16.2-stable`** (Commit `2df84ed`) — Windows WinError 10022 패치까지 배포된 안정본
* **이번 세션 작업**: 인수인계 문서 정합 + 계절성 검수 수정 + 안드로이드 Glance Top 3 / 전종목 시장 구분 이식 (`v2.17.0`) → 손자 五事·반대심문 탭 복구 (`v2.17.1`)
* **테스트 상태**: 단위 테스트 100% 통과 (`pytest`)
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla Modern JS (ES6+) Frontend
* **태그 이력**: `v2.16.0-stable` (`04a5b35`) → `v2.16.1-stable` (`bfc1f18`) → `v2.16.2-stable` (`2df84ed`) → **`v2.17.0`**

---

## 2. 🌟 핵심 퀀트 기능 (유지)

### 1. 🏆 오늘의 선취매 추천 TOP 10 뷰 (`#pane-v11-pre-entry`)
* 도넛 차트, 8대 테마 랭킹, 10대 히어로 카드, 진입/엑시트 스트립, 연도별 트랙레코드, 플레이북/시뮬레이터 버튼.

### 2. 🚀 90일 진입 디스커버리 TOP (`#pane-v11-discovery`)
* 시즌 종료 제외 토글, 5대 상태 호버 팝오버, 진입/엑시트 윈도우.

### 3. 🎯 동적 피크 일자 & 플레이북 모달 (`#discovery-detail-modal`)
* 종목별 피크일 `08~26일`, P50/P90/PF, 실패 연도·무효화 조건.

### 4. 📅 10대 정량 이벤트 마스터 캘린더 (`#pane-v11-calendar`)
* 180/365일 연말·연초 18대 이벤트.

### 5. 🪟 Windows 비동기 소켓 안정화 (`src/kr_quant/web/app.py`)
* `ProactorBasePipeTransport._call_connection_lost` 패치 (`WinError 10022`).

---

## 3. 🔎 v2.16.2 검수에서 발견한 문제와 v2.17.0 수정

| 검수 항목 | 문제 | 수정 |
|---|---|---|
| 인수인계 문서 | `v2.16.0` / `04a5b35`로 고정 | 실제 태그 `v2.16.2`와 이번 작업 `v2.17.0` 반영 |
| 캐시 버스터 / 푸터 | `?v=2.16.0`, 푸터 `v1.3 Engine` | `?v=2.17.0`, 푸터 `v2.17 Engine` |
| 12개월 히트맵 | 행 클릭이 `discoveryRows`를 참조해 모달이 안 열림 | `seasonalityRows` + `data-index` + `openHeatmapPlaybook()` |
| AI 역추적 탭 | 기간/건수 맥락 없음 | 룩백·진입 윈도우·상위 30건 헤더 표시 |
| 시장 구분 | 시세에 KOSDAQ이 있는데 전 종목 `KOSPI` | `ticker_meta_map()`으로 캐시/디스커버리 시장 오버레이 |
| 대시보드 Glance | `#dash-seasonality-banner`가 비어 있음 | 안드로이드 Glance Top 3와 같은 선취매 3종 + 전종목 스캔 카운트 |

전종목 커버리지 (시세 parquet 기준):
* 상장 시세 유니버스 약 **2,978종** (KOSPI + KOSDAQ)
* 계절성 스캔 캐시 약 **2,368종** (월별 표본 6개월 미만은 제외)

---

## 4. 🛠️ 핵심 소스코드 구조

```
kr_quant_research/
├── src/kr_quant/
│   ├── strategy/
│   │   ├── discovery_engine.py      # 종목별 계절성 점수, 일 단위 피크일자, 플레이북
│   │   ├── theme_engine.py          # 8대 테마, 수익 기여도
│   │   ├── seasonality.py           # 전종목 DB, 시장 오버레이, Glance Top 3, exclude_expired
│   │   ├── event_calendar.py        # 10대 정량 이벤트 카탈로그
│   │   └── event_explainer.py       # AI 인과성 역추적
│   ├── web/
│   │   ├── app.py                   # FastAPI, WinError 10022 패치, /api/seasonality/*
│   │   └── static/
│   │       ├── index.html           # 대시보드 + 5대 서브탭 + Glance 배너
│   │       ├── styles.css           # 다크 테마, Glance 카드
│   │       └── app.js               # 도넛, 팝오버, Glance Top 3, 히트맵 플레이북
└── tests/unit/
    ├── test_seasonality.py
    ├── test_seasonality_discovery.py
    ├── test_seasonality_highlights.py
    ├── test_theme_engine.py
    └── test_web_app.py
```

---

## 5. 🤖 그록(Grok) 연계 프롬프트 가이드

```text
안녕하세요 Grok! 우리는 'kr_quant_research' (한국 주식 정량 계절성 & 캘린더 퀀트 시스템) 프로젝트를 진행 중입니다.

[현재 깃 저장소 상태]
• 작업 폴더: C:\Users\a4jud\kr_quant_research
• 안정 태그: v2.16.2-stable (Commit: 2df84ed)
• 후속 작업: v2.17.0 (인수인계 정합, 히트맵 플레이북 클릭 수정, KOSPI/KOSDAQ 시장 구분, 대시보드 Glance Top 3)
• 테스트: 169개 단위 테스트 100% 통과
• 핵심 구현 기능:
  1) 오늘의 선취매 TOP 10 뷰 (8대 테마 SVG 도넛 + 기여도 랭킹 + 히어로 카드)
  2) 90일 진입 디스커버리 TOP (시즌 종료 제외 토글 + 5대 상태 호버 팝오버)
  3) 종목별 동적 피크 일자(08~26일) 및 선취매 플레이북 모달 (P50/P90/PF)
  4) 10대 이벤트 마스터 캘린더 (18대 연말/연초 이벤트)
  5) Windows 비동기 소켓 연결 해제 안정화 (WinError 10022)
  6) 대시보드 오늘의 선취매 Top 3 (안드로이드 Glance 대응) + 전종목 스캔 카운트
[주요 소스코드 경로]
- 전략 엔진: src/kr_quant/strategy/ (discovery_engine.py, theme_engine.py, seasonality.py, event_calendar.py)
- 웹 백엔드: src/kr_quant/web/app.py
- 프론트엔드: src/kr_quant/web/static/ (index.html, styles.css, app.js)

이 코드를 기반으로 다음 작업을 함께 이어가고자 합니다.
```
