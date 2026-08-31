"""연속·동반·방향전환. Overlay only. Never invent 연기금 bulk rank."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _as_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).replace(".", "-").replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _num(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def signed_streak(nets: list[float]) -> dict[str, Any]:
    """`nets` newest-first. Zero breaks the streak."""
    if not nets:
        return {"days": 0, "direction": "FLAT", "cumulative": 0.0, "capped": False}
    first = nets[0]
    if first > 0:
        sign = 1
        direction = "BUY"
    elif first < 0:
        sign = -1
        direction = "SELL"
    else:
        return {"days": 0, "direction": "FLAT", "cumulative": 0.0, "capped": False}
    days = 0
    acc = 0.0
    for value in nets:
        cur = 1 if value > 0 else -1 if value < 0 else 0
        if cur != sign:
            break
        days += 1
        acc += value
    return {
        "days": days,
        "direction": direction,
        "cumulative": acc,
        "capped": days == len(nets) and days > 0,
    }


def direction_turn(nets: list[float], min_days: int = 5) -> dict[str, Any] | None:
    """Newest-first. Prior streak >= min_days then today opposite sign."""
    if len(nets) < min_days + 1:
        return None
    today = nets[0]
    today_sign = 1 if today > 0 else -1 if today < 0 else 0
    if today_sign == 0:
        return None
    prior = signed_streak(nets[1:])
    if prior["days"] < min_days or prior["direction"] == "FLAT":
        return None
    prior_sign = 1 if prior["direction"] == "BUY" else -1
    if today_sign != -prior_sign:
        return None
    return {
        "from": prior["direction"],
        "to": "BUY" if today_sign > 0 else "SELL",
        "prior_days": prior["days"],
        "prior_cumulative": prior["cumulative"],
        "today": today,
        "capped": prior["capped"],
    }


def window_sums(nets: list[float], windows: tuple[int, ...] = (5, 20, 60, 90)) -> dict[str, Any]:
    """Newest-first. Trading-day windows, not calendar."""
    out: dict[str, Any] = {}
    for width in windows:
        chunk = nets[:width]
        out[f"w{width}"] = round(sum(chunk), 4)
        out[f"w{width}_n"] = len(chunk)
        out[f"w{width}_capped"] = len(nets) < width
    return out


def cumulative_table(events: list[dict[str, Any]], window: int = 20) -> list[dict[str, Any]]:
    key = f"w{window}"
    rows = [e for e in events if isinstance(e, dict) and e.get(key) is not None]
    rows.sort(key=lambda r: abs(float(r.get(key) or 0)), reverse=True)
    return rows


def daily_chart(rows: list[dict[str, Any]], *, max_days: int = 90) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = _as_date(row.get("trade_date") or row.get("date"))
        if not day:
            continue
        slot = by_date.setdefault(day, {"date": day})
        kind = str(row.get("investor_type") or "")
        if kind:
            slot[kind] = _num(row.get("net_value") if row.get("net_value") is not None else row.get("net_qty"))
        if row.get("foreign") is not None:
            slot["FOREIGN"] = _num(row.get("foreign"))
        if row.get("institution") is not None:
            slot["INSTITUTION_TOTAL"] = _num(row.get("institution"))
    ordered = sorted(by_date.values(), key=lambda r: str(r.get("date") or ""))
    return ordered[-max_days:]


def sample_rebalance(rows: list[dict[str, Any]], names: dict[str, str] | None = None) -> dict[str, Any]:
    """Coverage sample only. Not all-market pension rebalancing."""
    names = names or {}
    last = None
    for row in rows:
        day = _as_date(row.get("trade_date"))
        if day and (last is None or day > last):
            last = day
    if not last:
        return {
            "used_in_quant": False,
            "sample": True,
            "empty": True,
            "note": "공식 수급 행이 없어 표본 리밸런싱을 못 그립니다.",
        }
    types = {str(r.get("investor_type") or "") for r in rows}
    party = "FUND" if "FUND" in types else "INSTITUTION_TOTAL"
    party_ko = "기금" if party == "FUND" else "기관합계"
    latest = [
        r
        for r in rows
        if _as_date(r.get("trade_date")) == last and str(r.get("investor_type") or "") == party
    ]
    scored = []
    for row in latest:
        code = "".join(ch for ch in str(row.get("ticker") or "") if ch.isdigit()).zfill(6)
        net = _num(row.get("net_value") if row.get("net_value") is not None else row.get("net_qty"))
        scored.append({"ticker": code, "company": names.get(code, code), "net": net})
    buys = sorted([x for x in scored if x["net"] > 0], key=lambda x: x["net"], reverse=True)
    sells = sorted([x for x in scored if x["net"] < 0], key=lambda x: x["net"])
    return {
        "used_in_quant": False,
        "sample": True,
        "empty": False,
        "as_of": last,
        "party": party,
        "party_ko": party_ko,
        "n": len(scored),
        "buy_n": len(buys),
        "sell_n": len(sells),
        "net_sum": round(sum(x["net"] for x in scored), 2),
        "top_buy": buys[:5],
        "top_sell": sells[:5],
        "note": (
            f"{party_ko} 당일 순매수는 관심종목·고유동성 표본 {len(scored)}종목입니다. "
            "전시장 연기금 리밸런싱이 아니며 Quant에 넣지 않습니다."
        ),
    }


def same_sign(a: float, b: float) -> bool:
    if a == 0 or b == 0:
        return False
    return (a > 0) == (b > 0)


def _newest_first(points: list[dict[str, Any]], value_key: str = "net") -> list[float]:
    ordered = sorted(points, key=lambda p: str(p.get("date") or ""), reverse=True)
    return [_num(p.get(value_key)) for p in ordered]


def ticker_events(
    ticker: str,
    company: str | None,
    series: dict[str, list[dict[str, Any]]],
    *,
    paired_a: str,
    paired_b: str,
    min_turn: int = 5,
    source: str,
    party_label: str,
) -> dict[str, Any]:
    """`series` maps party -> [{date, net}, ...]"""
    primary = series.get(paired_a) or []
    secondary = series.get(paired_b) or []
    a_nets = _newest_first(primary)
    streak = signed_streak(a_nets)
    turn = direction_turn(a_nets, min_days=min_turn)
    last_a = a_nets[0] if a_nets else 0.0
    last_b = _newest_first(secondary)[0] if secondary else 0.0
    last_date = None
    if primary:
        last_date = max(str(p.get("date") or "") for p in primary)
    windows = window_sums(a_nets)
    return {
        "ticker": str(ticker).zfill(6),
        "company": company or ticker,
        "party": paired_a,
        "party_ko": party_label,
        "days": streak["days"],
        "direction": streak["direction"],
        "cumulative": streak["cumulative"],
        "capped": streak["capped"],
        **windows,
        "today_a": last_a,
        "today_b": last_b,
        "paired": same_sign(last_a, last_b),
        "paired_direction": (
            "BUY" if last_a > 0 and last_b > 0 else "SELL" if last_a < 0 and last_b < 0 else None
        ),
        "turn": turn,
        "last_date": last_date,
        "source": source,
        "used_in_quant": False,
    }


def tables_from_rows(
    rows: list[dict[str, Any]],
    *,
    min_streak: int = 2,
    min_turn: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    consecutive: list[dict[str, Any]] = []
    paired: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("days") or 0) >= min_streak and row.get("direction") in {"BUY", "SELL"}:
            consecutive.append(row)
        if row.get("paired"):
            paired.append(row)
        if row.get("turn"):
            turns.append({**row, **{f"turn_{k}": v for k, v in dict(row["turn"]).items()}})
    consecutive.sort(key=lambda r: (int(r.get("days") or 0), abs(float(r.get("cumulative") or 0))), reverse=True)
    paired.sort(key=lambda r: abs(float(r.get("today_a") or 0)) + abs(float(r.get("today_b") or 0)), reverse=True)
    turns.sort(key=lambda r: int(r.get("turn_prior_days") or r.get("prior_days") or 0), reverse=True)
    return {"consecutive": consecutive, "paired": paired, "turns": turns}


def from_official_rows(
    rows: list[dict[str, Any]],
    names: dict[str, str] | None = None,
    min_turn: int = 5,
) -> dict[str, Any]:
    """KIS daily rows. Pair 기금+외인 when FUND exists, else 기관합계+외인. Never call FUND 국민연금."""
    names = names or {}
    by_ticker: dict[str, dict[str, list[dict[str, Any]]]] = {}
    types: set[str] = set()
    for row in rows:
        code = "".join(ch for ch in str(row.get("ticker") or "") if ch.isdigit()).zfill(6)
        kind = str(row.get("investor_type") or "")
        if not code or not kind:
            continue
        types.add(kind)
        by_ticker.setdefault(code, {}).setdefault(kind, []).append(
            {"date": _as_date(row.get("trade_date")), "net": _num(row.get("net_value") if row.get("net_value") is not None else row.get("net_qty"))}
        )
    pair_a = "FUND" if "FUND" in types else "INSTITUTION_TOTAL"
    pair_b = "FOREIGN"
    label = "기금" if pair_a == "FUND" else "기관합계"
    events: list[dict[str, Any]] = []
    for code, series in by_ticker.items():
        events.append(
            ticker_events(
                code,
                names.get(code),
                series,
                paired_a=pair_a,
                paired_b=pair_b,
                min_turn=min_turn,
                source="KIS",
                party_label=label,
            )
        )
    tables = tables_from_rows(events, min_turn=min_turn)
    return {
        "used_in_quant": False,
        "source": "KIS",
        "cum5": cumulative_table(events, 5),
        "cum20": cumulative_table(events, 20),
        "cum60": cumulative_table(events, 60),
        "pair": f"{label}+외인",
        "pair_note": (
            "기금은 원천 라벨 그대로입니다. 국민연금·연기금이라고 부르지 않습니다."
            if pair_a == "FUND"
            else "KIS 기금 행이 없어 기관합계+외인으로 동반을 봅니다."
        ),
        "tickers": len(by_ticker),
        **tables,
    }


def daily_from_toss_records(records: list[dict[str, Any]], days: int = 20) -> list[dict[str, Any]]:
    from kr_quant.flow.investor import _breakdown_net, net_of

    out: list[dict[str, Any]] = []
    for rec in records[: max(1, days)]:
        if not isinstance(rec, dict):
            continue
        holding = rec.get("foreignerHolding") if isinstance(rec.get("foreignerHolding"), dict) else {}
        try:
            holding_rate = float(str(holding.get("holdingRate")).replace(",", ""))
        except (TypeError, ValueError):
            holding_rate = None
        out.append(
            {
                "date": _as_date(rec.get("date")),
                "foreign": net_of(rec.get("foreigner")),
                "institution": net_of(rec.get("institution")),
                "individual": net_of(rec.get("individual")),
                "pension": _breakdown_net(rec, "pensionFund") + _breakdown_net(rec, "pension"),
                "pe": _breakdown_net(rec, "privateEquityFund"),
                "foreign_holding_rate": holding_rate,
            }
        )
    return out


def from_toss_cache_rows(rows: list[dict[str, Any]], min_turn: int = 5) -> dict[str, Any]:
    """Toss cache. Pair is 기관+외인. Toss pensionFund is not 국민연금 확정."""
    events: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        daily = row.get("daily")
        if not isinstance(daily, list) or not daily:
            skipped += 1
            continue
        series = {
            "INSTITUTION_TOTAL": [{"date": d.get("date"), "net": d.get("institution")} for d in daily],
            "FOREIGN": [{"date": d.get("date"), "net": d.get("foreign")} for d in daily],
        }
        events.append(
            ticker_events(
                str(row.get("ticker") or ""),
                row.get("company"),
                series,
                paired_a="INSTITUTION_TOTAL",
                paired_b="FOREIGN",
                min_turn=min_turn,
                source="TOSS",
                party_label="기관합계",
            )
        )
    tables = tables_from_rows(events, min_turn=min_turn)
    return {
        "used_in_quant": False,
        "source": "TOSS",
        "cum5": cumulative_table(events, 5),
        "cum20": cumulative_table(events, 20),
        "cum60": cumulative_table(events, 60),
        "pair": "기관+외인",
        "pair_note": (
            "토스 일별 투자자 매매입니다. 기관+외인 동반이며 연기금 전종목 순위가 아닙니다. "
            "토스 분류 연기금 수치는 국민연금 단독이 아닙니다."
        ),
        "tickers": len(events),
        "skipped_no_daily": skipped,
        **tables,
    }
