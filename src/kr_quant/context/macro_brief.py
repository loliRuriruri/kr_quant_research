"""Domestic/international macro comments. Overlay only — never writes quant_score."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num or num in {float("inf"), float("-inf")}:
        return None
    return num


def _item(kind: str, key: str, label: str, value: Any, unit: str, as_of: str | None, tone: str, comment: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": key,
        "label": label,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "tone": tone,
        "comment": comment,
        "used_in_quant": False,
    }


def _tone_rate_move(delta: float | None, *, hike_is_bad: bool = True) -> str:
    if delta is None:
        return "중립"
    if abs(delta) < 0.03:
        return "중립"
    up = delta > 0
    if hike_is_bad:
        return "부담" if up else "우호"
    return "우호" if up else "부담"


def _comment_spread(value: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", "장단기 금리차 관측이 없습니다."
    day = f" ({as_of})" if as_of else ""
    if value < 0:
        return "부담", f"10년-2년 스프레드 {value:.2f}%p로 역전입니다{day}. 침체 신호로 읽히며 위험자산에 부담입니다."
    if value < 0.30:
        return "중립", f"스프레드 {value:.2f}%p로 평탄합니다{day}. 경기·금리 방향이 아직 분명하지 않습니다."
    return "우호", f"스프레드 {value:.2f}%p로 정상 기울기입니다{day}. 금리 곡선만 보면 위험자산에 우호적입니다."


def _comment_policy_rate(label: str, value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", f"{label} 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    if value >= 5.0:
        tone = "부담"
        extra = "긴축이 높은 구간입니다."
    elif value >= 3.5:
        tone = "부담" if (delta or 0) >= 0 else "중립"
        extra = "아직 제약적인 금리입니다."
    elif value <= 2.0:
        tone = "우호"
        extra = "완화 구간에 가깝습니다."
    else:
        tone = _tone_rate_move(delta)
        extra = "중간 구간입니다."
    move = ""
    if delta is not None:
        move = f" 직전 대비 {delta:+.2f}%p."
    return tone, f"{label} {value:.2f}%{day}.{move} {extra} 할인율·자금조달 측면에서 위험자산에 {'부담' if tone == '부담' else '우호' if tone == '우호' else '중립'}입니다."


def _comment_yield(label: str, value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", f"{label} 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    tone = _tone_rate_move(delta)
    if value >= 4.5 and tone != "우호":
        tone = "부담"
    move = "" if delta is None else f" 직전 대비 {delta:+.2f}%p."
    if tone == "부담":
        why = "금리가 오르거나 높은 구간이면 주식 할인율에 부담입니다."
    elif tone == "우호":
        why = "금리가 내리면 위험자산 할인율에 우호적입니다."
    else:
        why = "최근 변화가 작아 방향이 뚜렷하지 않습니다."
    return tone, f"{label} {value:.2f}%{day}.{move} {why}"


def _comment_fx(label: str, value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", f"{label} 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    if value >= 1450:
        tone = "부담"
        level = "원화가 많이 약합니다."
    elif value >= 1380:
        tone = "부담" if (delta or 0) >= 0 else "중립"
        level = "원/달러가 높은 편입니다."
    elif value <= 1250:
        tone = "우호"
        level = "원화가 비교적 강합니다."
    else:
        tone = "부담" if (delta or 0) > 5 else "우호" if (delta or 0) < -5 else "중립"
        level = "중간 환율대입니다."
    move = "" if delta is None else f" 직전 대비 {delta:+.1f}."
    return tone, f"{label} {value:.1f}{day}.{move} {level} 원화 약세는 외국인 수급·수입물가에 부담입니다."


def _comment_cpi(label: str, value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", f"{label} 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    tone = _tone_rate_move(delta)
    move = "" if delta is None else f" 직전 대비 {delta:+.2f}."
    if tone == "부담":
        why = "물가가 오르면 금리 인하가 늦어질 수 있어 부담입니다."
    elif tone == "우호":
        why = "물가 상승이 꺾이면 금리 부담이 줄어듭니다."
    else:
        why = "물가 방향이 뚜렷하지 않습니다."
    return tone, f"{label} {value:.2f}{day}.{move} {why}"


def _comment_unrate(value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", "실업률 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    move = "" if delta is None else f" 직전 대비 {delta:+.2f}%p."
    if delta is not None and delta > 0.15:
        return "부담", f"미국 실업률 {value:.1f}%{day}.{move} 고용이 빠르게 식으면 경기 둔화 부담입니다. 금리 인하 기대는 별개입니다."
    if delta is not None and delta < -0.10:
        return "우호", f"미국 실업률 {value:.1f}%{day}.{move} 고용이 버티면 위험자산에 우호적입니다."
    if value >= 5.5:
        return "부담", f"미국 실업률 {value:.1f}%{day}.{move} 높은 편이라 경기 부담으로 봅니다."
    return "중립", f"미국 실업률 {value:.1f}%{day}.{move} 큰 변화가 없어 중립입니다."


def _comment_index(label: str, last: float | None, ret_1d: float | None, ret_1y: float | None, as_of: str | None) -> tuple[str, str]:
    if last is None:
        return "미연결", f"{label} 시세가 없습니다."
    day = f" · {as_of}" if as_of else ""
    d1 = "" if ret_1d is None else f" 1일 {(ret_1d * 100):+.2f}%"
    y1 = "" if ret_1y is None else f" 1년 {(ret_1y * 100):+.1f}%"
    if ret_1d is not None and ret_1d <= -0.012:
        tone = "부담"
        why = "단기 낙폭이 큽니다."
    elif ret_1d is not None and ret_1d >= 0.008:
        tone = "우호"
        why = "단기 상승입니다."
    elif ret_1y is not None and ret_1y < 0:
        tone = "부담"
        why = "1년 수익률이 마이너스입니다."
    elif ret_1y is not None and ret_1y > 0.08:
        tone = "우호"
        why = "중기 추세는 살아 있습니다."
    else:
        tone = "중립"
        why = "방향이 뚜렷하지 않습니다."
    return tone, f"{label} {last:,.2f}{day}.{d1}{y1}. {why} 비교지수이며 한국 공식 시세는 KRX입니다."


def _comment_m2(value: float | None, delta: float | None, as_of: str | None) -> tuple[str, str]:
    if value is None:
        return "미연결", "M2 관측이 없습니다."
    day = f" · {as_of}" if as_of else ""
    tone = "우호" if (delta or 0) > 0 else "중립" if delta is None or delta == 0 else "부담"
    move = "" if delta is None else f" 직전 대비 {delta:+.1f}."
    return tone, f"M2 {value:,.1f}{day}.{move} 유동성이 늘면 위험자산에 우호, 줄면 부담으로 읽습니다."


def _stance(items: list[dict[str, Any]], title: str) -> dict[str, Any]:
    live = [row for row in items if row.get("tone") not in {None, "미연결"}]
    good = sum(1 for row in live if row.get("tone") == "우호")
    bad = sum(1 for row in live if row.get("tone") == "부담")
    mid = len(live) - good - bad
    if not live:
        return {
            "title": title,
            "tone": "미연결",
            "label": "데이터 없음",
            "comment": f"{title} 지표를 아직 받지 못했습니다. 설정에서 FRED·한국은행 키를 확인하세요.",
            "good": 0,
            "bad": 0,
            "neutral": 0,
        }
    if bad >= good + 2:
        tone, label = "부담", "위험자산에 부담"
        extra = "금리·환율·물가 쪽이 주식에 불리하게 기울었습니다."
    elif good >= bad + 2:
        tone, label = "우호", "위험자산에 우호"
        extra = "금리·환율·지수 쪽이 주식에 유리한 편입니다."
    else:
        tone, label = "혼합", "우호와 부담이 섞임"
        extra = "한쪽으로 단정하지 말고 금리와 환율을 같이 보세요."
    return {
        "title": title,
        "tone": tone,
        "label": label,
        "comment": f"{title} 우호 {good} · 부담 {bad} · 중립 {mid}. {extra}",
        "good": good,
        "bad": bad,
        "neutral": mid,
    }


def _fred_map(fred: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (fred or {}).get("series") or []:
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out


def _ecos_map(ecos: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in (ecos or {}).get("series") or []:
        if isinstance(row, dict) and row.get("alias"):
            out[str(row["alias"])] = row
    return out


def _fmt_ecos_time(raw: Any) -> str | None:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return str(raw) if raw else None


def build_macro_brief(
    fred: dict[str, Any] | None = None,
    ecos: dict[str, Any] | None = None,
    yahoo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fred_rows = _fred_map(fred)
    ecos_rows = _ecos_map(ecos)
    domestic: list[dict[str, Any]] = []
    international: list[dict[str, Any]] = []

    kr_rate = ecos_rows.get("기준금리") or {}
    tone, comment = _comment_policy_rate("한국 기준금리", _num(kr_rate.get("value")), _num(kr_rate.get("delta")), _fmt_ecos_time(kr_rate.get("time")))
    domestic.append(_item("domestic", "bok_rate", "한국 기준금리", _num(kr_rate.get("value")), "%", _fmt_ecos_time(kr_rate.get("time")), tone, comment))

    ktb = ecos_rows.get("국고채3년") or {}
    tone, comment = _comment_yield("국고채 3년", _num(ktb.get("value")), _num(ktb.get("delta")), _fmt_ecos_time(ktb.get("time")))
    domestic.append(_item("domestic", "ktb3y", "국고채 3년", _num(ktb.get("value")), "%", _fmt_ecos_time(ktb.get("time")), tone, comment))

    fx_kr = ecos_rows.get("원달러환율") or {}
    tone, comment = _comment_fx("원/달러(한은)", _num(fx_kr.get("value")), _num(fx_kr.get("delta")), _fmt_ecos_time(fx_kr.get("time")))
    domestic.append(_item("domestic", "usdkrw_bok", "원/달러(한은)", _num(fx_kr.get("value")), "원", _fmt_ecos_time(fx_kr.get("time")), tone, comment))

    cpi_kr = ecos_rows.get("소비자물가지수") or {}
    tone, comment = _comment_cpi("한국 CPI", _num(cpi_kr.get("value")), _num(cpi_kr.get("delta")), _fmt_ecos_time(cpi_kr.get("time")))
    domestic.append(_item("domestic", "cpi_kr", "한국 CPI", _num(cpi_kr.get("value")), str(cpi_kr.get("unit") or "지수"), _fmt_ecos_time(cpi_kr.get("time")), tone, comment))

    m2 = ecos_rows.get("M2") or {}
    tone, comment = _comment_m2(_num(m2.get("value")), _num(m2.get("delta")), _fmt_ecos_time(m2.get("time")))
    domestic.append(_item("domestic", "m2", "M2", _num(m2.get("value")), str(m2.get("unit") or ""), _fmt_ecos_time(m2.get("time")), tone, comment))

    fed = fred_rows.get("FEDFUNDS") or {}
    tone, comment = _comment_policy_rate("연준 기준금리", _num(fed.get("value")), _num(fed.get("delta")), fed.get("date"))
    international.append(_item("international", "FEDFUNDS", "연준 기준금리", _num(fed.get("value")), "%", fed.get("date"), tone, comment))

    dgs10 = fred_rows.get("DGS10") or {}
    tone, comment = _comment_yield("미국 10년", _num(dgs10.get("value")), _num(dgs10.get("delta")), dgs10.get("date"))
    international.append(_item("international", "DGS10", "미국 10년", _num(dgs10.get("value")), "%", dgs10.get("date"), tone, comment))

    dgs2 = fred_rows.get("DGS2") or {}
    tone, comment = _comment_yield("미국 2년", _num(dgs2.get("value")), _num(dgs2.get("delta")), dgs2.get("date"))
    international.append(_item("international", "DGS2", "미국 2년", _num(dgs2.get("value")), "%", dgs2.get("date"), tone, comment))

    spread = fred_rows.get("T10Y2Y") or {}
    tone, comment = _comment_spread(_num(spread.get("value")), spread.get("date"))
    international.append(_item("international", "T10Y2Y", "장단기 스프레드", _num(spread.get("value")), "%p", spread.get("date"), tone, comment))

    cpi_us = fred_rows.get("CPIAUCSL") or {}
    tone, comment = _comment_cpi("미국 CPI", _num(cpi_us.get("value")), _num(cpi_us.get("delta")), cpi_us.get("date"))
    international.append(_item("international", "CPIAUCSL", "미국 CPI", _num(cpi_us.get("value")), "지수", cpi_us.get("date"), tone, comment))

    unrate = fred_rows.get("UNRATE") or {}
    tone, comment = _comment_unrate(_num(unrate.get("value")), _num(unrate.get("delta")), unrate.get("date"))
    international.append(_item("international", "UNRATE", "미국 실업률", _num(unrate.get("value")), "%", unrate.get("date"), tone, comment))

    fx_us = fred_rows.get("DEXKOUS") or {}
    tone, comment = _comment_fx("원/달러(FRED)", _num(fx_us.get("value")), _num(fx_us.get("delta")), fx_us.get("date"))
    international.append(_item("international", "DEXKOUS", "원/달러(FRED)", _num(fx_us.get("value")), "원", fx_us.get("date"), tone, comment))

    for row in (yahoo or {}).get("indexes") or []:
        if not isinstance(row, dict) or row.get("error"):
            continue
        label = str(row.get("label") or row.get("symbol") or "")
        tone, comment = _comment_index(label, _num(row.get("last")), _num(row.get("ret_1d")), _num(row.get("ret_1y")), row.get("as_of"))
        bucket = "domestic" if label.upper() in {"KOSPI", "KOSDAQ"} or str(row.get("symbol") or "").startswith("^K") else "international"
        item = _item(bucket, str(row.get("symbol") or label), label, _num(row.get("last")), "", row.get("as_of"), tone, comment)
        if bucket == "domestic":
            domestic.append(item)
        else:
            international.append(item)

    kr = _stance(domestic, "국내")
    us = _stance(international, "국제")
    overall = _stance(domestic + international, "종합")
    if kr["tone"] == "부담" and us["tone"] == "부담":
        overall["tone"] = "부담"
        overall["label"] = "국내·국제 모두 부담"
        overall["comment"] = "국내와 국제 매크로가 같이 부담입니다. 위험자산 비중을 키우기 어려운 구간으로 읽습니다. Quant 점수에는 넣지 않습니다."
    elif kr["tone"] == "우호" and us["tone"] == "우호":
        overall["tone"] = "우호"
        overall["label"] = "국내·국제 모두 우호"
        overall["comment"] = "국내와 국제 매크로가 같이 우호적입니다. 그래도 개별 종목 점수와 합산하지 않습니다."
    return {
        "used_in_quant": False,
        "disclaimer": "우호·부담은 금리·환율·물가·비교지수를 종합 분석한 거시경제 지표이며, Quant 모델과 독립적인 시장 모니터링 데이터입니다.",
        "overall": overall,
        "domestic": {"stance": kr, "items": domestic},
        "international": {"stance": us, "items": international},
        "as_of": {
            "fred": next((row.get("date") for row in (fred or {}).get("series") or [] if row.get("date")), None),
            "ecos": next((_fmt_ecos_time(row.get("time")) for row in (ecos or {}).get("series") or [] if row.get("time")), None),
            "yahoo": next((row.get("as_of") for row in (yahoo or {}).get("indexes") or [] if row.get("as_of")), None),
        },
    }


def compute_yencarry_monitor(yahoo_indexes: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluates Yen Carry Trade risk based on USD/JPY, Nikkei 225, and US-JP rate trends."""
    by_sym = {str(row.get("symbol") or ""): row for row in (yahoo_indexes or []) if isinstance(row, dict)}
    usdjpy = by_sym.get("JPY=X") or {}
    jpykrw = by_sym.get("JPYKRW=X") or {}
    nikkei = by_sym.get("^N225") or {}
    tnx = by_sym.get("^TNX") or {}

    rate = _num(usdjpy.get("last"))
    ret_1m = _num(usdjpy.get("ret_1m"))
    ret_5d = _num(usdjpy.get("ret_5d"))
    nikkei_1m = _num(nikkei.get("ret_1m"))
    us_yield = _num(tnx.get("last"))

    # Logic: When USD/JPY drops rapidly (Yen sharp appreciation), carry traders face margin calls / unwinding
    unwind_score = 30  # baseline safe (0~100)
    risk_level = "STABLE"
    risk_ko = "안정"
    reasons = []

    if rate is not None:
        if rate < 142.0:
            unwind_score += 25
            reasons.append(f"엔/달러 {rate:.1f}엔으로 엔화 강세 구간")
        elif rate > 155.0:
            reasons.append(f"엔/달러 {rate:.1f}엔으로 엔화 약세 유지 (캐리 유효)")

    if ret_1m is not None and ret_1m <= -0.04:
        unwind_score += 30
        reasons.append(f"최근 1개월 엔화 급격한 절상 (USD/JPY {ret_1m*100:+.1f}%)")
    elif ret_5d is not None and ret_5d <= -0.02:
        unwind_score += 15
        reasons.append(f"최근 5일 엔화 단기 급등 (USD/JPY {ret_5d*100:+.1f}%)")

    if nikkei_1m is not None and nikkei_1m <= -0.05:
        unwind_score += 20
        reasons.append(f"일본 닛케이 225 1개월 {nikkei_1m*100:+.1f}% 하락 동조")

    if unwind_score >= 65:
        risk_level = "UNWIND_RISK"
        risk_ko = "청산 경보"
        summary = "엔화 급격한 강세 및 일본 증시 변동성으로 엔 캐리 트레이드 청산 압력이 높습니다. 글로벌 유동성 축소 및 코스피 대형주 외국인 매도 압력에 유의하세요."
    elif unwind_score >= 45:
        risk_level = "WATCH"
        risk_ko = "변동성 주시"
        summary = "미·일 금리차 및 환율 변동으로 엔 캐리 포지션의 재조정 가능성이 있습니다. 시장 모니터링이 필요한 구간입니다."
    else:
        risk_level = "STABLE"
        risk_ko = "안정"
        summary = "엔/달러 환율과 미·일 금리 흐름이 안정적이며, 급격한 엔 캐리 청산 징후는 낮습니다."

    return {
        "used_in_quant": False,
        "risk_level": risk_level,
        "risk_ko": risk_ko,
        "unwind_score": min(100, unwind_score),
        "summary": summary,
        "usdjpy": {"last": rate, "ret_5d": ret_5d, "ret_1m": ret_1m, "spark": usdjpy.get("spark")},
        "jpykrw": {"last": _num(jpykrw.get("last")), "ret_1m": _num(jpykrw.get("ret_1m"))},
        "nikkei": {"last": _num(nikkei.get("last")), "ret_1m": nikkei_1m, "spark": nikkei.get("spark")},
        "us_10y_yield": us_yield,
        "reasons": reasons,
        "disclaimer": "엔/달러 환율 속도와 닛케이 225, 금리차를 모니터링하는 위험 관리 지표입니다.",
    }


def compute_commodity_crypto_brief(yahoo_indexes: list[dict[str, Any]]) -> dict[str, Any]:
    """Generates insightful macro comments on Gold, Oil, Copper, and Bitcoin."""
    by_sym = {str(row.get("symbol") or ""): row for row in (yahoo_indexes or []) if isinstance(row, dict)}
    gold = by_sym.get("GC=F") or {}
    oil = by_sym.get("CL=F") or {}
    copper = by_sym.get("HG=F") or {}
    btc = by_sym.get("BTC-USD") or {}

    items = []
    if gold.get("last") is not None:
        g_last = float(gold["last"])
        g_1m = _num(gold.get("ret_1m"))
        g_tone = "우호" if (g_1m or 0) > 0.03 else "중립"
        items.append({
            "id": "gold",
            "name": "금 선물 (Gold)",
            "last": g_last,
            "unit": "$/oz",
            "ret_1d": _num(gold.get("ret_1d")),
            "ret_1m": g_1m,
            "tone": g_tone,
            "comment": f"온스당 ${g_last:,.1f}. 글로벌 지정학 위험 및 중앙은행 준비자산 수요 흐름을 반영합니다.",
            "spark": gold.get("spark"),
        })

    if oil.get("last") is not None:
        o_last = float(oil["last"])
        o_1m = _num(oil.get("ret_1m"))
        o_tone = "부담" if o_last >= 85 or (o_1m or 0) > 0.08 else "우호" if o_last <= 65 else "중립"
        items.append({
            "id": "oil",
            "name": "WTI 원유 (Crude Oil)",
            "last": o_last,
            "unit": "$/bbl",
            "ret_1d": _num(oil.get("ret_1d")),
            "ret_1m": o_1m,
            "tone": o_tone,
            "comment": f"배럴당 ${o_last:.2f}. 한국 제조업 에너지 원가 및 인플레이션 압력 지표입니다.",
            "spark": oil.get("spark"),
        })

    if copper.get("last") is not None:
        c_last = float(copper["last"])
        c_1m = _num(copper.get("ret_1m"))
        c_tone = "우호" if (c_1m or 0) > 0.03 else "부담" if (c_1m or 0) < -0.05 else "중립"
        items.append({
            "id": "copper",
            "name": "구리 선물 (Dr. Copper)",
            "last": c_last,
            "unit": "$/lb",
            "ret_1d": _num(copper.get("ret_1d")),
            "ret_1m": c_1m,
            "tone": c_tone,
            "comment": f"파운드당 ${c_last:.2f}. 글로벌 제조업 및 인프라 경기 선행 바로미터입니다.",
            "spark": copper.get("spark"),
        })

    if btc.get("last") is not None:
        b_last = float(btc["last"])
        b_1m = _num(btc.get("ret_1m"))
        b_tone = "우호" if (b_1m or 0) > 0.05 else "부담" if (b_1m or 0) < -0.08 else "중립"
        items.append({
            "id": "btc",
            "name": "비트코인 (Bitcoin)",
            "last": b_last,
            "unit": "$",
            "ret_1d": _num(btc.get("ret_1d")),
            "ret_1m": b_1m,
            "tone": b_tone,
            "comment": f"${b_last:,.0f}. 글로벌 유동성 및 위험자산 선호도(Risk-on/off) 선행 프록시입니다.",
            "spark": btc.get("spark"),
        })

    return {"used_in_quant": False, "items": items}


def build_macro_dashboard(settings: Any, *, refresh: bool = False) -> dict[str, Any]:
    from kr_quant.ingest.ecos import ecos_snapshot
    from kr_quant.ingest.fred import macro_snapshot
    from kr_quant.ingest.yahoo import index_snapshot

    fred = macro_snapshot(getattr(settings, "fred_api_key", None))
    try:
        ecos = ecos_snapshot(getattr(settings, "bok_ecos_api_key", None))
    except Exception as exc:  # noqa: BLE001
        ecos = {"configured": False, "used_in_quant": False, "error": str(exc)[:180], "series": []}
    try:
        yahoo = index_snapshot(refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        yahoo = {"configured": True, "used_in_quant": False, "error": str(exc)[:180], "indexes": []}
    brief = build_macro_brief(fred, ecos, yahoo)
    indexes_list = (yahoo or {}).get("indexes") or []
    yencarry = compute_yencarry_monitor(indexes_list)
    commodities_crypto = compute_commodity_crypto_brief(indexes_list)

    # Grouped assets for visual dashboard
    grouped_assets = {
        "indices": [row for row in indexes_list if row.get("category") == "index"],
        "fx": [row for row in indexes_list if row.get("category") == "fx"],
        "commodities": [row for row in indexes_list if row.get("category") == "commodity"],
        "crypto": [row for row in indexes_list if row.get("category") == "crypto"],
        "rates": [row for row in indexes_list if row.get("category") == "rate"],
    }

    news: dict[str, Any] = {"configured": False, "used_in_quant": False, "groups": [], "encyc": []}
    client_id = getattr(settings, "naver_client_id", None)
    client_secret = getattr(settings, "naver_client_secret", None)
    if client_id and client_secret:
        try:
            from kr_quant.ingest.naver_search import market_news_bundle

            news = market_news_bundle(client_id, client_secret, refresh=refresh)
        except Exception as exc:  # noqa: BLE001
            news = {"configured": True, "used_in_quant": False, "error": str(exc)[:180], "groups": [], "encyc": []}
    else:
        news["error"] = "네이버 검색 Client ID/Secret이 없습니다. API 설정에서 넣으면 금리·환율·증시 뉴스가 붙습니다."
    now = datetime.now(timezone.utc).isoformat()
    return {
        "used_in_quant": False,
        "fetched_at": now,
        "disclaimer": brief["disclaimer"],
        "fred": fred,
        "ecos": ecos,
        "yahoo": yahoo,
        "grouped_assets": grouped_assets,
        "yencarry": yencarry,
        "commodities_crypto": commodities_crypto,
        "brief": brief,
        "news": news,
    }
