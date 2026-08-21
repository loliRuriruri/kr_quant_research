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
        "comment": f"{title} 우호 {good} · 부담 {bad} · 중립 {mid}. {extra} Quant 점수에는 넣지 않습니다.",
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
        "disclaimer": "우호·부담은 금리·환율·물가·비교지수를 읽은 조사 코멘트입니다. Quant 순위와 합산하지 않으며 매수·매도 지시가 아닙니다.",
        "overall": overall,
        "domestic": {"stance": kr, "items": domestic},
        "international": {"stance": us, "items": international},
        "as_of": {
            "fred": next((row.get("date") for row in (fred or {}).get("series") or [] if row.get("date")), None),
            "ecos": next((_fmt_ecos_time(row.get("time")) for row in (ecos or {}).get("series") or [] if row.get("time")), None),
            "yahoo": next((row.get("as_of") for row in (yahoo or {}).get("indexes") or [] if row.get("as_of")), None),
        },
    }


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
        yahoo = index_snapshot()
    except Exception as exc:  # noqa: BLE001
        yahoo = {"configured": True, "used_in_quant": False, "error": str(exc)[:180], "indexes": []}
    brief = build_macro_brief(fred, ecos, yahoo)
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
        "brief": brief,
        "news": news,
    }
