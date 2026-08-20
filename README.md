# KR Quant Research

한국 주식 **조사 후보**를 매일 같은 공식으로 뽑는 프로그램입니다.  
`stock_screener`의 재무 Quant와 `korea-quant-discovery-engine-v2`의 시장·관심종목을 합쳤지만, **점수는 섞지 않습니다.**

자동매매·주문은 없습니다.

기능·설정·한도·검증 질문 전체는 [`docs/KR_QUANT_REVIEW_BRIEF.md`](docs/KR_QUANT_REVIEW_BRIEF.md) (GPT 등에 붙여 넣을 브리프).

## 계층

| 계층 | 하는 일 | 점수에 넣나 |
|---|---|---|
| Discovery | KRX+OpenDART TTM, Value/Quality/Growth/Stability, TOP20 게이트 | 예 |
| Context | 시장 국면, 관심종목, 왜 나왔는가 | 아니오 |
| Research | VER4 지침 리포트, 네이버/Toss/FRED | 아니오 |
| Timing | 전략·백테스트 (아직 자리만) | 아니오 |

모멘텀은 공식 수정주가가 없어 Quant에서 꺼 둡니다 (`1.0.0-no-momentum`).

## 실행

```powershell
cd C:\Users\a4jud\kr_quant_research
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
.\Start-KR-Quant.bat
```

대시보드: http://127.0.0.1:8790  
시세 신선도·런타임 설정: `GET /api/system/spec` · 평일 18:30 KST에 KRX 일봉만 자동 갱신 (OpenDART 제외).  
기존 스크리너(:8787)와 코덱스 Streamlit(:8501)은 그대로 둡니다.

```powershell
.\.venv\Scripts\python.exe -m kr_quant.cli demo
.\.venv\Scripts\python.exe -m kr_quant.cli doctor
.\.venv\Scripts\python.exe -m pytest -q
```

## 기존 프로젝트

- `C:\Users\a4jud\stock_screener` — 재무 엔진 원본
- `C:\TEST\korea-quant-discovery-engine-v2` — 시장·전략 화면 원본
