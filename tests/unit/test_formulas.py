from __future__ import annotations

from kr_quant.financials import formulas as F
from kr_quant.scoring.composite import factor_specs, metric_weight_total


def test_weights_sum_to_100(settings):
    assert metric_weight_total(settings.config) == 100
    from kr_quant.scoring.composite import enabled_weight_total

    assert enabled_weight_total(settings.config) == 100
    by_factor = {}
    for factor, _name, spec in factor_specs(settings.config):
        by_factor[factor] = by_factor.get(factor, 0) + spec["weight"]
    assert by_factor["value"] == 30
    assert by_factor["quality"] == 25
    assert by_factor["growth"] == 25
    assert by_factor["momentum"] == 10
    assert by_factor["financial_stability"] == 10


def test_per_and_earnings_yield_loss():
    per = F.compute_per(1e12, -1e9)
    ey = F.compute_earnings_yield(1e12, -1e9)
    assert per.state == F.INVALID and per.score == 0
    assert ey.state == F.INVALID and ey.score == 0
    assert ey.raw == -0.001


def test_per_normal():
    per = F.compute_per(1e12, 1e11)
    assert per.state == F.NORMAL
    assert abs(per.raw - 10.0) < 1e-12


def test_negative_fcf_not_ranked():
    m = F.compute_fcf_yield(-1e9, 1e12, ["NEGATIVE_FCF"])
    assert m.score == 0
    assert m.counts_as_observed
    assert not m.participates_in_percentile


def test_negative_ev_with_positive_op():
    ev, flags = F.compute_ev(1e10, 0, 0, 0, 5e10, 0)
    assert ev < 0
    m = F.compute_ev_ebit(ev, 1e9, flags)
    assert m.raw == 0
    assert m.participates_in_percentile
    assert "NEGATIVE_EV_REVIEW" in m.flags


def test_roic_negative_ic_not_top():
    m = F.compute_roic(1e9, 0.25, -1e9, -1e9, 1e10, 1e10)
    assert m.state == F.MISSING
    assert "CAPITAL_LIGHT_NEGATIVE_IC" in m.flags
    assert m.score == 50


def test_roic_formula():
    # NOPAT = 100 * 0.75 = 75; avg IC = 500; ROIC = 0.15
    m = F.compute_roic(100.0, 0.25, 400.0, 600.0, 2000.0, 2000.0)
    assert m.state == F.NORMAL
    assert abs(m.raw - 0.15) < 1e-12


def test_fcf_definition():
    fcf, flags = F.compute_fcf(120.0, 20.0)
    assert fcf == 100.0
    assert flags == []


def test_growth_four_states():
    n = F.apply_profit_growth_state("op_yoy_ttm", 10.0, 12.0)
    assert n.state == F.NORMAL and abs(n.raw - 0.2) < 1e-12
    d = F.apply_profit_growth_state("op_yoy_ttm", 10.0, -1.0)
    assert d.state == F.DETERIORATION and d.score == 0
    t = F.apply_profit_growth_state("op_yoy_ttm", -1.0, 5.0)
    assert t.state == F.TURNAROUND and t.score == 50 and not t.participates_in_percentile
    p = F.apply_profit_growth_state("op_yoy_ttm", -1.0, -2.0)
    assert p.state == F.PERSISTENT_LOSS and p.score == 0


def test_op_cagr_uses_cagr_not_simple_ratio():
    m = F.compute_op_cagr(8.0, 1.0)
    assert m.state == F.NORMAL
    assert abs(m.raw - 1.0) < 1e-12  # 2x per year for 3 years is 8x, CAGR=1.0? (8/1)^(1/3)-1 = 1.0 yes


def test_tax_rate_median_then_fallback():
    rate, flags = F.select_tax_rate([(100, 20), (100, 22), (100, 24)], None, None)
    assert abs(rate - 0.22) < 1e-12
    assert flags == []
    rate2, flags2 = F.select_tax_rate([], 100.0, 20.0)
    assert abs(rate2 - 0.20) < 1e-12
    assert "TAX_RATE_FALLBACK" in flags2
    rate3, flags3 = F.select_tax_rate([], None, None)
    assert rate3 == 0.25
    assert "TAX_RATE_FALLBACK" in flags3


def test_interest_coverage_net_cash():
    m = F.compute_interest_coverage(10.0, 0.0, net_cash=True, has_debt=False)
    assert m.score == 100
    bad = F.compute_interest_coverage(10.0, 0.0, net_cash=False, has_debt=True)
    assert bad.state == F.MISSING
    assert "INTEREST_MAPPING_ERROR" in bad.flags
    loss = F.compute_interest_coverage(-5.0, 1.0, net_cash=False, has_debt=True)
    assert loss.score == 0


def test_current_ratio_zero_liabilities():
    m = F.compute_current_ratio(100.0, 0.0)
    assert m.score == 100
    assert "ZERO_CURRENT_LIABILITIES" in m.flags


def test_bs_identity():
    assert F.bs_identity_ok(100.0, 40.0, 60.0)
    assert not F.bs_identity_ok(100.0, 40.0, 50.0)


def test_interest_bearing_debt_no_double_count_none():
    d = F.interest_bearing_debt(10, 5, 20, 8, 2, include_lease=True)
    assert d == 45
