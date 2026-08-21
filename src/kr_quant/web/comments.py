"""Per-row Korean pick comments. Overlays only — never writes quant_score."""

from __future__ import annotations

from typing import Any

from kr_quant.web.guide import DATA_FLAG_KO, flag_notes, format_krw, format_pct


SELECTION = {
    "quant": (
        "보통주 유니버스(시총·거래대금·재무 게이트)를 통과한 뒤 "
        "Value 30 / Quality 25 / Growth 25 / Momentum 10 / Stability 10으로 점수를 냅니다. "
        "TOP20은 커버리지·신뢰도와 영업이익·순이익·CFO 양수가 필요합니다. LLM은 점수를 고치지 않습니다."
    ),
    "flow": (
        "토스 투자자 매매의 최근 거래일 순매수(주수)를 합산합니다. "
        "쌍끌이는 외인·기관이 둘 다 순매수, 사모는 토스 사모펀드, "
        "쌍끌이+사모는 둘 다, 개인이탈은 그 위에 개인 순매도입니다. "
        "기타법인·연기금이 있으면 같이 보여 줍니다. Quant 점수와 무관합니다."
    ),
    "empty": (
        "빈집은 외인·기관이 같이 판 뒤, 연속 매도 2일 이상이거나 "
        "외인 보유수량 대비 0.5% 이상, 또는 합산 2만주 이상 이탈일 때만 잡습니다. "
        "하루 소액 쌍매도는 빈집이 아닙니다. Quant에 넣지 않습니다."
    ),
    "trade": (
        "수급 셋업에 KRX 일봉 스토캐스틱 5,3,3과 일목 9-26-52를 붙입니다. "
        "기본은 퀀트 TOP100 밖입니다. 매수 지시가 아닙니다."
    ),
    "us13f": (
        "SEC EDGAR 13F-HR 분기 말 보유입니다. 신규·확대·청산은 직전 분기 대비 주수 변화입니다. "
        "최대 45일 시차가 있고 Quant에 넣지 않습니다."
    ),
    "toss": "토스 Open API 시세 랭킹입니다. 급상승·급하락·거래대금 순이며 Quant 점수와 무관합니다.",
    "watch": "직접 저장한 메모 목록입니다. 점수나 수급 순위가 아닙니다.",
    "reports": "종목 상세에서 버튼을 눌러 저장한 리포트입니다. Quant 점수는 바꾸지 않습니다.",
}


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


def _int(value: Any) -> int | None:
    num = _num(value)
    if num is None:
        return None
    return int(num)


def _iga(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return "펀드가"
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return text + ("가" if (code - 0xAC00) % 28 == 0 else "이")
    return text + "가"


def _ul(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return "이 종목을"
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return text + ("를" if (code - 0xAC00) % 28 == 0 else "을")
    return text + "를"


def _usd(value: Any) -> str | None:
    num = _num(value)
    if num is None or abs(num) < 1:
        return None
    sign = "-" if num < 0 else ""
    mag = abs(num)
    if mag >= 1e9:
        return f"{sign}${mag / 1e9:.2f}B"
    if mag >= 1e6:
        return f"{sign}${mag / 1e6:.0f}M"
    return f"{sign}${mag:,.0f}"


def quant_comment(row: dict[str, Any]) -> str:
    bits: list[str] = []
    rank = _int(row.get("quant_rank"))
    score = _num(row.get("quant_score"))
    if rank is not None:
        bits.append(f"조건 통과 종목 중 {rank}위")
    if score is not None:
        bits.append(f"Quant {score:.1f}점")
    head = ", ".join(bits) + "." if bits else "재무 Quant 후보입니다."
    ranked: list[tuple[float, str]] = []
    for label, key in (
        ("가치", "value_score"),
        ("품질", "quality_score"),
        ("성장", "growth_score"),
        ("모멘텀", "momentum_score"),
        ("안정", "financial_score"),
    ):
        val = _num(row.get(key))
        if val is not None:
            ranked.append((val, label))
    ranked.sort(reverse=True)
    if ranked:
        top = ranked[:2]
        drive = ", ".join(f"{lab} {val:.0f}점" for val, lab in top)
        head += f" {drive}이 점수를 이끕니다."
    pen = _num(row.get("risk_penalty"))
    if pen and pen >= 1:
        head += f" 리스크 페널티 −{pen:.1f}점."
    cov = _num(row.get("weighted_metric_coverage"))
    conf = _num(row.get("data_confidence"))
    gate: list[str] = []
    if cov is not None:
        gate.append(f"커버리지 {cov * 100:.0f}%")
    if conf is not None:
        gate.append(f"신뢰도 {conf:.0f}")
    if gate:
        head += " " + " · ".join(gate) + "."
    notes = flag_notes(row.get("data_flags"), DATA_FLAG_KO)
    if notes:
        head += f" 참고: {notes[0]['label']}."
    head += " 재무 게이트를 통과한 조사 후보이며 매수 신호가 아닙니다."
    return head


def quant_comment_short(row: dict[str, Any]) -> str:
    parts: list[str] = []
    rank = _int(row.get("quant_rank"))
    if rank is not None:
        parts.append(f"{rank}위")
    ranked: list[tuple[float, str]] = []
    for label, key in (
        ("가치", "value_score"),
        ("품질", "quality_score"),
        ("성장", "growth_score"),
        ("모멘텀", "momentum_score"),
        ("안정", "financial_score"),
    ):
        val = _num(row.get(key))
        if val is not None:
            ranked.append((val, label))
    ranked.sort(reverse=True)
    if ranked:
        parts.append("/".join(lab for _, lab in ranked[:2]) + " 우위")
    pen = _num(row.get("risk_penalty"))
    if pen and pen >= 1:
        parts.append(f"페널티 −{pen:.0f}")
    cov = _num(row.get("weighted_metric_coverage"))
    if cov is not None:
        parts.append(f"커버 {cov * 100:.0f}%")
    return " · ".join(parts) or "재무 Quant 후보"


def flow_comment(row: dict[str, Any]) -> str:
    days = _int(row.get("days")) or 5
    foreign = _int(row.get("foreign_net")) or 0
    inst = _int(row.get("institution_net")) or 0
    bits = [f"최근 {days}거래일 외인 {foreign:+,}주 · 기관 {inst:+,}주가 같이 샀습니다."]
    amt = format_krw(row.get("dual_krw"))
    if amt:
        bits.append(f"추정 {amt}.")
    if row.get("pe_buy"):
        pe = _int(row.get("pe_net")) or 0
        bits.append(f"사모도 {pe:+,}주 순매수.")
        streak = _int(row.get("pe_streak")) or 0
        if streak >= 2:
            bits.append(f"{streak}일 연속.")
    if row.get("in_quant") and row.get("quant_rank") not in (None, ""):
        bits.append(f"퀀트 {row.get('quant_rank')}위와 겹칩니다.")
    else:
        bits.append("퀀트 점수와 무관한 수급 후보입니다.")
    bits.append("주수×종가 추정이라 실제 체결금액이 아닙니다.")
    return " ".join(bits)


def flow_comment_short(row: dict[str, Any]) -> str:
    foreign = _int(row.get("foreign_net")) or 0
    inst = _int(row.get("institution_net")) or 0
    bits = [f"외인 {foreign:+,}", f"기관 {inst:+,}"]
    amt = format_krw(row.get("dual_krw"))
    if amt:
        bits.append(amt)
    if row.get("dual_pe_retail"):
        bits.append("사모·개인이탈")
    elif row.get("pe_buy"):
        bits.append("사모 동반")
    if row.get("other_corp_buy"):
        bits.append("기타법인")
    return " · ".join(bits)


def pe_comment(row: dict[str, Any]) -> str:
    pe = _int(row.get("pe_net")) or 0
    streak = _int(row.get("pe_streak")) or 0
    bits = [f"토스 분류 사모펀드가 {pe:+,}주 순매수했습니다."]
    if streak >= 2:
        bits.append(f"{streak}일 연속이라 매집으로 봅니다.")
    amt = format_krw(row.get("pe_krw"))
    if amt:
        bits.append(f"추정 {amt}.")
    bits.append("기관 전체와 다를 수 있으며 Quant에 넣지 않습니다.")
    return " ".join(bits)


def pe_comment_short(row: dict[str, Any]) -> str:
    pe = _int(row.get("pe_net")) or 0
    bits = [f"사모 {pe:+,}주"]
    streak = _int(row.get("pe_streak")) or 0
    if streak >= 2:
        bits.append(f"{streak}일 연속")
    amt = format_krw(row.get("pe_krw"))
    if amt:
        bits.append(amt)
    return " · ".join(bits)


def empty_comment(row: dict[str, Any]) -> str:
    bits: list[str] = []
    if row.get("comeback"):
        bits.append("앞선 날은 팔고 최근 1~2일은 다시 산 복귀 조짐입니다.")
    elif row.get("empty"):
        bits.append("외인·기관이 같이 순매도했고, 연속 매도·보유대비 이탈 비율로 빈집으로 봤습니다.")
    elif row.get("empty_raw"):
        bits.append("외인·기관 쌍매도는 있으나 규모가 작아 빈집으로 보지 않았습니다.")
    elif row.get("retail_absorb"):
        bits.append("기관·외인 매도 물량을 개인이 받았습니다.")
    else:
        bits.append("외인 지분이 낮거나 이탈 흔적이 있는 빈집 후보입니다.")
    rate = format_pct(row.get("foreign_holding_rate"), 1)
    if rate:
        bits.append(f"외인 지분 {rate}.")
    streak = _int(row.get("sell_streak")) or 0
    if streak:
        bits.append(f"연속 매도 {streak}일.")
    if row.get("empty"):
        amt = format_krw(row.get("empty_krw"))
        if amt:
            bits.append(f"이탈 추정 {amt}.")
    if row.get("retail_absorb") and not any("개인" in b for b in bits):
        bits.append("개인이 그 물량을 받았습니다.")
    bits.append("빈집 필터이며 매수 지시가 아닙니다.")
    return " ".join(bits)


def empty_comment_short(row: dict[str, Any]) -> str:
    if row.get("comeback"):
        tag = "복귀"
    elif row.get("empty"):
        tag = "쌍매도"
    elif row.get("retail_absorb"):
        tag = "개인받음"
    else:
        tag = "저비중"
    bits = [tag]
    rate = format_pct(row.get("foreign_holding_rate"), 1)
    if rate:
        bits.append(f"외인 {rate}")
    streak = _int(row.get("sell_streak")) or 0
    if streak:
        bits.append(f"{streak}일")
    if row.get("empty"):
        amt = format_krw(row.get("empty_krw"))
        if amt:
            bits.append(amt)
    return " · ".join(bits)


def trade_comment(row: dict[str, Any]) -> str:
    setups = [str(x) for x in (row.get("setups") or []) if x]
    if row.get("in_quant") and row.get("quant_rank") not in (None, ""):
        where = f"퀀트 {row.get('quant_rank')}위와 겹칩니다"
    else:
        where = "퀀트 TOP100 밖입니다"
    setup = "·".join(setups) if setups else "수급 셋업 없음"
    bits = [f"{where}. {setup}."]
    ta = row.get("ta") if isinstance(row.get("ta"), dict) else {}
    labels = [str(x) for x in (ta.get("labels") or []) if x]
    if labels:
        bits.append("기술: " + ", ".join(labels[:3]) + ".")
    bits.append("일봉 수급+기술 연구이며 주문이 아닙니다.")
    return " ".join(bits)


def trade_comment_short(row: dict[str, Any]) -> str:
    setups = [str(x) for x in (row.get("setups") or []) if x]
    bits = ["퀀트 겹침" if row.get("in_quant") else "퀀트 밖"]
    if setups:
        bits.append("·".join(setups[:3]))
    ta = row.get("ta") if isinstance(row.get("ta"), dict) else {}
    labels = [str(x) for x in (ta.get("labels") or []) if x]
    if labels:
        bits.append(labels[0])
    return " · ".join(bits)


def toss_comment(row: dict[str, Any], label: str) -> str:
    rank = row.get("rank")
    title = label or "시세 랭킹"
    head = f"토스 {title}"
    if rank not in (None, ""):
        head += f" {rank}위"
    head += "입니다."
    chg = _num(row.get("change_rate"))
    if chg is not None:
        pct = chg * (100 if abs(chg) <= 1 else 1)
        head += f" 등락 {pct:+.2f}%."
    amt = format_krw(row.get("trading_amount"))
    if amt:
        head += f" 거래대금 {amt}."
    head += " 시세 랭킹일 뿐 재무 Quant과 무관합니다."
    return head


def toss_comment_short(row: dict[str, Any], label: str) -> str:
    rank = row.get("rank")
    title = label or "시세"
    head = f"{title} {rank}위" if rank not in (None, "") else title
    chg = _num(row.get("change_rate"))
    if chg is not None:
        pct = chg * (100 if abs(chg) <= 1 else 1)
        head += f" · {pct:+.1f}%"
    return head


def us13f_comment(row: dict[str, Any], mode: str) -> str:
    filer = str(row.get("filer_ko") or row.get("name_ko") or row.get("filer") or row.get("name") or "펀드")
    issuer = str(row.get("issuer_ko") or row.get("issuer") or "이 종목")
    usd = _usd(row.get("value") if mode != "exits" else row.get("prev_value"))
    delta = _usd(row.get("value_delta"))
    weight = format_pct(row.get("weight"), 1)
    if mode == "new":
        bits = [f"{_iga(filer)} 이번 분기 {_ul(issuer)} 신규 편입했습니다."]
    elif mode == "increases":
        bits = [f"{_iga(filer)} {_ul(issuer)} 더 담았습니다."]
    elif mode == "exits":
        bits = [f"{_iga(filer)} {_ul(issuer)} 청산했습니다."]
    elif mode == "common":
        n = _int(row.get("n_filers")) or 0
        bits = [f"추적 펀드 {n}곳이 같이 보유한 공통 종목입니다."]
    elif mode == "trend":
        score = row.get("score")
        bits = [f"신규·확대에서 청산·축소를 뺀 점수 {score}입니다."]
    elif mode == "weights":
        bits = [f"{filer} 포트폴리오에서 {issuer} 비중입니다."]
    else:
        bits = [f"{filer}의 13F 보유입니다."]
    if usd:
        bits.append(f"금액 {usd}.")
    if delta and mode in {"increases", "exits", "trend", "new"}:
        bits.append(f"변화 {delta}.")
    if weight and mode in {"new", "increases", "weights"}:
        bits.append(f"펀드 내 {weight}.")
    bits.append("분기 말 스냅샷+최대 45일 시차이며 Quant에 넣지 않습니다.")
    return " ".join(bits)


def us13f_comment_short(row: dict[str, Any], mode: str) -> str:
    filer = str(row.get("filer_ko") or row.get("name_ko") or row.get("filer") or row.get("name") or "")
    usd = _usd(row.get("value") if mode != "exits" else row.get("prev_value"))
    action = {"new": "신규", "increases": "확대", "exits": "청산", "common": "공통", "trend": "트렌드", "weights": "비중"}.get(mode, mode)
    bits = [x for x in (filer, action) if x]
    if mode == "common":
        n = _int(row.get("n_filers"))
        if n:
            bits = [f"{n}곳 공통"]
    if usd:
        bits.append(usd)
    weight = format_pct(row.get("weight"), 1)
    if weight and mode in {"new", "increases", "weights"}:
        bits.append(weight)
    return " · ".join(bits) or "13F"


def watch_comment(row: dict[str, Any]) -> str:
    note = str(row.get("note") or "").strip()
    head = "직접 저장한 관심종목입니다. 점수나 수급 순위가 아닙니다."
    if note:
        head += f" 메모: {note}"
    return head


def annotate_quant_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from kr_quant.sunzi.fa import annotate_fa

    annotate_fa(rows)
    for row in rows:
        if isinstance(row, dict):
            row["comment"] = quant_comment(row)
            row["comment_short"] = quant_comment_short(row)
            if row.get("fa_label"):
                row["comment_short"] = f"{row['comment_short']} · {row['fa_label']}"
    return rows


def annotate_flow(payload: dict[str, Any]) -> dict[str, Any]:
    payload["selection"] = payload.get("selection") or SELECTION["flow"]
    payload["selection_empty"] = payload.get("selection_empty") or SELECTION["empty"]
    payload["selection_trade"] = payload.get("selection_trade") or SELECTION["trade"]
    for key in (
        "rows",
        "dual",
        "private_equity",
        "dual_pe",
        "dual_pe_retail",
        "other_corp",
        "pension",
        "empty",
        "comeback",
        "low_foreign",
        "trading",
        "trading_ex_quant",
    ):
        for row in payload.get(key) or []:
            if not isinstance(row, dict):
                continue
            row["comment_flow"] = flow_comment(row)
            row["comment_flow_short"] = flow_comment_short(row)
            row["comment_pe"] = pe_comment(row)
            row["comment_pe_short"] = pe_comment_short(row)
            row["comment_empty"] = empty_comment(row)
            row["comment_empty_short"] = empty_comment_short(row)
            row["comment_trade"] = trade_comment(row)
            row["comment_trade_short"] = trade_comment_short(row)
    return payload


def annotate_13f(payload: dict[str, Any]) -> dict[str, Any]:
    payload["selection"] = payload.get("selection") or SELECTION["us13f"]
    mapping = {
        "new": "new",
        "increases": "increases",
        "exits": "exits",
        "common": "common",
        "trend": "trend",
    }
    for key, mode in mapping.items():
        for row in payload.get(key) or []:
            if isinstance(row, dict):
                row["comment"] = us13f_comment(row, mode)
                row["comment_short"] = us13f_comment_short(row, mode)
    for filer in payload.get("filers") or []:
        if not isinstance(filer, dict):
            continue
        n = filer.get("n")
        filer["comment"] = (
            f"{filer.get('name_ko') or filer.get('name') or '펀드'} 13F입니다. "
            f"종목 {n or '—'}개. 분기 말 보유이며 Quant에 넣지 않습니다."
        )
        for row in filer.get("top") or []:
            if isinstance(row, dict):
                merged = {**row, "filer_ko": filer.get("name_ko"), "name": filer.get("name")}
                row["comment"] = us13f_comment(merged, "weights")
                row["comment_short"] = us13f_comment_short(merged, "weights")
    return payload


def annotate_toss_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for group in groups:
        label = str(group.get("label") or "")
        for row in group.get("rows") or []:
            if isinstance(row, dict):
                row["comment"] = toss_comment(row, label)
                row["comment_short"] = toss_comment_short(row, label)
    return groups
