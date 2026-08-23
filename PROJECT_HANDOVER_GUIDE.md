# 🚀 KR Quant Research - 프로젝트 인수인계 & 그록(Grok) 연계 가이드 (`v2.16.0-stable`)

## 1. 📌 현재 프로젝트 상태 요약
* **저장소 (GitHub)**: `https://github.com/loliRuriruri/kr_quant_research.git`
* **최신 릴리스 태그**: **`v2.16.0-stable`** (Commit `04a5b35`)
* **테스트 상태**: 166개 단위 테스트 **100% 정상 통과 (`pytest`)**
* **실행 환경**: Python 3.12 (Virtualenv: `.venv`), FastAPI Backend, Vanilla Modern JS (ES6+) Frontend

---

## 2. 🌟 최근 완성 및 배포된 핵심 퀀트 기능들

### 1. 🏆 오늘의 선취매 추천 TOP 10 뷰 (`#pane-v11-pre-entry`)
* **도넛 차트 (`#theme-donut-svg`)**: 8대 핵심 계절성 테마의 수익 기여도(%) 시각화 및 원클릭 슬라이스 필터링.
* **8대 테마 랭킹 카드 (`#theme-ranking-list`)**: 테마별 기대수익, 승률, 👑 대표 대장주 및 촉매 이벤트 표출.
* **10대 대형 히어로 카드 (`.pre-entry-card`)**:
  * 🥇 1~10위 골드/실버/브론즈 뱃지
  * 5대 핵심 KPI (5년 평균수익률, 5년 승률(노란색 강조), 초과알파, 5년 MDD, 손익비 PF)
  * **진입 권장 vs 목표 엑시트 타이밍 스트립** (`📈 진입: MM/DD ~ MM/DD  ➔  목표 엑시트: MM/DD ~ MM/DD`)
  * 연도별 실측 트랙레코드 칩 바 (`'21 +12%` `'22 +18%` ...)
  * 💡 AI 핵심 투자 촉매 & 모멘텀 요약 박스
  * `[상세 플레이북 ➔]` 및 `[📊 시뮬레이터 연동]` 버튼

### 2. 🚀 90일 진입 디스커버리 TOP (`#pane-v11-discovery`)
* **`[☑️ 시즌 종료 제외 (진입 유효만)]` 토글 버튼**: 피크가 이미 통과된 `SEASON_END` 종목을 원클릭으로 제외/포함.
* **`[ℹ️ 상태 가이드]` 버튼 & 실시간 마우스 호버(Hover) 팝오버**: 상태 뱃지에 마우스를 올리면 5대 상태(`🟢 ACTIVE`, `🟡 WATCH`, `🟣 DISCOVERY`, `🟠 WEAKENING`, `🔴 BROKEN`)의 판정 조건과 실전 매매 대응 가이드가 플로팅 팝업으로 즉각 표출.
* **깔끔한 테이블 레이아웃**: 글자 수가 잘리던 AI 설명 열을 제거하고, 종목명/티커/시장 뱃지 및 진입/엑시트 일정 스트립을 시원하게 확대.

### 3. 🎯 일(Day) 단위 동적 피크 일자 & 정밀 플레이북 모달 (`#discovery-detail-modal`)
* 종목별 고유 피크 일자(`08일 ~ 26일`) 자동 산출 및 맞춤형 진입/엑시트 윈도우.
* P50 기대수익률, P90 낙관 기대치, 손익비(PF), 실패 연도 원인 분석 및 무효화 조건 표출.

### 4. 📅 10대 정량 이벤트 마스터 캘린더 (`#pane-v11-calendar`)
* 180일/365일 연말·연초 18대 주요 퀀트 이벤트(10월 ESMO/실적, 11월 난방/광군제/지스타, 12월 배당/KOSPI200/대주주양도세, 1월 산타/CES/JPMHC/갤럭시) 전수 수록.

---

## 3. 🛠️ 핵심 소스코드 구조 및 아키텍처

```
kr_quant_research/
├── src/kr_quant/
│   ├── strategy/
│   │   ├── discovery_engine.py      # 종목별 계절성 점수, 일 단위 피크일자(08~26일), 진입/엑시트 윈도우, 플레이북 생성
│   │   ├── theme_engine.py          # 8대 테마 정의, 후보 종목 매핑, 수익 기여도(Weight Share %) 산출
│   │   ├── seasonality.py           # 10년치 DB 빌드, 90일 디스커버리 스캔 (exclude_expired 지원)
│   │   ├── event_calendar.py        # 10대 정량 이벤트 카탈로그 (18개 연말/연초 이벤트)
│   │   └── event_explainer.py       # AI 인과성 역추적 및 실패 연도 분석
│   ├── web/
│   │   ├── app.py                   # FastAPI 라우터 (/api/seasonality/discovery, /api/seasonality/themes 등)
│   │   └── static/
│   │       ├── index.html           # 대시보드 UI 마크업, 5대 서브탭, 모달 컨테이너
│   │       ├── styles.css           # 다크 테마, 글래스모피즘 팝오버, 히어로 카드 스타일
│   │       └── app.js               # 프론트엔드 라우팅, SVG 도넛 차트 렌더러, 팝오버 이벤트
└── tests/unit/
    ├── test_seasonality_discovery.py
    ├── test_theme_engine.py
    └── test_web_app.py
```

---

## 4. 🤖 그록(Grok) 연계 프롬프트 가이드 (복사해서 바로 사용 가능)

```text
안녕하세요 Grok! 우리는 'kr_quant_research' (한국 주식 정량 계절성 & 캘린더 퀀트 시스템) 프로젝트를 진행 중입니다.

[현재 깃 저장소 상태]
• GitHub Tag: v2.16.0-stable (Commit: 04a5b35)
• 핵심 구현 기능:
  1) 오늘의 선취매 TOP 10 뷰 (8대 테마 SVG 도넛 차트 + 기여도 랭킹 + 10대 리치 히어로 카드)
  2) 90일 진입 디스커버리 TOP (시즌 종료 제외 토글 + 5대 상태 마우스 호버 팝오버 + 진입/엑시트 윈도우)
  3) 종목별 맞춤형 동적 피크 일자(08~26일) 및 선취매 상세 플레이북 모달 (P50/P90/PF 산출)
  4) 10대 이벤트 마스터 캘린더 (18대 연말/연초 정량 이벤트)
• 전체 166개 단위 테스트 100% 통과 완료 상태입니다.

이 코드를 기반으로 다음 작업을 함께 이어가고자 합니다.
```
