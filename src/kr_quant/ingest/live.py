from __future__ import annotations

import calendar
import io
import json
import logging
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4
from xml.etree import ElementTree as ET

import pandas as pd

from kr_quant.atomic_io import write_csv_atomic, write_parquet_atomic
from kr_quant.exceptions import SourceNotReady
from kr_quant.ingest.krx import KrxOpenApiAdapter
from kr_quant.ingest.opendart import OpenDartAdapter
from kr_quant.ingest.store import write_raw_json
from kr_quant.normalize.accounts import load_account_lookup, map_account, normalize_amount
from kr_quant.normalize.security_master import normalize_krx_rows
from kr_quant.settings import Settings
from kr_quant.universe.identifiers import canonical_ticker
from kr_quant.universe.tradability import normalize_krx_risk_class

DART_USABLE_FACTS = "usable_facts"
DART_NO_FILING = "no_filing_for_period"
DART_NO_CORP_MAPPING = "no_corp_mapping"
DART_UNSUPPORTED = "unsupported_security"
DART_RATE_LIMITED = "rate_limited"
DART_TRANSIENT = "transient_error"
DART_PERMANENT = "permanent_error"
DART_USABLE_TARGET_PCT = 90.0
DART_PERMANENT_STATUSES = frozenset({"010", "011", "012", "014", "021", "100", "900"})
DART_RATE_STATUSES = frozenset({"020", "800"})
DART_RESPONSE_OUTCOMES = frozenset({DART_USABLE_FACTS, DART_NO_FILING})
DART_TERMINAL_OUTCOMES = frozenset(
    {DART_USABLE_FACTS, DART_NO_FILING, DART_NO_CORP_MAPPING, DART_UNSUPPORTED, DART_PERMANENT}
)

logger = logging.getLogger("kr_quant.ingest.live")

REPORT_AVAILABLE_MONTH_DAY = {
    "11013": (5, 16),
    "11012": (8, 16),
    "11014": (11, 16),
}


def dart_report_schedule(as_of: date, history_years: int = 4) -> list[tuple[int, str]]:
    """Return only reports whose statutory filing window has already passed.

    The oldest year keeps the annual filing only; the following years keep all
    available quarterly filings. New current-year reports appear automatically
    after their normal filing deadline instead of being hard-coded by calendar year.
    """
    start_year = as_of.year - max(1, int(history_years))
    reports: list[tuple[int, str]] = []
    for year in range(as_of.year, start_year - 1, -1):
        available: list[str] = []
        annual_available = date(year + 1, 4, 1)
        if annual_available <= as_of:
            available.append("11011")
        for code in ("11014", "11012", "11013"):
            month, day = REPORT_AVAILABLE_MONTH_DAY[code]
            if date(year, month, day) <= as_of:
                available.append(code)
        if year == start_year:
            available = [code for code in available if code == "11011"]
        reports.extend((year, code) for code in available)
    return reports


def should_retry_dart_job(
    record: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    no_data_retry_hours: int = 24,
    error_retry_hours: int = 1,
) -> bool:
    if not record:
        return True
    status = str(record.get("status") or "")
    if status == "000":
        return False
    if status in DART_PERMANENT_STATUSES:
        return False
    fetched = pd.to_datetime(record.get("fetched_at"), utc=True, errors="coerce")
    if pd.isna(fetched):
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_hours = (current.astimezone(timezone.utc) - fetched.to_pydatetime()).total_seconds() / 3600
    retry_after = no_data_retry_hours if status == "013" else error_retry_hours
    return age_hours >= retry_after


def opendart_status_from_error(exc: BaseException) -> str:
    text = str(exc)
    for token in (*sorted(DART_PERMANENT_STATUSES), *sorted(DART_RATE_STATUSES)):
        if f"status={token}" in text:
            return token
    return "ERR"


def dart_universe_partitions(master: pd.DataFrame) -> dict[str, list[str]]:
    """Split the master into DART-eligible, unmapped, and unsupported names."""
    df = master.copy()
    if df.empty or "ticker" not in df.columns:
        return {"eligible": [], "no_corp_mapping": [], "unsupported_security": []}
    df["ticker"] = df["ticker"].map(canonical_ticker)
    df = df[df["ticker"].astype(str) != ""].drop_duplicates("ticker")
    if "corp_code" not in df.columns:
        codes = df["ticker"].astype(str).tolist()
        return {"eligible": codes, "no_corp_mapping": [], "unsupported_security": []}
    for col in ("kind", "secu_group", "company", "corp_code"):
        if col not in df.columns:
            df[col] = ""
    kind = df["kind"].astype(str)
    group = df["secu_group"].astype(str)
    name = df["company"].astype(str)
    common = kind.str.contains("보통") | (kind == "")
    not_pref = ~kind.str.contains("우선")
    stock = group.str.contains("주권") | (group == "")
    not_etf = ~name.str.contains("ETF|ETN|스팩|SPAC|리츠|REIT", case=False, regex=True)
    security_ok = common & not_pref & stock & not_etf
    has_corp = df["corp_code"].notna() & (df["corp_code"].astype(str).str.len() >= 8)
    return {
        "eligible": df.loc[security_ok & has_corp, "ticker"].astype(str).tolist(),
        "no_corp_mapping": df.loc[security_ok & ~has_corp, "ticker"].astype(str).tolist(),
        "unsupported_security": df.loc[~security_ok, "ticker"].astype(str).tolist(),
    }


def classify_dart_ticker_outcome(*, has_facts: bool, job_rows: list[dict[str, Any]] | None = None) -> str:
    if has_facts:
        return DART_USABLE_FACTS
    statuses = [str(row.get("status") or "") for row in job_rows or []]
    if not statuses:
        return DART_TRANSIENT
    if any(status in DART_RATE_STATUSES for status in statuses):
        return DART_RATE_LIMITED
    if any(status in DART_PERMANENT_STATUSES for status in statuses):
        return DART_PERMANENT
    if all(status in {"000", "013"} for status in statuses):
        return DART_NO_FILING
    return DART_TRANSIENT


def ticker_outcome_retryable(record: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if not record:
        return True
    outcome = str(record.get("outcome") or "")
    if outcome in {DART_USABLE_FACTS, DART_NO_CORP_MAPPING, DART_UNSUPPORTED, DART_PERMANENT}:
        return False
    stamp = {"fetched_at": record.get("updated_at") or record.get("fetched_at")}
    if outcome == DART_NO_FILING:
        return should_retry_dart_job({**stamp, "status": "013"}, now=now)
    return should_retry_dart_job({**stamp, "status": "ERR"}, now=now)


def dart_coverage_report(
    master: pd.DataFrame | None,
    facts: pd.DataFrame | None,
    outcomes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parts = dart_universe_partitions(master if master is not None else pd.DataFrame())
    eligible = [canonical_ticker(code) for code in parts["eligible"]]
    eligible_set = {code for code in eligible if code}
    fact_tickers: set[str] = set()
    fact_rows = 0
    if facts is not None and not getattr(facts, "empty", True) and "ticker" in facts.columns:
        fact_rows = int(len(facts))
        fact_tickers = {canonical_ticker(code) for code in facts["ticker"].tolist()}
        fact_tickers.discard("")
    labels = {canonical_ticker(key): value for key, value in (outcomes or {}).items()}
    attempted = 0
    response = 0
    no_filing = 0
    errors = 0
    for ticker in eligible_set:
        rec = labels.get(ticker)
        outcome = rec.get("outcome") if isinstance(rec, dict) else rec
        if ticker in fact_tickers:
            outcome = DART_USABLE_FACTS
        if not outcome:
            continue
        attempted += 1
        if outcome in DART_RESPONSE_OUTCOMES:
            response += 1
        if outcome == DART_NO_FILING:
            no_filing += 1
        if outcome in {DART_TRANSIENT, DART_RATE_LIMITED, DART_PERMANENT}:
            errors += 1
    usable = len(fact_tickers & eligible_set) if eligible_set else len(fact_tickers)
    universe = len(eligible_set)
    def _pct(num: int) -> float | None:
        return None if not universe else round(num / universe * 100, 1)
    return {
        "rows": fact_rows,
        "tickers": usable,
        "universe_tickers": universe,
        "coverage_pct": _pct(usable),
        "usable_tickers": usable,
        "usable_pct": _pct(usable),
        "attempted_tickers": attempted if attempted else usable,
        "attempted_pct": _pct(attempted if attempted else usable),
        "response_tickers": response if response else usable,
        "response_pct": _pct(response if response else usable),
        "no_filing_tickers": no_filing,
        "no_corp_mapping_tickers": len(parts["no_corp_mapping"]),
        "unsupported_tickers": len(parts["unsupported_security"]),
        "error_tickers": errors,
        "target_pct": DART_USABLE_TARGET_PCT,
        "usable_target_met": bool(universe and usable / universe * 100 >= DART_USABLE_TARGET_PCT),
    }


def dart_backfill_eta(total: int, cursor: int, batch_size: int, *, batch_minutes: float = 8.0) -> dict[str, Any]:
    size = max(1, int(batch_size or 50))
    remaining = max(0, int(total) - int(cursor or 0))
    batches = (remaining + size - 1) // size if remaining else 0
    return {
        "remaining_tickers": remaining,
        "remaining_batches": batches,
        "eta_days": batches,
        "batch_minutes": batch_minutes,
    }


def needs_more_dart_backfill(coverage: dict[str, Any] | None, backfill: dict[str, Any] | None = None) -> bool:
    payload = coverage or {}
    usable = payload.get("usable_pct")
    if usable is None:
        usable = payload.get("coverage_pct")
    if usable is not None and float(usable) >= DART_USABLE_TARGET_PCT:
        return False
    progress = backfill or {}
    if int(progress.get("completed_cycles") or 0) >= 1 and not progress.get("has_retryable"):
        return False
    return True


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def infer_period(year: int, reprt_code: str, acc_mt: int = 12) -> tuple[date, date]:
    offsets = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}
    months = offsets.get(str(reprt_code), 12)
    if acc_mt == 12:
        end_month = months
        end_year = year
    else:
        # fiscal year `year` ends in acc_mt of calendar year `year`
        end_month = ((acc_mt - 12 + months - 1) % 12) + 1
        end_year = year if acc_mt >= months else year - 1
        if acc_mt < 12 and months == 12:
            end_year, end_month = year, acc_mt
    end = _last_day(end_year, end_month)
    start = date(end.year, 1, 1) if acc_mt == 12 else date(end.year - (1 if end.month < acc_mt else 0), ((acc_mt % 12) + 1) or 1, 1)
    if acc_mt == 12:
        start = date(year, 1, 1)
    return start, end


def rcept_to_date(rcept_no: str | None) -> date | None:
    if not rcept_no or len(str(rcept_no)) < 8:
        return None
    text = str(rcept_no)[:8]
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def live_dir(settings: Settings) -> Path:
    path = settings.staged_dir / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def upsert_parquet(path: Path, new_df: pd.DataFrame, key_cols: list[str]) -> None:
    if new_df.empty:
        return
    if path.exists():
        old = pd.read_parquet(path)
        combo = pd.concat([old, new_df], ignore_index=True)
        combo = combo.drop_duplicates(key_cols, keep="last")
    else:
        combo = new_df
    write_parquet_atomic(combo, path)


def fetch_krx_master(settings: Settings, as_of: date) -> pd.DataFrame:
    adapter = KrxOpenApiAdapter(settings.krx_api_key or "", settings.config["ingest"]["krx_base_url"])
    frames = []
    for market in settings.config["universe"]["markets"]:
        rows = adapter.fetch_master(as_of, market)
        write_raw_json(
            settings.raw_dir / "krx",
            "krx",
            f"master_{market.lower()}",
            as_of.isoformat(),
            f"{market}_{as_of.isoformat()}",
            rows,
        )
        recs = []
        for raw in rows:
            from kr_quant.universe.identifiers import canonical_ticker

            ticker = canonical_ticker(raw.get("ISU_SRT_CD") or "")
            recs.append(
                {
                    "security_id": str(raw.get("ISU_CD") or ticker),
                    "ticker": ticker,
                    "company": raw.get("ISU_ABBRV") or raw.get("ISU_NM"),
                    "market": market,
                    "kind": raw.get("KIND_STKCERT_TP_NM") or "",
                    "secu_group": raw.get("SECUGRP_NM") or "",
                    "list_date": raw.get("LIST_DD"),
                    "sect": raw.get("SECT_TP_NM") or "",
                    "listed_shares": raw.get("LIST_SHRS"),
                }
            )
        frames.append(pd.DataFrame(recs))
    master = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    dest = live_dir(settings) / "krx_master.parquet"
    write_parquet_atomic(master, dest)
    logger.info("KRX master %s rows=%s", as_of, len(master))
    return master


def _krx_status_from_risk_class(value: object) -> tuple[str | None, str | None]:
    normalized = normalize_krx_risk_class(value)
    if "상장폐지" in normalized or "정리매매" in normalized:
        return "DELIST_PROCESS", "KRX_MASTER_RISK_CLASS"
    if "관리종목" in normalized:
        return "ADMIN_ISSUE", "KRX_MASTER_RISK_CLASS"
    if "투자주의환기" in normalized:
        return "INVESTMENT_INELIGIBLE", "KRX_MASTER_RISK_CLASS"
    return None, None


def build_krx_status_snapshot(
    settings: Settings,
    as_of: date,
    *,
    master: pd.DataFrame | None = None,
    prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create an auditable daily tradability snapshot from official KRX inputs.

    This does not claim that a missing/zero-volume row is an official halt.
    It records it as NO_CURRENT_TRADE or UNVERIFIED so the quant gate fails
    closed until a current positive-price/volume observation is available.
    """
    folder = live_dir(settings)
    if master is None:
        path = folder / "krx_master.parquet"
        master = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    if prices is None:
        path = folder / "prices.parquet"
        prices = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    required_master = {"ticker", "market", "sect"}
    required_prices = {"ticker", "trade_date", "market", "close", "volume"}
    if master.empty or not required_master.issubset(master.columns):
        raise SourceNotReady("KRX status snapshot requires current master rows")
    if prices.empty or not required_prices.issubset(prices.columns):
        raise SourceNotReady("KRX status snapshot requires current daily price rows")

    krx = master.copy()
    krx["ticker"] = krx["ticker"].astype(str).str.zfill(6)
    krx = krx.drop_duplicates("ticker", keep="last")
    daily = prices.copy()
    daily["ticker"] = daily["ticker"].astype(str).str.zfill(6)
    daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce").dt.date
    daily = daily[daily["trade_date"] == as_of].copy()
    if daily.empty:
        raise SourceNotReady(f"KRX status snapshot has no daily rows for {as_of}")
    expected_markets = set(settings.config["universe"]["markets"])
    observed_markets = set(daily["market"].dropna().astype(str))
    if not expected_markets.issubset(observed_markets):
        missing = sorted(expected_markets - observed_markets)
        raise SourceNotReady(f"KRX status snapshot missing markets for {as_of}: {missing}")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily["volume"] = pd.to_numeric(daily["volume"], errors="coerce")
    daily = daily.sort_values("trade_date").drop_duplicates("ticker", keep="last")
    daily["daily_present"] = True

    columns = ["ticker", "close", "volume", "daily_present"]
    merged = krx.merge(daily[columns], on="ticker", how="left")
    records: list[dict[str, Any]] = []
    for row in merged.to_dict("records"):
        risk_status, basis = _krx_status_from_risk_class(row.get("sect"))
        present = row.get("daily_present") is True
        close = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        volume = pd.to_numeric(pd.Series([row.get("volume")]), errors="coerce").iloc[0]
        if risk_status:
            status = risk_status
        elif not present:
            status, basis = "UNVERIFIED", "KRX_DAILY_ROW_MISSING"
        elif pd.isna(close) or pd.isna(volume) or float(close) <= 0 or float(volume) <= 0:
            status, basis = "NO_CURRENT_TRADE", "KRX_DAILY_NON_POSITIVE_PRICE_OR_VOLUME"
        else:
            status, basis = "ACTIVE", "KRX_DAILY_TRADED"
        records.append(
            {
                "ticker": str(row.get("ticker") or "").zfill(6),
                "as_of_date": as_of.isoformat(),
                "status": status,
                "market": str(row.get("market") or ""),
                "company": str(row.get("company") or ""),
                "krx_risk_class": str(row.get("sect") or ""),
                "daily_present": bool(present),
                "close": None if pd.isna(close) else float(close),
                "volume": None if pd.isna(volume) else float(volume),
                "basis": basis,
                "source": "KRX_OPEN_API_MASTER_AND_DAILY",
            }
        )
    snapshot = pd.DataFrame(records)

    destination = settings.status_csv
    if destination.exists():
        try:
            old = pd.read_csv(destination, dtype={"ticker": str})
            if {"ticker", "as_of_date"}.issubset(old.columns):
                snapshot = pd.concat([old, snapshot], ignore_index=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ignoring unreadable prior KRX status snapshot %s: %s", destination, exc)
    snapshot["ticker"] = snapshot["ticker"].astype(str).str.zfill(6)
    snapshot = snapshot.drop_duplicates(["ticker", "as_of_date"], keep="last")
    snapshot = snapshot.sort_values(["as_of_date", "market", "ticker"]).reset_index(drop=True)
    write_csv_atomic(snapshot, destination)
    logger.info("KRX status snapshot %s rows=%s path=%s", as_of, len(records), destination)
    return snapshot[snapshot["as_of_date"].astype(str) == as_of.isoformat()].copy()


def calendar_guard(lookback_days: int) -> int:
    days = max(1, int(lookback_days))
    return max(days * 3, days + 80)


def krx_session_available(settings: Settings, as_of: date) -> dict[str, Any]:
    """Probe whether KRX already serves a complete session for as_of.

    Empty markets mean the official daily file is not ready yet. This does not
    walk back to an older session; the caller should retry the same date.
    """
    if not settings.krx_api_key:
        return {"ready": False, "as_of": as_of.isoformat(), "error": "KRX_API_KEY가 없습니다.",
                "failure_kind": "configuration", "retryable": False}
    try:
        adapter = KrxOpenApiAdapter(settings.krx_api_key, settings.config["ingest"]["krx_base_url"])
        missing: list[str] = []
        counts: dict[str, int] = {}
        for market in list(settings.config["universe"]["markets"]):
            rows = adapter.fetch_daily_maybe(as_of, market)
            counts[str(market)] = len(rows)
            if not rows:
                missing.append(str(market))
        return {
            "ready": not missing,
            "as_of": as_of.isoformat(),
            "missing_markets": missing,
            "market_rows": counts,
            "failure_kind": "not_published" if missing else None,
            "retryable": bool(missing),
        }
    except Exception as exc:  # noqa: BLE001
        import requests
        from kr_quant.ingest.krx import KrxResponseError
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        retryable = (isinstance(exc, (requests.Timeout, requests.ConnectionError))
                     or status == 429 or (isinstance(status, int) and status >= 500))
        kind = 'response_invalid' if isinstance(exc, KrxResponseError) else 'request_error'
        if status in (401, 403):
            kind = 'authorization'
        detail = f"KRX {kind} ({type(exc).__name__}{' HTTP ' + str(status) if status else ''})"
        logger.warning("KRX session probe failed for %s: %s", as_of, detail)
        return {"ready": False, "as_of": as_of.isoformat(), "error": detail,
                "failure_kind": kind, "retryable": retryable}


def fetch_krx_prices_range(
    settings: Settings,
    as_of: date,
    lookback_days: int,
    *,
    sleep_sec: float = 0.0,
) -> pd.DataFrame:
    adapter = KrxOpenApiAdapter(settings.krx_api_key or "", settings.config["ingest"]["krx_base_url"])
    dest = live_dir(settings) / "prices.parquet"
    configured_markets = list(settings.config["universe"]["markets"])
    required_markets = set(configured_markets)
    have: set[date] = set()
    if dest.exists():
        old = pd.read_parquet(dest)
        if {"trade_date", "market"}.issubset(old.columns):
            old_dates = pd.to_datetime(old["trade_date"], errors="coerce").dt.date
            old_markets = old["market"].astype(str)
            coverage = pd.DataFrame({"trade_date": old_dates, "market": old_markets}).dropna()
            have = {
                trade_date
                for trade_date, group in coverage.groupby("trade_date")
                if required_markets.issubset(set(group["market"]))
            }

    collected = 0
    cur = as_of
    guard = 0
    limit = calendar_guard(lookback_days)
    pause = float(sleep_sec or 0)
    while collected < lookback_days and guard < limit:
        guard += 1
        if cur in have:
            collected += 1
            cur -= timedelta(days=1)
            continue
        frames = []
        empty = 0
        for market in configured_markets:
            rows = adapter.fetch_daily_maybe(cur, market)
            if not rows:
                empty += 1
                continue
            write_raw_json(
                settings.raw_dir / "krx",
                "krx",
                f"daily_{market.lower()}",
                cur.isoformat(),
                f"{market}_{cur.isoformat()}",
                rows,
            )
            frames.append(normalize_krx_rows(rows, market, cur))
        if frames and empty == 0 and len(frames) == len(configured_markets):
            day = pd.concat(frames, ignore_index=True)
            upsert_parquet(dest, day, ["ticker", "trade_date"])
            have.add(cur)
            collected += 1
            logger.info("KRX prices %s rows=%s (%s/%s)", cur, len(day), collected, lookback_days)
            if pause > 0:
                time.sleep(pause)
        else:
            logger.info("KRX skip empty %s", cur)
        cur -= timedelta(days=1)

    if collected < lookback_days:
        raise SourceNotReady(
            f"KRX complete-market history shortfall: collected={collected}, required={lookback_days}"
        )
    prices = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()
    master_path = live_dir(settings) / "krx_master.parquet"
    if master_path.exists():
        build_krx_status_snapshot(
            settings,
            as_of,
            master=pd.read_parquet(master_path),
            prices=prices,
        )
    return prices


def fetch_dart_corp_map(settings: Settings) -> pd.DataFrame:
    adapter = OpenDartAdapter(
        settings.opendart_api_key or "",
        settings.config["ingest"]["opendart_base_url"],
        sleep_sec=settings.opendart_sleep_sec,
    )
    blob = adapter.fetch_corp_map()
    zf = zipfile.ZipFile(io.BytesIO(blob))
    xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
    root = ET.fromstring(zf.read(xml_name))
    rows = []
    for el in root.findall("list"):
        stock = (el.findtext("stock_code") or "").strip()
        rows.append(
            {
                "corp_code": (el.findtext("corp_code") or "").strip().zfill(8),
                "corp_name": (el.findtext("corp_name") or "").strip(),
                "stock_code": stock.zfill(6) if stock else "",
                "modify_date": (el.findtext("modify_date") or "").strip(),
            }
        )
    df = pd.DataFrame(rows)
    dest = live_dir(settings) / "corp_map.parquet"
    write_parquet_atomic(df, dest)
    listed = df[df["stock_code"].str.len() == 6]
    logger.info("DART corp map listed=%s", len(listed))
    return df


def _concept_priority(account_id: str | None) -> int:
    aid = account_id or ""
    if aid.startswith("ifrs-full_"):
        return 0
    if aid.startswith("dart_"):
        return 1
    return 2


def parse_financial_payload(
    payload: dict[str, Any],
    ticker: str,
    corp_code: str,
    year: int,
    reprt_code: str,
    fs_div: str,
    acc_mt: int,
    lookup: dict[str, str],
    sign_by_canonical: dict[str, str],
) -> list[dict[str, Any]]:
    items = list(payload.get("list") or [])
    start, end = infer_period(year, reprt_code, acc_mt)
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        canonical = map_account(item.get("account_id"), item.get("account_nm"), lookup)
        if not canonical:
            continue
        amount = normalize_amount(item.get("thstrm_amount"), sign_by_canonical.get(canonical, "+"))
        if amount is None:
            continue
        rcept = item.get("rcept_no")
        avail = rcept_to_date(rcept) or end
        rec = {
            "security_id": ticker,
            "ticker": ticker,
            "corp_code": corp_code,
            "canonical_account": canonical,
            "account_id": item.get("account_id"),
            "account_nm": item.get("account_nm"),
            "sj_div": item.get("sj_div"),
            "fs_div": fs_div,
            "bsns_year": int(year),
            "reprt_code": reprt_code,
            "period_start": start,
            "period_end": end,
            "normalized_value": amount,
            "currency": item.get("currency") or "KRW",
            "rcept_no": rcept,
            "rcept_dt": avail,
            "available_date": avail,
            "revision_id": 1,
            "is_correction": False,
            "is_withdrawn": False,
            "_prio": _concept_priority(item.get("account_id")),
        }
        prev = best.get(canonical)
        if prev is None or rec["_prio"] < prev["_prio"]:
            best[canonical] = rec
    out = []
    for rec in best.values():
        rec.pop("_prio", None)
        out.append(rec)
    return out


def fetch_dart_companies(settings: Settings, corp_codes: Iterable[str]) -> pd.DataFrame:
    adapter = OpenDartAdapter(
        settings.opendart_api_key or "",
        settings.config["ingest"]["opendart_base_url"],
        sleep_sec=settings.opendart_sleep_sec,
    )
    dest = live_dir(settings) / "company.parquet"
    have: set[str] = set()
    if dest.exists():
        have = set(pd.read_parquet(dest)["corp_code"].astype(str).str.zfill(8))
    rows = []
    for raw in corp_codes:
        code = str(raw).zfill(8)
        if code in have:
            continue
        try:
            payload = adapter.fetch_company(code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("company fail %s: %s", code, exc)
            continue
        if str(payload.get("status")) != "000":
            continue
        rows.append(
            {
                "corp_code": code,
                "stock_code": str(payload.get("stock_code") or "").zfill(6),
                "corp_name": payload.get("corp_name"),
                "induty_code": payload.get("induty_code"),
                "acc_mt": int(payload.get("acc_mt") or 12),
                "ceo_nm": payload.get("ceo_nm"),
            }
        )
        if len(rows) >= 50:
            upsert_parquet(dest, pd.DataFrame(rows), ["corp_code"])
            rows = []
    if rows:
        upsert_parquet(dest, pd.DataFrame(rows), ["corp_code"])
    return pd.read_parquet(dest) if dest.exists() else pd.DataFrame()


def fetch_dart_financials(
    settings: Settings,
    targets: list[dict[str, Any]],
    reports: list[tuple[int, str]] | None = None,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    adapter = OpenDartAdapter(
        settings.opendart_api_key or "",
        settings.config["ingest"]["opendart_base_url"],
        sleep_sec=settings.opendart_sleep_sec,
    )
    lookup = load_account_lookup(settings.account_map)
    sign_by_canonical = {
        name: spec.get("sign", "+") for name, spec in settings.account_map.get("accounts", {}).items()
    }
    reports = dart_report_schedule(as_of or date.today()) if reports is None else reports
    job_path = live_dir(settings) / "dart_jobs.parquet"
    done_jobs: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    if job_path.exists():
        jobs = pd.read_parquet(job_path)
        for rec in jobs.to_dict("records"):
            done_jobs[(str(rec["corp_code"]), int(rec["year"]), str(rec["reprt_code"]), str(rec["fs_div"]))] = rec

    facts_path = live_dir(settings) / "financial_facts.parquet"
    new_facts: list[dict[str, Any]] = []
    new_jobs: list[dict[str, Any]] = []
    fetched = 0
    for target in targets:
        corp = str(target["corp_code"]).zfill(8)
        ticker = canonical_ticker(target["ticker"]) or str(target["ticker"]).zfill(6)
        acc_mt = int(target.get("acc_mt") or 12)
        for year, code in reports:
            for fs_div in ("CFS", "OFS"):
                key = (corp, year, code, fs_div)
                previous = done_jobs.get(key)
                if not should_retry_dart_job(previous):
                    if str((previous or {}).get("status")) == "000":
                        if int((previous or {}).get("n_mapped") or 0) > 0:
                            break
                        continue
                    continue
                try:
                    payload = adapter.fetch_financials(corp, str(year), code, fs_div)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("fs fail %s %s %s %s: %s", ticker, year, code, fs_div, exc)
                    job_record = {
                            "corp_code": corp,
                            "year": year,
                            "reprt_code": code,
                            "fs_div": fs_div,
                            "status": opendart_status_from_error(exc),
                            "n_mapped": 0,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        }
                    new_jobs.append(job_record)
                    done_jobs[key] = job_record
                    continue
                status = str(payload.get("status"))
                rows = parse_financial_payload(
                    payload, ticker, corp, year, code, fs_div, acc_mt, lookup, sign_by_canonical
                )
                job_record = {
                        "corp_code": corp,
                        "year": year,
                        "reprt_code": code,
                        "fs_div": fs_div,
                        "status": status,
                        "n_mapped": len(rows),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                new_jobs.append(job_record)
                done_jobs[key] = job_record
                fetched += 1
                if status == "000" and rows:
                    new_facts.extend(rows)
                    break
                if fetched % 25 == 0:
                    if new_facts:
                        upsert_parquet(
                            facts_path,
                            pd.DataFrame(new_facts),
                            ["ticker", "canonical_account", "fs_div", "bsns_year", "reprt_code"],
                        )
                        new_facts = []
                    if new_jobs:
                        upsert_parquet(job_path, pd.DataFrame(new_jobs), ["corp_code", "year", "reprt_code", "fs_div"])
                        new_jobs = []
                    logger.info("DART progress fetched=%s ticker=%s %s %s", fetched, ticker, year, code)
    if new_facts:
        upsert_parquet(
            facts_path,
            pd.DataFrame(new_facts),
            ["ticker", "canonical_account", "fs_div", "bsns_year", "reprt_code"],
        )
    if new_jobs:
        upsert_parquet(job_path, pd.DataFrame(new_jobs), ["corp_code", "year", "reprt_code", "fs_div"])
    return pd.read_parquet(facts_path) if facts_path.exists() else pd.DataFrame()


def build_live_master(settings: Settings, as_of: date) -> pd.DataFrame:
    folder = live_dir(settings)
    krx = pd.read_parquet(folder / "krx_master.parquet")
    corp = pd.read_parquet(folder / "corp_map.parquet") if (folder / "corp_map.parquet").exists() else pd.DataFrame()
    company = pd.read_parquet(folder / "company.parquet") if (folder / "company.parquet").exists() else pd.DataFrame()
    prices = pd.read_parquet(folder / "prices.parquet")
    prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.date
    latest = prices[prices["trade_date"] == as_of][["ticker", "market_cap", "listed_shares", "close", "company"]].drop_duplicates("ticker")
    master = krx.merge(latest, on="ticker", how="left", suffixes=("", "_px"))
    if not corp.empty:
        corp = corp[corp["stock_code"] != ""]
        master = master.merge(corp[["stock_code", "corp_code"]], left_on="ticker", right_on="stock_code", how="left")
    if not company.empty:
        master = master.merge(company[["corp_code", "induty_code", "acc_mt"]], on="corp_code", how="left")
    if "company_px" in master.columns:
        master["company"] = master["company"].fillna(master["company_px"])
    keep = [
        c
        for c in [
            "security_id",
            "ticker",
            "corp_code",
            "company",
            "market",
            "kind",
            "secu_group",
            "sect",
            "list_date",
            "induty_code",
            "acc_mt",
            "market_cap",
            "listed_shares",
        ]
        if c in master.columns
    ]
    out = master[keep].drop_duplicates("ticker")
    write_parquet_atomic(out, folder / "master.parquet")
    extra = out[["ticker", "listed_shares"]].rename(columns={"listed_shares": "shares_latest"}).copy()
    extra["shares_latest"] = pd.to_numeric(
        extra["shares_latest"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    extra["shares_12m_ago"] = None
    extra["potential_dilution_pct"] = None
    extra["cb_bw_count_24m"] = 0
    write_parquet_atomic(extra, folder / "extra.parquet")
    return out


def select_ingest_targets(master: pd.DataFrame, max_corps: int | None) -> pd.DataFrame:
    df = master.copy()
    for col in ("kind", "secu_group", "company", "corp_code"):
        if col not in df.columns:
            df[col] = ""
    kind = df["kind"].astype(str)
    group = df["secu_group"].astype(str)
    name = df["company"].astype(str)
    common = kind.str.contains("보통") | (kind == "")
    not_pref = ~kind.str.contains("우선")
    stock = group.str.contains("주권") | (group == "")
    not_etf = ~name.str.contains("ETF|ETN|스팩|SPAC|리츠|REIT", case=False, regex=True)
    df = df[common & not_pref & stock & not_etf]
    df = df[df["corp_code"].notna() & (df["corp_code"].astype(str).str.len() >= 8)]
    if "market_cap" in df.columns:
        df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")
        df = df.sort_values("market_cap", ascending=False)
    if max_corps:
        df = df.head(max_corps)
    return df


def plan_dart_backfill_targets(
    master: pd.DataFrame,
    facts: pd.DataFrame,
    *,
    batch_size: int,
    state: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a stable, resumable full-universe DART batch.

    The first cycle places tickers without any stored facts first. Later calls keep
    the stored order so new facts do not move the cursor and accidentally skip names.
    """
    eligible = select_ingest_targets(master, None).copy()
    if eligible.empty:
        return eligible, {"cursor": 0, "total_targets": 0, "ticker_order": [], "completed_cycles": 0}
    eligible["ticker"] = eligible["ticker"].map(lambda value: canonical_ticker(value) or str(value).zfill(6))
    eligible = eligible[eligible["ticker"].astype(str) != ""].drop_duplicates("ticker")
    current = eligible["ticker"].tolist()
    current_set = set(current)
    previous = [canonical_ticker(code) or str(code).zfill(6) for code in (state or {}).get("ticker_order") or []]
    order = [code for code in previous if code in current_set]
    newcomers = [code for code in current if code not in set(order)]
    if not order:
        covered: set[str] = set()
        if facts is not None and not facts.empty and "ticker" in facts.columns:
            covered = {canonical_ticker(code) or str(code).zfill(6) for code in facts["ticker"].tolist()}
        missing = [code for code in current if code not in covered]
        present = [code for code in current if code in covered]
        order = missing + present
    else:
        order.extend(newcomers)

    total = len(order)
    size = max(1, min(int(batch_size or 50), 500))
    cursor = int((state or {}).get("cursor") or 0)
    if cursor < 0 or cursor >= total:
        cursor = 0
    end = min(total, cursor + size)
    batch_codes = order[cursor:end]
    completed = end >= total
    next_cursor = 0 if completed else end
    cycles = int((state or {}).get("completed_cycles") or 0) + (1 if completed else 0)
    indexed = eligible.set_index("ticker", drop=False)
    batch = indexed.loc[[code for code in batch_codes if code in indexed.index]].reset_index(drop=True)
    progress = {
        "cursor": cursor,
        "next_cursor": next_cursor,
        "batch_start": cursor,
        "batch_end": end,
        "batch_size": int(len(batch)),
        "total_targets": total,
        "ticker_order": order,
        "last_batch_tickers": batch_codes,
        "completed_cycle": completed,
        "completed_cycles": cycles,
    }
    return batch, progress


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _seed_partition_outcomes(
    outcomes: dict[str, Any],
    partitions: dict[str, list[str]],
    *,
    now: str,
    fact_tickers: set[str] | None = None,
) -> dict[str, Any]:
    merged = dict(outcomes)
    if fact_tickers is not None:
        for ticker, rec in list(merged.items()):
            code = canonical_ticker(ticker) or str(ticker).zfill(6)
            outcome = rec.get("outcome") if isinstance(rec, dict) else str(rec or "")
            if outcome == DART_USABLE_FACTS and code not in fact_tickers:
                del merged[ticker]
    for ticker in partitions.get("no_corp_mapping") or []:
        code = canonical_ticker(ticker)
        if code and (not isinstance(merged.get(code), dict) or not merged[code].get("outcome")):
            merged[code] = {"outcome": DART_NO_CORP_MAPPING, "updated_at": now, "attempts": 0}
    for ticker in partitions.get("unsupported_security") or []:
        code = canonical_ticker(ticker)
        if code and (not isinstance(merged.get(code), dict) or not merged[code].get("outcome")):
            merged[code] = {"outcome": DART_UNSUPPORTED, "updated_at": now, "attempts": 0}
    return merged


def backfill_dart_financials(settings: Settings, as_of: date, *, batch_size: int = 50) -> dict[str, Any]:
    """Advance one resumable full-universe DART batch and persist its checkpoint."""
    folder = live_dir(settings)
    if not (folder / "krx_master.parquet").exists() or not (folder / "prices.parquet").exists():
        raise FileNotFoundError("KRX 마스터와 시세가 없습니다. 먼저 빠른 갱신 또는 전체 갱신을 실행하세요.")
    if not (folder / "corp_map.parquet").exists():
        fetch_dart_corp_map(settings)
    master = build_live_master(settings, as_of)
    facts_path = folder / "financial_facts.parquet"
    facts = pd.read_parquet(facts_path) if facts_path.exists() else pd.DataFrame()
    fact_tickers: set[str] = set()
    if not facts.empty and "ticker" in facts.columns:
        fact_tickers = {canonical_ticker(code) or str(code).zfill(6) for code in facts["ticker"].tolist()}
    state_path = folder / "dart_backfill_state.json"
    prior = _read_json(state_path)
    batch, progress = plan_dart_backfill_targets(master, facts, batch_size=batch_size, state=prior)
    partitions = dart_universe_partitions(master)
    started_at = datetime.now(timezone.utc).isoformat()
    outcomes = _seed_partition_outcomes(
        prior.get("ticker_outcomes") or {},
        partitions,
        now=started_at,
        fact_tickers=fact_tickers,
    )
    started = {
        **progress,
        "status": "running",
        "as_of": as_of.isoformat(),
        "started_at": started_at,
        "completed_at": None,
        "error": None,
        "ticker_outcomes": outcomes,
        "state_path": str(state_path),
        "completed_cycles": int(progress.get("completed_cycles") or 0),
    }
    _write_json_atomic(state_path, started)
    if batch.empty:
        coverage = dart_coverage_report(master, facts, outcomes)
        eta = dart_backfill_eta(int(progress.get("total_targets") or 0), int(progress.get("next_cursor") or 0), batch_size)
        finished = {
            **started,
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "coverage": coverage,
            **eta,
            "has_retryable": False,
        }
        _write_json_atomic(state_path, finished)
        return finished

    skip_codes = []
    fetch_rows = []
    for row in batch.to_dict("records"):
        ticker = canonical_ticker(row.get("ticker")) or str(row.get("ticker") or "").zfill(6)
        previous = outcomes.get(ticker)
        prev_outcome = (previous.get("outcome") if isinstance(previous, dict) else str(previous or "")) if previous else ""
        if previous and not ticker_outcome_retryable(previous):
            if prev_outcome == DART_USABLE_FACTS and ticker not in fact_tickers:
                pass
            else:
                skip_codes.append(ticker)
                continue
        fetch_rows.append(row)
    prior_batch_start = prior.get("batch_start")
    planned_batch_start = progress.get("batch_start")
    same_batch = (
        str(prior.get("as_of")) == as_of.isoformat()
        and prior.get("status") in {"success", "complete"}
        and list(prior.get("last_batch_tickers") or []) == list(progress.get("last_batch_tickers") or [])
        and prior_batch_start is not None
        and planned_batch_start is not None
        and int(prior_batch_start) == int(planned_batch_start)
    )
    if same_batch and not fetch_rows:
        coverage = dart_coverage_report(master, facts, outcomes)
        eta = dart_backfill_eta(int(progress.get("total_targets") or 0), int(progress.get("next_cursor") or 0), batch_size)
        finished = {
            **started,
            "status": "success",
            "cursor": int(progress["next_cursor"]),
            "processed_this_run": 0,
            "skipped_already_done": skip_codes,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "coverage": coverage,
            **eta,
            "note": "같은 날 같은 배치를 다시 수집하지 않았습니다.",
        }
        _write_json_atomic(state_path, finished)
        return finished

    if fetch_rows:
        fetch_dart_companies(settings, [str(row.get("corp_code") or "") for row in fetch_rows])
        refreshed = build_live_master(settings, as_of)
        refreshed["ticker"] = refreshed["ticker"].map(lambda value: canonical_ticker(value) or str(value).zfill(6))
        fetch_codes = {canonical_ticker(row.get("ticker")) or str(row.get("ticker") or "").zfill(6) for row in fetch_rows}
        batch = refreshed[refreshed["ticker"].isin(fetch_codes)].copy()
        fetch_dart_financials(settings, batch.to_dict("records"), as_of=as_of)
    else:
        batch = batch.iloc[0:0].copy()

    facts = pd.read_parquet(facts_path) if facts_path.exists() else pd.DataFrame()
    fact_tickers: set[str] = set()
    if not facts.empty and "ticker" in facts.columns:
        fact_tickers = {canonical_ticker(code) or str(code).zfill(6) for code in facts["ticker"].tolist()}
    jobs_by_corp: dict[str, list[dict[str, Any]]] = {}
    job_path = folder / "dart_jobs.parquet"
    if job_path.exists():
        jobs = pd.read_parquet(job_path)
        for rec in jobs.to_dict("records"):
            jobs_by_corp.setdefault(str(rec.get("corp_code") or "").zfill(8), []).append(rec)
    stamp = datetime.now(timezone.utc).isoformat()
    for row in fetch_rows:
        ticker = canonical_ticker(row.get("ticker")) or str(row.get("ticker") or "").zfill(6)
        corp = str(row.get("corp_code") or "").zfill(8)
        outcome = classify_dart_ticker_outcome(has_facts=ticker in fact_tickers, job_rows=jobs_by_corp.get(corp) or [])
        previous = outcomes.get(ticker) if isinstance(outcomes.get(ticker), dict) else {}
        outcomes[ticker] = {
            "outcome": outcome,
            "updated_at": stamp,
            "attempts": int((previous or {}).get("attempts") or 0) + 1,
            "corp_code": corp,
        }
    coverage = dart_coverage_report(master, facts, outcomes)
    eta = dart_backfill_eta(int(progress.get("total_targets") or 0), int(progress.get("next_cursor") or 0), batch_size)
    has_retryable = any(
        ticker_outcome_retryable(rec)
        for ticker, rec in outcomes.items()
        if canonical_ticker(ticker) in set(progress.get("ticker_order") or [])
    ) or any(code not in outcomes for code in progress.get("ticker_order") or [])
    finished = {
        **started,
        "status": "success",
        "cursor": int(progress["next_cursor"]),
        "processed_this_run": int(len(fetch_rows)),
        "skipped_already_done": skip_codes,
        "covered_tickers": coverage.get("usable_tickers"),
        "coverage_pct": coverage.get("usable_pct"),
        "coverage": coverage,
        "ticker_outcomes": outcomes,
        "completed_at": stamp,
        "has_retryable": has_retryable,
        "cycle_complete": bool(progress.get("completed_cycle")),
        **eta,
    }
    _write_json_atomic(state_path, finished)
    return finished


def bootstrap_live(
    settings: Settings,
    as_of: date,
    lookback_days: int = 80,
    max_corps: int | None = 500,
) -> dict[str, Any]:
    logger.info("bootstrap as_of=%s lookback=%s max_corps=%s", as_of, lookback_days, max_corps)
    fetch_krx_master(settings, as_of)
    fetch_krx_prices_range(settings, as_of, lookback_days)
    corp = fetch_dart_corp_map(settings)
    master = build_live_master(settings, as_of)
    targets = select_ingest_targets(master, max_corps)
    logger.info("ingest targets=%s", len(targets))
    if not targets.empty:
        fetch_dart_companies(settings, targets["corp_code"].tolist())
        master = build_live_master(settings, as_of)
        targets = select_ingest_targets(master, max_corps)
        fetch_dart_financials(settings, targets.to_dict("records"), as_of=as_of)
        master = build_live_master(settings, as_of)
    facts_path = live_dir(settings) / "financial_facts.parquet"
    n_facts = len(pd.read_parquet(facts_path)) if facts_path.exists() else 0
    status_rows = 0
    if settings.status_csv.exists():
        status = pd.read_csv(settings.status_csv, dtype={"ticker": str})
        status_rows = int((status["as_of_date"].astype(str) == as_of.isoformat()).sum())
    return {
        "as_of": as_of.isoformat(),
        "targets": int(len(targets)),
        "facts": int(n_facts),
        "corp_map": int(len(corp)),
        "status_rows": status_rows,
        "status_path": str(settings.status_csv),
        "staged": str(live_dir(settings)),
    }
