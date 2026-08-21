from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from kr_quant.models import RunContext


HISTORY_TABLE = "fact_daily_ranking"


def connect(db_path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    from kr_quant.flow.store import init_investor_db

    init_investor_db(con)
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
            run_id VARCHAR,
            model_id VARCHAR,
            model_version VARCHAR,
            config_hash VARCHAR,
            code_commit VARCHAR,
            source_bundle_hash VARCHAR,
            result_hash VARCHAR,
            as_of_date DATE,
            cutoff_ts TIMESTAMPTZ,
            decision_date DATE,
            security_id VARCHAR,
            ticker VARCHAR,
            company VARCHAR,
            market VARCHAR,
            sector VARCHAR,
            industry VARCHAR,
            universe_eligible BOOLEAN,
            quant_score DOUBLE,
            quant_score_raw DOUBLE,
            risk_penalty DOUBLE,
            quant_rank INTEGER,
            data_confidence DOUBLE,
            weighted_metric_coverage DOUBLE,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (run_id, as_of_date, security_id)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS run_manifest (
            run_id VARCHAR PRIMARY KEY,
            as_of_date DATE,
            model_version VARCHAR,
            status VARCHAR,
            config_hash VARCHAR,
            source_bundle_hash VARCHAR,
            result_hash VARCHAR,
            code_commit VARCHAR,
            cutoff_ts TIMESTAMPTZ,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS latest_success (
            model_version VARCHAR PRIMARY KEY,
            run_id VARCHAR,
            as_of_date DATE,
            result_hash VARCHAR
        )
        """
    )


def load_previous(
    con: duckdb.DuckDBPyConnection,
    model_version: str,
    as_of_date,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Return previous-day map and whether model version broke."""
    row = con.execute(
        f"""
        SELECT as_of_date, model_version
        FROM {HISTORY_TABLE}
        WHERE as_of_date < ?
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        [as_of_date],
    ).fetchone()
    if row is None:
        return {}, False
    prev_date, prev_ver = row
    if str(prev_ver) != str(model_version):
        return {}, True
    df = con.execute(
        f"""
        SELECT ticker, quant_rank, quant_score
        FROM {HISTORY_TABLE}
        WHERE as_of_date = ? AND model_version = ?
        """,
        [prev_date, model_version],
    ).fetchdf()
    out: dict[str, dict[str, Any]] = {}
    if df.empty:
        return out, False
    n = max(len(df[df["quant_rank"].notna()]), 1)
    for rec in df.to_dict("records"):
        rank = rec["quant_rank"]
        pct = None if pd.isna(rank) else 100.0 * (n - int(rank)) / max(n - 1, 1)
        out[rec["ticker"]] = {
            "quant_rank": None if pd.isna(rank) else int(rank),
            "quant_score": rec["quant_score"],
            "rank_percentile": pct,
        }
    return out, False


def detect_events(records: list[dict[str, Any]], cfg: dict[str, Any], model_break: bool) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = []
    ch = cfg["changes"]
    for rec in records:
        ticker = rec["ticker"]
        rank = rec.get("quant_rank")
        prev_rank = rec.get("previous_rank")
        score_change = rec.get("score_change")
        rank_change = rec.get("rank_change")
        if model_break:
            ev.append(_event(rec, "MODEL_BREAK"))
            continue
        if rank is not None and rank <= 100 and (prev_rank is None or prev_rank > 100):
            ev.append(_event(rec, "NEW_TOP100"))
        if rank is not None and rank <= 20 and (prev_rank is None or prev_rank > 20):
            ev.append(_event(rec, "NEW_TOP20"))
        if prev_rank is not None and prev_rank <= 20 and (rank is None or rank > 20):
            ev.append(_event(rec, "EXIT_TOP20"))
        if score_change is not None and score_change >= float(ch["score_up"]):
            ev.append(_event(rec, "SCORE_UP_5"))
        if score_change is not None and score_change <= float(ch["score_down"]):
            ev.append(_event(rec, "SCORE_DOWN_5"))
        pct_chg = rec.get("rank_percentile_change")
        if (rank_change is not None and rank_change >= int(ch["rank_abs"])) or (
            pct_chg is not None and pct_chg >= float(ch["rank_percentile_points"])
        ):
            ev.append(_event(rec, "RANK_SURGE"))
        if (rank_change is not None and rank_change <= -int(ch["rank_abs"])) or (
            pct_chg is not None and pct_chg <= -float(ch["rank_percentile_points"])
        ):
            ev.append(_event(rec, "RANK_DROP"))
        _ = ticker
    return ev


def _event(rec: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "run_id": rec["run_id"],
        "as_of_date": rec["as_of_date"],
        "ticker": rec["ticker"],
        "company": rec.get("company"),
        "event": kind,
        "quant_rank": rec.get("quant_rank"),
        "previous_rank": rec.get("previous_rank"),
        "quant_score": rec.get("quant_score"),
        "score_change": rec.get("score_change"),
    }


def persist_history(con: duckdb.DuckDBPyConnection, ctx: RunContext, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    slim = pd.DataFrame(
        [
            {
                "run_id": r["run_id"],
                "model_id": r["model_id"],
                "model_version": r["model_version"],
                "config_hash": r["config_hash"],
                "code_commit": r["code_commit"],
                "source_bundle_hash": r["source_bundle_hash"],
                "result_hash": r["result_hash"],
                "as_of_date": r["as_of_date"],
                "cutoff_ts": r["cutoff_ts"],
                "decision_date": r["decision_date"],
                "security_id": r["security_id"],
                "ticker": r["ticker"],
                "company": r["company"],
                "market": r["market"],
                "sector": r.get("sector"),
                "industry": r.get("industry"),
                "universe_eligible": r["universe_eligible"],
                "quant_score": r["quant_score"],
                "quant_score_raw": r["quant_score_raw"],
                "risk_penalty": r["risk_penalty"],
                "quant_rank": r.get("quant_rank"),
                "data_confidence": r["data_confidence"],
                "weighted_metric_coverage": r["weighted_metric_coverage"],
            }
            for r in records
        ]
    )
    con.execute(f"DELETE FROM {HISTORY_TABLE} WHERE run_id = ?", [ctx.run_id])
    con.register("slim_df", slim)
    con.execute(
        f"""
        INSERT INTO {HISTORY_TABLE} (
            run_id, model_id, model_version, config_hash, code_commit,
            source_bundle_hash, result_hash, as_of_date, cutoff_ts, decision_date,
            security_id, ticker, company, market, sector, industry, universe_eligible,
            quant_score, quant_score_raw, risk_penalty, quant_rank,
            data_confidence, weighted_metric_coverage
        )
        SELECT
            run_id, model_id, model_version, config_hash, code_commit,
            source_bundle_hash, result_hash, CAST(as_of_date AS DATE), CAST(cutoff_ts AS TIMESTAMPTZ),
            CAST(decision_date AS DATE), security_id, ticker, company, market, sector, industry,
            universe_eligible, quant_score, quant_score_raw, risk_penalty, quant_rank,
            data_confidence, weighted_metric_coverage
        FROM slim_df
        """
    )
    con.unregister("slim_df")
    con.execute("DELETE FROM run_manifest WHERE run_id = ?", [ctx.run_id])
    con.execute(
        """
        INSERT INTO run_manifest
        (run_id, as_of_date, model_version, status, config_hash, source_bundle_hash, result_hash, code_commit, cutoff_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ctx.run_id,
            ctx.as_of_date,
            ctx.model_version,
            ctx.status,
            ctx.config_hash,
            ctx.source_bundle_hash,
            ctx.result_hash,
            ctx.code_commit,
            ctx.cutoff_ts,
        ],
    )
    if ctx.status == "success":
        con.execute("DELETE FROM latest_success WHERE model_version = ?", [ctx.model_version])
        con.execute(
            "INSERT INTO latest_success VALUES (?, ?, ?, ?)",
            [ctx.model_version, ctx.run_id, ctx.as_of_date, ctx.result_hash],
        )
