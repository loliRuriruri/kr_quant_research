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
from kr_quant.universe.tradability import normalize_krx_risk_class

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
    fetched = pd.to_datetime(record.get("fetched_at"), utc=True, errors="coerce")
    if pd.isna(fetched):
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_hours = (current.astimezone(timezone.utc) - fetched.to_pydatetime()).total_seconds() / 3600
    retry_after = no_data_retry_hours if status == "013" else error_retry_hours
    return age_hours >= retry_after


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
        return {"ready": False, "as_of": as_of.isoformat(), "error": "KRX_API_KEY가 없습니다."}
    try:
        adapter = KrxOpenApiAdapter(settings.krx_api_key, settings.config["ingest"]["krx_base_url"])
        missing: list[str] = []
        for market in list(settings.config["universe"]["markets"]):
            rows = adapter.fetch_daily_maybe(as_of, market)
            if not rows:
                missing.append(str(market))
        return {
            "ready": not missing,
            "as_of": as_of.isoformat(),
            "missing_markets": missing,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("KRX session probe failed for %s: %s", as_of, exc)
        return {"ready": False, "as_of": as_of.isoformat(), "error": str(exc)[:200]}


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
        ticker = str(target["ticker"]).zfill(6)
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
                            "status": "ERR",
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
    eligible["ticker"] = eligible["ticker"].astype(str).str.zfill(6)
    eligible = eligible.drop_duplicates("ticker")
    current = eligible["ticker"].tolist()
    current_set = set(current)
    previous = [str(code).zfill(6) for code in (state or {}).get("ticker_order") or []]
    order = [code for code in previous if code in current_set]
    newcomers = [code for code in current if code not in set(order)]
    if not order:
        covered: set[str] = set()
        if facts is not None and not facts.empty and "ticker" in facts.columns:
            covered = set(facts["ticker"].astype(str).str.zfill(6))
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
    state_path = folder / "dart_backfill_state.json"
    prior = _read_json(state_path)
    batch, progress = plan_dart_backfill_targets(master, facts, batch_size=batch_size, state=prior)
    started = {
        **prior,
        **progress,
        "status": "running",
        "as_of": as_of.isoformat(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "state_path": str(state_path),
    }
    _write_json_atomic(state_path, started)
    if batch.empty:
        finished = {**started, "status": "complete", "completed_at": datetime.now(timezone.utc).isoformat()}
        _write_json_atomic(state_path, finished)
        return finished

    fetch_dart_companies(settings, batch["corp_code"].astype(str).tolist())
    refreshed = build_live_master(settings, as_of)
    refreshed["ticker"] = refreshed["ticker"].astype(str).str.zfill(6)
    batch_codes = set(progress["last_batch_tickers"])
    batch = refreshed[refreshed["ticker"].isin(batch_codes)].copy()
    fetch_dart_financials(settings, batch.to_dict("records"), as_of=as_of)

    facts = pd.read_parquet(facts_path) if facts_path.exists() else pd.DataFrame()
    covered = 0
    if not facts.empty and "ticker" in facts.columns:
        covered = int(facts["ticker"].astype(str).str.zfill(6).nunique())
    total = int(progress["total_targets"])
    finished = {
        **started,
        "status": "success",
        "cursor": int(progress["next_cursor"]),
        "processed_this_run": int(len(batch)),
        "covered_tickers": covered,
        "coverage_pct": None if not total else round(covered / total * 100, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
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
