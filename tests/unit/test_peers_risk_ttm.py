from __future__ import annotations

from datetime import date

import pandas as pd

from kr_quant.financials.quarters import derive_discrete_quarters, ttm_from_discrete
from kr_quant.models import FactorInputs
from kr_quant.pit.filings import assert_no_future_rows
from kr_quant.risk.rules import apply_soft_penalties
from kr_quant.scoring.peers import average_ranks, percentile_high, winsor_bounds
from kr_quant.exceptions import PointInTimeLeak


def test_average_rank_ties():
    ranks = average_ranks([10.0, 20.0, 20.0, 30.0])
    assert ranks == [1.0, 2.5, 2.5, 4.0]
    ph = percentile_high(ranks)
    assert ph[0] == 0.0
    assert ph[-1] == 100.0
    assert abs(ph[1] - 50.0) < 1e-9


def test_winsor_bounds_medium_n():
    values = list(range(1, 31))
    cfg = {
        "winsor": {
            "large_n": {"min_n": 40, "lower": 0.025, "upper": 0.975},
            "medium_n": {"min_n": 20, "lower": 0.05, "upper": 0.95},
        }
    }
    lo, hi = winsor_bounds([float(v) for v in values], 30, cfg)
    assert lo < hi
    assert lo >= 1
    assert hi <= 30


def test_risk_penalty_cap_and_unique(settings):
    inp = FactorInputs(
        ticker="X",
        security_id="X",
        market="KOSPI",
        sector="제조업",
        industry="전자",
        sector_code="C",
        industry_code="C26",
        market_cap=1e12,
        preferred_market_cap=0.0,
        close=10000,
        adj_close=None,
        revenue_ttm=100,
        revenue_ttm_lag4=120,
        op_ttm=10,
        op_ttm_lag4=12,
        pretax_ttm=10,
        ni_ttm=8,
        nio_ttm=8,
        nio_ttm_lag4=9,
        cfo_ttm=-1,
        capex_ttm=5,
        interest_expense_ttm=20,
        income_tax_ttm=2,
        assets=100,
        assets_4q=100,
        liabilities=96,
        equity=4,
        equity_4q=4,
        equity_owners=4,
        equity_owners_4q=4,
        nci=0,
        cash=1,
        sfa=0,
        cash_4q=1,
        sfa_4q=0,
        current_assets=20,
        current_liabilities=30,
        interest_bearing_debt=50,
        interest_bearing_debt_4q=50,
        revenue_fy0=100,
        revenue_fy3=140,
        op_fy0=10,
        op_fy3=20,
        fcf_fy_hist=[-1, -2, 1],
        revenue_yoy_hist=[-0.1, -0.1, -0.1],
        op_yoy_hist=[-0.1, -0.1, -0.1],
        shares_latest=110,
        shares_12m_ago=100,
        potential_dilution_pct=0.2,
        cb_bw_count_24m=2,
    )
    penalty, flags, _ = apply_soft_penalties(inp, settings.config)
    assert penalty <= 15
    assert len(flags) == len(set(flags))
    assert penalty == 15


def test_ttm_from_cumulative_quarters():
    rows = []
    for year, code, val in [
        (2023, "11013", 100),
        (2023, "11012", 210),
        (2023, "11014", 330),
        (2023, "11011", 460),
        (2024, "11013", 120),
        (2024, "11012", 250),
        (2024, "11014", 390),
    ]:
        month = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}[code]
        day = 31 if month in (3, 12) else 30
        rows.append(
            {
                "security_id": "A",
                "canonical_account": "revenue",
                "fs_div": "CFS",
                "currency": "KRW",
                "bsns_year": year,
                "reprt_code": code,
                "period_start": date(year, 1, 1),
                "period_end": date(year, month, day),
                "normalized_value": val,
                "available_date": date(year, month, day),
                "rcept_no": f"{year}{code}",
            }
        )
    df = pd.DataFrame(rows)
    qs, flags = derive_discrete_quarters(df, "revenue")
    assert not flags
    discrete = {(q.fiscal_year, q.quarter): q.amount for q in qs}
    assert discrete[(2023, 1)] == 100
    assert discrete[(2023, 2)] == 110
    assert discrete[(2023, 3)] == 120
    assert discrete[(2023, 4)] == 130
    ttm, window, err = ttm_from_discrete(qs)
    assert err is None
    # last 4: 2023Q4 + 2024Q1-Q3 = 130+120+130+140 = 520
    assert ttm == 520


def test_pit_rejects_future_row():
    df = pd.DataFrame({"available_date": [date(2024, 12, 31)]})
    try:
        assert_no_future_rows(df, date(2024, 12, 30))
    except PointInTimeLeak:
        return
    raise AssertionError("expected PointInTimeLeak")
