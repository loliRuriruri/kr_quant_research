from __future__ import annotations

from typing import Any

from kr_quant.models import FactorInputs


def _neg_streak(values: list[float | None], n: int = 3) -> bool:
    if len(values) < n:
        return False
    window = values[-n:]
    return all(v is not None and v < 0 for v in window)


def apply_soft_penalties(inp: FactorInputs, cfg: dict[str, Any]) -> tuple[float, list[str], dict[str, Any]]:
    rules = cfg["risk"]["rules"]
    cap = float(cfg["risk"]["soft_penalty_cap"])
    flags: list[str] = []
    detail: dict[str, Any] = {}

    if _neg_streak(inp.revenue_yoy_hist, 3):
        flags.append("REV_DECLINE_STREAK")
        detail["REV_DECLINE_STREAK"] = inp.revenue_yoy_hist[-3:]

    op_hist = inp.op_yoy_hist
    if len(op_hist) >= 3 and _neg_streak(op_hist, 3):
        # only if currently profitable (OP>0)
        if inp.op_ttm is not None and inp.op_ttm > 0:
            flags.append("OP_DECLINE_STREAK")
            detail["OP_DECLINE_STREAK"] = op_hist[-3:]

    fcf_hist = [v for v in inp.fcf_fy_hist[-3:]]
    neg_fy = sum(1 for v in fcf_hist if v is not None and v < 0)
    fcf_now = None
    if inp.cfo_ttm is not None and inp.capex_ttm is not None:
        fcf_now = inp.cfo_ttm - inp.capex_ttm
    if neg_fy >= 2 and fcf_now is not None and fcf_now < 0:
        flags.append("FCF_DETERIORATION")
        detail["FCF_DETERIORATION"] = {"fy": fcf_hist, "ttm": fcf_now}

    assets = inp.assets
    debt = inp.interest_bearing_debt
    cash = inp.cash or 0.0
    if assets and assets > 0 and debt is not None:
        nda = (debt - cash) / assets
        icov = None
        if inp.interest_expense_ttm and inp.interest_expense_ttm > 0 and inp.op_ttm is not None:
            icov = inp.op_ttm / inp.interest_expense_ttm
        lev = rules["leverage_stress"]
        if nda > float(lev["net_debt_assets_gt"]) and icov is not None and icov < float(lev["coverage_lt"]):
            flags.append("LEVERAGE_STRESS")
            detail["LEVERAGE_STRESS"] = {"net_debt_assets": nda, "interest_coverage": icov}

    if assets and assets > 0 and inp.equity is not None:
        eq_ratio = inp.equity / assets
        if eq_ratio < float(rules["thin_equity"]["equity_assets_lt"]):
            flags.append("THIN_EQUITY")
            detail["THIN_EQUITY"] = eq_ratio

    if inp.shares_latest and inp.shares_12m_ago and inp.shares_12m_ago > 0:
        dil = inp.shares_latest / inp.shares_12m_ago - 1.0
        if dil >= float(rules["dilution_12m_high"]["pct_gte"]):
            flags.append("DILUTION_12M_HIGH")
            detail["DILUTION_12M"] = dil
        elif dil >= float(rules["dilution_12m_medium"]["pct_gte"]):
            flags.append("DILUTION_12M_MEDIUM")
            detail["DILUTION_12M"] = dil

    if inp.potential_dilution_pct is not None and inp.potential_dilution_pct >= float(
        rules["cb_bw_overhang"]["potential_dilution_gte"]
    ):
        flags.append("CB_BW_OVERHANG")
        detail["CB_BW_OVERHANG"] = inp.potential_dilution_pct

    if inp.cb_bw_count_24m >= int(rules["repeated_cb_bw"]["count_24m_gte"]):
        flags.append("REPEATED_CB_BW")
        detail["REPEATED_CB_BW"] = inp.cb_bw_count_24m

    if inp.nio_ttm is not None and inp.op_ttm is not None and inp.nio_ttm > 0 and inp.op_ttm <= 0:
        flags.append("ONE_OFF_EARNINGS_RISK")
        detail["ONE_OFF_EARNINGS_RISK"] = "nio_pos_op_neg"
    elif inp.pretax_ttm is not None and inp.op_ttm is not None and abs(inp.pretax_ttm) > 0:
        gap = (inp.pretax_ttm - inp.op_ttm) / abs(inp.pretax_ttm)
        if gap > 0.5:
            flags.append("ONE_OFF_EARNINGS_RISK")
            detail["ONE_OFF_EARNINGS_RISK"] = gap

    penalty_map = {
        "REV_DECLINE_STREAK": float(rules["rev_decline_streak"]["penalty"]),
        "OP_DECLINE_STREAK": float(rules["op_decline_streak"]["penalty"]),
        "FCF_DETERIORATION": float(rules["fcf_deterioration"]["penalty"]),
        "LEVERAGE_STRESS": float(rules["leverage_stress"]["penalty"]),
        "THIN_EQUITY": float(rules["thin_equity"]["penalty"]),
        "DILUTION_12M_MEDIUM": float(rules["dilution_12m_medium"]["penalty"]),
        "DILUTION_12M_HIGH": float(rules["dilution_12m_high"]["penalty"]),
        "CB_BW_OVERHANG": float(rules["cb_bw_overhang"]["penalty"]),
        "REPEATED_CB_BW": float(rules["repeated_cb_bw"]["penalty"]),
        "ONE_OFF_EARNINGS_RISK": float(rules["one_off_earnings_risk"]["penalty"]),
    }
    unique = list(dict.fromkeys(flags))
    penalty = min(cap, sum(penalty_map[f] for f in unique))
    return penalty, unique, detail


def is_hard_excluded(reasons: list[str], hard_set: set[str]) -> bool:
    return any(r in hard_set for r in reasons)
