from __future__ import annotations

from typing import Any
import math


def _i(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError, OverflowError):
        return 0


def _f(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def net_of(block: Any) -> int:
    if not isinstance(block, dict):
        return 0
    return _i(block.get("netBuyVolume"))


def _sum_net(rows: list[dict[str, Any]], key: str) -> int:
    return sum(net_of(r.get(key)) for r in rows)


def _holding_rate(row: dict[str, Any]) -> float | None:
    hold = row.get("foreignerHolding")
    if not isinstance(hold, dict):
        return None
    return _f(hold.get("holdingRate"))


def _breakdown_net(row: dict[str, Any], key: str) -> int:
    inst = row.get("institution") if isinstance(row.get("institution"), dict) else {}
    br = inst.get("breakdown") or {}
    return net_of(br.get(key))


def _party_net(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in row and isinstance(row.get(key), dict):
            return net_of(row.get(key))
    inst = row.get("institution") if isinstance(row.get("institution"), dict) else {}
    br = inst.get("breakdown") if isinstance(inst.get("breakdown"), dict) else {}
    for key in keys:
        if key in br:
            return net_of(br.get(key))
    return 0


def summarize_records(records: list[dict[str, Any]], days: int = 5) -> dict[str, Any]:
    rows = [r for r in records if isinstance(r, dict)][: max(1, days)]
    # Retain proof of missing source fields before legacy display conversion
    # turns them into zero. Zero is valid only if explicitly supplied.
    source_complete = bool(rows)
    for row in rows:
        for party in ('foreigner', 'institution'):
            block = row.get(party)
            value = block.get('netBuyVolume') if isinstance(block, dict) else None
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(str(value).replace(',', '')))
            except (TypeError, ValueError):
                valid = False
            source_complete = source_complete and valid
    foreign = _sum_net(rows, "foreigner")
    institution = _sum_net(rows, "institution")
    individual = _sum_net(rows, "individual")
    pe = sum(_breakdown_net(row, "privateEquityFund") for row in rows)
    trust = sum(_breakdown_net(row, "trust") + _breakdown_net(row, "investmentTrust") for row in rows)
    pension = sum(_breakdown_net(row, "pensionFund") + _breakdown_net(row, "pension") for row in rows)
    other_corp = sum(
        _party_net(row, "otherCorporation", "other_corporation", "otherCorp", "corporation") for row in rows
    )
    pe_streak = 0
    for row in rows:
        if _breakdown_net(row, "privateEquityFund") > 0:
            pe_streak += 1
        else:
            break

    recent_n = 2 if len(rows) >= 4 else 1
    recent = rows[:recent_n]
    prior = rows[recent_n:]
    recent_foreign = _sum_net(recent, "foreigner")
    recent_institution = _sum_net(recent, "institution")
    prior_foreign = _sum_net(prior, "foreigner") if prior else 0
    prior_institution = _sum_net(prior, "institution") if prior else 0
    comeback = bool(prior) and prior_foreign < 0 and prior_institution < 0 and recent_foreign > 0 and recent_institution > 0

    sell_streak = 0
    for row in rows:
        if net_of(row.get("foreigner")) < 0 and net_of(row.get("institution")) < 0:
            sell_streak += 1
        else:
            break

    latest = rows[0] if rows else {}
    hold = latest.get("foreignerHolding") if isinstance(latest, dict) else None
    foreign_rate = _holding_rate(latest) if latest else None
    foreign_qty = _i((hold or {}).get("holdingQuantity")) if isinstance(hold, dict) else 0
    rates = [rate for rate in (_holding_rate(r) for r in rows) if rate is not None]
    foreign_rate_chg = (rates[0] - rates[-1]) if len(rates) >= 2 else None

    empty_raw = foreign < 0 and institution < 0
    smart_sell = abs(min(foreign, 0)) + abs(min(institution, 0))
    total_abs = abs(foreign) + abs(institution) + abs(individual) + abs(other_corp)
    empty_share = (smart_sell / total_abs) if total_abs else 0.0
    holding_exit = None
    if foreign_qty and foreign_qty > 0 and foreign < 0:
        holding_exit = abs(foreign) / float(foreign_qty)
    empty = bool(
        empty_raw
        and (
            sell_streak >= 2
            or smart_sell >= 20_000
            or (holding_exit is not None and holding_exit >= 0.005 and smart_sell >= 100)
        )
    )
    dual = foreign > 0 and institution > 0
    pe_buy = pe > 0
    dual_pe = dual and pe_buy
    dual_pe_retail = dual_pe and individual < 0
    first = rows[-1]["date"] if rows else None
    last = rows[0]["date"] if rows else None
    from kr_quant.flow.events import daily_from_toss_records, direction_turn, signed_streak

    daily = daily_from_toss_records(rows, days=len(rows))
    foreign_streak = signed_streak([d["foreign"] for d in daily])
    inst_streak = signed_streak([d["institution"] for d in daily])
    dual_day = [d["foreign"] if d["foreign"] > 0 and d["institution"] > 0 else (d["foreign"] if d["foreign"] < 0 and d["institution"] < 0 else 0.0) for d in daily]
    dual_streak = signed_streak(dual_day)
    turn_dual = direction_turn(dual_day, min_days=5)
    return {
        "days": len(rows),
        "source_complete": source_complete,
        "from": first,
        "to": last,
        "foreign_net": foreign,
        "institution_net": institution,
        "individual_net": individual,
        "pe_net": pe,
        "trust_net": trust,
        "pension_net": pension,
        "other_corp_net": other_corp,
        "dual": dual,
        "pe_buy": pe_buy,
        "pe_streak": pe_streak,
        "pe_accum": pe > 0 and pe_streak >= 2,
        "dual_pe": dual_pe,
        "dual_pe_retail": dual_pe_retail,
        "other_corp_buy": other_corp > 0,
        "pension_buy": pension > 0,
        "empty_raw": empty_raw,
        "empty_share": round(empty_share, 4),
        "holding_exit": None if holding_exit is None else round(holding_exit, 4),
        "empty": empty,
        "retail_absorb": empty_raw and individual > 0,
        "comeback": comeback,
        "sell_streak": sell_streak,
        "foreign_streak": foreign_streak["days"] if foreign_streak["direction"] != "FLAT" else 0,
        "foreign_direction": foreign_streak["direction"],
        "institution_streak": inst_streak["days"] if inst_streak["direction"] != "FLAT" else 0,
        "institution_direction": inst_streak["direction"],
        "dual_streak": dual_streak["days"] if dual_streak["direction"] != "FLAT" else 0,
        "dual_direction": dual_streak["direction"],
        "turn_dual": turn_dual,
        "daily": daily,
        "recent_foreign_net": recent_foreign,
        "recent_institution_net": recent_institution,
        "foreign_holding_rate": foreign_rate,
        "foreign_holding_qty": foreign_qty,
        "foreign_rate_chg": foreign_rate_chg,
        "used_in_quant": False,
    }


def classify_setups(row: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if row.get("dual"):
        tags.append("쌍끌이")
    if row.get("pe_accum"):
        tags.append("사모매집")
    elif row.get("pe_buy"):
        tags.append("사모순매수")
    if row.get("empty"):
        tags.append("빈집")
    if row.get("comeback"):
        tags.append("복귀")
    if row.get("dual") and row.get("pe_buy"):
        tags.append("쌍끌이+사모")
    if row.get("dual_pe_retail"):
        tags.append("쌍끌이+사모+개인이탈")
    if row.get("other_corp_buy"):
        tags.append("기타법인")
    if row.get("pension_buy") and (row.get("dual") or row.get("pe_buy")):
        tags.append("연기금")
    return tags


def setup_notional(row: dict[str, Any]) -> float:
    vals: list[float] = []
    if row.get("dual"):
        vals.append(float(row.get("dual_krw") or 0))
    if row.get("pe_buy"):
        vals.append(float(row.get("pe_krw") or 0))
    if row.get("empty"):
        vals.append(float(row.get("empty_krw") or 0))
    return max(vals) if vals else 0.0


def ta_match(row: dict[str, Any], ta_mode: str = "") -> bool:
    mode = (ta_mode or "").strip()
    if not mode or mode in {"any", "all"}:
        return True
    ta = row.get("ta") if isinstance(row.get("ta"), dict) else {}
    cloud = ta.get("ichi_cloud")
    if mode == "stoch_os":
        return bool(ta.get("stoch_over_sold"))
    if mode == "stoch_ob":
        return bool(ta.get("stoch_over_bought"))
    if mode == "stoch_golden":
        return bool(ta.get("stoch_golden"))
    if mode == "ichi_above":
        return cloud == "above"
    if mode == "ichi_below":
        return cloud == "below"
    if mode == "ichi_tk":
        return bool(ta.get("ichi_tk_up") or ta.get("ichi_tk_golden"))
    if mode == "ta_bull":
        return ta.get("stoch_bias") == "bull" or ta.get("ichi_bias") == "bull" or cloud == "above" or bool(ta.get("stoch_golden"))
    if mode == "confluence":
        flow_long = bool(row.get("dual") or row.get("pe_buy") or row.get("comeback"))
        ta_long = bool(
            ta.get("stoch_golden")
            or ta.get("stoch_over_sold")
            or cloud == "above"
            or ta.get("ichi_tk_golden")
        )
        return flow_long and ta_long
    return True


def filter_trading(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
    mode: str = "setup",
    exclude_quant: bool = True,
    min_krw: float = 0,
    ta_mode: str = "",
) -> list[dict[str, Any]]:
    q = query.strip().lower()
    out: list[dict[str, Any]] = []
    for row in rows:
        if exclude_quant and row.get("in_quant"):
            continue
        hay = f"{row.get('ticker') or ''} {row.get('company') or ''}".lower()
        if q and q not in hay:
            continue
        dual = bool(row.get("dual"))
        pe = bool(row.get("pe_buy") or row.get("pe_accum"))
        empty = bool(row.get("empty"))
        comeback = bool(row.get("comeback"))
        if mode == "setup" and not (dual or pe or empty or comeback):
            continue
        if mode == "dual" and not dual:
            continue
        if mode == "pe" and not pe:
            continue
        if mode == "empty" and not empty:
            continue
        if mode == "comeback" and not comeback:
            continue
        if mode == "dual_pe" and not (dual and pe):
            continue
        if mode == "dual_pe_retail" and not row.get("dual_pe_retail"):
            continue
        if mode == "other_corp" and not row.get("other_corp_buy"):
            continue
        if mode == "pension" and not row.get("pension_buy"):
            continue
        if min_krw and setup_notional(row) < float(min_krw):
            continue
        if not ta_match(row, ta_mode):
            continue
        out.append(row)
    out.sort(key=setup_notional, reverse=True)
    return out


def search_empty_houses(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
    mode: str = "empty",
    max_foreign_rate: float | None = None,
    min_exit_krw: float = 0,
) -> list[dict[str, Any]]:
    q = query.strip().lower()
    out: list[dict[str, Any]] = []
    rate_cap = max_foreign_rate
    if mode == "low_foreign" and rate_cap is None:
        rate_cap = 0.05
    for row in rows:
        hay = f"{row.get('ticker') or ''} {row.get('company') or ''}".lower()
        if q and q not in hay:
            continue
        if mode == "empty" and not row.get("empty"):
            continue
        if mode == "comeback" and not row.get("comeback"):
            continue
        if mode == "retail" and not row.get("retail_absorb"):
            continue
        if mode == "low_foreign":
            rate = row.get("foreign_holding_rate")
            if rate is None or float(rate) > float(rate_cap or 0.05):
                continue
        elif rate_cap is not None:
            rate = row.get("foreign_holding_rate")
            if rate is not None and float(rate) > float(rate_cap):
                continue
        if min_exit_krw and float(row.get("empty_krw") or 0) < float(min_exit_krw):
            continue
        out.append(row)
    if mode == "low_foreign":
        out.sort(key=lambda r: float(r.get("foreign_holding_rate") if r.get("foreign_holding_rate") is not None else 99))
    else:
        out.sort(key=lambda r: float(r.get("empty_krw") or 0), reverse=True)
    return out
