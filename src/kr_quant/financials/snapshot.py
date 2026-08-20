from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from kr_quant.calendar import shift_trading_days, trading_days_from_dates
from kr_quant.factors.metrics import history_component
from kr_quant.financials import formulas as F
from kr_quant.financials.quarters import (
    derive_discrete_quarters,
    lag_ttm,
    select_latest_valid_facts,
    ttm_from_discrete,
)
from kr_quant.models import FactorInputs
from kr_quant.pit.filings import assert_no_future_rows, history_window
from kr_quant.universe.builder import classify_security, liquidity_pass, map_industry


FLOW_ACCOUNTS = [
    "revenue",
    "operating_profit",
    "pretax_income",
    "net_income",
    "net_income_owners",
    "income_tax",
    "interest_expense",
    "cfo",
    "ppe_acquisition",
    "intangible_acquisition",
]
BS_ACCOUNTS = [
    "total_assets",
    "total_liabilities",
    "total_equity",
    "equity_owners",
    "nci",
    "cash",
    "short_term_financial_assets",
    "current_assets",
    "current_liabilities",
    "short_term_borrowings",
    "current_portion_ltd",
    "long_term_borrowings",
    "bonds",
    "lease_liabilities",
]


def _latest_bs(facts: pd.DataFrame, account: str) -> tuple[float | None, pd.Series | None]:
    sub = facts[facts["canonical_account"] == account]
    if sub.empty:
        return None, None
    sub = sub.sort_values(["period_end", "available_date"])
    row = sub.iloc[-1]
    return float(row["normalized_value"]), row


def _bs_asof(facts: pd.DataFrame, account: str, period_end_max: date | None) -> float | None:
    sub = facts[facts["canonical_account"] == account]
    if sub.empty:
        return None
    sub = sub.copy()
    sub["period_end"] = pd.to_datetime(sub["period_end"]).dt.date
    if period_end_max is not None:
        sub = sub[sub["period_end"] <= period_end_max]
    if sub.empty:
        return None
    return float(sub.sort_values(["period_end", "available_date"]).iloc[-1]["normalized_value"])


def _choose_fs_div(facts: pd.DataFrame) -> pd.DataFrame:
    if facts.empty or "fs_div" not in facts.columns:
        return facts
    if (facts["fs_div"] == "CFS").any():
        return facts[facts["fs_div"] == "CFS"]
    return facts[facts["fs_div"] == "OFS"]


def build_inputs_for_security(
    ticker: str,
    as_of: date,
    price_row: pd.Series,
    price_hist: pd.DataFrame,
    facts: pd.DataFrame,
    cfg: dict[str, Any],
    industry_info: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> tuple[FactorInputs, list[str]]:
    extra = extra or {}
    reasons: list[str] = []
    facts = select_latest_valid_facts(facts, as_of)
    assert_no_future_rows(facts, as_of)
    facts = _choose_fs_div(facts)
    pit_integrity = 1.0
    if facts.empty:
        reasons.append("CORE_DATA_INCOMPLETE")
        pit_integrity = 0.0

    ttm: dict[str, float | None] = {}
    ttm_lag: dict[str, float | None] = {}
    n_quarter = 0
    q_margins: list[float] = []
    q4_anom = False
    flow_ok = True
    fs_div = None
    latest_end: date | None = None
    available: date | None = None
    rcept = None

    for acc in FLOW_ACCOUNTS:
        qs, flags = derive_discrete_quarters(facts, acc)
        if "Q4_DERIVATION_ANOMALY" in flags:
            q4_anom = True
        if "INCOMPLETE_CUMULATIVE" in flags:
            flow_ok = False
        val, window, err = ttm_from_discrete(
            qs,
            min_days=int(cfg["point_in_time"]["ttm_duration_min_days"]),
            max_days=int(cfg["point_in_time"]["ttm_duration_max_days"]),
        )
        ttm[acc] = val
        lag_val, _ = lag_ttm(
            qs,
            4,
            min_days=int(cfg["point_in_time"]["ttm_duration_min_days"]),
            max_days=int(cfg["point_in_time"]["ttm_duration_max_days"]),
        )
        ttm_lag[acc] = lag_val
        if acc == "operating_profit":
            n_quarter = max(n_quarter, len(qs))
        if acc == "revenue":
            n_quarter = max(n_quarter, len(qs))
        if window:
            fs_div = window[-1].fs_div
            latest_end = window[-1].period_end
            available = window[-1].available_date
            rcept = window[-1].rcept_no

    # quarterly op margins for last 8 discrete quarters
    op_q, _ = derive_discrete_quarters(facts, "operating_profit")
    rev_q, _ = derive_discrete_quarters(facts, "revenue")
    rev_map = {(q.fiscal_year, q.quarter): q.amount for q in rev_q}
    for q in sorted(op_q, key=lambda x: (x.fiscal_year, x.quarter)):
        den = rev_map.get((q.fiscal_year, q.quarter))
        if den and den != 0:
            q_margins.append(q.amount / den)

    bs_latest: dict[str, float | None] = {}
    bs_meta = None
    for acc in BS_ACCOUNTS:
        val, row = _latest_bs(facts, acc)
        bs_latest[acc] = val
        if row is not None:
            bs_meta = row
    if bs_meta is not None:
        pend = pd.to_datetime(bs_meta["period_end"]).date()
        latest_end = latest_end or pend
        available = available or pd.to_datetime(bs_meta["available_date"]).date()
        rcept = rcept or str(bs_meta.get("rcept_no", ""))

    end_4q = None
    if latest_end is not None:
        # approximate 4q ago as 365 days before latest BS
        from datetime import timedelta

        end_4q = latest_end - timedelta(days=365)

    bs_4q = {acc: _bs_asof(facts, acc, end_4q) if end_4q else None for acc in BS_ACCOUNTS}

    # FY annuals for CAGR
    fy = facts[(facts["reprt_code"] == "11011")].copy()
    n_annual = 0
    rev_fy0 = rev_fy3 = op_fy0 = op_fy3 = None
    tax_pairs: list[tuple[float, float]] = []
    fcf_fy_hist: list[float | None] = []
    if not fy.empty:
        fy["bsns_year"] = fy["bsns_year"].astype(int)
        years = sorted(fy["bsns_year"].unique())
        n_annual = len(years)
        if years:
            y0 = years[-1]
            y3 = y0 - 3

            def fy_acc(year: int, acc: str) -> float | None:
                sub = fy[(fy["bsns_year"] == year) & (fy["canonical_account"] == acc)]
                if sub.empty:
                    return None
                return float(sub.sort_values("available_date").iloc[-1]["normalized_value"])

            rev_fy0 = fy_acc(y0, "revenue")
            rev_fy3 = fy_acc(y3, "revenue")
            op_fy0 = fy_acc(y0, "operating_profit")
            op_fy3 = fy_acc(y3, "operating_profit")
            for y in years[-3:]:
                pretax = fy_acc(y, "pretax_income")
                tax = fy_acc(y, "income_tax")
                if pretax is not None and tax is not None:
                    tax_pairs.append((pretax, tax))
                cfo = fy_acc(y, "cfo")
                ppe = fy_acc(y, "ppe_acquisition") or 0.0
                ina = fy_acc(y, "intangible_acquisition") or 0.0
                if cfo is None:
                    fcf_fy_hist.append(None)
                else:
                    fcf_fy_hist.append(cfo - (abs(ppe) + abs(ina)))

    capex = None
    ppe = ttm.get("ppe_acquisition")
    ina = ttm.get("intangible_acquisition")
    extra_flags: list[str] = []
    if ppe is None and ina is None:
        extra_flags.append("CAPEX_MISSING")
    elif ppe is None or ina is None:
        extra_flags.append("CAPEX_PARTIAL")
        capex = (abs(ppe) if ppe is not None else 0.0) + (abs(ina) if ina is not None else 0.0)
    else:
        capex = abs(ppe) + abs(ina)

    debt = F.interest_bearing_debt(
        bs_latest.get("short_term_borrowings"),
        bs_latest.get("current_portion_ltd"),
        bs_latest.get("long_term_borrowings"),
        bs_latest.get("bonds"),
        bs_latest.get("lease_liabilities"),
        include_lease=bool(cfg["formulas"]["include_lease_in_debt"]),
    )
    debt_4q = F.interest_bearing_debt(
        bs_4q.get("short_term_borrowings"),
        bs_4q.get("current_portion_ltd"),
        bs_4q.get("long_term_borrowings"),
        bs_4q.get("bonds"),
        bs_4q.get("lease_liabilities"),
        include_lease=bool(cfg["formulas"]["include_lease_in_debt"]),
    )

    if industry_info.get("peer_taxonomy_weak"):
        extra_flags.append("PEER_TAXONOMY_WEAK")

    recon = 1.0
    if fs_div == "OFS":
        recon = 0.6
    if not flow_ok:
        recon = min(recon, 0.6)
    if q4_anom:
        extra_flags.append("Q4_DERIVATION_ANOMALY")
        recon = min(recon, 0.6)
    if not F.bs_identity_ok(
        bs_latest.get("total_assets"),
        bs_latest.get("total_liabilities"),
        bs_latest.get("total_equity"),
        float(cfg["point_in_time"]["accounting_identity_tol"]),
    ):
        recon = 0.0

    # growth history from successive TTM windows
    rev_hist: list[float | None] = []
    op_hist: list[float | None] = []
    rev_q_all, _ = derive_discrete_quarters(facts, "revenue")
    op_q_all, _ = derive_discrete_quarters(facts, "operating_profit")
    ordered_ends = sorted({(q.fiscal_year, q.quarter) for q in rev_q_all})
    for i in range(max(0, len(ordered_ends) - 12), len(ordered_ends)):
        cut = ordered_ends[: i + 1]
        if len(cut) < 4:
            continue
        last4 = set(cut[-4:])
        prev4 = set(cut[-8:-4]) if len(cut) >= 8 else set()
        rev_now = sum(q.amount for q in rev_q_all if (q.fiscal_year, q.quarter) in last4)
        op_now = sum(q.amount for q in op_q_all if (q.fiscal_year, q.quarter) in last4)
        if prev4:
            rev_prev = sum(q.amount for q in rev_q_all if (q.fiscal_year, q.quarter) in prev4)
            op_prev = sum(q.amount for q in op_q_all if (q.fiscal_year, q.quarter) in prev4)
            rev_hist.append(None if rev_prev == 0 else rev_now / rev_prev - 1)
            op_hist.append(None if op_prev == 0 else op_now / op_prev - 1)

    def _num(v: Any) -> float | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return float(str(v).replace(",", "").replace(" ", ""))
        except ValueError:
            return None

    shares = _num(extra.get("shares_latest", price_row.get("listed_shares")))
    shares_12m = _num(extra.get("shares_12m_ago"))
    if shares_12m is None and price_hist is not None and not price_hist.empty:
        hist_t = price_hist[price_hist["ticker"] == ticker].copy()
        if not hist_t.empty:
            hist_t["trade_date"] = pd.to_datetime(hist_t["trade_date"]).dt.date
            old = hist_t.sort_values("trade_date")
            if len(old) > 0:
                shares_12m = _num(old.iloc[0].get("listed_shares"))

    inp = FactorInputs(
        ticker=ticker,
        security_id=str(price_row.get("security_id") or ticker),
        market=str(price_row.get("market")),
        sector=industry_info.get("sector"),
        industry=industry_info.get("industry"),
        sector_code=industry_info.get("sector_code"),
        industry_code=industry_info.get("industry_code"),
        market_cap=float(price_row["market_cap"]) if pd.notna(price_row.get("market_cap")) else None,
        preferred_market_cap=float(extra.get("preferred_market_cap") or 0.0),
        close=float(price_row["close"]) if pd.notna(price_row.get("close")) else None,
        adj_close=(
            float(price_row["adj_close"])
            if pd.notna(price_row.get("adj_close"))
            else extra.get("adj_close")
        ),
        revenue_ttm=ttm.get("revenue"),
        revenue_ttm_lag4=ttm_lag.get("revenue"),
        op_ttm=ttm.get("operating_profit"),
        op_ttm_lag4=ttm_lag.get("operating_profit"),
        pretax_ttm=ttm.get("pretax_income"),
        ni_ttm=ttm.get("net_income"),
        nio_ttm=ttm.get("net_income_owners"),
        nio_ttm_lag4=ttm_lag.get("net_income_owners"),
        cfo_ttm=ttm.get("cfo"),
        capex_ttm=capex,
        interest_expense_ttm=ttm.get("interest_expense"),
        income_tax_ttm=ttm.get("income_tax"),
        assets=bs_latest.get("total_assets"),
        assets_4q=bs_4q.get("total_assets"),
        liabilities=bs_latest.get("total_liabilities"),
        equity=bs_latest.get("total_equity"),
        equity_4q=bs_4q.get("total_equity"),
        equity_owners=bs_latest.get("equity_owners"),
        equity_owners_4q=bs_4q.get("equity_owners"),
        nci=bs_latest.get("nci") or 0.0,
        cash=bs_latest.get("cash"),
        sfa=bs_latest.get("short_term_financial_assets") or 0.0,
        cash_4q=bs_4q.get("cash"),
        sfa_4q=bs_4q.get("short_term_financial_assets") or 0.0,
        current_assets=bs_latest.get("current_assets"),
        current_liabilities=bs_latest.get("current_liabilities"),
        interest_bearing_debt=debt,
        interest_bearing_debt_4q=debt_4q,
        revenue_fy0=rev_fy0,
        revenue_fy3=rev_fy3,
        op_fy0=op_fy0,
        op_fy3=op_fy3,
        fcf_fy_hist=fcf_fy_hist,
        revenue_yoy_hist=rev_hist[-3:],
        op_yoy_hist=op_hist[-3:],
        quarterly_op_margins=q_margins[-8:],
        annual_tax_pairs=tax_pairs,
        shares_latest=None if shares is None or pd.isna(shares) else float(shares),
        shares_12m_ago=None if shares_12m is None else float(shares_12m),
        diluted_shares_ttm=extra.get("diluted_shares_ttm"),
        diluted_shares_ttm_lag4=extra.get("diluted_shares_ttm_lag4"),
        potential_dilution_pct=extra.get("potential_dilution_pct"),
        cb_bw_count_24m=int(extra.get("cb_bw_count_24m") or 0),
        fs_div=fs_div,
        latest_period_end=latest_end,
        available_date=available,
        rcept_no=rcept,
        pit_integrity=pit_integrity,
        history_score=history_component(n_annual, n_quarter),
        recon_score=recon,
        q4_anomaly=q4_anom,
        flow_subtraction_ok=flow_ok,
        n_annual=n_annual,
        n_quarter=n_quarter,
        listed_pref_unknown=bool(extra.get("listed_pref_unknown", False)),
        extra_flags=extra_flags,
        return_3m=extra.get("return_3m"),
        return_6m=extra.get("return_6m"),
        return_12m=extra.get("return_12m"),
        market_return_6m=extra.get("market_return_6m"),
        high_52w=extra.get("high_52w"),
    )

    class_reasons = classify_security(
        {
            "company": price_row.get("company"),
            "kind": price_row.get("kind"),
            "secu_group": price_row.get("secu_group"),
        },
        extra.get("universe_rules") or {},
        industry_info,
    )
    reasons.extend(class_reasons)

    # liquidity using PIT price history
    hist = price_hist[price_hist["ticker"] == ticker].copy()
    if not hist.empty:
        hist["trade_date"] = pd.to_datetime(hist["trade_date"]).dt.date
        days = trading_days_from_dates(hist["trade_date"].tolist())
        start = shift_trading_days(as_of, -int(cfg["universe"]["liquidity"]["lookback_trading_days"]) + 1, days)
        window = hist[hist["trade_date"] >= (start or date.min)] if start else hist
        window = window[window["trade_date"] <= as_of]
        values = [float(v) for v in window["trading_value"].dropna().tolist()]
        ok, liq_reasons = liquidity_pass(values, int(window["trade_date"].nunique()), cfg)
        if not ok:
            reasons.extend(liq_reasons)

    return inp, list(dict.fromkeys(reasons))
