# -*- coding: utf-8 -*-
"""Read-only pipeline health: real artifact state outranks the ledger.

A1 foundation only — no network, no ingest, no mutations, no repair execution.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from kr_quant.freshness import expected_price_date, trading_session_lag
from kr_quant.ingest.live import DART_USABLE_TARGET_PCT, dart_coverage_report
from kr_quant.settings import Settings

COMPONENT_STATES = frozenset(
    {"HEALTHY", "STALE", "PARTIAL", "MISSING", "CORRUPT", "UPDATING", "BLOCKED"}
)
PIPELINE_STATES = frozenset(
    {
        "READY",
        "NEEDS_DAILY_UPDATE",
        "REPAIR_REQUIRED",
        "WAITING_SOURCE",
        "RUNNING",
        "PARTIAL",
        "FAILED",
    }
)

# Derived from current Quant consumers (ingest.live required_* + financials.snapshot /
# quarters / run_from_staged / build_inputs_for_security).
REQUIRED_PRICES = frozenset(
    {"ticker", "trade_date", "market", "close", "volume", "market_cap", "trading_value"}
)
REQUIRED_MASTER = frozenset({"ticker", "market", "sect"})
REQUIRED_FACTS = frozenset(
    {
        "ticker",
        "security_id",
        "available_date",
        "canonical_account",
        "fs_div",
        "currency",
        "bsns_year",
        "reprt_code",
        "normalized_value",
        "period_end",
    }
)
REQUIRED_QUANT_STOCKS = frozenset({"ticker"})


def _component(
    state: str,
    *,
    reason: str | None = None,
    as_of: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if state not in COMPONENT_STATES:
        raise ValueError(f"unsupported component state: {state}")
    row: dict[str, Any] = {"state": state}
    if reason is not None:
        row["reason"] = reason
    if as_of is not None:
        row["as_of"] = as_of
    row.update(extra)
    return row


def _inspect_parquet(
    path: Path,
    *,
    required_columns: frozenset[str],
) -> dict[str, Any]:
    """Bounded parquet inspection via metadata + schema (no full pandas load)."""
    if not path.exists():
        return {"ok": False, "state": "MISSING", "reason": "file_missing", "path": str(path)}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"ok": False, "state": "CORRUPT", "reason": f"stat_failed:{type(exc).__name__}", "path": str(path)}
    if size <= 0:
        return {"ok": False, "state": "CORRUPT", "reason": "empty_file", "path": str(path), "size": size}
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        names = {field.name for field in pf.schema_arrow}
        rows = int(pf.metadata.num_rows) if pf.metadata is not None else 0
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "state": "CORRUPT",
            "reason": f"unreadable_parquet:{type(exc).__name__}",
            "path": str(path),
            "size": size,
        }
    missing_cols = sorted(required_columns - names)
    if missing_cols:
        return {
            "ok": False,
            "state": "CORRUPT",
            "reason": "schema_missing_columns",
            "path": str(path),
            "size": size,
            "rows": rows,
            "missing_columns": missing_cols,
        }
    if rows <= 0:
        return {
            "ok": False,
            "state": "CORRUPT",
            "reason": "zero_rows",
            "path": str(path),
            "size": size,
            "rows": 0,
        }
    return {
        "ok": True,
        "state": "HEALTHY",
        "path": str(path),
        "size": size,
        "rows": rows,
        "columns": sorted(names),
    }


def _max_trade_date(path: Path) -> date | None:
    try:
        import pandas as pd

        frame = pd.read_parquet(path, columns=["trade_date"])
        if frame.empty:
            return None
        parsed = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
        if parsed.empty:
            return None
        return parsed.max().date()
    except Exception:  # noqa: BLE001
        return None


def _live_path(settings: Settings, name: str) -> Path:
    return settings.staged_dir / "live" / name


def _coverage_from_state(settings: Settings, facts_ok: bool) -> dict[str, Any]:
    live = settings.staged_dir / "live"
    master_path = live / "master.parquet"
    facts_path = live / "financial_facts.parquet"
    backfill_path = live / "dart_backfill_state.json"
    outcomes: dict[str, Any] = {}
    if backfill_path.exists():
        try:
            payload = json.loads(backfill_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("ticker_outcomes"), dict):
                outcomes = payload["ticker_outcomes"]
        except (OSError, json.JSONDecodeError):
            outcomes = {}
    master = None
    facts = None
    try:
        import pandas as pd

        if master_path.exists():
            try:
                master = pd.read_parquet(
                    master_path,
                    columns=["ticker", "market", "sect", "kind", "secu_group", "corp_code"],
                )
            except Exception:  # noqa: BLE001
                try:
                    master = pd.read_parquet(master_path, columns=["ticker"])
                except Exception:  # noqa: BLE001
                    master = None
        if facts_ok and facts_path.exists():
            try:
                facts = pd.read_parquet(facts_path, columns=["ticker"])
            except Exception:  # noqa: BLE001
                facts = None
    except Exception:  # noqa: BLE001
        pass
    report = dart_coverage_report(master, facts, outcomes)
    pct = report.get("usable_pct")
    if pct is None:
        pct = report.get("coverage_pct")
    try:
        pct_f = float(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct_f = None
    if pct_f is None:
        state = "MISSING"
        reason = "coverage_unavailable"
    elif pct_f >= float(DART_USABLE_TARGET_PCT):
        state = "HEALTHY"
        reason = "coverage_target_met"
    else:
        state = "PARTIAL"
        reason = "coverage_below_target"
    return _component(
        state,
        reason=reason,
        coverage_pct=pct_f,
        target_pct=float(DART_USABLE_TARGET_PCT),
        tickers=report.get("tickers"),
        universe_tickers=report.get("universe_tickers"),
    )


def _krx_health(settings: Settings, *, expected: date, now: datetime | None) -> dict[str, Any]:
    path = _live_path(settings, "prices.parquet")
    inspected = _inspect_parquet(path, required_columns=REQUIRED_PRICES)
    if not inspected["ok"]:
        return _component(
            inspected["state"],
            reason=inspected.get("reason"),
            path=inspected.get("path"),
            size=inspected.get("size"),
            rows=inspected.get("rows"),
            missing_columns=inspected.get("missing_columns"),
        )
    max_day = _max_trade_date(path)
    as_of = None if max_day is None else max_day.isoformat()
    if max_day is None:
        return _component(
            "CORRUPT",
            reason="trade_date_unreadable",
            as_of=None,
            path=str(path),
            rows=inspected["rows"],
        )
    if max_day < expected:
        return _component(
            "STALE",
            reason="price_behind_expected",
            as_of=as_of,
            expected_date=expected.isoformat(),
            lag_trading_days=trading_session_lag(max_day, expected),
            path=str(path),
            rows=inspected["rows"],
        )
    return _component(
        "HEALTHY",
        reason="prices_current",
        as_of=as_of,
        expected_date=expected.isoformat(),
        lag_trading_days=0,
        path=str(path),
        rows=inspected["rows"],
    )


def _master_health(settings: Settings) -> dict[str, Any]:
    path = _live_path(settings, "master.parquet")
    inspected = _inspect_parquet(path, required_columns=REQUIRED_MASTER)
    if not inspected["ok"]:
        return _component(
            inspected["state"],
            reason=inspected.get("reason"),
            path=inspected.get("path"),
            size=inspected.get("size"),
            rows=inspected.get("rows"),
            missing_columns=inspected.get("missing_columns"),
        )
    return _component("HEALTHY", reason="master_readable", path=str(path), rows=inspected["rows"])


def _dart_essential_health(settings: Settings) -> dict[str, Any]:
    path = _live_path(settings, "financial_facts.parquet")
    inspected = _inspect_parquet(path, required_columns=REQUIRED_FACTS)
    if not inspected["ok"]:
        return _component(
            inspected["state"],
            reason=inspected.get("reason") or "financial_facts_missing",
            path=inspected.get("path"),
            size=inspected.get("size"),
            rows=inspected.get("rows"),
            missing_columns=inspected.get("missing_columns"),
        )
    return _component(
        "HEALTHY",
        reason="financial_facts_present",
        path=str(path),
        rows=inspected["rows"],
    )


def _quant_health(
    settings: Settings,
    *,
    price_as_of: str | None,
    blocked_by: list[str],
) -> dict[str, Any]:
    if blocked_by:
        return _component("BLOCKED", reason="upstream_required_missing", blocked_by=list(blocked_by))

    from kr_quant.run_generation import load_manifest

    manifest = load_manifest(settings)
    if not isinstance(manifest, dict):
        return _component(
            "MISSING",
            reason="committed_manifest_missing",
            path=str(settings.output_dir / "current_manifest.json"),
        )

    run_id = manifest.get("run_id")
    generation_dir_raw = manifest.get("generation_dir")
    if not run_id or not generation_dir_raw:
        return _component(
            "CORRUPT",
            reason="committed_manifest_incomplete",
            manifest_keys=sorted(manifest.keys()),
        )

    from kr_quant.run_generation import generation_dir as expected_generation_dir

    generation_dir = Path(str(generation_dir_raw))
    expected_dir = expected_generation_dir(settings, str(run_id))
    if generation_dir.resolve() != expected_dir.resolve():
        return _component(
            "CORRUPT",
            reason="committed_generation_dir_mismatch",
            run_id=str(run_id),
            generation_dir=str(generation_dir),
            expected_generation_dir=str(expected_dir),
        )
    if not generation_dir.exists() or not generation_dir.is_dir():
        return _component(
            "MISSING",
            reason="committed_generation_dir_missing",
            run_id=str(run_id),
            generation_dir=str(generation_dir),
        )

    stocks_path = generation_dir / "latest_all_stocks.parquet"
    quality_path = generation_dir / "data_quality_report.json"

    inspected = _inspect_parquet(stocks_path, required_columns=REQUIRED_QUANT_STOCKS)
    if not inspected["ok"]:
        return _component(
            inspected["state"],
            reason=inspected.get("reason") or "committed_all_stocks_missing",
            path=inspected.get("path"),
            size=inspected.get("size"),
            rows=inspected.get("rows"),
            run_id=str(run_id),
            generation_dir=str(generation_dir),
            missing_columns=inspected.get("missing_columns"),
        )

    if not quality_path.exists():
        return _component(
            "MISSING",
            reason="committed_quality_report_missing",
            path=str(quality_path),
            run_id=str(run_id),
            generation_dir=str(generation_dir),
        )

    as_of: str | None = None
    try:
        payload = json.loads(quality_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return _component(
                "CORRUPT",
                reason="committed_quality_report_invalid",
                path=str(quality_path),
                run_id=str(run_id),
            )
        if payload.get("as_of_date"):
            as_of = str(payload.get("as_of_date"))[:10]
        quality_run = payload.get("run_id")
        if quality_run is not None and str(quality_run) != str(run_id):
            return _component(
                "CORRUPT",
                reason="committed_quality_run_id_mismatch",
                path=str(quality_path),
                run_id=str(run_id),
                quality_run_id=str(quality_run),
            )
    except (OSError, json.JSONDecodeError, TypeError):
        return _component(
            "CORRUPT",
            reason="committed_quality_report_unreadable",
            path=str(quality_path),
            run_id=str(run_id),
        )

    manifest_as_of = str(manifest.get("as_of_date") or manifest.get("as_of") or "")[:10] or None
    if as_of is None:
        return _component(
            "CORRUPT",
            reason="quant_as_of_missing",
            path=str(stocks_path),
            rows=inspected["rows"],
            run_id=str(run_id),
        )
    if manifest_as_of and manifest_as_of != as_of:
        return _component(
            "CORRUPT",
            reason="quant_as_of_mismatch",
            as_of=as_of,
            manifest_as_of=manifest_as_of,
            run_id=str(run_id),
        )

    if price_as_of and as_of < price_as_of:
        return _component(
            "STALE",
            reason="quant_behind_prices",
            as_of=as_of,
            price_as_of=price_as_of,
            path=str(stocks_path),
            rows=inspected["rows"],
            run_id=str(run_id),
            generation_dir=str(generation_dir),
        )

    return _component(
        "HEALTHY",
        reason="committed_quant_aligned",
        as_of=as_of,
        price_as_of=price_as_of,
        path=str(stocks_path),
        rows=inspected["rows"],
        run_id=str(run_id),
        generation_dir=str(generation_dir),
    )


def _kis_health(settings: Settings, *, expected: date) -> dict[str, Any]:
    from kr_quant.freshness import _official_flow_freshness

    flow = _official_flow_freshness(settings, expected)
    mapped = {
        "fresh": "HEALTHY",
        "partial": "PARTIAL",
        "stale": "STALE",
        "missing": "MISSING",
        "unavailable": "CORRUPT",
        "future": "STALE",
    }.get(str(flow.get("state") or "missing"), "MISSING")
    return _component(
        mapped,
        reason=f"official_flow:{flow.get('state')}",
        as_of=flow.get("observed_date"),
        expected_date=expected.isoformat(),
        used_in_quant=False,
        coverage=flow.get("coverage"),
    )


def _season_health(settings: Settings, *, busy: bool) -> dict[str, Any]:
    """A1: diagnose current season readiness only — no LKG serving / no build."""
    from kr_quant.run_generation import is_updating
    from kr_quant.web.season_snapshot import _digest, _folder, read_bundle, source_identity

    lookback = 5  # primary/default season bundle
    season_root = _folder(settings)
    updating = bool(busy) or is_updating(settings)
    hist_like = _season_historical_artifacts(season_root)

    if updating:
        return _component(
            "UPDATING",
            reason="source_or_runner_updating",
            cache_present=bool(hist_like),
            path=str(season_root),
            lookback=lookback,
            lkg_serving="deferred_to_a4",
        )

    # Read-only current contract (same as production read_bundle). Never request_build.
    try:
        bundle = read_bundle(settings, lookback=lookback)
    except Exception as exc:  # noqa: BLE001
        return _component(
            "CORRUPT",
            reason=f"season_read_failed:{type(exc).__name__}",
            path=str(season_root),
            lookback=lookback,
            lkg_serving="deferred_to_a4",
        )

    if isinstance(bundle, dict) and bundle.get("generation_id"):
        return _component(
            "HEALTHY",
            reason="current_season_bundle_valid",
            as_of=(bundle.get("identity") or {}).get("day") if isinstance(bundle.get("identity"), dict) else None,
            path=str(season_root / f"{bundle.get('generation_id')}.json"),
            generation_id=str(bundle.get("generation_id")),
            lookback=lookback,
            lkg_serving="deferred_to_a4",
        )

    # Distinguish corrupt current file vs stale history vs empty.
    try:
        identity = source_identity(settings, lookback)
        expected = _digest(identity)
        expected_path = season_root / f"{expected}.json"
        if expected_path.exists():
            return _component(
                "CORRUPT",
                reason="current_generation_file_invalid",
                path=str(expected_path),
                generation_id=expected,
                lookback=lookback,
                lkg_serving="deferred_to_a4",
            )
    except Exception:  # noqa: BLE001
        expected = None
        expected_path = None

    pointer = season_root / f"latest_lb_{lookback}.json"
    if pointer.exists() and not (expected_path and expected_path.exists()):
        return _component(
            "STALE",
            reason="season_pointer_without_current_generation",
            path=str(pointer),
            lookback=lookback,
            historical_present=True,
            lkg_serving="deferred_to_a4",
        )

    if hist_like:
        return _component(
            "STALE",
            reason="season_historical_only_not_current",
            path=str(season_root),
            lookback=lookback,
            historical_present=True,
            lkg_serving="deferred_to_a4",
        )

    return _component(
        "MISSING",
        reason="current_season_bundle_absent",
        path=str(season_root),
        lookback=lookback,
        historical_present=False,
        lkg_serving="deferred_to_a4",
    )


def _season_historical_artifacts(season_root: Path) -> list[str]:
    """Production-like artifacts only (hex generation ids / latest_lb_*)."""
    if not season_root.exists():
        return []
    found: list[str] = []
    for path in sorted(season_root.glob("*.json")):
        name = path.name
        stem = path.stem
        if name.startswith("latest_lb_"):
            found.append(name)
        elif len(stem) == 64 and all(ch in "0123456789abcdef" for ch in stem.lower()):
            found.append(name)
    return found


def _pipeline_state(
    *,
    components: Mapping[str, Mapping[str, Any]],
    busy: bool,
) -> tuple[str, bool]:
    if busy:
        return "RUNNING", False

    dart = components.get("dart_essential") or {}
    quant = components.get("quant") or {}
    krx = components.get("krx") or {}

    repair_triggers = []
    for name in ("dart_essential", "master", "krx"):
        state = (components.get(name) or {}).get("state")
        if state in {"MISSING", "CORRUPT"}:
            repair_triggers.append(name)
    if quant.get("state") in {"MISSING", "CORRUPT"}:
        repair_triggers.append("quant")
    if quant.get("state") == "BLOCKED" and dart.get("state") in {"MISSING", "CORRUPT"}:
        repair_triggers.append("quant_blocked")

    if repair_triggers:
        return "REPAIR_REQUIRED", True

    if krx.get("state") == "STALE" or quant.get("state") == "STALE":
        return "NEEDS_DAILY_UPDATE", False

    if krx.get("state") == "HEALTHY" and dart.get("state") == "HEALTHY" and quant.get("state") == "HEALTHY":
        return "READY", False

    return "PARTIAL", False


def pipeline_health(
    settings: Settings,
    *,
    now: datetime | None = None,
    busy: bool = False,
    ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only health snapshot.

    ``ledger`` is informational only and must never upgrade missing/corrupt
    artifacts to HEALTHY.
    """
    expected = expected_price_date(now)
    krx = _krx_health(settings, expected=expected, now=now)
    master = _master_health(settings)
    dart_essential = _dart_essential_health(settings)
    facts_ok = dart_essential.get("state") == "HEALTHY"
    dart_coverage = _coverage_from_state(settings, facts_ok=facts_ok)

    blocked_by: list[str] = []
    if dart_essential.get("state") in {"MISSING", "CORRUPT"}:
        blocked_by.append("dart_essential")
    if master.get("state") in {"MISSING", "CORRUPT"}:
        blocked_by.append("master")
    if krx.get("state") in {"MISSING", "CORRUPT"}:
        blocked_by.append("krx")

    quant = _quant_health(settings, price_as_of=krx.get("as_of"), blocked_by=blocked_by)
    kis = _kis_health(settings, expected=expected)
    season = _season_health(settings, busy=busy)

    components = {
        "krx": krx,
        "master": master,
        "dart_essential": dart_essential,
        "dart_coverage": dart_coverage,
        "quant": quant,
        "kis": kis,
        "season": season,
    }
    pipeline_state, repair_required = _pipeline_state(components=components, busy=busy)
    if pipeline_state not in PIPELINE_STATES:
        raise ValueError(f"unsupported pipeline state: {pipeline_state}")

    ledger_info = None
    if isinstance(ledger, Mapping):
        ledger_info = {
            "dart_status": ((ledger.get("steps") or {}).get("dart") or {}).get("status"),
            "quant_status": ((ledger.get("steps") or {}).get("quant") or {}).get("status"),
            "krx_status": ((ledger.get("steps") or {}).get("krx") or {}).get("status"),
            "note": "informational_only_artifact_outranks_ledger",
        }

    return {
        "pipeline_state": pipeline_state,
        "expected_price_date": expected.isoformat(),
        "components": components,
        "repair_required": bool(repair_required) or pipeline_state == "REPAIR_REQUIRED",
        "busy": bool(busy),
        "ledger": ledger_info,
        "authority": "artifact",
    }
