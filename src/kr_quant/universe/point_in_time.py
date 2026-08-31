from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.universe.identifiers import canonical_ticker

HISTORY_COLUMNS = ["ticker", "event_type", "event_date", "market", "company", "source", "detail"]
ACTIVE_EVENTS = frozenset({"LIST", "RESUME", "MARKET_TRANSFER"})
INACTIVE_EVENTS = frozenset({"DELIST", "HALT"})


def _day(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def filter_master_as_of(master: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply only listing-life facts that are actually present in the master.

    Unknown dates are retained and disclosed. Dropping them would fabricate a
    cleaner historical universe than the source can support.
    """
    if master is None or master.empty:
        return pd.DataFrame(), {
            "as_of_date": as_of.isoformat(),
            "input_count": 0,
            "eligible_count": 0,
            "listing_date_coverage": 0.0,
            "delisting_date_coverage": 0.0,
            "excluded_not_yet_listed": 0,
            "excluded_already_delisted": 0,
            "state": "MISSING",
        }

    frame = master.copy()
    listing_col = next((name for name in ("list_date", "listing_date") if name in frame.columns), None)
    delisting_col = next((name for name in ("delist_date", "delisting_date") if name in frame.columns), None)
    listed = (
        pd.to_datetime(frame[listing_col], errors="coerce").dt.date
        if listing_col
        else pd.Series([None] * len(frame), index=frame.index, dtype=object)
    )
    delisted = (
        pd.to_datetime(frame[delisting_col], errors="coerce").dt.date
        if delisting_col
        else pd.Series([None] * len(frame), index=frame.index, dtype=object)
    )
    future_listing = listed.notna() & (listed > as_of)
    past_delisting = delisted.notna() & (delisted <= as_of)
    keep = ~(future_listing | past_delisting)
    listing_coverage = float(listed.notna().mean()) if len(frame) else 0.0
    delisting_coverage = float(delisted.notna().mean()) if len(frame) and delisting_col else 0.0
    state = "PARTIAL_LISTING_LIFE"
    if listing_coverage >= 0.95 and delisting_col and delisting_coverage >= 0.95:
        state = "LISTING_LIFE_COVERED"
    elif listing_coverage < 0.50:
        state = "LIMITED"
    return frame.loc[keep].copy(), {
        "as_of_date": as_of.isoformat(),
        "input_count": int(len(frame)),
        "eligible_count": int(keep.sum()),
        "listing_date_coverage": round(listing_coverage, 4),
        "delisting_date_coverage": round(delisting_coverage, 4),
        "excluded_not_yet_listed": int(future_listing.sum()),
        "excluded_already_delisted": int(past_delisting.sum()),
        "state": state,
    }


def build_universe_snapshot(
    master: pd.DataFrame,
    price_day: pd.DataFrame,
    *,
    as_of: date,
    source_mode: str,
    captured_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    captured_at = captured_at or datetime.now(timezone.utc)
    eligible_master, life = filter_master_as_of(master, as_of)
    current = price_day.copy() if price_day is not None else pd.DataFrame()
    if "ticker" in current.columns:
        current["ticker"] = current["ticker"].map(lambda value: canonical_ticker(value) or str(value).zfill(6))
        observed = set(current["ticker"])
    else:
        observed = set()
    snapshot = eligible_master.copy()
    if "ticker" not in snapshot.columns:
        snapshot["ticker"] = pd.Series(dtype=str)
    snapshot["ticker"] = snapshot["ticker"].map(lambda value: canonical_ticker(value) or str(value).zfill(6))
    snapshot["observed_price_on_as_of"] = snapshot["ticker"].isin(observed)
    snapshot["as_of_date"] = as_of.isoformat()
    snapshot["captured_at"] = captured_at.isoformat()
    snapshot["source_mode"] = source_mode

    lag_days = (captured_at.date() - as_of).days
    if source_mode == "demo":
        capture_state = "DEMO"
    elif 0 <= lag_days <= 4:
        capture_state = "CONTEMPORANEOUS"
    else:
        capture_state = "RECONSTRUCTED_CURRENT_MASTER"
    snapshot["capture_state"] = capture_state
    evidence = {
        **life,
        "capture_state": capture_state,
        "captured_at": captured_at.isoformat(),
        "observed_price_count": int(snapshot["observed_price_on_as_of"].sum()),
        "snapshot_count": int(len(snapshot)),
        "source_mode": source_mode,
        "survivorship_bias_controlled": capture_state == "CONTEMPORANEOUS",
        "limitation": (
            "해당 거래일 무렵 저장한 KRX 구성종목 스냅샷입니다. 이후 과거 재현에 사용할 수 있습니다."
            if capture_state == "CONTEMPORANEOUS"
            else "현재 마스터로 과거 시점을 재구성했으므로 당시 상장폐지 종목 누락 가능성을 제거하지 못합니다."
        ),
    }
    return snapshot, evidence


def _snapshot_dates(output_dir: Path) -> list[date]:
    dates: list[date] = []
    for path in output_dir.glob("as_of_date=*/universe_snapshot.parquet"):
        parsed = _day(path.parent.name.removeprefix("as_of_date="))
        if parsed:
            dates.append(parsed)
    return sorted(set(dates))


def strategy_universe_evidence(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]],
    selection_as_of: str | None,
) -> dict[str, Any]:
    history_starts = [_day(row.get("from")) for row in rows if isinstance(row, dict)]
    history_starts = [value for value in history_starts if value is not None]
    snapshots = _snapshot_dates(output_dir)
    return {
        "selection_mode": "CURRENT_TOP20_RETROSPECTIVE",
        "selection_as_of": selection_as_of,
        "backtest_history_from": min(history_starts).isoformat() if history_starts else None,
        "archived_snapshot_count": len(snapshots),
        "archived_snapshot_from": snapshots[0].isoformat() if snapshots else None,
        "archived_snapshot_to": snapshots[-1].isoformat() if snapshots else None,
        "survivorship_bias_controlled": False,
        "research_grade": "LIMITED_CURRENT_COHORT",
        "limitation": (
            "현재 퀀트 TOP20으로 뽑힌 종목을 과거 가격에 소급 적용한 종목별 규칙 연구입니다. "
            "각 과거 시점의 상장·상장폐지 종목 전체를 다시 선정한 횡단면 PIT 백테스트가 아니므로 생존편향이 남습니다."
        ),
        "next_step": "일별 universe_snapshot.parquet가 누적된 이후 해당 날짜 구성종목만 사용한 횡단면 재선정 백테스트로 전환합니다.",
        "pit_portfolio_available": len(snapshots) >= 3,
    }


def empty_listing_history() -> pd.DataFrame:
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def _tickers(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty or "ticker" not in frame.columns:
        return pd.Series(dtype=str)
    return frame["ticker"].map(lambda value: canonical_ticker(value) or str(value).zfill(6))


def active_members(history: pd.DataFrame, as_of: date) -> set[str]:
    if history is None or history.empty:
        return set()
    work = history.copy()
    work["ticker"] = _tickers(work)
    work["event_date"] = pd.to_datetime(work["event_date"], errors="coerce").dt.date
    work = work.dropna(subset=["event_date"])
    work = work[work["event_date"] <= as_of].sort_values(["ticker", "event_date"])
    if work.empty:
        return set()
    last = work.drop_duplicates("ticker", keep="last")
    return set(last.loc[last["event_type"].isin(ACTIVE_EVENTS), "ticker"])


def update_listing_history(
    history: pd.DataFrame | None,
    master: pd.DataFrame,
    as_of: date,
    *,
    source: str = "KRX_MASTER",
) -> pd.DataFrame:
    """Append LIST/DELIST/TRANSFER from today's master vs prior active set."""
    prior = history.copy() if history is not None and not history.empty else empty_listing_history()
    if prior.empty:
        prior = empty_listing_history()
    current = master.copy() if master is not None else pd.DataFrame()
    if current.empty or "ticker" not in current.columns:
        return prior
    current["ticker"] = _tickers(current)
    current = current[current["ticker"].astype(str) != ""].drop_duplicates("ticker")
    current_set = set(current["ticker"])
    prev_as_of = as_of - timedelta(days=1)
    previous = active_members(prior, prev_as_of)
    rows: list[dict[str, Any]] = []
    indexed = current.set_index("ticker", drop=False)
    for ticker in sorted(current_set - previous):
        row = indexed.loc[ticker]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        list_date = _day(row.get("list_date"))
        market = str(row.get("market") or "")
        company = str(row.get("company") or "")
        rows.append(
            {
                "ticker": ticker,
                "event_type": "LIST",
                "event_date": list_date or as_of,
                "market": market,
                "company": company,
                "source": source,
                "detail": "master_appearance",
            }
        )
    for ticker in sorted(previous - current_set):
        rows.append(
            {
                "ticker": ticker,
                "event_type": "DELIST",
                "event_date": as_of,
                "market": "",
                "company": "",
                "source": source,
                "detail": "missing_from_master",
            }
        )
    if "market" in current.columns and not prior.empty:
        last_market = (
            prior.sort_values("event_date")
            .drop_duplicates("ticker", keep="last")
            .set_index("ticker")["market"]
            if "market" in prior.columns
            else pd.Series(dtype=str)
        )
        for ticker in sorted(current_set & previous):
            market = str(indexed.loc[ticker].get("market") or "")
            old = str(last_market.get(ticker) or "")
            if market and old and market != old:
                rows.append(
                    {
                        "ticker": ticker,
                        "event_type": "MARKET_TRANSFER",
                        "event_date": as_of,
                        "market": market,
                        "company": str(indexed.loc[ticker].get("company") or ""),
                        "source": source,
                        "detail": f"{old}->{market}",
                    }
                )
    if not rows:
        return prior
    added = pd.DataFrame(rows)
    out = pd.concat([prior, added], ignore_index=True)
    out["ticker"] = _tickers(out)
    out["event_date"] = pd.to_datetime(out["event_date"], errors="coerce").dt.date
    return out.drop_duplicates(["ticker", "event_type", "event_date"], keep="last").reset_index(drop=True)


def load_listing_history(settings) -> pd.DataFrame:
    path = settings.staged_dir / "live" / "listing_history.parquet"
    if not path.exists():
        path = settings.staged_dir / "demo" / "listing_history.parquet"
    if not path.exists():
        return empty_listing_history()
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return empty_listing_history()


def save_listing_history(settings, history: pd.DataFrame) -> None:
    from kr_quant.atomic_io import write_parquet_atomic

    folder = settings.staged_dir / "live"
    folder.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(history, folder / "listing_history.parquet")


def load_archived_snapshot(output_dir: Path, as_of: date) -> pd.DataFrame | None:
    path = Path(output_dir) / f"as_of_date={as_of.isoformat()}" / "universe_snapshot.parquet"
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None
    if frame.empty:
        return None
    frame["ticker"] = _tickers(frame)
    return frame


def universe_as_of(
    as_of: date,
    *,
    master: pd.DataFrame,
    output_dir: Path | None = None,
    history: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Members that should exist on as_of, with an honest reconstruction source."""
    archived = load_archived_snapshot(output_dir, as_of) if output_dir is not None else None
    if archived is not None:
        life = {
            "as_of_date": as_of.isoformat(),
            "eligible_count": int(len(archived)),
            "reconstruction_source": "ARCHIVED_SNAPSHOT",
            "survivorship_bias_controlled": True,
            "state": "ARCHIVED_SNAPSHOT",
        }
        return archived, life
    hist = history if history is not None else empty_listing_history()
    active = active_members(hist, as_of)
    if active:
        frame = master.copy() if master is not None else pd.DataFrame()
        if not frame.empty and "ticker" in frame.columns:
            frame["ticker"] = _tickers(frame)
            present = frame[frame["ticker"].isin(active)].copy()
        else:
            present = pd.DataFrame({"ticker": sorted(active)})
        missing = sorted(active - set(present["ticker"] if "ticker" in present.columns else []))
        if missing:
            extra = pd.DataFrame({"ticker": missing})
            present = pd.concat([present, extra], ignore_index=True)
        delist_events = int((hist["event_type"] == "DELIST").sum()) if not hist.empty else 0
        return present, {
            "as_of_date": as_of.isoformat(),
            "eligible_count": int(len(present)),
            "reconstruction_source": "LISTING_HISTORY",
            "survivorship_bias_controlled": delist_events > 0,
            "delist_events": delist_events,
            "history_only_tickers": len(missing),
            "state": "LISTING_HISTORY",
        }
    filtered, life = filter_master_as_of(master, as_of)
    life = {
        **life,
        "reconstruction_source": "CURRENT_MASTER",
        "survivorship_bias_controlled": life.get("state") == "LISTING_LIFE_COVERED",
    }
    return filtered, life


def facts_as_of(facts: pd.DataFrame, as_of: date) -> pd.DataFrame:
    if facts is None or facts.empty:
        return pd.DataFrame() if facts is None else facts.copy()
    if "available_date" not in facts.columns:
        out = facts.copy()
        out.attrs["pit_financials"] = False
        return out
    work = facts.copy()
    available = pd.to_datetime(work["available_date"], errors="coerce").dt.date
    return work[available.notna() & (available <= as_of)].copy()


def pit_cross_section(
    as_of: date,
    *,
    master: pd.DataFrame,
    facts: pd.DataFrame | None = None,
    output_dir: Path | None = None,
    history: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    members, evidence = universe_as_of(as_of, master=master, output_dir=output_dir, history=history)
    tickers = set(_tickers(members)) if not members.empty else set()
    usable_facts = facts_as_of(facts, as_of) if facts is not None else pd.DataFrame()
    fact_tickers = set(_tickers(usable_facts)) if not usable_facts.empty else set()
    evidence["financial_pit"] = "available_date" in (facts.columns if facts is not None else [])
    evidence["members_with_pit_facts"] = int(len(tickers & fact_tickers))
    evidence["future_listing_in_members"] = 0
    if not members.empty and "list_date" in members.columns:
        listed = pd.to_datetime(members["list_date"], errors="coerce").dt.date
        evidence["future_listing_in_members"] = int((listed.notna() & (listed > as_of)).sum())
    return members, evidence


def validate_historical_universes(
    dates: list[date],
    *,
    master: pd.DataFrame,
    output_dir: Path | None = None,
    history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    reports = []
    for as_of in dates:
        members, evidence = pit_cross_section(
            as_of,
            master=master,
            output_dir=output_dir,
            history=history,
        )
        reports.append(
            {
                "as_of_date": as_of.isoformat(),
                "member_count": int(len(members)),
                "future_listing_in_members": evidence.get("future_listing_in_members") or 0,
                "reconstruction_source": evidence.get("reconstruction_source"),
                "survivorship_bias_controlled": bool(evidence.get("survivorship_bias_controlled")),
            }
        )
    return {
        "dates": [item["as_of_date"] for item in reports],
        "ok": bool(reports) and all(item["future_listing_in_members"] == 0 for item in reports),
        "reports": reports,
    }


def pit_portfolio_study(
    output_dir: Path,
    *,
    top_n: int = 20,
    cost_bps: float = 10.0,
) -> dict[str, Any]:
    """Equal-weight members from archived snapshots. Not a current-TOP20 backtest."""
    dates = _snapshot_dates(output_dir)
    if len(dates) < 3:
        return {
            "selection_mode": "PIT_ARCHIVED_UNIVERSE",
            "research_grade": "UNAVAILABLE",
            "survivorship_bias_controlled": False,
            "used_in_quant": False,
            "archived_snapshot_count": len(dates),
            "limitation": "보관된 유니버스 스냅샷이 3개 미만이라 횡단면 PIT 재선정을 주장하지 않습니다.",
        }
    holdings: set[str] = set()
    turnovers: list[float] = []
    for as_of in dates:
        snap = load_archived_snapshot(output_dir, as_of)
        if snap is None or snap.empty:
            continue
        if "top20_eligible" in snap.columns:
            chosen = snap[snap["top20_eligible"].fillna(False).astype(bool)]
            if chosen.empty:
                chosen = snap
        else:
            chosen = snap
        tickers = list(_tickers(chosen).drop_duplicates())
        tickers = tickers[:top_n]
        nxt = set(tickers)
        if holdings:
            traded = len(holdings.symmetric_difference(nxt)) / max(len(holdings | nxt), 1)
            turnovers.append(traded)
        holdings = nxt
    mean_turnover = sum(turnovers) / len(turnovers) if turnovers else 0.0
    return {
        "selection_mode": "PIT_ARCHIVED_UNIVERSE",
        "research_grade": "PIT_ARCHIVED_UNIVERSE",
        "survivorship_bias_controlled": True,
        "used_in_quant": False,
        "archived_snapshot_count": len(dates),
        "rebalance_count": len(dates),
        "mean_turnover": round(mean_turnover, 4),
        "cost_bps": float(cost_bps),
        "estimated_turnover_cost": round(mean_turnover * float(cost_bps) / 10_000, 6),
        "distinct_from": "CURRENT_TOP20_RETROSPECTIVE",
        "limitation": "보관 스냅샷 구성종목의 동일가중 교체 연구입니다. 현재 TOP20 소급 연구와 같은 결과가 아닙니다.",
    }
