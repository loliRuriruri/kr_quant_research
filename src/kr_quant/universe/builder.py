from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from kr_quant.financials.formulas import bs_identity_ok
from kr_quant.models import FactorInputs, ScoredName
from kr_quant.universe.tradability import krx_risk_class_excluded


def load_ksic_map(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def map_industry(induty_code: str | None, ksic: pd.DataFrame) -> dict[str, str | None]:
    if not induty_code:
        return {
            "sector_code": None,
            "sector": None,
            "industry_code": None,
            "industry": None,
            "exclude_model": None,
            "peer_taxonomy_weak": True,
        }
    code = re.sub(r"\D", "", str(induty_code))
    prefix2 = code[:2] if len(code) >= 2 else code
    hit = ksic[ksic["ksic_prefix"] == prefix2]
    if hit.empty:
        return {
            "sector_code": None,
            "sector": None,
            "industry_code": None,
            "industry": None,
            "exclude_model": None,
            "peer_taxonomy_weak": True,
        }
    row = hit.iloc[0]
    excl = str(row.get("exclude_model", "")).strip()
    return {
        "sector_code": row["sector_code"] or None,
        "sector": row["sector"] or None,
        "industry_code": row["industry_code"] or None,
        "industry": row["industry"] or None,
        "exclude_model": excl or None,
        "peer_taxonomy_weak": False,
    }


def _match_any(text: str, pattern: str) -> bool:
    if not text or not pattern:
        return False
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def classify_security(
    row: dict[str, Any],
    universe_rules: dict[str, Any],
    industry_info: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    name = str(row.get("company") or row.get("isu_nm") or "")
    kind = str(row.get("kind") or row.get("KIND_STKCERT_TP_NM") or "")
    group = str(row.get("secu_group") or row.get("SECUGRP_NM") or "")
    krx_risk_class = row.get("sect") or row.get("SECT_TP_NM") or ""
    patterns = universe_rules.get("name_patterns", {})

    aliases = universe_rules.get("security_types", {})
    pref = aliases.get("preferred_aliases", [])
    if any(a and a in kind for a in pref) or "우선" in kind:
        reasons.append("PREFERRED_SHARE")
    common_ok = any(a and a in kind for a in aliases.get("common_stock_aliases", [])) or "보통" in kind
    if kind and not common_ok and "PREFERRED_SHARE" not in reasons:
        reasons.append("NOT_COMMON_STOCK")

    for token in universe_rules.get("security_types", {}).get("exclude_security_groups", []):
        if token and token in group:
            reasons.append("NON_COMMON_SECURITY")

    if _match_any(name, patterns.get("spac", "")):
        reasons.append("SPAC")
    if _match_any(name, patterns.get("reit", "")) or industry_info.get("exclude_model") == "REIT":
        reasons.append("REIT_MODEL_NOT_AVAILABLE")
    if _match_any(name, patterns.get("infra_fund", "")):
        reasons.append("INFRA_FUND_MODEL_NOT_AVAILABLE")
    if industry_info.get("exclude_model") == "FINANCIAL":
        reasons.append("FINANCIAL_MODEL_NOT_AVAILABLE")
    if krx_risk_class_excluded(krx_risk_class):
        reasons.append("TRADING_STATUS_EXCLUDED")
    return list(dict.fromkeys(reasons))


def liquidity_pass(
    trading_values: list[float],
    observation_days: int,
    cfg: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    liq = cfg["universe"]["liquidity"]
    if observation_days < int(liq["min_observations_in_63d"]):
        reasons.append("LIQUIDITY_FAIL")
    if not trading_values:
        reasons.append("LIQUIDITY_FAIL")
        return False, list(dict.fromkeys(reasons))
    s = pd.Series(trading_values)
    if float(s.median()) < float(liq["min_median_trading_value_krw"]):
        reasons.append("LIQUIDITY_FAIL")
    return len(reasons) == 0, reasons


def apply_universe_gates(
    name: ScoredName,
    cfg: dict[str, Any],
    as_of: date,
    status: str | None,
    status_available: bool,
) -> None:
    reasons = list(name.exclusion_reasons)
    inp = name.inputs
    uni = cfg["universe"]

    if inp.market not in uni["markets"]:
        reasons.append("MARKET_EXCLUDED")
    if inp.market_cap is None or inp.market_cap < float(uni["min_market_cap_krw"]):
        reasons.append("MARKET_CAP_FAIL")
    if inp.close is None or inp.close <= 0 or inp.market_cap is None or inp.market_cap <= 0:
        reasons.append("CORE_DATA_INCOMPLETE")

    if inp.equity is not None and inp.equity <= 0:
        reasons.append("NEGATIVE_EQUITY")
    if inp.equity_owners is not None and inp.equity_owners <= 0:
        reasons.append("NEGATIVE_EQUITY")

    stale_days = int(cfg["point_in_time"]["stale_financial_days"])
    if inp.latest_period_end is None:
        reasons.append("CORE_DATA_INCOMPLETE")
    elif (as_of - inp.latest_period_end).days > stale_days:
        reasons.append("STALE_FINANCIALS")

    core_ok = all(
        [
            inp.market_cap,
            inp.revenue_ttm is not None,
            inp.op_ttm is not None,
            inp.nio_ttm is not None,
            inp.assets is not None,
            inp.liabilities is not None,
            inp.equity is not None,
            inp.cfo_ttm is not None,
            inp.capex_ttm is not None,
            inp.close is not None,
        ]
    )
    if not core_ok:
        reasons.append("CORE_DATA_INCOMPLETE")

    if not bs_identity_ok(
        inp.assets,
        inp.liabilities,
        inp.equity,
        float(cfg["point_in_time"]["accounting_identity_tol"]),
    ):
        name.inputs.recon_score = 0.0
        reasons.append("RECONCILIATION_FAIL")

    if status_available and status in {
        "SUSPENDED",
        "ADMIN_ISSUE",
        "DELIST_PROCESS",
        "INVESTMENT_INELIGIBLE",
    }:
        reasons.append("TRADING_STATUS_EXCLUDED")

    hard = set(cfg.get("_hard_exclusions", []))
    # default hard set from spec
    hard.update(
        {
            "NEGATIVE_EQUITY",
            "AUDIT_OPINION_FAIL",
            "DISTRESS_STATUS",
            "TRADING_STATUS_EXCLUDED",
            "CORE_DATA_INCOMPLETE",
            "FINANCIAL_MODEL_NOT_AVAILABLE",
            "REIT_MODEL_NOT_AVAILABLE",
            "INFRA_FUND_MODEL_NOT_AVAILABLE",
            "SPAC",
            "FILING_LINEAGE_CONFLICT",
            "STALE_FINANCIALS",
            "PREFERRED_SHARE",
            "NOT_COMMON_STOCK",
            "NON_COMMON_SECURITY",
            "LIQUIDITY_FAIL",
            "MARKET_CAP_FAIL",
            "MARKET_EXCLUDED",
        }
    )
    name.exclusion_reasons = list(dict.fromkeys(reasons))
    name.hard_reasons = [r for r in name.exclusion_reasons if r in hard]
    name.universe_eligible = len(name.hard_reasons) == 0

    top100 = uni["top100"]
    top20 = uni["top20"]
    recon_ok = name.inputs.recon_score > 0
    name.top100_eligible = (
        name.universe_eligible
        and name.coverage >= float(top100["min_weighted_coverage"])
        and name.data_confidence >= float(top100["min_data_confidence"])
        and recon_ok
    )
    pos_ok = (
        (inp.op_ttm or 0) > 0
        and (inp.nio_ttm or 0) > 0
        and (inp.cfo_ttm or 0) > 0
    )
    name.top20_eligible = (
        name.top100_eligible
        and name.coverage >= float(top20["min_weighted_coverage"])
        and name.data_confidence >= float(top20["min_data_confidence"])
        and pos_ok
        and not name.hard_reasons
    )
