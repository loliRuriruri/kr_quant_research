from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


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
        current["ticker"] = current["ticker"].astype(str).str.zfill(6)
        observed = set(current["ticker"])
    else:
        observed = set()
    snapshot = eligible_master.copy()
    if "ticker" not in snapshot.columns:
        snapshot["ticker"] = pd.Series(dtype=str)
    snapshot["ticker"] = snapshot["ticker"].astype(str).str.zfill(6)
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
    }
