from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.factors.share_adj import _levels
from kr_quant.flow.investor import classify_setups, filter_trading, search_empty_houses, summarize_records
from kr_quant.flow.universe import build_universe, quant_rank_map, quant_top_map, resolve_names
from kr_quant.ingest.tossinvest import get_investor_trading
from kr_quant.settings import Settings
from kr_quant.timing.snapshot import attach_technicals

FLOW_SCHEMA = 4


def cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "investor_flow.json"


def _load_cache(root: Path) -> dict[str, Any] | None:
    path = cache_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_cache(root: Path, payload: dict[str, Any]) -> None:
    path = cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def candidate_tickers(settings: Settings, extra: list[str] | None = None) -> list[tuple[str, str]]:
    rows, _meta = build_universe(settings, extra=extra, limit=160)
    return rows


def _fwd_return(hist: pd.DataFrame, start: date, horizon: int) -> float | None:
    if hist is None or hist.empty:
        return None
    work = hist.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work[work["trade_date"] >= start].sort_values("trade_date")
    if work.empty:
        return None
    work = work.sort_values("trade_date")
    if len(work) < 2:
        return None
    from kr_quant.factors.share_adj import _levels

    levels = _levels(work)
    if len(levels) < min(3, horizon):
        if len(levels) < 2:
            return None
        start_lv, end_lv = levels[0][1], levels[-1][1]
        return None if start_lv <= 0 else end_lv / start_lv - 1.0
    # return from first day in window to +horizon if we have that many trading days
    if len(levels) > horizon:
        start_lv, end_lv = levels[0][1], levels[horizon][1]
        return None if start_lv <= 0 else end_lv / start_lv - 1.0
    start_lv, end_lv = levels[0][1], levels[-1][1]
    return None if start_lv <= 0 else end_lv / start_lv - 1.0


def analyze_hit_rate(rows: list[dict[str, Any]], key: str = "ret_5d") -> dict[str, Any]:
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    if not vals:
        return {"n": 0, "hit": None, "avg": None, "median": None}
    hit = sum(1 for v in vals if v > 0) / len(vals)
    avg = sum(vals) / len(vals)
    ordered = sorted(vals)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {"n": len(vals), "hit": round(hit, 3), "avg": round(avg, 4), "median": round(median, 4)}


AMOUNT_BUCKETS: tuple[tuple[str, float], ...] = (
    ("전체", 0),
    ("10억+", 1_000_000_000),
    ("50억+", 5_000_000_000),
    ("100억+", 10_000_000_000),
)


def filter_by_min_krw(rows: list[dict[str, Any]], amount_key: str, min_krw: float = 0) -> list[dict[str, Any]]:
    if not min_krw:
        return list(rows)
    thresh = float(min_krw)
    return [r for r in rows if float(r.get(amount_key) or 0) >= thresh]


def amount_bucket_stats(rows: list[dict[str, Any]], amount_key: str, ret_key: str = "ret_5d") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label, thresh in AMOUNT_BUCKETS:
        subset = filter_by_min_krw(rows, amount_key, thresh)
        stats = analyze_hit_rate(subset, ret_key)
        out.append({"label": label, "min_krw": thresh, **stats})
    return out


def _flow_ready(cached: dict[str, Any] | None, days: int) -> bool:
    return bool(
        cached
        and cached.get("days") == days
        and cached.get("flow_schema") == FLOW_SCHEMA
        and isinstance(cached.get("empty"), list)
    )


def _flow_lists(payload: dict[str, Any]) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
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
        rows = payload.get(key)
        if isinstance(rows, list):
            out.append(rows)
    return out


def attach_company_names(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    missing: list[str] = []
    for rows in _flow_lists(payload):
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("ticker") or "").zfill(6)
            company = str(row.get("company") or "")
            if code and company in {"", code}:
                missing.append(code)
    if not missing:
        return payload
    names, types = resolve_names(settings, missing)
    for rows in _flow_lists(payload):
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("ticker") or "").zfill(6)
            if names.get(code) and str(row.get("company") or "") in {"", code}:
                row["company"] = names[code]
            if types.get(code):
                row["security_type"] = types[code]
    return payload


_QUOTE_CACHE: dict[str, Any] = {"at": 0.0, "quotes": {}}


def attach_live_quotes(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Toss last price overlay. Daily flow itself is not tick-by-tick."""
    if not settings.toss_client_id or not settings.toss_client_secret:
        payload["quotes_live"] = False
        return payload
    codes: list[str] = []
    for rows in _flow_lists(payload):
        for row in rows:
            if isinstance(row, dict) and row.get("ticker"):
                codes.append(str(row["ticker"]).zfill(6))
    uniq = list(dict.fromkeys(codes))
    now = time.time()
    quotes: dict[str, dict[str, Any]] = dict(_QUOTE_CACHE.get("quotes") or {})
    if now - float(_QUOTE_CACHE.get("at") or 0) > 120 or any(c not in quotes for c in uniq):
        from kr_quant.ingest.tossinvest import get_prices

        quotes = {}
        for i in range(0, len(uniq), 40):
            try:
                batch = get_prices(settings.toss_client_id, settings.toss_client_secret, uniq[i : i + 40])
            except Exception:  # noqa: BLE001
                batch = []
            for item in batch:
                if not isinstance(item, dict):
                    continue
                price = item.get("price") if isinstance(item.get("price"), dict) else item
                symbol = str(item.get("symbol") or item.get("code") or "")
                digits = "".join(ch for ch in symbol if ch.isdigit()).zfill(6)
                try:
                    last = float(str(price.get("lastPrice") or price.get("close") or item.get("lastPrice") or "").replace(",", "") or 0)
                except ValueError:
                    last = 0.0
                try:
                    chg = float(str(price.get("changeRate") or item.get("changeRate") or 0).replace(",", "") or 0)
                except ValueError:
                    chg = 0.0
                if abs(chg) > 1:
                    chg = chg / 100.0
                if digits:
                    quotes[digits] = {"last": last or None, "change_rate": chg, "live": True}
        _QUOTE_CACHE["at"] = now
        _QUOTE_CACHE["quotes"] = quotes
    for rows in _flow_lists(payload):
        for row in rows:
            if not isinstance(row, dict):
                continue
            q = quotes.get(str(row.get("ticker") or "").zfill(6)) or {}
            if q:
                row["last"] = q.get("last")
                row["change_rate"] = q.get("change_rate")
                row["quote_live"] = True
    payload["quotes_live"] = True
    payload["quote_note"] = "최근가는 토스 시세(장중 가능). 수급 자체는 일별 투자자 매매이며 KRX 종가 기반 추정금액·기술지표입니다."
    return payload


def _with_comments(payload: dict[str, Any]) -> dict[str, Any]:
    from kr_quant.web.comments import annotate_flow

    return annotate_flow(payload)


def load_flow(settings: Settings, days: int = 5) -> dict[str, Any]:
    cached = _load_cache(settings.root)
    if _flow_ready(cached, days):
        named = attach_company_names(cached, settings)
        return _with_comments(attach_live_quotes(attach_technicals(named, settings), settings))
    if cached and cached.get("days") == days:
        patched = attach_company_names({**cached, "need_scan": True, "used_in_quant": False}, settings)
        return _with_comments(attach_live_quotes(patched, settings))
    return {
        "configured": bool(settings.toss_client_id and settings.toss_client_secret),
        "used_in_quant": False,
        "need_scan": True,
        "days": days,
        "dual": [],
        "private_equity": [],
        "dual_pe": [],
        "dual_pe_retail": [],
        "other_corp": [],
        "pension": [],
        "empty": [],
        "comeback": [],
        "low_foreign": [],
        "trading": [],
        "trading_ex_quant": [],
        "rows": [],
        "stats": {},
        "disclaimer": "",
    }


def scan_flow(
    settings: Settings,
    *,
    days: int = 5,
    tickers: list[tuple[str, str]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cached = None if force else _load_cache(settings.root)
    if (
        _flow_ready(cached, days)
        and (time.time() - float(cached.get("fetched_at") or 0)) < 1800  # type: ignore[union-attr]
    ):
        named = attach_company_names(cached, settings)
        return _with_comments(attach_live_quotes(attach_technicals(named, settings), settings))
    if not settings.toss_client_id or not settings.toss_client_secret:
        return {"configured": False, "used_in_quant": False, "error": "토스증권 키가 필요합니다.", "rows": []}

    universe_meta: dict[str, list[str]] = {}
    if tickers is None:
        universe, universe_meta = build_universe(settings, limit=160)
    else:
        universe = tickers
    quant_top = set(quant_top_map(settings))
    ranks = quant_rank_map(settings)
    prices_path = None
    for folder in (settings.staged_dir / "live", settings.staged_dir / "demo"):
        p = folder / "prices.parquet"
        if p.exists():
            prices_path = p
            break
    prices = pd.read_parquet(prices_path) if prices_path else pd.DataFrame()

    rows: list[dict[str, Any]] = []
    errors = 0
    for code, company in universe:
        try:
            payload = get_investor_trading(settings.toss_client_id, settings.toss_client_secret, code)
            records = payload.get("records") if isinstance(payload, dict) else []
            summary = summarize_records(records if isinstance(records, list) else [], days=days)
        except Exception:  # noqa: BLE001
            errors += 1
            continue
        last = None
        hist = pd.DataFrame()
        if not prices.empty:
            hist = prices[prices["ticker"].astype(str).str.zfill(6) == code]
            start = date.fromisoformat(str(summary.get("from"))) if summary.get("from") else None
            if start and not hist.empty:
                summary["ret_5d"] = _fwd_return(hist, start, 5)
                summary["ret_20d"] = _fwd_return(hist, start, 20)
            if not hist.empty:
                last = float(pd.to_numeric(hist.sort_values("trade_date")["close"].iloc[-1], errors="coerce") or 0)
                if (not company or company == code) and "company" in hist.columns:
                    hist_name = str(hist.sort_values("trade_date")["company"].iloc[-1] or "")
                    if hist_name and hist_name != code:
                        company = hist_name
        pe_krw = None if last is None else summary["pe_net"] * last
        dual_krw = None
        empty_krw = None
        if last is not None:
            smart = summary["foreign_net"] + summary["institution_net"]
            dual_krw = smart * last
            empty_krw = -smart * last
        row = {
            "ticker": code,
            "company": company,
            **summary,
            "pe_krw": pe_krw,
            "dual_krw": dual_krw,
            "empty_krw": empty_krw,
            "other_corp_krw": None if last is None else summary["other_corp_net"] * last,
            "pension_krw": None if last is None else summary["pension_net"] * last,
            "in_quant": code in quant_top,
            "quant_rank": ranks.get(code),
            "sources": universe_meta.get(code, []),
        }
        row["setups"] = classify_setups(row)
        rows.append(row)
        time.sleep(0.05)

    dual = [r for r in rows if r.get("dual")]
    pe = [r for r in rows if r.get("pe_buy")]
    dual_pe = [r for r in rows if r.get("dual_pe")]
    dual_pe_retail = [r for r in rows if r.get("dual_pe_retail")]
    other_corp = [r for r in rows if r.get("other_corp_buy")]
    pension = [r for r in rows if r.get("pension_buy") and (r.get("dual") or r.get("pe_buy"))]
    empty = search_empty_houses(rows, mode="empty")
    comeback = search_empty_houses(rows, mode="comeback")
    low_foreign = search_empty_houses(rows, mode="low_foreign", max_foreign_rate=0.05)
    dual.sort(key=lambda r: float(r.get("dual_krw") or 0), reverse=True)
    pe.sort(key=lambda r: float(r.get("pe_krw") or 0), reverse=True)
    dual_pe.sort(key=lambda r: float(r.get("dual_krw") or 0) + float(r.get("pe_krw") or 0), reverse=True)
    dual_pe_retail.sort(key=lambda r: float(r.get("dual_krw") or 0) + float(r.get("pe_krw") or 0), reverse=True)
    other_corp.sort(key=lambda r: float(r.get("other_corp_net") or 0), reverse=True)
    pension.sort(key=lambda r: float(r.get("pension_net") or 0), reverse=True)
    out = {
        "configured": True,
        "used_in_quant": False,
        "flow_schema": FLOW_SCHEMA,
        "days": days,
        "scanned": len(rows),
        "errors": errors,
        "fetched_at": time.time(),
        "disclaimer": "순매수는 주수 기준이며 이후 수익률은 참고용입니다.",
        "dual": dual,
        "private_equity": pe,
        "dual_pe": dual_pe,
        "dual_pe_retail": dual_pe_retail,
        "other_corp": other_corp,
        "pension": pension,
        "empty": empty,
        "comeback": comeback,
        "low_foreign": low_foreign,
        "trading": filter_trading(rows, mode="setup", exclude_quant=False),
        "trading_ex_quant": filter_trading(rows, mode="setup", exclude_quant=True),
        "rows": rows,
        "stats": {
            "dual_5d": analyze_hit_rate(dual, "ret_5d"),
            "dual_20d": analyze_hit_rate(dual, "ret_20d"),
            "pe_5d": analyze_hit_rate(pe, "ret_5d"),
            "pe_20d": analyze_hit_rate(pe, "ret_20d"),
            "empty_5d": analyze_hit_rate(empty, "ret_5d"),
            "comeback_5d": analyze_hit_rate(comeback, "ret_5d"),
            "dual_pe_5d": analyze_hit_rate(dual_pe, "ret_5d"),
            "dual_pe_retail_5d": analyze_hit_rate(dual_pe_retail, "ret_5d"),
            "dual_buckets": amount_bucket_stats(dual, "dual_krw"),
            "pe_buckets": amount_bucket_stats(pe, "pe_krw"),
        },
    }
    out = attach_company_names(out, settings)
    out = attach_technicals(out, settings, prices=prices)
    _save_cache(settings.root, out)
    return _with_comments(attach_live_quotes(out, settings))
