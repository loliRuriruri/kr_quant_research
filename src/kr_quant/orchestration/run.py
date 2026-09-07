from __future__ import annotations

import json
import logging
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from kr_quant.atomic_io import write_parquet_atomic
from kr_quant.calendar import next_trading_day, trading_days_from_dates
from kr_quant.factors.metrics import make_scored
from kr_quant.financials.snapshot import build_inputs_for_security
from kr_quant.fixtures import generate_demo_dataset
from kr_quant.hashing import sha256_file, sha256_json, source_bundle_hash
from kr_quant.history.changes import (
    connect,
    detect_events,
    init_db,
    load_previous,
    persist_history,
)
from kr_quant.models import RunContext, ScoredName
from kr_quant.pit.filings import as_of_prices, history_window
from kr_quant.quality.price_integrity import latest_clean_price_segments
from kr_quant.ranking.daily import OUTPUT_COLS, export_table, flatten_flags, to_records, top_slice
from kr_quant.reporting.quality import build_quality_report, write_json
from kr_quant.scoring.composite import apply_composite, factor_specs
from kr_quant.scoring.peers import assign_peer_scores
from kr_quant.settings import Settings
from kr_quant.universe.builder import apply_universe_gates, load_ksic_map, map_industry
from kr_quant.universe.point_in_time import (
    build_universe_snapshot,
    load_listing_history,
    pit_cross_section,
    save_listing_history,
    update_listing_history,
)

logger = logging.getLogger("kr_quant.run")


def code_commit(root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:  # noqa: BLE001
        return "ungoverned"


def _load_status(path: Path, as_of: date) -> tuple[dict[str, str], bool]:
    if not path.exists():
        return {}, False
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
    except Exception:  # noqa: BLE001
        return {}, False
    if not {"ticker", "as_of_date", "status"}.issubset(df.columns):
        return {}, False
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce").dt.date
    # Trading eligibility is a daily observation. Never reuse yesterday's
    # ACTIVE value for today's ranking.
    df = df[df["as_of_date"] == as_of]
    if df.empty:
        return {}, False
    latest = df.drop_duplicates("ticker", keep="last")
    return {str(r.ticker).zfill(6): str(r.status) for r in latest.itertuples()}, True


def _csv_ready(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("risk_flags", "data_flags", "exclusion_reasons"):
        if col in out.columns:
            out[col] = out[col].map(flatten_flags)
    keep = [c for c in OUTPUT_COLS if c in out.columns]
    return out[keep]


def run_from_staged(
    settings: Settings,
    as_of: date,
    staged_dir: Path,
    status_path: Path | None = None,
    publish_latest: bool = True,
    source_mode: str = "staged",
) -> dict[str, Any]:
    cfg = settings.config
    tz = ZoneInfo(settings.timezone)
    cutoff = datetime(as_of.year, as_of.month, as_of.day, 19, 30, tzinfo=tz)
    prices = pd.read_parquet(staged_dir / "prices.parquet")
    facts = pd.read_parquet(staged_dir / "financial_facts.parquet")
    master = pd.read_parquet(staged_dir / "master.parquet")
    extra_path = staged_dir / "extra.parquet"
    extra_df = pd.read_parquet(extra_path) if extra_path.exists() else pd.DataFrame()
    extra_map = {}
    if not extra_df.empty:
        extra_map = extra_df.set_index("ticker").to_dict("index")

    hashes = {
        "prices.parquet": sha256_file(staged_dir / "prices.parquet"),
        "financial_facts.parquet": sha256_file(staged_dir / "financial_facts.parquet"),
        "master.parquet": sha256_file(staged_dir / "master.parquet"),
    }
    bundle = source_bundle_hash(hashes)
    ctx = RunContext(
        run_id=f"krq-{as_of.isoformat()}-{cfg['model']['version']}-{bundle[:12]}",
        as_of_date=as_of,
        cutoff_ts=cutoff,
        decision_date=next_trading_day(as_of, trading_days_from_dates(pd.to_datetime(prices["trade_date"]).dt.date)),
        model_id=settings.model_id,
        model_version=settings.model_version,
        config_hash=settings.config_hash,
        source_bundle_hash=bundle,
        code_commit=code_commit(settings.root),
        status="running",
    )

    status_file = status_path or settings.status_csv
    status_map, status_ok = _load_status(status_file, as_of)
    if cfg.get("status_feed", {}).get("required_for_success", True) and not status_ok:
        ctx.status = "partial"
        ctx.warnings.append("STATUS_FEED_MISSING")

    day = as_of_prices(prices, as_of)
    if day.empty:
        ctx.status = "failed"
        ctx.warnings.append("SOURCE_NOT_READY")
        raise RuntimeError(f"no KRX prices for as_of={as_of}")
    try:
        listing_history = update_listing_history(load_listing_history(settings), master, as_of)
        save_listing_history(settings, listing_history)
        _, pit_evidence = pit_cross_section(
            as_of,
            master=master,
            facts=facts,
            output_dir=settings.output_dir,
            history=listing_history,
        )
    except Exception:  # noqa: BLE001
        listing_history = None
        pit_evidence = {"reconstruction_source": "CURRENT_MASTER", "survivorship_bias_controlled": False}
    universe_snapshot, universe_evidence = build_universe_snapshot(
        master,
        day,
        as_of=as_of,
        source_mode=source_mode,
    )
    universe_evidence["pit"] = pit_evidence
    if universe_evidence.get("capture_state") != "CONTEMPORANEOUS":
        pit_ok = bool(pit_evidence.get("survivorship_bias_controlled")) and pit_evidence.get("reconstruction_source") in {
            "ARCHIVED_SNAPSHOT",
            "LISTING_HISTORY",
        }
        universe_evidence["survivorship_bias_controlled"] = pit_ok
    # The master may contain names listed after a historical as-of date. Keep
    # unknown dates with an explicit coverage warning instead of inventing a
    # complete delisting history.
    master = universe_snapshot.drop(
        columns=["observed_price_on_as_of", "as_of_date", "captured_at", "source_mode", "capture_state"],
        errors="ignore",
    )
    from kr_quant.quality.corporate_actions import apply_official_adjustments, load_actions_from_settings
    from kr_quant.quality.price_integrity import attach_official_action_explanations

    actions = load_actions_from_settings(settings)
    prices = apply_official_adjustments(prices, actions)
    hist = history_window(prices, as_of)
    current_tickers = set(day["ticker"].astype(str))
    hist = hist[hist["ticker"].astype(str).isin(current_tickers)].reset_index(drop=True)
    momentum_hist, price_integrity_issues, price_integrity_summary = latest_clean_price_segments(
        hist,
        cfg.get("corporate_actions") or {},
    )
    price_integrity_issues, price_integrity_summary = attach_official_action_explanations(
        price_integrity_issues,
        price_integrity_summary,
        actions,
    )
    mom_by_ticker: dict[str, dict] = {}
    if cfg.get("factors", {}).get("momentum", {}).get("enabled") and cfg.get("corporate_actions", {}).get(
        "listed_shares_adjustment"
    ):
        from kr_quant.factors.share_adj import compute_share_adj_momentum

        mom_by_ticker = compute_share_adj_momentum(momentum_hist, as_of, cfg, validate_integrity=False)
    ksic = load_ksic_map(settings.root / "config" / "sector_map_ksic.csv")
    master_map = master.drop_duplicates("ticker").set_index("ticker")
    company_by_ticker = {}
    if "company" in master.columns:
        company_by_ticker = {
            str(t): str(c) for t, c in zip(master["ticker"], master["company"]) if pd.notna(c)
        }

    names: list[ScoredName] = []
    for rec in day.to_dict("records"):
        ticker = str(rec["ticker"])
        mrow = master_map.loc[ticker] if ticker in master_map.index else None
        if mrow is not None:
            rec["kind"] = rec.get("kind") or mrow.get("kind") or ""
            rec["secu_group"] = rec.get("secu_group") or mrow.get("secu_group") or ""
            rec["sect"] = rec.get("sect") or mrow.get("sect") or ""
            rec["company"] = rec.get("company") or mrow.get("company") or ticker
            rec["list_date"] = rec.get("list_date") or mrow.get("list_date")
        induty = None if mrow is None else mrow.get("induty_code")
        industry_info = map_industry(None if induty is None or pd.isna(induty) else str(induty), ksic)
        sec_facts = facts[facts["ticker"] == ticker]
        extra = dict(extra_map.get(ticker) or {})
        extra.update(mom_by_ticker.get(ticker) or {})
        extra["universe_rules"] = settings.universe_rules
        inp, reasons = build_inputs_for_security(
            ticker, as_of, pd.Series(rec), hist, sec_facts, cfg, industry_info, extra
        )
        scored = make_scored(inp, cfg)
        scored.exclusion_reasons.extend(reasons)
        names.append(scored)

    for _factor, metric_name, mspec in factor_specs(cfg):
        assign_peer_scores(names, metric_name, mspec["direction"], cfg["peers"])

    for n in names:
        apply_composite(n, cfg, as_of)
        ticker = str(n.inputs.ticker).zfill(6)
        ticker_status_available = status_ok and ticker in status_map
        apply_universe_gates(
            n,
            cfg,
            as_of,
            status_map.get(ticker),
            ticker_status_available,
        )

    db = connect(settings.db_path)
    init_db(db)
    prev, model_break = load_previous(db, ctx.model_version, as_of)
    if model_break:
        ctx.warnings.append("MODEL_BREAK")
    records = to_records(names, ctx, company_by_ticker, prev)
    ctx.result_hash = sha256_json(
        [
            {
                "ticker": r["ticker"],
                "quant_score": r["quant_score"],
                "quant_rank": r["quant_rank"],
                "risk_penalty": r["risk_penalty"],
            }
            for r in sorted(records, key=lambda x: x["ticker"])
        ]
    )
    for r in records:
        r["result_hash"] = ctx.result_hash

    events = detect_events(records, cfg, model_break)
    if ctx.status == "running":
        ctx.status = "success" if not ctx.warnings else "partial"

    all_df = export_table(records)
    top100 = top_slice(all_df, 100, "top100_eligible")
    top20 = top_slice(all_df, 20, "top20_eligible")
    events_df = pd.DataFrame(events)

    eligibility_cols = [
        column
        for column in ("ticker", "universe_eligible", "top100_eligible", "top20_eligible", "exclusion_reasons")
        if column in all_df.columns
    ]
    if eligibility_cols:
        eligibility = all_df[eligibility_cols].copy()
        eligibility["ticker"] = eligibility["ticker"].astype(str).str.zfill(6)
        universe_snapshot = universe_snapshot.merge(eligibility, on="ticker", how="left")

    dated = settings.output_dir / f"as_of_date={as_of.isoformat()}"
    dated.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(all_df, dated / "all_stocks.parquet")
    write_parquet_atomic(top100, dated / "top100.parquet")
    write_parquet_atomic(top20, dated / "top20.parquet")
    _csv_ready(top100).to_csv(dated / "top100.csv", index=False, encoding="utf-8-sig")
    _csv_ready(top20).to_csv(dated / "top20.csv", index=False, encoding="utf-8-sig")
    if not events_df.empty:
        write_parquet_atomic(events_df, dated / "change_events.parquet")
    write_parquet_atomic(price_integrity_issues, dated / "price_integrity_issues.parquet")
    write_parquet_atomic(universe_snapshot, dated / "universe_snapshot.parquet")
    write_json(dated / "universe_evidence.json", universe_evidence)

    persist_history(db, ctx, records)
    hist_path = settings.output_dir / "daily_history.parquet"
    hist_df = db.execute(
        "SELECT * FROM fact_daily_ranking ORDER BY as_of_date, coalesce(quant_rank, 999999)"
    ).fetchdf()
    write_parquet_atomic(hist_df, hist_path)

    quality = build_quality_report(
        ctx,
        names,
        records,
        extra={
            "event_counts": events_df["event"].value_counts().to_dict() if not events_df.empty else {},
            "source_mode": source_mode,
            "price_integrity": price_integrity_summary,
            "universe_evidence": universe_evidence,
        },
    )
    write_json(dated / "data_quality_report.json", quality)

    manifest: dict[str, Any] = {
        "run_id": ctx.run_id,
        "status": ctx.status,
        "as_of_date": as_of.isoformat(),
        "decision_date": ctx.decision_date.isoformat(),
        "result_hash": ctx.result_hash,
        "config_hash": ctx.config_hash,
        "source_bundle_hash": ctx.source_bundle_hash,
        "warnings": ctx.warnings,
        "source_mode": source_mode,
        "universe_evidence": universe_evidence,
        "output_dir": str(dated),
    }

    # Keep the last known-good local snapshot intact when a run is partial.
    # Dated outputs above remain available for diagnosis and audit.
    if publish_latest and ctx.status == "success":
        from kr_quant.run_generation import mark_updating, publish_run_generation

        try:
            generation = publish_run_generation(
                settings,
                run_id=ctx.run_id,
                as_of=as_of.isoformat(),
                all_stocks=all_df,
                top100=_csv_ready(top100),
                top20=_csv_ready(top20),
                quality=quality,
                universe_evidence=universe_evidence,
                universe_snapshot=universe_snapshot,
                price_integrity_issues=price_integrity_issues,
                extra={
                    "result_hash": ctx.result_hash,
                    "source_bundle_hash": ctx.source_bundle_hash,
                    "status": ctx.status,
                },
            )
            write_parquet_atomic(hist_df, settings.output_dir / "daily_history.parquet")
            manifest["generation"] = {
                "run_id": generation.get("run_id"),
                "committed_at": generation.get("committed_at"),
                "generation_dir": generation.get("generation_dir"),
            }
            # Ledger failure must not relabel a successfully committed Quant generation.
            try:
                from kr_quant.research.selection_ledger import capture_quant_selection
                observed = capture_quant_selection(settings)
                manifest["selection_batch_id"] = observed["payload"]["batch_id"]
            except Exception as exc:
                logger.warning("selection observation not recorded: %s", exc)
                manifest["selection_record_status"] = "unavailable"
        except Exception as exc:  # noqa: BLE001
            logger.warning("generation commit failed; dated outputs remain: %s", exc)
            ctx.warnings.append("GENERATION_COMMIT_FAILED")
            try:
                mark_updating(settings, ctx.run_id, updating=False)
            except Exception:  # noqa: BLE001
                pass

    write_json(dated / "run_manifest.json", manifest)
    logger.info("run complete status=%s names=%s top20=%s", ctx.status, len(names), len(top20))
    return {
        "context": ctx,
        "names": names,
        "records": records,
        "top100": top100,
        "top20": top20,
        "quality": quality,
        "universe_snapshot": universe_snapshot,
        "universe_evidence": universe_evidence,
        "manifest": manifest,
    }


def run_demo(settings: Settings, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date(2024, 12, 30)
    staged = settings.data_dir / "staged" / "demo"
    generate_demo_dataset(staged, as_of=as_of)
    status = staged / "manual_status.csv"
    return run_from_staged(settings, as_of, staged, status_path=status, source_mode="demo")


def ingest_krx_day(settings: Settings, as_of: date, markets: list[str] | None = None) -> Path:
    from kr_quant.ingest.krx import KrxOpenApiAdapter
    from kr_quant.ingest.store import write_raw_json
    from kr_quant.normalize.security_master import normalize_krx_rows

    markets = markets or list(settings.config["universe"]["markets"])
    adapter = KrxOpenApiAdapter(
        settings.krx_api_key or "",
        settings.config["ingest"]["krx_base_url"],
    )
    frames = []
    for market in markets:
        rows = adapter.fetch_daily(as_of, market)
        write_raw_json(
            settings.raw_dir / "krx",
            "krx",
            f"daily_{market.lower()}",
            as_of.isoformat(),
            f"{market}_{as_of.isoformat()}",
            rows,
        )
        frames.append(normalize_krx_rows(rows, market, as_of))
    out = pd.concat(frames, ignore_index=True)
    dest_dir = settings.staged_dir / "live"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "prices.parquet"
    if dest.exists():
        old = pd.read_parquet(dest)
        old["trade_date"] = pd.to_datetime(old["trade_date"]).dt.date
        out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
        combo = pd.concat([old[old["trade_date"] != as_of], out], ignore_index=True)
        write_parquet_atomic(combo, dest)
    else:
        write_parquet_atomic(out, dest)
    return dest


def ingest_dart_financials(
    settings: Settings,
    tickers: list[str],
    years: list[int],
    max_corps: int | None = None,
) -> Path:
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    from kr_quant.ingest.opendart import OpenDartAdapter
    from kr_quant.ingest.store import write_raw_json
    from kr_quant.normalize.accounts import load_account_lookup, map_account, normalize_amount

    adapter = OpenDartAdapter(
        settings.opendart_api_key or "",
        settings.config["ingest"]["opendart_base_url"],
        sleep_sec=settings.opendart_sleep_sec,
    )
    blob = adapter.fetch_corp_map()
    write_raw_json(settings.raw_dir / "opendart", "opendart", "corpCode", date.today().isoformat(), "corpCode", {"bytes": len(blob)})
    zf = zipfile.ZipFile(io.BytesIO(blob))
    xml_name = [n for n in zf.namelist() if n.lower().endswith(".xml")][0]
    root = ET.fromstring(zf.read(xml_name))
    corp_rows = []
    for el in root.findall("list"):
        corp_rows.append(
            {
                "corp_code": (el.findtext("corp_code") or "").strip(),
                "corp_name": (el.findtext("corp_name") or "").strip(),
                "stock_code": (el.findtext("stock_code") or "").strip(),
                "modify_date": (el.findtext("modify_date") or "").strip(),
            }
        )
    corp_df = pd.DataFrame(corp_rows)
    dest_dir = settings.staged_dir / "live"
    dest_dir.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(corp_df, dest_dir / "corp_map.parquet")

    lookup = load_account_lookup(settings.account_map)
    sign_by_canonical = {
        name: spec.get("sign", "+") for name, spec in settings.account_map.get("accounts", {}).items()
    }
    wanted = set(t.zfill(6) for t in tickers)
    mapped = corp_df[corp_df["stock_code"].isin(wanted)]
    if max_corps:
        mapped = mapped.head(max_corps)
    report_codes = settings.config["ingest"]["report_codes"]
    facts: list[dict[str, Any]] = []
    for rec in mapped.to_dict("records"):
        for year in years:
            for code in report_codes:
                for fs_div in ("CFS", "OFS"):
                    try:
                        payload = adapter.fetch_financials(rec["corp_code"], str(year), code, fs_div)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("dart fetch failed %s %s %s %s: %s", rec["corp_code"], year, code, fs_div, exc)
                        continue
                    write_raw_json(
                        settings.raw_dir / "opendart",
                        "opendart",
                        "fnlttSinglAcntAll",
                        date.today().isoformat(),
                        f"{rec['corp_code']}_{year}_{code}_{fs_div}",
                        payload,
                    )
                    if str(payload.get("status")) != "000":
                        if fs_div == "CFS":
                            continue
                        break
                    for item in payload.get("list") or []:
                        canonical = map_account(item.get("account_id"), item.get("account_nm"), lookup)
                        if not canonical:
                            continue
                        amount = normalize_amount(item.get("thstrm_amount"), sign_by_canonical.get(canonical, "+"))
                        if amount is None:
                            continue
                        facts.append(
                            {
                                "security_id": rec["stock_code"],
                                "ticker": rec["stock_code"],
                                "corp_code": rec["corp_code"],
                                "canonical_account": canonical,
                                "account_id": item.get("account_id"),
                                "account_nm": item.get("account_nm"),
                                "sj_div": item.get("sj_div"),
                                "fs_div": fs_div,
                                "bsns_year": int(year),
                                "reprt_code": code,
                                "period_start": None,
                                "period_end": item.get("thstrm_dt") or f"{year}-12-31",
                                "normalized_value": amount,
                                "currency": item.get("currency") or "KRW",
                                "rcept_no": item.get("rcept_no"),
                                "rcept_dt": item.get("rcept_no", "")[:8] if item.get("rcept_no") else None,
                                "available_date": (item.get("rcept_no") or "19000101")[:8],
                                "revision_id": 1,
                                "is_correction": False,
                                "is_withdrawn": False,
                            }
                        )
                    if fs_div == "CFS" and (payload.get("list")):
                        break
    facts_df = pd.DataFrame(facts)
    if not facts_df.empty:
        facts_df["available_date"] = pd.to_datetime(facts_df["available_date"], format="%Y%m%d", errors="coerce").dt.date
        dest = dest_dir / "financial_facts.parquet"
        if dest.exists():
            old = pd.read_parquet(dest)
            facts_df = pd.concat([old, facts_df], ignore_index=True)
        write_parquet_atomic(facts_df, dest)
    master_dest = dest_dir / "master.parquet"
    master = mapped.rename(columns={"stock_code": "ticker", "corp_name": "company"})[
        ["ticker", "corp_code", "company"]
    ].copy()
    master["security_id"] = master["ticker"]
    master["market"] = "KOSPI"
    master["kind"] = "보통주"
    master["secu_group"] = "주권"
    master["list_date"] = None
    master["induty_code"] = None
    master["acc_mt"] = 12
    write_parquet_atomic(master, master_dest)
    return dest_dir / "financial_facts.parquet"
