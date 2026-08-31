"""DuckDB persistence for official investor flows. Overlay only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from kr_quant.settings import Settings

TABLE = "investor_flows_daily"


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_investor_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            trade_date DATE,
            ticker VARCHAR,
            investor_type VARCHAR,
            investor_type_raw VARCHAR,
            buy_value DOUBLE,
            sell_value DOUBLE,
            net_value DOUBLE,
            buy_qty DOUBLE,
            sell_qty DOUBLE,
            net_qty DOUBLE,
            is_final BOOLEAN,
            source VARCHAR,
            fetched_at TIMESTAMP,
            run_id VARCHAR,
            PRIMARY KEY (trade_date, ticker, investor_type, source)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ownership_positions (
            report_date DATE,
            ticker VARCHAR,
            holder_name VARCHAR,
            holding_ratio DOUBLE,
            previous_ratio DOUBLE,
            share_count DOUBLE,
            receipt_no VARCHAR,
            available_date DATE,
            source VARCHAR,
            fetched_at TIMESTAMP,
            PRIMARY KEY (report_date, ticker, holder_name, source, receipt_no)
        )
        """
    )


def upsert_flows(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    init_investor_db(con)
    n = 0
    for row in rows:
        con.execute(
            f"""
            INSERT OR REPLACE INTO {TABLE} (
                trade_date, ticker, investor_type, investor_type_raw,
                buy_value, sell_value, net_value, buy_qty, sell_qty, net_qty,
                is_final, source, fetched_at, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row.get("trade_date"),
                row.get("ticker"),
                row.get("investor_type"),
                row.get("investor_type_raw"),
                row.get("buy_value"),
                row.get("sell_value"),
                row.get("net_value"),
                row.get("buy_qty"),
                row.get("sell_qty"),
                row.get("net_qty"),
                bool(row.get("is_final", True)),
                row.get("source") or "KIS",
                row.get("fetched_at") or datetime.now(timezone.utc).replace(tzinfo=None),
                row.get("run_id"),
            ],
        )
        n += 1
    return n


def coverage(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    init_investor_db(con)
    total = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    tickers = con.execute(f"SELECT count(DISTINCT ticker) FROM {TABLE}").fetchone()[0]
    last = con.execute(f"SELECT max(trade_date) FROM {TABLE}").fetchone()[0]
    types = [r[0] for r in con.execute(f"SELECT DISTINCT investor_type FROM {TABLE} ORDER BY 1").fetchall()]
    return {
        "rows": int(total or 0),
        "tickers": int(tickers or 0),
        "last_date": None if last is None else (last.isoformat() if hasattr(last, "isoformat") else str(last)[:10]),
        "investor_types": types,
        "used_in_quant": False,
    }


def load_all_flows(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    init_investor_db(con)
    cur = con.execute(
        f"""
        SELECT trade_date, ticker, investor_type, investor_type_raw,
               buy_value, sell_value, net_value, buy_qty, sell_qty, net_qty,
               is_final, source, fetched_at
        FROM {TABLE}
        ORDER BY ticker, trade_date, investor_type
        """
    )
    cols = [d[0] for d in cur.description]
    out = []
    for rec in cur.fetchall():
        row = dict(zip(cols, rec, strict=False))
        if isinstance(row.get("trade_date"), date):
            row["trade_date"] = row["trade_date"].isoformat()
        out.append(row)
    return out


def load_ticker(con: duckdb.DuckDBPyConnection, ticker: str) -> list[dict[str, Any]]:
    init_investor_db(con)
    from kr_quant.universe.identifiers import canonical_ticker

    code = canonical_ticker(ticker)
    cur = con.execute(
        f"""
        SELECT trade_date, ticker, investor_type, investor_type_raw,
               buy_value, sell_value, net_value, buy_qty, sell_qty, net_qty,
               is_final, source, fetched_at
        FROM {TABLE}
        WHERE ticker = ?
        ORDER BY trade_date DESC, investor_type
        """,
        [code],
    )
    cols = [d[0] for d in cur.description]
    out = []
    for rec in cur.fetchall():
        row = dict(zip(cols, rec))
        if isinstance(row.get("trade_date"), date):
            row["trade_date"] = row["trade_date"].isoformat()
        out.append(row)
    return out


def upsert_ownership(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    init_investor_db(con)
    n = 0
    for row in rows:
        receipt = str(row.get("receipt_no") or row.get("rcept_no") or "none")
        holder = str(row.get("holder_name") or "")
        from kr_quant.universe.identifiers import canonical_ticker

        ticker = canonical_ticker(row.get("ticker") or "")
        if ticker == "000000":
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO ownership_positions (
                report_date, ticker, holder_name, holding_ratio, previous_ratio,
                share_count, receipt_no, available_date, source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row.get("report_date"),
                ticker,
                holder,
                row.get("holding_ratio"),
                row.get("previous_ratio"),
                row.get("share_count"),
                receipt,
                row.get("available_date") or row.get("report_date"),
                row.get("source") or "OPENDART_MAJORSTOCK",
                row.get("fetched_at") or datetime.now(timezone.utc).replace(tzinfo=None),
            ],
        )
        n += 1
    return n


def coverage_ownership(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    init_investor_db(con)
    total = con.execute("SELECT count(*) FROM ownership_positions").fetchone()[0]
    tickers = con.execute("SELECT count(DISTINCT ticker) FROM ownership_positions").fetchone()[0]
    last = con.execute("SELECT max(report_date) FROM ownership_positions").fetchone()[0]
    return {
        "rows": int(total or 0),
        "tickers": int(tickers or 0),
        "last_date": None if last is None else (last.isoformat() if hasattr(last, "isoformat") else str(last)[:10]),
        "used_in_quant": False,
    }


def load_ownership(con: duckdb.DuckDBPyConnection, *, nps_only: bool = False) -> list[dict[str, Any]]:
    init_investor_db(con)
    cur = con.execute(
        """
        SELECT report_date, ticker, holder_name, holding_ratio, previous_ratio,
               share_count, receipt_no, available_date, source, fetched_at
        FROM ownership_positions
        ORDER BY report_date DESC, holding_ratio DESC
        """
    )
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    from kr_quant.ownership.nps import is_nps_holder

    for rec in cur.fetchall():
        row = dict(zip(cols, rec, strict=False))
        if isinstance(row.get("report_date"), date):
            row["report_date"] = row["report_date"].isoformat()
        if isinstance(row.get("available_date"), date):
            row["available_date"] = row["available_date"].isoformat()
        row["is_nps"] = is_nps_holder(row.get("holder_name"))
        row["used_in_quant"] = False
        if nps_only and not row["is_nps"]:
            continue
        out.append(row)
    return out


def open_settings(settings: Settings) -> duckdb.DuckDBPyConnection:
    con = connect(settings.db_path)
    init_investor_db(con)
    return con
