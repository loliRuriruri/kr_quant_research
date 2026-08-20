from __future__ import annotations

from typing import Any

from kr_quant.financials import formulas as F
from kr_quant.models import FactorInputs, MetricResult, ScoredName
from kr_quant.risk.rules import apply_soft_penalties


def history_component(n_annual: int, n_quarter: int) -> float:
    if n_annual >= 4 and n_quarter >= 12:
        return 1.0
    if n_annual >= 3 and n_quarter >= 8:
        return 0.7
    if n_quarter >= 4:
        return 0.4
    return 0.0


def _momentum_disabled(name: str) -> MetricResult:
    return MetricResult(
        name=name,
        raw=None,
        state="INSUFFICIENT_HISTORY",
        flags=["MOMENTUM_DISABLED_NO_ADJ_CLOSE"],
        participates_in_percentile=False,
        counts_as_observed=False,
        score=50.0,
    )


def _implied_start_price(end_px: float | None, ret: float | None) -> float | None:
    if end_px is None or ret is None:
        return None
    return end_px / (1.0 + ret)


def build_metrics(inp: FactorInputs, cfg: dict[str, Any]) -> dict[str, MetricResult]:
    metrics: dict[str, MetricResult] = {}

    sfa_for_ev = inp.sfa if cfg["formulas"]["ev_deduct_sfa"] else 0.0
    ev, ev_flags = F.compute_ev(
        inp.market_cap,
        inp.preferred_market_cap,
        inp.interest_bearing_debt,
        inp.nci,
        inp.cash,
        sfa_for_ev,
    )
    if inp.listed_pref_unknown:
        ev_flags.append("PREFERRED_CAPITAL_UNKNOWN")

    fcf, fcf_flags = F.compute_fcf(inp.cfo_ttm, inp.capex_ttm)
    tax_rate, tax_flags = F.select_tax_rate(
        inp.annual_tax_pairs,
        inp.pretax_ttm,
        inp.income_tax_ttm,
        default_rate=float(cfg["formulas"]["default_tax_rate"]),
        max_rate=float(cfg["formulas"]["tax_rate_max"]),
    )
    ic_latest = F.invested_capital(inp.equity, inp.interest_bearing_debt, inp.cash, inp.sfa)
    ic_4q = F.invested_capital(inp.equity_4q, inp.interest_bearing_debt_4q, inp.cash_4q, inp.sfa_4q)

    metrics["per"] = F.compute_per(inp.market_cap, inp.nio_ttm)
    metrics["earnings_yield"] = F.compute_earnings_yield(inp.market_cap, inp.nio_ttm)
    metrics["pbr"] = F.compute_pbr(inp.market_cap, inp.equity_owners)
    metrics["ev_ebit"] = F.compute_ev_ebit(ev, inp.op_ttm, ev_flags)
    metrics["fcf_yield"] = F.compute_fcf_yield(fcf, inp.market_cap, fcf_flags)
    metrics["roic"] = F.compute_roic(
        inp.op_ttm,
        tax_rate,
        ic_latest,
        ic_4q,
        inp.assets,
        inp.assets_4q,
        extra_flags=tax_flags,
        small_ic_ratio=float(cfg["formulas"]["small_ic_asset_ratio"]),
    )
    metrics["operating_margin"] = F.compute_operating_margin(inp.op_ttm, inp.revenue_ttm)
    metrics["roe"] = F.compute_roe(inp.nio_ttm, inp.equity_owners, inp.equity_owners_4q)
    metrics["cfo_net_income"] = F.compute_cfo_ni(inp.cfo_ttm, inp.ni_ttm)
    metrics["margin_stability_8q"] = F.compute_margin_stability(inp.quarterly_op_margins)
    metrics["revenue_yoy_ttm"] = F.compute_revenue_yoy(inp.revenue_ttm, inp.revenue_ttm_lag4)
    metrics["op_yoy_ttm"] = F.apply_profit_growth_state("op_yoy_ttm", inp.op_ttm_lag4, inp.op_ttm)
    metrics["revenue_cagr_3y"] = F.compute_revenue_cagr(inp.revenue_fy0, inp.revenue_fy3)

    shares = inp.diluted_shares_ttm or inp.shares_latest
    low_conf = inp.diluted_shares_ttm is None
    eps, eps_flags = F.compute_eps_proxy(inp.nio_ttm, shares, low_conf)
    shares_lag = inp.diluted_shares_ttm_lag4 or inp.shares_12m_ago or shares
    if inp.diluted_shares_ttm_lag4 is None and inp.shares_12m_ago is None and shares is not None:
        eps_flags = [*eps_flags, "EPS_SHARES_LAG_PROXY"]
    eps_lag, _ = F.compute_eps_proxy(inp.nio_ttm_lag4, shares_lag, low_conf)
    metrics["eps_yoy_ttm"] = F.apply_profit_growth_state("eps_yoy_ttm", eps_lag, eps, eps_flags)
    metrics["op_cagr_3y"] = F.compute_op_cagr(inp.op_fy0, inp.op_fy3)

    mom_enabled = bool(cfg["factors"]["momentum"].get("enabled", False))
    share_adj = bool(cfg.get("corporate_actions", {}).get("listed_shares_adjustment", False))
    official_adj = bool(cfg.get("corporate_actions", {}).get("adjusted_price_feed", False)) and inp.adj_close is not None
    adj_ok = official_adj or (share_adj and inp.adj_close is not None)
    if not mom_enabled or not adj_ok:
        for key in ("return_3m", "return_6m", "return_12m", "market_relative_6m", "high_52w_distance"):
            metrics[key] = _momentum_disabled(key)
    else:
        metrics["return_3m"] = F.compute_price_return(
            inp.adj_close, _implied_start_price(inp.adj_close, inp.return_3m), "return_3m"
        )
        metrics["return_6m"] = F.compute_price_return(
            inp.adj_close, _implied_start_price(inp.adj_close, inp.return_6m), "return_6m"
        )
        metrics["return_12m"] = F.compute_price_return(
            inp.adj_close, _implied_start_price(inp.adj_close, inp.return_12m), "return_12m"
        )
        metrics["market_relative_6m"] = F.compute_market_relative(inp.return_6m, inp.market_return_6m)
        metrics["high_52w_distance"] = F.compute_high52_distance(inp.adj_close, inp.high_52w)
        if share_adj:
            for key in ("return_3m", "return_6m", "return_12m", "market_relative_6m", "high_52w_distance"):
                metrics[key].flags.append("SHARE_ADJ_MOMENTUM")

    net_cash = (
        inp.interest_bearing_debt is not None
        and inp.cash is not None
        and (inp.interest_bearing_debt - inp.cash) < 0
    )
    has_debt = inp.interest_bearing_debt is not None and inp.interest_bearing_debt > 0
    metrics["net_debt_assets"] = F.compute_net_debt_assets(inp.interest_bearing_debt, inp.cash, inp.assets)
    metrics["debt_ratio"] = F.compute_debt_ratio(inp.liabilities, inp.equity)
    metrics["interest_coverage"] = F.compute_interest_coverage(
        inp.op_ttm, inp.interest_expense_ttm, net_cash=net_cash, has_debt=has_debt
    )
    metrics["cfo_assets"] = F.compute_cfo_assets(inp.cfo_ttm, inp.assets, inp.assets_4q)
    metrics["current_ratio"] = F.compute_current_ratio(inp.current_assets, inp.current_liabilities)

    if inp.extra_flags:
        for m in metrics.values():
            m.flags.extend(inp.extra_flags)
    return metrics


def make_scored(inp: FactorInputs, cfg: dict[str, Any]) -> ScoredName:
    metrics = build_metrics(inp, cfg)
    penalty, risk_flags, _detail = apply_soft_penalties(inp, cfg)
    data_flags: list[str] = []
    for m in metrics.values():
        data_flags.extend(m.flags)
    return ScoredName(
        inputs=inp,
        metrics=metrics,
        value_score=0.0,
        quality_score=0.0,
        growth_score=0.0,
        momentum_score=0.0,
        financial_score=0.0,
        quant_score_raw=0.0,
        risk_penalty=penalty,
        quant_score=0.0,
        coverage=0.0,
        data_confidence=0.0,
        confidence_components={},
        risk_flags=risk_flags,
        data_flags=list(dict.fromkeys(data_flags)),
        hard_reasons=[],
        universe_eligible=True,
        top100_eligible=False,
        top20_eligible=False,
        metric_peer_scores={},
        metric_values={},
        metric_peer_context={},
    )
