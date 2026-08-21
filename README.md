# KR Quant Research 📈

> **한국 주식 퀀트 스코어링 & 글로벌 매크로·기관 수급·업종·13F 통합 인텔리전스 시스템**  
> GitHub Repository: [loliRuriruri/KR-Quant-Research](https://github.com/loliRuriruri/KR-Quant-Research)

---

## 🌟 주요 기능 (Key Features)

1. **⭐ 재무 팩터 퀀트 스코어링 (Quant Scoring)**
   - 시가총액·거래대금 조건을 통과한 코스피/코스닥 전 종목 대상 5대 팩터(가치, 퀄리티, 성장, 안정성, 모멘텀) 종합 평가.
   - 투명한 팩터 분해 바 차트 및 일봉 백테스트 전략 랩 제공.

2. **🔍 테마 스크리너 (Thematic Screener)**
   - 밸류에이션 저평가, 고성장주, 고배당 우량주, 턴어라운드 후보 등 목적별 정밀 스크리닝.
   - 퀀트 TOP 20 포함/제외 토글 지원 (숨은 진주 발굴).

3. **🌐 글로벌 매크로 & 계절성 분석 (Macro & Seasonality)**
   - **글로벌 자산군 바로미터**: 코스피, 코스닥, S&P 500, 나스닥, 닛케이 225, 환율(USD/KRW, USD/JPY, DXY), 원자재(금, WTI 유가, 구리), 암호화폐(비트코인, 이더리움) 실시간 시세 연동.
   - **거시경제 핵심 지표**: 한국은행 ECOS 및 미 연준 FRED 기반 기준금리, 한-미 기준금리차, 국고채 3년, 장단기 스프레드(10Y-2Y), CPI 물가지수, 실업률, M2 통화량.
   - **엔 캐리 트레이드 청산 위험 모니터**: USD/JPY 속도 및 미·일 금리차 기반 유동성 위기 감지.
   - **주식시장 30개년 역사적 계절성(Seasonality) 히트맵**: 1월~12월 월별 평균 수익률, 상승 승률(%) 및 현재 월 전술 진단.
   - 30초 실시간 자동 동기화(Live Sync) 및 즉시 새로고침 지원.

4. **🏛️ 메이저 수급 & 국민연금 지분 (Major Flow & NPS Holdings)**
   - **기관·외국인 수급 추적**: KIS Open API 기반 일별 기관/외인 순매수, 연속 순매수(Streak), 동반 매수(Double Buy), 방향 전환(Reversal) 탐지.
   - **국민연금 5% 대량보유 공시**: OpenDART 5% 이상 대량보유상황보고 기반 지분 변동, 신규 편입 및 비중 증감 추적.

5. **📊 업종·섹터 6축 분석 (Sector Momentum Leaderboard)**
   - KSIC 업종별 상대강도(RS), 상승 확산도(Breadth), 실적 성장률, 밸류에이션 종합 6축 랭킹.
   - 주도 업종 모멘텀 바 차트 및 원클릭 대표 종목 상세 분석 모달 연동.

6. **🇺🇸 미국 13F 슈퍼인베스터 시각화 (Superinvestor Portfolio)**
   - 워런 버핏(버크셔 해서웨이), 마이클 버리(사이온), 레이 달리오(브릿지워터) 등 글로벌 대가들의 분기별 Top 5 포트폴리오 비중 스택 바(Stack Bar) 차트.
   - 대가들의 신규 편입(New Buys) 및 전량 청산(Exits) 카드 제공.

---

## 🚀 빠른 시작 (Quick Start)

### 1. 설치 및 가상환경 구성
```powershell
# 1) 저장소 클론
git clone https://github.com/loliRuriruri/KR-Quant-Research.git
cd KR-Quant-Research

# 2) 파이썬 가상환경 생성 및 패키지 설치
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"

# 3) 환경설정 파일 복사
copy .env.example .env
```

### 2. 서버 실행
```powershell
# 배치 파일로 간편 실행
.\Start-KR-Quant.bat

# 또는 직접 uvicorn 실행
.\.venv\Scripts\python.exe -m uvicorn kr_quant.web.app:app --host 0.0.0.0 --port 8790
```
* 브라우저에서 **`http://localhost:8790`** 접속.

---

## 🌍 외부 공유 및 배포 방법 (How to Share & Deploy)

내 컴퓨터에서 실행 중인 이 대시보드를 친구, 동료 또는 외부에 공유하는 3가지 방법입니다.

### 방법 1. Cloudflare Tunnel (가장 추천: 무료 + 1분 만에 외부 링크 생성)
포트포워딩이나 복잡한 설정 없이, 즉시 안전한 공용 HTTPS URL을 무료로 발급받아 공유할 수 있습니다.

```powershell
# 1) Cloudflare Tunnel 다운로드 (Windows)
# https://github.com/cloudflare/cloudflared/releases 에서 cloudflared-windows-amd64.exe 다운로드 후 실행

# 2) 로컬 서버 포트(8790)에 무료 터널 열기
cloudflared tunnel --url http://localhost:8790
```
* 터미널에 출력되는 **`https://xxxx.trycloudflare.com`** 링크를 복사하여 카카오톡이나 모바일/타인에게 공유하면 바로 외부에서 접속할 수 있습니다!

---

### 방법 2. 같은 Wi-Fi/로컬 네트워크 내 공유
같은 공유기나 와이파이를 사용하는 기기(스마트폰, 태블릿, 노트북)에서 접속하는 방법입니다.

1. 서버를 `0.0.0.0`으로 실행합니다:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn kr_quant.web.app:app --host 0.0.0.0 --port 8790
   ```
2. 내 PC의 로컬 IP를 확인합니다 (`ipconfig` 실행 ➔ `IPv4 주소` 확인, 예: `192.168.0.15`).
3. 스마트폰이나 다른 PC 브라우저에서 `http://192.168.0.15:8790` 으로 접속합니다.

---

### 방법 3. 클라우드 상시 배포 (Render / Railway / VPS)
PC를 켜두지 않고 24시간 웹에 상시 서비스로 띄우고 싶을 때 사용합니다.

* **Render.com / Railway.app (무료/소액)**:
  1. [Render.com](https://render.com) 회원가입 후 **New Web Service** 클릭.
  2. GitHub 저장소 `loliRuriruri/KR-Quant-Research` 연결.
  3. **Build Command**: `pip install -e .`
  4. **Start Command**: `uvicorn kr_quant.web.app:app --host 0.0.0.0 --port $PORT`
  5. 배포 완료 시 나만의 무료 도메인 (`https://kr-quant-research.onrender.com`)이 생성됩니다.

---

## 🔑 API 키 설정 가이드

웹 UI 우측 상단의 **[API 설정]** 메뉴에서 필요한 Open API 키를 등록하면 추가 기능이 활성화됩니다:

| API | 용도 | 무료 발급 링크 |
|---|---|---|
| **OpenDART** | 상장사 재무제표 수집 및 국민연금 5% 대량보유 공시 | [opendart.fss.or.kr](https://opendart.fss.or.kr) |
| **KRX Open API** | 한국거래소 공식 전종목 시세 및 수정주가 | [openapi.krx.co.kr](https://openapi.krx.co.kr) |
| **한국투자증권 (KIS)** | 투자자별(외인/기관/사모) 일별 실시간 공식 수급 | [apiportal.koreainvestment.com](https://apiportal.koreainvestment.com) |
| **한국은행 ECOS** | 국내 기준금리, 국고채, M2 통화량, CPI 물가 | [ecos.bok.or.kr](https://ecos.bok.or.kr) |
| **미국 연준 FRED** | 연준 기준금리, 미국 10년/2년 국채금리, 장단기 스프레드 | [fred.stlouisfed.org](https://fred.stlouisfed.org) |
| **네이버 검색** | 실시간 증시·금리·환율 뉴스 및 백과사전 용어 연동 | [developers.naver.com](https://developers.naver.com) |
| **xAI / DeepSeek** | AI 심층 종목 분석 및 반대심문 리포트 생성 | [console.x.ai](https://console.x.ai) |

---

## 🧪 테스트 실행

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
* **139개 단위/통합 테스트 100% PASS** 유지.

---

## ⚠️ 유의 사항 (Disclaimer)
* 본 시스템에서 제공하는 모든 퀀트 점수, 매크로 지표, 수급 및 섹터 분석은 투자 리서치 및 연구 목적의 참고 자료입니다.
* 매수·매도에 대한 직접적인 투자 권유나 지시가 아니며, 최종 투자 판단과 책임은 투자자 본인에게 있습니다.

