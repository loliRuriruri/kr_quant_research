from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class MetricResult:
    name: str
    raw: float | None
    state: str
    flags: list[str] = field(default_factory=list)
    participates_in_percentile: bool = False
    counts_as_observed: bool = False
    score: float | None = None
    clipped: float | None = None
    peer_level: str | None = None
    peer_code: str | None = None
    peer_n: int | None = None


@dataclass
class FactorInputs:
    ticker: str
    security_id: str
    market: str
    sector: str | None
    industry: str | None
    sector_code: str | None
    industry_code: str | None
    market_cap: float | None
    preferred_market_cap: float
    close: float | None
    adj_close: float | None
    revenue_ttm: float | None
    revenue_ttm_lag4: float | None
    op_ttm: float | None
    op_ttm_lag4: float | None
    pretax_ttm: float | None
    ni_ttm: float | None
    nio_ttm: float | None
    nio_ttm_lag4: float | None
    cfo_ttm: float | None
    capex_ttm: float | None
    interest_expense_ttm: float | None
    income_tax_ttm: float | None
    assets: float | None
    assets_4q: float | None
    liabilities: float | None
    equity: float | None
    equity_4q: float | None
    equity_owners: float | None
    equity_owners_4q: float | None
    nci: float | None
    cash: float | None
    sfa: float | None
    cash_4q: float | None
    sfa_4q: float | None
    current_assets: float | None
    current_liabilities: float | None
    interest_bearing_debt: float | None
    interest_bearing_debt_4q: float | None
    revenue_fy0: float | None
    revenue_fy3: float | None
    op_fy0: float | None
    op_fy3: float | None
    fcf_fy_hist: list[float | None] = field(default_factory=list)
    revenue_yoy_hist: list[float | None] = field(default_factory=list)
    op_yoy_hist: list[float | None] = field(default_factory=list)
    quarterly_op_margins: list[float] = field(default_factory=list)
    annual_tax_pairs: list[tuple[float, float]] = field(default_factory=list)
    shares_latest: float | None = None
    shares_12m_ago: float | None = None
    diluted_shares_ttm: float | None = None
    diluted_shares_ttm_lag4: float | None = None
    potential_dilution_pct: float | None = None
    cb_bw_count_24m: int = 0
    fs_div: str | None = None
    latest_period_end: date | None = None
    available_date: date | None = None
    rcept_no: str | None = None
    pit_integrity: float = 1.0
    history_score: float = 0.0
    recon_score: float = 1.0
    q4_anomaly: bool = False
    flow_subtraction_ok: bool = True
    n_annual: int = 0
    n_quarter: int = 0
    listed_pref_unknown: bool = False
    extra_flags: list[str] = field(default_factory=list)
    return_3m: float | None = None
    return_6m: float | None = None
    return_12m: float | None = None
    market_return_6m: float | None = None
    high_52w: float | None = None
    krx_risk_class: str | None = None


@dataclass
class ScoredName:
    inputs: FactorInputs
    metrics: dict[str, MetricResult]
    value_score: float
    quality_score: float
    growth_score: float
    momentum_score: float
    financial_score: float
    quant_score_raw: float
    risk_penalty: float
    quant_score: float
    coverage: float
    data_confidence: float
    confidence_components: dict[str, float]
    risk_flags: list[str]
    data_flags: list[str]
    hard_reasons: list[str]
    universe_eligible: bool
    top100_eligible: bool
    top20_eligible: bool
    metric_peer_scores: dict[str, float]
    metric_values: dict[str, float | None]
    metric_peer_context: dict[str, Any]
    exclusion_reasons: list[str] = field(default_factory=list)


@dataclass
class RunContext:
    run_id: str
    as_of_date: date
    cutoff_ts: datetime
    decision_date: date
    model_id: str
    model_version: str
    config_hash: str
    source_bundle_hash: str
    code_commit: str
    result_hash: str = ""
    status: str = "running"
    warnings: list[str] = field(default_factory=list)
