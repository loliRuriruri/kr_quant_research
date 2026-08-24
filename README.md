# KR Quant Research

한국 주식 **재무 퀀트 스코어링**과 수급·매크로·계절성·13F를 한곳에서 보는 리서치 시스템입니다.  
주문·잔고·체결 기능은 없습니다. 점수는 참고용이며 투자 권유가 아닙니다.

- GitHub: [loliRuriruri/kr_quant_research](https://github.com/loliRuriruri/kr_quant_research)
- 공개 웹(읽기 전용 스냅샷): [korea-quant-research.pages.dev](https://korea-quant-research.pages.dev/)

---

## 두 가지 동작 방식

이 프로젝트는 **로컬 엔진**과 **공개 웹**이 분리되어 있습니다.

| | 로컬 대시보드 | 공개 웹 (Cloudflare Pages) |
|---|---|---|
| 주소 | `http://127.0.0.1:8790` | https://korea-quant-research.pages.dev/ |
| PC가 꺼져 있어도 접속 | 불가 | 가능 |
| API 키·수집·재계산 | 이 PC에서만 | 없음 (키를 웹에 올리지 않음) |
| 백테스트, 트레이딩 랩, 계절성 플레이북 | 최신 데이터로 실행·조회 | 마지막 업로드 결과 조회 |
| API 설정 | 있음 | 숨김 (키를 웹에 올리지 않음) |
| 실행 파이프라인 | 실행 가능 | 같은 화면, 실행 버튼 비활성 |
| 보여주는 데이터 | 실시간으로 이 PC가 계산한 결과 | **마지막으로 업로드한 스냅샷** |
| 갱신 방법 | 실행 파이프라인 `live` / `screen` | 로컬 계산 후 `Start-KR-Quant-Public.bat` |

핵심: **웹이 혼자 KRX/OpenDART를 받아 점수를 다시 매기지는 않습니다.**  
최신 시세로 공개 사이트를 바꾸려면 이 PC에서 계산한 뒤 스냅샷을 올려야 합니다.

```
[이 PC]  API 키 → KRX/OpenDART/KIS 수집 → 퀀트 계산 → parquet/json
    │
    ├─ 로컬 웹  http://127.0.0.1:8790   (전체 기능)
    │
    └─ Start-KR-Quant-Public.bat
           → dist-public (키·로그·원문 제외)
           → Cloudflare Pages
           → https://korea-quant-research.pages.dev/
```

---

## 로컬 방식 (연구·수집·백테스트)

이 컴퓨터에서 FastAPI 대시보드를 켭니다. `.env`의 API 키로 공식 데이터를 받고, 퀀트 점수를 계산합니다.

### 설치

```powershell
git clone https://github.com/loliRuriruri/kr_quant_research.git
cd kr_quant_research
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
```

### 실행

`Start-KR-Quant.bat` 을 실행합니다.  
브라우저에서 **http://127.0.0.1:8790** 으로 접속합니다.

포트 8790이 이미 쓰이면, 이미 켜진 대시보드를 연 것으로 보면 됩니다. 같은 포트를 두 번 켜지 마세요.

### 로컬에서 할 수 있는 일

- 재무 5대 팩터 점수 (가치 30 / 품질 25 / 성장 25 / 모멘텀 10 / 안정 10)
- 테마 스크리너, 업종 6축, 매크로, 13F
- 메이저 수급·빈집·트레이딩 랩 (종목명 자동완성, 전 종목 검색)
- 계절성 선취매 TOP 10, 종목 클릭 시 플레이북
- 전략 백테스트: 확인창 → 로딩 오버레이 → 4대 전략 결과
- 은하퀀트전설
- API 설정, 실행 파이프라인 (KRX 시세, OpenDART, 재계산)

### 데이터 원칙 (로컬 계산)

- 가격·종목 마스터의 기본 출처는 **KRX**
- 재무·공시의 기본 출처는 **OpenDART** (`available_date <= run_date`)
- **KIS**는 수급 교차검증·보조이며 퀀트 점수에 넣지 않음
- **ECOS / FRED**는 거시 오버레이
- **네이버**는 뉴스 탐색용이며 투자 사실의 단독 근거로 쓰지 않음
- 가격만으로 외인·기금 수급을 만들지 않음
- 원천이 `FUND`이면 검증 전까지 **연기금/국민연금으로 이름을 바꾸지 않음**
- AI는 설명만 담당하고 점수·순위를 수정하지 않음
- 주문 실행 없음

### API 키

로컬 화면 **API 설정**에서 넣습니다. 키는 `.env`에만 저장됩니다.

| API | 용도 |
|---|---|
| OpenDART | 재무제표, 대량보유 공시 |
| KRX Open API | 전종목 시세·마스터 |
| KIS | 투자자별 수급 (오버레이) |
| ECOS / FRED | 거시 |
| 네이버 검색 | 뉴스 탐색 |
| xAI / DeepSeek | AI 리포트 (점수 미변경) |

---

## 공개 웹 방식 (읽기 전용 스냅샷)

주소: **https://korea-quant-research.pages.dev/**

Cloudflare Pages에 올라간 **정적 파일**입니다. PC가 꺼져 있어도 접속됩니다.  
로컬과 **같은 메뉴·화면**을 쓰되, 데이터는 마지막으로 업로드한 읽기 전용 JSON 스냅샷을 사용합니다.

- 로컬과 같은 대시보드·랭킹·수급·매크로·계절성·백테스트 메뉴
- API 설정은 숨기고, 실행 파이프라인은 같은 화면에서 버튼만 비활성
- 수집·재계산·AI 생성·저장 동작은 로컬에서만 가능
- `.env`, 로그, 원문 응답, 서버 코드 없음
- 값이 없으면 0으로 채우지 않고 **미수집**으로 표시
- 각 숫자에 기준일, 출처, 공식/관측/모델, 계산식, 누락, 경고를 붙임

즉, 로컬과 공개 웹의 차이는 메뉴 축약이 아니라 **관리·변경 기능의 유무**입니다. 공개 웹에서는 모든 화면을 조회할 수 있지만 새 수집이나 계산은 이 PC에서 실행한 뒤 다시 업로드해야 합니다.

### 공개 웹을 최신 정보로 갱신하는 방법

1. `Start-KR-Quant.bat`으로 로컬 대시보드를 켭니다.
2. **실행 파이프라인**에서 실데이터 수집 + 재계산(`live` 또는 `screen`)을 돌립니다. 장 마감 후가 안전합니다.
3. `Start-KR-Quant-Public.bat`을 실행합니다. 창에 진행 로그가 나옵니다. `[DONE]`까지 닫지 마세요. (한글 깨짐 방지를 위해 창 메시지는 영문입니다.)
4. https://korea-quant-research.pages.dev/ 에서 **Ctrl+F5**.

같은 작업의 별칭: `Publish-KR-Quant-Public.bat`

명령줄:

```powershell
cd C:\Users\a4jud\kr_quant_research
node scripts/build-public.mjs
npx wrangler pages deploy dist-public --project-name korea-quant-research --branch main
```

로컬 대시보드를 켜 두면, 평일 18:30 `live`가 성공한 뒤 공개 웹도 같이 올리도록 연결돼 있습니다. PC가 꺼져 있으면 그날 스냅샷은 갱신되지 않습니다.

### 임시 터널 (비권장)

`Start-KR-Quant-Tunnel.bat`은 이 PC를 `trycloudflare.com`으로 잠깐 엽니다.  
외부 호스트·Cloudflare 전달 요청은 자동으로 읽기 전용 모드가 되어 API 설정·실행 화면과 모든 변경 API가 차단됩니다. PC가 켜져 있어야 하므로 장기 공유에는 **Pages 공개 웹**을 쓰세요.

---

## 배치 파일 요약

| 파일 | 하는 일 |
|---|---|
| `Start-KR-Quant.bat` | 로컬 대시보드 (전체 기능) |
| `Start-KR-Quant-Public.bat` | 로컬 스냅샷 → Cloudflare Pages 업로드 |
| `Publish-KR-Quant-Public.bat` | 위와 동일 (별칭) |
| `Start-KR-Quant-Tunnel.bat` | PC가 켜져 있는 동안만 임시 외부 URL |

---

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 면책

퀀트 점수, 매크로, 수급, 섹터 분석은 연구용 참고 자료입니다.  
매수·매도 지시가 아니며 투자 판단과 책임은 본인에게 있습니다.
