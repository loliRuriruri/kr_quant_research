from __future__ import annotations

from statistics import median
from typing import Iterable, Sequence

from kr_quant.models import MetricResult

MISSING = "DATA_MISSING"
INVALID = "ECONOMICALLY_INVALID"
NORMAL = "NORMAL"
INSUFFICIENT = "INSUFFICIENT_HISTORY"
TURNAROUND = "TURNAROUND"
DETERIORATION = "DETERIORATION_TO_LOSS"
PERSISTENT_LOSS = "PERSISTENT_LOSS"
ZERO_DENOM = "ZERO_DENOMINATOR"


def _ok(x: float | None) -> bool:
    return x is not None and x == x


def missing(name: str, extra_flags: Sequence[str] | None = None) -> MetricResult:
    return MetricResult(
        name=name,
        raw=None,
        state=MISSING,
        flags=list(extra_flags or []),
        participates_in_percentile=False,
        counts_as_observed=False,
        score=50.0,
    )


def invalid(name: str, raw: float | None, flags: Sequence[str] | None = None) -> MetricResult:
    return MetricResult(
        name=name,
        raw=raw,
        state=INVALID,
        flags=list(flags or []),
        participates_in_percentile=False,
        counts_as_observed=True,
        score=0.0,
    )


def normal(name: str, raw: float, flags: Sequence[str] | None = None) -> MetricResult:
    return MetricResult(
        name=name,
        raw=raw,
        state=NORMAL,
        flags=list(flags or []),
        participates_in_percentile=True,
        counts_as_observed=True,
    )


def safe_div(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return num / den


def mean_pair(a: float | None, b: float | None) -> float | None:
    vals = [x for x in (a, b) if _ok(x)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_per(market_cap: float | None, nio_ttm: float | None) -> MetricResult:
    if not _ok(market_cap) or not _ok(nio_ttm):
        return missing("per")
    if nio_ttm <= 0 or market_cap <= 0:
        return MetricResult(
            name="per",
            raw=None,
            state=INVALID,
            flags=["LOSS_MAKING"],
            participates_in_percentile=False,
            counts_as_observed=True,
            score=0.0,
        )
    return normal("per", market_cap / nio_ttm)


def compute_earnings_yield(market_cap: float | None, nio_ttm: float | None) -> MetricResult:
    if not _ok(market_cap) or not _ok(nio_ttm) or market_cap <= 0:
        return missing("earnings_yield")
    raw = nio_ttm / market_cap
    if nio_ttm <= 0:
        return invalid("earnings_yield", raw, ["LOSS_MAKING"])
    return normal("earnings_yield", raw)


def compute_pbr(market_cap: float | None, equity_owners: float | None) -> MetricResult:
    if not _ok(market_cap) or not _ok(equity_owners):
        return missing("pbr")
    if equity_owners <= 0:
        return invalid("pbr", None, ["NEGATIVE_EQUITY"])
    if market_cap <= 0:
        return missing("pbr")
    return normal("pbr", market_cap / equity_owners)


def compute_ev(
    market_cap: float | None,
    preferred_mv: float,
    debt: float | None,
    nci: float | None,
    cash: float | None,
    sfa: float | None,
) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    if not _ok(market_cap):
        return None, flags
    d = 0.0 if not _ok(debt) else float(debt)
    n = 0.0 if not _ok(nci) else float(nci)
    c = 0.0 if not _ok(cash) else float(cash)
    s = 0.0 if not _ok(sfa) else float(sfa)
    if not _ok(debt):
        flags.append("DEBT_ASSUMED_ZERO")
    if not _ok(sfa):
        flags.append("SFA_ASSUMED_ZERO")
    ev = float(market_cap) + float(preferred_mv or 0.0) + d + n - c - s
    if ev <= 0:
        flags.append("NEGATIVE_EV_REVIEW")
    return ev, flags


def compute_ev_ebit(ev: float | None, op_ttm: float | None, ev_flags: Sequence[str]) -> MetricResult:
    if ev is None or not _ok(op_ttm):
        return missing("ev_ebit", ev_flags)
    if op_ttm <= 0:
        return invalid("ev_ebit", None, [*ev_flags, "LOSS_MAKING"])
    if ev <= 0:
        return MetricResult(
            name="ev_ebit",
            raw=0.0,
            state=NORMAL,
            flags=[*ev_flags, "NEGATIVE_EV_REVIEW"],
            participates_in_percentile=True,
            counts_as_observed=True,
        )
    return normal("ev_ebit", ev / op_ttm, ev_flags)


def compute_fcf(cfo_ttm: float | None, capex_ttm: float | None) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    if not _ok(cfo_ttm) or not _ok(capex_ttm):
        return None, flags
    fcf = float(cfo_ttm) - float(capex_ttm)
    if fcf <= 0:
        flags.append("NEGATIVE_FCF")
    return fcf, flags


def compute_fcf_yield(fcf_ttm: float | None, market_cap: float | None, flags: Sequence[str]) -> MetricResult:
    if not _ok(fcf_ttm) or not _ok(market_cap) or market_cap <= 0:
        return missing("fcf_yield", flags)
    raw = fcf_ttm / market_cap
    if fcf_ttm <= 0:
        return invalid("fcf_yield", raw, [*flags, "NEGATIVE_FCF"])
    return normal("fcf_yield", raw, flags)


def compute_roe(nio_ttm: float | None, equity_latest: float | None, equity_4q: float | None) -> MetricResult:
    if not _ok(nio_ttm):
        return missing("roe")
    avg_eq = mean_pair(equity_latest, equity_4q)
    if not _ok(avg_eq) or avg_eq == 0:
        return missing("roe", [ZERO_DENOM])
    flags = []
    if _ok(equity_latest) and _ok(equity_latest) and equity_latest is not None:
        pass
    raw = nio_ttm / avg_eq
    return normal("roe", raw, flags)


def compute_operating_margin(op_ttm: float | None, revenue_ttm: float | None) -> MetricResult:
    if not _ok(op_ttm) or not _ok(revenue_ttm) or revenue_ttm == 0:
        return missing("operating_margin")
    return normal("operating_margin", op_ttm / revenue_ttm)


def compute_cfo_ni(cfo_ttm: float | None, ni_ttm: float | None) -> MetricResult:
    if not _ok(cfo_ttm) or not _ok(ni_ttm):
        return missing("cfo_net_income")
    if ni_ttm <= 0:
        return invalid("cfo_net_income", None, ["LOSS_MAKING"])
    return normal("cfo_net_income", cfo_ttm / ni_ttm)


def sample_stddev(values: Sequence[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return var ** 0.5


def compute_margin_stability(quarterly_op_margins: Sequence[float]) -> MetricResult:
    if len(quarterly_op_margins) < 6:
        return missing("margin_stability_8q", [INSUFFICIENT])
    window = list(quarterly_op_margins)[-8:]
    sd = sample_stddev(window)
    if sd is None:
        return missing("margin_stability_8q")
    return normal("margin_stability_8q", sd)


def select_tax_rate(
    annual_pairs: Sequence[tuple[float, float]],
    pretax_ttm: float | None,
    tax_ttm: float | None,
    default_rate: float = 0.25,
    max_rate: float = 0.35,
) -> tuple[float, list[str]]:
    flags: list[str] = []
    valid: list[float] = []
    for pretax, tax in annual_pairs[-3:]:
        if pretax > 0:
            rate = tax / pretax
            if 0.0 <= rate <= max_rate:
                valid.append(rate)
    if valid:
        return float(median(valid)), flags
    if _ok(pretax_ttm) and pretax_ttm > 0 and _ok(tax_ttm):
        rate = tax_ttm / pretax_ttm
        if 0.0 <= rate <= max_rate:
            flags.append("TAX_RATE_FALLBACK")
            return float(rate), flags
    flags.append("TAX_RATE_FALLBACK")
    return float(default_rate), flags


def invested_capital(equity: float | None, debt: float | None, cash: float | None, sfa: float | None) -> float | None:
    if not _ok(equity):
        return None
    d = 0.0 if not _ok(debt) else float(debt)
    c = 0.0 if not _ok(cash) else float(cash)
    s = 0.0 if not _ok(sfa) else float(sfa)
    return float(equity) + d - c - s


def compute_roic(
    op_ttm: float | None,
    tax_rate: float,
    ic_latest: float | None,
    ic_4q: float | None,
    assets_latest: float | None,
    assets_4q: float | None,
    extra_flags: Sequence[str] | None = None,
    small_ic_ratio: float = 0.05,
) -> MetricResult:
    flags = list(extra_flags or [])
    flags.append("ROIC_CASH_CLASSIFICATION_SIMPLE")
    if not _ok(op_ttm):
        return missing("roic", flags)
    nopat = op_ttm * (1.0 - tax_rate)
    avg_ic = mean_pair(ic_latest, ic_4q)
    if not _ok(avg_ic) or avg_ic <= 0:
        return MetricResult(
            name="roic",
            raw=None,
            state=MISSING,
            flags=[*flags, "CAPITAL_LIGHT_NEGATIVE_IC"],
            participates_in_percentile=False,
            counts_as_observed=False,
            score=50.0,
        )
    avg_assets = mean_pair(assets_latest, assets_4q)
    if _ok(avg_assets) and avg_assets > 0 and avg_ic < small_ic_ratio * avg_assets:
        flags.append("SMALL_DENOMINATOR_ROIC")
    raw = nopat / avg_ic
    return normal("roic", raw, flags)


def yoy(current: float | None, lagged: float | None) -> float | None:
    if not _ok(current) or not _ok(lagged) or lagged == 0:
        return None
    return current / lagged - 1.0


def cagr(latest: float | None, old: float | None, years: int = 3) -> float | None:
    if not _ok(latest) or not _ok(old) or old <= 0 or latest <= 0 or years <= 0:
        return None
    return (latest / old) ** (1.0 / years) - 1.0


def apply_profit_growth_state(name: str, prev: float | None, curr: float | None, extra: Sequence[str] | None = None) -> MetricResult:
    flags = list(extra or [])
    if not _ok(prev) or not _ok(curr):
        return missing(name, flags)
    if prev > 0 and curr > 0:
        raw = curr / prev - 1.0
        return normal(name, raw, flags)
    if prev > 0 and curr <= 0:
        return MetricResult(
            name=name,
            raw=None if prev == 0 else (curr / prev - 1.0 if prev else None),
            state=DETERIORATION,
            flags=flags,
            participates_in_percentile=False,
            counts_as_observed=True,
            score=0.0,
        )
    if prev <= 0 and curr > 0:
        return MetricResult(
            name=name,
            raw=None,
            state=TURNAROUND,
            flags=flags,
            participates_in_percentile=False,
            counts_as_observed=True,
            score=50.0,
        )
    return MetricResult(
        name=name,
        raw=None,
        state=PERSISTENT_LOSS,
        flags=flags,
        participates_in_percentile=False,
        counts_as_observed=True,
        score=0.0,
    )


def compute_revenue_yoy(curr: float | None, lag: float | None) -> MetricResult:
    if not _ok(curr) or not _ok(lag) or curr <= 0 or lag <= 0:
        return missing("revenue_yoy_ttm")
    return normal("revenue_yoy_ttm", curr / lag - 1.0)


def compute_revenue_cagr(fy0: float | None, fy3: float | None) -> MetricResult:
    raw = cagr(fy0, fy3, 3)
    if raw is None:
        return missing("revenue_cagr_3y")
    return normal("revenue_cagr_3y", raw)


def compute_op_cagr(fy0: float | None, fy3: float | None) -> MetricResult:
    state = apply_profit_growth_state("op_cagr_3y", fy3, fy0)
    if state.state == NORMAL:
        raw = cagr(fy0, fy3, 3)
        if raw is None:
            return missing("op_cagr_3y")
        return normal("op_cagr_3y", raw, state.flags)
    return state


def compute_eps_proxy(nio: float | None, shares: float | None, low_conf: bool) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    if low_conf:
        flags.append("EPS_PROXY_LOW_CONFIDENCE")
    if not _ok(nio) or not _ok(shares) or shares <= 0:
        return None, flags
    return nio / shares, flags


def compute_net_debt_assets(debt: float | None, cash: float | None, assets: float | None) -> MetricResult:
    if not _ok(debt) or not _ok(assets) or assets == 0:
        return missing("net_debt_assets")
    c = 0.0 if not _ok(cash) else float(cash)
    return normal("net_debt_assets", (float(debt) - c) / assets)


def compute_debt_ratio(liab: float | None, equity: float | None) -> MetricResult:
    if not _ok(liab) or not _ok(equity):
        return missing("debt_ratio")
    if equity == 0:
        return missing("debt_ratio", [ZERO_DENOM])
    return normal("debt_ratio", liab / equity)


def compute_interest_coverage(
    op_ttm: float | None,
    interest_ttm: float | None,
    net_cash: bool,
    has_debt: bool,
) -> MetricResult:
    if not _ok(op_ttm):
        return missing("interest_coverage")
    if not _ok(interest_ttm) or interest_ttm <= 0:
        if net_cash:
            return MetricResult(
                name="interest_coverage",
                raw=None,
                state=NORMAL,
                flags=["ZERO_INTEREST_NET_CASH"],
                participates_in_percentile=False,
                counts_as_observed=True,
                score=100.0,
            )
        if has_debt:
            return missing("interest_coverage", ["INTEREST_MAPPING_ERROR"])
        return missing("interest_coverage")
    if op_ttm <= 0:
        return invalid("interest_coverage", op_ttm / interest_ttm, ["LOSS_MAKING"])
    return normal("interest_coverage", op_ttm / interest_ttm)


def compute_cfo_assets(cfo_ttm: float | None, assets: float | None, assets_4q: float | None) -> MetricResult:
    if not _ok(cfo_ttm):
        return missing("cfo_assets")
    avg_a = mean_pair(assets, assets_4q)
    if not _ok(avg_a) or avg_a == 0:
        return missing("cfo_assets", [ZERO_DENOM])
    return normal("cfo_assets", cfo_ttm / avg_a)


def compute_current_ratio(ca: float | None, cl: float | None) -> MetricResult:
    if not _ok(ca) or not _ok(cl):
        return missing("current_ratio")
    if cl == 0:
        return MetricResult(
            name="current_ratio",
            raw=None,
            state=NORMAL,
            flags=["ZERO_CURRENT_LIABILITIES"],
            participates_in_percentile=False,
            counts_as_observed=True,
            score=100.0,
        )
    return normal("current_ratio", ca / cl)


def compute_price_return(end_px: float | None, start_px: float | None, name: str) -> MetricResult:
    if not _ok(end_px) or not _ok(start_px) or start_px <= 0:
        return MetricResult(
            name=name,
            raw=None,
            state=INSUFFICIENT,
            flags=[INSUFFICIENT],
            participates_in_percentile=False,
            counts_as_observed=False,
            score=50.0,
        )
    return normal(name, end_px / start_px - 1.0)


def compute_market_relative(stock_ret: float | None, mkt_ret: float | None) -> MetricResult:
    if not _ok(stock_ret) or not _ok(mkt_ret):
        return MetricResult(
            name="market_relative_6m",
            raw=None,
            state=INSUFFICIENT,
            flags=[INSUFFICIENT],
            participates_in_percentile=False,
            counts_as_observed=False,
            score=50.0,
        )
    return normal("market_relative_6m", stock_ret - mkt_ret)


def compute_high52_distance(px: float | None, high: float | None) -> MetricResult:
    if not _ok(px) or not _ok(high) or high <= 0:
        return MetricResult(
            name="high_52w_distance",
            raw=None,
            state=INSUFFICIENT,
            flags=[INSUFFICIENT],
            participates_in_percentile=False,
            counts_as_observed=False,
            score=50.0,
        )
    return normal("high_52w_distance", px / high - 1.0)


def bs_identity_ok(assets: float | None, liab: float | None, equity: float | None, tol: float = 0.005) -> bool:
    if not _ok(assets) or not _ok(liab) or not _ok(equity):
        return False
    return abs(assets - liab - equity) / max(assets, 1.0) <= tol


def interest_bearing_debt(
    short_term: float | None,
    current_portion: float | None,
    long_term: float | None,
    bonds: float | None,
    leases: float | None,
    include_lease: bool = True,
) -> float | None:
    parts = [short_term, current_portion, long_term, bonds]
    if include_lease:
        parts.append(leases)
    present = [p for p in parts if _ok(p)]
    if not present:
        return None
    return float(sum(present))
