# KR Quant Research — 기준 핸드오프 (P0)

적용 런타임: `C:\Users\a4jud\kr_quant_research` FastAPI 대시보드 (`:8790`).  
Streamlit 페이지를 새로 만들지 않는다. 기존 화면과 FastAPI 구조를 보존한다.

참고 분석(복제 금지):

- `docs/FASTJUSIK_PENSION_REFERENCE_ANALYSIS.md` — fastjusik.com/pension 화면 구조 분석
- `docs/GROK_BUILD_KR_QUANT_V1_3_FASTJUSIK_FLOW_EVENT_ADDENDUM.md` — 독립 구현 명세

## 절대 조건

- Fundamental Quant는 결정론. 수급·손자 五事·LLM은 `used_in_quant=false`.
- 한국 가격 정본은 KRX, 재무는 OpenDART. KIS는 수급·교차검증 전용 READ-ONLY.
- Fastjusik 소스·공개 API·브랜드·문구·데이터를 복사하거나 런타임 의존하지 않는다.
- API 키는 `.env`에만 두고 코드·문서·화면에 원문을 넣지 않는다.
- KIS `FUND`는 원천이 “연기금/국민연금”이라고 명시하지 않는 한 그 이름으로 부르지 않는다. 화면 표기는 **기금**.
- 종목별 일별 투자자 API는 관심종목·고유동성부터. 공식 전종목 bulk가 확인되기 전 전 종목 기금 순위를 표시하지 않는다.
- 주문·매수매도 신호·투자 조언을 만들지 않는다.

## P0 범위 (이번 구현)

1. `investor_flows_daily` DuckDB 스키마와 저장/조회
2. 투자자 유형 원문 → 정규화 + source 추적
3. KIS 투자자 수급 어댑터 인터페이스 (실호출은 키·한도 있을 때만)
4. API 없이 돌아가는 fixture 테스트
5. 데이터 없을 때 원인·다음 조치를 한국어로 보여주는 화면
6. P1 화면(연속/동반/전환 탭)을 붙일 수 있는 repository/service

P1 이후: 연속 수급·동반·방향전환 탭, 종목 상세 90일 차트, OpenDART 5% 보유. 전 종목 순위는 bulk 원천 확인 후.

## 이 앱에서의 파일

| 역할 | 파일 |
|---|---|
| 유형 정규화 | `src/kr_quant/flow/types.py` |
| DuckDB | `src/kr_quant/flow/store.py` |
| KIS 어댑터 | `src/kr_quant/ingest/kis.py` |
| 수집 대상 | `src/kr_quant/flow/priority.py` |
| 수집 서비스 | `src/kr_quant/flow/official.py` |
| 화면 | FastAPI `view-investor` |
| 설정 | `config/investor_flow.yaml` |
