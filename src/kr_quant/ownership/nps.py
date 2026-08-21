"""OpenDART 국민연금 5%+ 대량보유. Overlay only. Not KIS 기금, not Toss pensionFund."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from kr_quant.settings import Settings

logger = logging.getLogger("kr_quant.ownership.nps")

NPS_TOKENS = ("국민연금공단", "국민연금", "national pension service", "national pension")


def is_nps_holder(name: Any) -> bool:
    text = str(name or "").strip().lower()
    if not text:
        return False
    compact = text.replace(" ", "")
    return any(tok.lower().replace(" ", "") in compact or tok.lower() in text for tok in NPS_TOKENS)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _ratio(value: Any) -> float | None:
    num = _num(value)
    if num is None:
        return None
    if abs(num) > 1.5:
        return num / 100.0
    return num


def _as_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).replace(".", "-")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def parse_majorstock(payload: dict[str, Any], *, ticker: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    items = payload.get("list") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        holder = item.get("repror") or item.get("nm") or item.get("holder") or ""
        ratio = _ratio(item.get("stkrt") or item.get("hold_stock") or item.get("hold_rt") or item.get("hold_rate"))
        change_pp = _num(item.get("stkrt_irds") or item.get("hold_stock_irds") or item.get("hold_rt_irds"))
        previous_ratio = None
        if ratio is not None and change_pp is not None:
            previous_ratio = ratio - (change_pp / 100.0)
        shares = _num(item.get("stkqy") or item.get("share_count"))
        report = _as_date(item.get("rcept_dt") or item.get("report_date"))
        stock = "".join(ch for ch in str(ticker or item.get("stock_code") or "") if ch.isdigit()).zfill(6)
        if stock == "000000":
            stock = ""
        rows.append(
            {
                "report_date": report,
                "ticker": stock,
                "corp_code": str(item.get("corp_code") or "").zfill(8),
                "company": item.get("corp_name"),
                "holder_name": str(holder).strip(),
                "is_nps": is_nps_holder(holder),
                "holding_ratio": ratio,
                "previous_ratio": None if previous_ratio is None else round(previous_ratio, 6),
                "ratio_change": None if change_pp is None else change_pp,
                "share_count": shares,
                "receipt_no": str(item.get("rcept_no") or ""),
                "report_type": item.get("report_tp"),
                "source": "OPENDART_MAJORSTOCK",
                "used_in_quant": False,
            }
        )
    return rows


def _universe_corps(settings: Settings, limit: int = 80) -> dict[str, dict[str, str]]:
    import pandas as pd

    out: dict[str, dict[str, str]] = {}
    company_path = settings.staged_dir / "live" / "company.parquet"
    stocks_path = settings.output_dir / "latest_all_stocks.parquet"
    cross: dict[str, str] = {}
    names: dict[str, str] = {}
    if company_path.exists():
        cdf = pd.read_parquet(company_path)
        for rec in cdf.to_dict("records"):
            ticker = "".join(ch for ch in str(rec.get("stock_code") or rec.get("ticker") or "") if ch.isdigit()).zfill(6)
            corp = str(rec.get("corp_code") or "").zfill(8)
            if ticker != "000000" and corp not in {"", "00000000"}:
                cross[ticker] = corp
                names[ticker] = str(rec.get("corp_name") or rec.get("company") or "")
    ranked: list[str] = []
    if stocks_path.exists():
        sdf = pd.read_parquet(stocks_path)
        if "universe_eligible" in sdf.columns:
            sdf = sdf[sdf["universe_eligible"] == True]  # noqa: E712
        if "quant_rank" in sdf.columns:
            sdf = sdf.sort_values("quant_rank", na_position="last")
        for rec in sdf.head(max(20, int(limit))).to_dict("records"):
            ticker = "".join(ch for ch in str(rec.get("ticker") or "") if ch.isdigit()).zfill(6)
            if ticker != "000000":
                ranked.append(ticker)
                if rec.get("company"):
                    names[ticker] = str(rec["company"])
    for ticker in ranked:
        corp = cross.get(ticker)
        if not corp:
            continue
        out[corp] = {"corp_code": corp, "company": names.get(ticker, ""), "ticker": ticker}
    return out


def _list_nps_filings(adapter: Any, bgn: str, end: str, max_pages: int = 8) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            data = adapter.fetch_list_range(bgn, end, page_no=page, page_count=100, pblntf_detail_ty="D001")
        except TypeError:
            data = adapter.fetch_list("", bgn, end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("opendart list failed page %s: %s", page, exc)
            break
        items = data.get("list") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            report = str(item.get("report_nm") or "")
            filer = str(item.get("flr_nm") or "")
            if "대량보유" not in report and "주식등의 대량보유" not in report:
                continue
            if not is_nps_holder(filer):
                continue
            found.append(item)
        total_page = int(str(data.get("total_page") or 1))
        if page >= total_page:
            break
        time.sleep(getattr(adapter, "sleep_sec", 0.15) or 0.15)
    return found


def scan_nps_holdings(settings: Settings, lookback_days: int = 180, max_corps: int = 80) -> dict[str, Any]:
    from kr_quant.flow.store import coverage_ownership, open_settings, upsert_ownership
    from kr_quant.ingest.opendart import OpenDartAdapter

    if not settings.opendart_api_key:
        raise RuntimeError("OpenDART 키가 없습니다.")
    adapter = OpenDartAdapter(
        settings.opendart_api_key,
        "https://opendart.fss.or.kr/api",
        sleep_sec=float(getattr(settings, "opendart_sleep_sec", None) or 0.15),
    )
    end = date.today()
    span = min(90, max(30, int(lookback_days)))
    bgn = end - timedelta(days=span)
    filings = _list_nps_filings(adapter, bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    corps: dict[str, dict[str, str]] = {}
    for item in filings:
        corp = str(item.get("corp_code") or "").zfill(8)
        if corp in {"", "00000000"}:
            continue
        corps[corp] = {
            "corp_code": corp,
            "company": str(item.get("corp_name") or ""),
            "ticker": "".join(ch for ch in str(item.get("stock_code") or "") if ch.isdigit()).zfill(6),
        }
    for corp, meta in _universe_corps(settings, limit=max_corps).items():
        corps.setdefault(corp, meta)
    saved = 0
    nps_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    con = open_settings(settings)
    try:
        for i, (corp, meta) in enumerate(list(corps.items())[: max(1, int(max_corps))]):
            try:
                payload = adapter.fetch_majorstock(corp)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{corp}: {str(exc)[:120]}")
                continue
            parsed = parse_majorstock(payload, ticker=meta.get("ticker"))
            for row in parsed:
                if not row.get("ticker"):
                    row["ticker"] = meta.get("ticker") or ""
                if not row.get("company"):
                    row["company"] = meta.get("company")
                row["corp_code"] = corp
                row["available_date"] = row.get("report_date")
                row["fetched_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            nps_only = [r for r in parsed if r.get("is_nps")]
            saved += upsert_ownership(con, nps_only)
            nps_rows.extend(nps_only)
            time.sleep(getattr(adapter, "sleep_sec", 0.15) or 0.15)
            if i and i % 20 == 0:
                logger.info("nps majorstock %s/%s", i, len(corps))
        cov = coverage_ownership(con)
    finally:
        con.close()
    latest: dict[str, dict[str, Any]] = {}
    for row in nps_rows:
        code = str(row.get("ticker") or "")
        if not code:
            continue
        prev = latest.get(code)
        if prev is None or str(row.get("report_date") or "") >= str(prev.get("report_date") or ""):
            latest[code] = row
    return {
        "used_in_quant": False,
        "filings_nps": len(filings),
        "corps": len(corps),
        "saved": saved,
        "unique_tickers": len(latest),
        "errors": errors[:8],
        "coverage": cov,
        "note": "OpenDART 대량보유 공시에서 제출인·보고자가 국민연금인 행만 저장했습니다. KIS 기금·토스 연기금과 섞지 않습니다.",
    }


def _company_names(settings: Settings, codes: list[str]) -> dict[str, str]:
    import pandas as pd

    need = {"".join(ch for ch in str(c) if ch.isdigit()).zfill(6) for c in codes}
    need.discard("000000")
    names: dict[str, str] = {}
    paths = [
        settings.output_dir / "latest_all_stocks.parquet",
        settings.staged_dir / "live" / "krx_master.parquet",
        settings.staged_dir / "live" / "master.parquet",
    ]
    for path in paths:
        if not path.exists() or not need:
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        if "ticker" not in df.columns or "company" not in df.columns:
            continue
        tick = df["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        hit = df[tick.isin(need)]
        for rec in hit.to_dict("records"):
            code = "".join(ch for ch in str(rec.get("ticker") or "") if ch.isdigit()).zfill(6)
            company = str(rec.get("company") or "").strip()
            if code in need and company and company != code:
                names[code] = company
                need.discard(code)
    if need:
        try:
            from kr_quant.flow.universe import resolve_names

            extra, _types = resolve_names(settings, list(need))
            names.update({k: v for k, v in extra.items() if v})
        except Exception:  # noqa: BLE001
            pass
    return names


def holdings_payload(settings: Settings) -> dict[str, Any]:
    from kr_quant.flow.store import coverage_ownership, load_ownership, open_settings

    con = open_settings(settings)
    try:
        rows = load_ownership(con, nps_only=True)
        cov = coverage_ownership(con)
    finally:
        con.close()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("ticker") or "")
        if not code:
            continue
        prev = latest.get(code)
        if prev is None or str(row.get("report_date") or "") >= str(prev.get("report_date") or ""):
            latest[code] = row
    items = list(latest.values())
    names = _company_names(settings, [str(r.get("ticker") or "") for r in items])
    for row in items:
        code = str(row.get("ticker") or "")
        if names.get(code):
            row["company"] = names[code]
    items.sort(key=lambda r: float(r.get("holding_ratio") or 0), reverse=True)
    return {
        "used_in_quant": False,
        "configured": bool(settings.opendart_api_key),
        "coverage": cov,
        "rows": items,
        "n": len(items),
        "disclaimer": (
            "국민연금 5% 이상은 OpenDART 대량보유상황보고입니다. "
            "일별 수급의 기금·토스 연기금과 같은 데이터가 아니며 Quant에 넣지 않습니다."
        ),
    }
