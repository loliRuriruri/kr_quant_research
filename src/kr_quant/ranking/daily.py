from __future__ import annotations

from typing import Any

import pandas as pd

from kr_quant.models import RunContext, ScoredName

OUTPUT_COLS = [
    "run_id",
    "as_of_date",
    "cutoff_ts",
    "model_version",
    "ticker",
    "company",
    "market",
    "sector",
    "industry",
    "quant_rank",
    "quant_score",
    "quant_score_raw",
    "risk_penalty",
    "value_score",
    "quality_score",
    "growth_score",
    "momentum_score",
    "financial_score",
    "previous_rank",
    "rank_change",
    "previous_score",
    "score_change",
    "weighted_metric_coverage",
    "data_confidence",
    "risk_flags",
    "data_flags",
    "per",
    "pbr",
    "ev_ebit",
    "fcf_yield",
    "earnings_yield",
    "roic",
    "roe",
    "operating_margin",
    "revenue_yoy",
    "op_yoy",
    "revenue_3y_cagr",
    "op_3y_cagr",
    "return_3m",
    "return_6m",
    "return_12m",
    "net_debt_assets",
    "interest_coverage",
    "source_bundle_hash",
    "config_hash",
]


def rank_names(names: list[ScoredName]) -> list[ScoredName]:
    eligible = [n for n in names if n.universe_eligible]
    eligible.sort(
        key=lambda n: (
            -n.quant_score,
            -n.quant_score_raw,
            -n.data_confidence,
            n.inputs.ticker,
        )
    )
    return eligible


def rank_raw(names: list[ScoredName]) -> list[ScoredName]:
    ordered = sorted(
        names,
        key=lambda n: (
            -n.quant_score_raw,
            -n.data_confidence,
            n.inputs.ticker,
        ),
    )
    return ordered


def to_records(
    names: list[ScoredName],
    ctx: RunContext,
    company_by_ticker: dict[str, str],
    prev_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prev_by_ticker = prev_by_ticker or {}
    ranked = rank_names(names)
    raw_order = rank_raw(names)
    raw_rank = {n.inputs.ticker: i + 1 for i, n in enumerate(raw_order)}
    rank_map = {n.inputs.ticker: i + 1 for i, n in enumerate(ranked)}

    n_ranked = max(len(ranked), 1)
    out: list[dict[str, Any]] = []
    for n in names:
        ticker = n.inputs.ticker
        qrank = rank_map.get(ticker)
        prev = prev_by_ticker.get(ticker, {})
        prev_rank = prev.get("quant_rank")
        prev_score = prev.get("quant_score")
        score_change = None if prev_score is None else n.quant_score - prev_score
        rank_change = None if prev_rank is None or qrank is None else prev_rank - qrank
        rec = {
            "run_id": ctx.run_id,
            "model_id": ctx.model_id,
            "model_version": ctx.model_version,
            "config_hash": ctx.config_hash,
            "code_commit": ctx.code_commit,
            "source_bundle_hash": ctx.source_bundle_hash,
            "result_hash": ctx.result_hash,
            "as_of_date": ctx.as_of_date.isoformat(),
            "cutoff_ts": ctx.cutoff_ts.isoformat(),
            "decision_date": ctx.decision_date.isoformat(),
            "security_id": n.inputs.security_id,
            "ticker": ticker,
            "corp_code": "",
            "company": company_by_ticker.get(ticker, ticker),
            "market": n.inputs.market,
            "sector_code": n.inputs.sector_code,
            "sector": n.inputs.sector,
            "industry_code": n.inputs.industry_code,
            "industry": n.inputs.industry,
            "universe_eligible": n.universe_eligible,
            "exclusion_reasons": n.exclusion_reasons,
            "value_score": n.value_score,
            "quality_score": n.quality_score,
            "growth_score": n.growth_score,
            "momentum_score": n.momentum_score,
            "financial_score": n.financial_score,
            "quant_score_raw": n.quant_score_raw,
            "risk_penalty": n.risk_penalty,
            "quant_score": n.quant_score,
            "quant_rank_raw": raw_rank.get(ticker),
            "quant_rank": qrank,
            "previous_score": prev_score,
            "score_change": score_change,
            "previous_rank": prev_rank,
            "rank_change": rank_change,
            "previous_percentile": prev.get("rank_percentile"),
            "rank_percentile_change": None,
            "weighted_metric_coverage": n.coverage,
            "data_confidence": n.data_confidence,
            "confidence_components": n.confidence_components,
            "risk_flags": n.risk_flags,
            "data_flags": n.data_flags,
            "metric_values": n.metric_values,
            "metric_peer_scores": n.metric_peer_scores,
            "metric_peer_context": n.metric_peer_context,
            "top100_eligible": n.top100_eligible,
            "top20_eligible": n.top20_eligible,
            "per": n.metric_values.get("per"),
            "pbr": n.metric_values.get("pbr"),
            "ev_ebit": n.metric_values.get("ev_ebit"),
            "fcf_yield": n.metric_values.get("fcf_yield"),
            "earnings_yield": n.metric_values.get("earnings_yield"),
            "roic": n.metric_values.get("roic"),
            "roe": n.metric_values.get("roe"),
            "operating_margin": n.metric_values.get("operating_margin"),
            "revenue_yoy": n.metric_values.get("revenue_yoy_ttm"),
            "op_yoy": n.metric_values.get("op_yoy_ttm"),
            "revenue_3y_cagr": n.metric_values.get("revenue_cagr_3y"),
            "op_3y_cagr": n.metric_values.get("op_cagr_3y"),
            "return_3m": n.metric_values.get("return_3m"),
            "return_6m": n.metric_values.get("return_6m"),
            "return_12m": n.metric_values.get("return_12m"),
            "net_debt_assets": n.metric_values.get("net_debt_assets"),
            "interest_coverage": n.metric_values.get("interest_coverage"),
        }
        if qrank is not None:
            rec["rank_percentile"] = 100.0 * (n_ranked - qrank) / max(n_ranked - 1, 1)
            if prev.get("rank_percentile") is not None:
                rec["rank_percentile_change"] = rec["rank_percentile"] - prev["rank_percentile"]
        else:
            rec["rank_percentile"] = None
        out.append(rec)
    return out


def flatten_flags(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, list):
        return "|".join(str(v) for v in values)
    return str(values)


def export_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records)


def top_slice(df: pd.DataFrame, n: int, eligible_col: str) -> pd.DataFrame:
    work = df[df["universe_eligible"] & df[eligible_col]].copy()
    work = work[work["quant_rank"].notna()].sort_values("quant_rank")
    return work.head(n)
