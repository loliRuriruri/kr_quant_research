# 09. Volume / Flow / Indicators — VER3.7.2 Cloud-First Deep

## 1. Volume First

기술지표보다 가격·거래량을 우선한다.

- 당일 거래량 / 20일·60일 평균
- 거래대금과 회전율
- 상승일 vs 하락일 거래량
- 돌파 거래량과 리테스트 거래량
- 거래량 수축·Dry-up
- Climax volume
- Distribution / Accumulation days
- 이벤트 갭 거래량 유지·소진

## 2. Korea Flow — Cloud Default

### 기본 Layer: 완료 거래일

KRX/공식자료/검증된 웹에서 가능한 범위로:

- 외국인·기관·개인 확정 순매수
- 3D / 5D / 20D 누적
- 프로그램 EOD가 공개되면 별도 기록
- 공매도 거래비중·잔고의 최신 공개일
- 대차·신용의 최신 공개일

### 선택 Layer: 장중

검증 가능한 broker/provider/연결 도구가 실제로 있을 때만:

- 외국인·기관 장중 추정
- 프로그램 장중 순매수
- 회원사 동향

장중 데이터가 없으면 **미확인으로 두고 EOD + 가격·거래량을 사용한다.** 장중 수급 부재로 기술·가격전략을 생략하지 않는다.

## 3. Flow Interpretation

- 가격 상승 + EOD 외국인/기관 누적 개선 → Confirming 후보
- 가격 하락 + EOD 동반 순매도 + 거래량 확대 → Warning
- 가격 상승 + EOD 순매도 → 공급 소화인지 분배인지 거래량/매물대로 확인
- 주가 하락 + 공개 공매도/대차 증가 → Warning 후보
- 급락 후 거래량 소진 + 저점회복 → exhaustion 후보

수급은 펀더멘털 증거가 아니라 가격경로 증거다.

## 4. Volume Tools

가능한 데이터에서 OBV, CMF, A/D, Volume Profile, VWAP/Anchored VWAP, Up/Down Volume Ratio를 사용한다. 한 지표가 없다고 전체 거래량 분석을 생략하지 않는다.

## 5. Oscillators

필요한 2~4개만 선택한다: RSI(14), MACD(12,26,9), ADX/DMI, Bollinger, Stochastic, ROC.

## 6. Volatility

- ATR·ATR%
- 20/60일 실현변동성
- MDD
- 이벤트 갭 분포
- 손절 폭이 일상 변동성보다 좁지 않은지

## 7. Data Quality Flags

- EOD 기준일이 오래됨
- 제공자별 단위/정의 불일치
- 외국인 보유량 변화와 순매수 혼동
- 공매도 거래비중과 잔고 혼동
- 대차 증가를 실제 공매도 체결로 단정
- 장중 수급을 출처 없이 추정

## 8. Indicator Summary

| 항목 | 현재 상태 | 변화 | 해석 | 가격 영향 |
|---|---|---|---|---|
| 거래량 | | | | |
| 외국인/기관 EOD | | | | |
| 프로그램 | | | | |
| 공매도·대차·신용 | | | | |
| OBV/CMF | | | | |
| RSI/MACD/ADX | | | | |
| ATR | | | | |

최종적으로 `Confirming / Neutral / Warning / Rejecting`을 판정한다.
