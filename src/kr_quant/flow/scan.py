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

FLOW_SCHEMA = 6


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


def _fwd_return_detail(hist: pd.DataFrame, start: date, horizon: int) -> dict[str, Any]:
    """Return a forward result only after the full trading-session horizon exists.

    A D+5 return needs the signal session plus five later price observations.  The
    previous implementation silently used the newest available price for immature
    signals, which made D+5 and D+20 look like confirmed (and often identical)
    results.  Keep immature observations explicit so they are never included in
    hit-rate statistics.
    """
    detail: dict[str, Any] = {
        "status": "PENDING",
        "complete": False,
        "horizon": int(horizon),
        "observed_sessions": 0,
        "required_sessions": int(horizon),
        "start_date": None,
        "end_date": None,
    }
    if hist is None or hist.empty or horizon <= 0:
        return detail
    work = hist.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    work = work[work["trade_date"] >= start].sort_values("trade_date")
    if work.empty:
        return detail

    levels = _levels(work)
    if not levels:
        return detail
    detail["start_date"] = levels[0][0].isoformat()
    detail["end_date"] = levels[-1][0].isoformat()
    detail["observed_sessions"] = min(max(len(levels) - 1, 0), horizon)
    if len(levels) <= horizon:
        return detail

    start_date, start_lv = levels[0]
    end_date, end_lv = levels[horizon]
    detail.update(
        {
            "status": "COMPLETE",
            "complete": True,
            "observed_sessions": horizon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
    )
    if start_lv <= 0:
        detail.update({"status": "INVALID", "complete": False})
        return detail
    detail["return"] = end_lv / start_lv - 1.0
    return detail


def _fwd_return(hist: pd.DataFrame, start: date, horizon: int) -> float | None:
    detail = _fwd_return_detail(hist, start, horizon)
    value = detail.get("return")
    return float(value) if value is not None and detail.get("complete") else None


def attach_daily_prices(summary: dict[str, Any], hist: pd.DataFrame) -> dict[str, Any]:
    """Attach same-date KRX OHLC prices to newest-first Toss flow rows."""
    daily = summary.get("daily")
    if not isinstance(daily, list) or not daily or hist is None or hist.empty or "trade_date" not in hist.columns:
        return summary
    work = hist.copy()
    work["_flow_date"] = pd.to_datetime(work["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work = work.dropna(subset=["_flow_date"]).sort_values("_flow_date")
    if work.empty:
        return summary
    for key in ("open", "high", "low", "close"):
        if key in work.columns:
            work[key] = pd.to_numeric(work[key], errors="coerce")
    if "close" in work.columns:
        work["price_change_rate"] = work["close"].pct_change(fill_method=None)
    price_by_date: dict[str, dict[str, Any]] = {}
    for _, price_row in work.iterrows():
        point: dict[str, Any] = {}
        for key in ("open", "high", "low", "close", "price_change_rate"):
            value = price_row.get(key)
            if value is not None and not pd.isna(value):
                point[key] = round(float(value), 6)
        price_by_date[str(price_row["_flow_date"])] = point
    for flow_row in daily:
        if not isinstance(flow_row, dict):
            continue
        day = str(flow_row.get("date") or "")[:10]
        if day in price_by_date:
            flow_row.update(price_by_date[day])
    return summary


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
                from kr_quant.universe.identifiers import canonical_ticker

                digits = canonical_ticker(symbol)
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
                ret_5d = _fwd_return_detail(hist, start, 5)
                ret_20d = _fwd_return_detail(hist, start, 20)
                summary["ret_5d"] = ret_5d.get("return") if ret_5d.get("complete") else None
                summary["ret_20d"] = ret_20d.get("return") if ret_20d.get("complete") else None
                summary["ret_5d_meta"] = ret_5d
                summary["ret_20d_meta"] = ret_20d
            if not hist.empty:
                summary = attach_daily_prices(summary, hist)
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


def diagnose_ticker_flow(settings: Settings, query: str, days: int = 5) -> dict[str, Any]:
    q = str(query or "").strip()
    code = ""
    company = ""

    p = settings.output_dir / "latest_all_stocks.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if q.isdigit():
                code = q.zfill(6)
                sub = df[df["ticker"] == code]
                if not sub.empty:
                    company = str(sub["company"].iloc[0])
            else:
                sub = df[df["company"].str.contains(q, case=False, na=False)]
                if not sub.empty:
                    code = str(sub["ticker"].iloc[0]).zfill(6)
                    company = str(sub["company"].iloc[0])
        except Exception:
            pass

    if not code:
        from kr_quant.strategy.run import _prices
        prices_df = _prices(settings)
        if not prices_df.empty:
            if q.isdigit():
                code = q.zfill(6)
                matched = prices_df[prices_df["ticker"].astype(str).str.zfill(6) == code]
                if not matched.empty and "company" in matched.columns:
                    company = str(matched["company"].iloc[0])
            else:
                if "company" in prices_df.columns:
                    matched = prices_df[prices_df["company"].astype(str).str.contains(q, case=False, na=False)]
                    if not matched.empty:
                        code = str(matched["ticker"].iloc[0]).zfill(6)
                        company = str(matched["company"].iloc[0])

    if not code:
        return {"ok": False, "error": f"종목 '{query}'을(를) 찾을 수 없습니다."}

    cached = load_flow(settings, days=days)
    for r in cached.get("rows") or []:
        if str(r.get("ticker")).zfill(6) == code:
            return {"ok": True, "found_in_scan": True, "row": r}

    records = []
    if settings.toss_client_id and settings.toss_client_secret:
        try:
            from kr_quant.ingest.tossinvest import get_investor_trading
            payload = get_investor_trading(settings.toss_client_id, settings.toss_client_secret, code)
            records = payload.get("records") if isinstance(payload, dict) else []
        except Exception:
            records = []

    summary = summarize_records(records, days=days)
    from kr_quant.strategy.run import _prices
    prices = _prices(settings)
    hist = prices[prices["ticker"].astype(str).str.zfill(6) == code] if not prices.empty else pd.DataFrame()
    summary = attach_daily_prices(summary, hist)
    last = float(pd.to_numeric(hist.sort_values("trade_date")["close"].iloc[-1], errors="coerce") or 0) if not hist.empty else 0.0

    smart = (summary.get("foreign_net") or 0) + (summary.get("institution_net") or 0)
    dual_krw = smart * last if last else 0
    empty_krw = -smart * last if last else 0
    pe_krw = (summary.get("pe_net") or 0) * last if last else 0

    row = {
        "ticker": code,
        "company": company or code,
        **summary,
        "pe_krw": pe_krw,
        "dual_krw": dual_krw,
        "empty_krw": empty_krw,
        "other_corp_krw": (summary.get("other_corp_net") or 0) * last if last else 0,
        "pension_krw": (summary.get("pension_net") or 0) * last if last else 0,
        "in_quant": False,
    }
    row["setups"] = classify_setups(row)

    from kr_quant.timing.snapshot import attach_technicals
    from kr_quant.web.comments import flow_comment

    dummy_payload = {"rows": [row]}
    attached = attach_technicals(dummy_payload, settings, prices=prices)
    row = (attached.get("rows") or [row])[0]
    row["comment"] = flow_comment(row)

    return {"ok": True, "found_in_scan": False, "row": row}
