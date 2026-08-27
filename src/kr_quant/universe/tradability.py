from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


KRX_EXCLUDED_RISK_TOKENS = (
    "관리종목",
    "투자주의환기",
    "정리매매",
    "상장폐지",
)

TRADING_EXCLUDED_STATUSES = frozenset(
    {
        "SUSPENDED",
        "ADMIN_ISSUE",
        "DELIST_PROCESS",
        "INVESTMENT_INELIGIBLE",
    }
)

CANDIDATE_HARD_EXCLUSIONS = frozenset(
    {
        "AUDIT_OPINION_FAIL",
        "CORE_DATA_INCOMPLETE",
        "DELISTING_RISK",
        "DISTRESS_STATUS",
        "FILING_LINEAGE_CONFLICT",
        "FINANCIAL_MODEL_NOT_AVAILABLE",
        "INFRA_FUND_MODEL_NOT_AVAILABLE",
        "LIQUIDITY_FAIL",
        "MANAGEMENT_STOCK",
        "MARKET_CAP_FAIL",
        "MARKET_EXCLUDED",
        "NEGATIVE_EQUITY",
        "NON_COMMON_SECURITY",
        "NOT_COMMON_STOCK",
        "PREFERRED_SHARE",
        "REIT_MODEL_NOT_AVAILABLE",
        "SPAC",
        "STALE_FINANCIALS",
        "TRADING_HALT",
        "TRADING_STATUS_EXCLUDED",
        "TRADING_STATUS_UNVERIFIED",
    }
)

# Event/theme membership is broader than the investable quant candidate set.
# Missing financial-model fields, liquidity thresholds, or market-cap cutoffs
# should lower confidence, not erase a genuinely related listed company. These
# exclusions are limited to conditions that make a security unsafe or invalid
# to present as a currently tradable event-universe member.
EVENT_UNIVERSE_HARD_EXCLUSIONS = frozenset(
    {
        "DELISTING_RISK",
        "DISTRESS_STATUS",
        "MANAGEMENT_STOCK",
        "MARKET_EXCLUDED",
        "NON_COMMON_SECURITY",
        "NOT_COMMON_STOCK",
        "PREFERRED_SHARE",
        "SPAC",
        "TRADING_HALT",
        "TRADING_STATUS_EXCLUDED",
        "TRADING_STATUS_UNVERIFIED",
    }
)


@dataclass(frozen=True)
class TradabilityGateResult:
    ready: bool
    allowed_tickers: frozenset[str]
    as_of_date: date | None = None
    errors: tuple[str, ...] = ()


def normalize_krx_risk_class(value: object) -> str:
    """Normalize KRX security-section text without inventing missing status."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", "", text)


def krx_risk_class_excluded(value: object) -> bool:
    """Return True only for explicit KRX risk classifications we must hard-block."""
    normalized = normalize_krx_risk_class(value)
    return any(token in normalized for token in KRX_EXCLUDED_RISK_TOKENS)


def trading_status_exclusion_reason(
    status: object,
    *,
    status_available: bool,
    required: bool,
) -> str | None:
    """Return an explicit hard reason; a required but missing feed must never pass."""
    if required and not status_available:
        return "TRADING_STATUS_UNVERIFIED"
    normalized = str(status or "").strip().upper()
    if status_available and normalized in TRADING_EXCLUDED_STATUSES:
        return "TRADING_STATUS_EXCLUDED"
    return None


def parse_exclusion_reasons(value: Any) -> set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value).strip()
    if not text:
        return set()
    text = text.strip("[]")
    return {item.strip(" '\"\t\r\n") for item in re.split(r"[|,;]", text) if item.strip(" '\"\t\r\n")}


def _explicit_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, int) and value == 1:
        return True
    return str(value).strip().lower() in {"true", "1", "yes"}


def evaluate_candidate_tradability(
    prices: pd.DataFrame,
    scored: pd.DataFrame,
    master: pd.DataFrame,
) -> TradabilityGateResult:
    """Build a fail-closed candidate set from current prices, score gates, and KRX master."""
    errors: list[str] = []
    price_required = {"ticker", "close", "volume"}
    date_col = "trade_date" if "trade_date" in prices.columns else "date" if "date" in prices.columns else None
    if prices.empty or date_col is None or not price_required.issubset(prices.columns):
        errors.append("PRICE_SOURCE_NOT_READY")
    if scored.empty or not {"ticker", "universe_eligible", "exclusion_reasons"}.issubset(scored.columns):
        errors.append("SCORED_UNIVERSE_NOT_READY")
    if master.empty or not {"ticker", "sect"}.issubset(master.columns):
        errors.append("KRX_RISK_MASTER_NOT_READY")
    if errors:
        return TradabilityGateResult(False, frozenset(), errors=tuple(errors))

    px = prices[["ticker", date_col, "close", "volume"]].copy()
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px[date_col] = pd.to_datetime(px[date_col], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px["volume"] = pd.to_numeric(px["volume"], errors="coerce")
    px = px.dropna(subset=[date_col]).sort_values(["ticker", date_col])
    if px.empty:
        return TradabilityGateResult(False, frozenset(), errors=("PRICE_SOURCE_NOT_READY",))

    market_as_of = px[date_col].max()
    last = px.groupby("ticker", as_index=False).tail(1)
    active = last[
        (last[date_col] == market_as_of)
        & (last["close"] >= 1000.0)
        & (last["volume"] > 0)
    ]
    active_tickers = set(active["ticker"])

    score = scored.copy()
    score["ticker"] = score["ticker"].astype(str).str.zfill(6)
    score = score.drop_duplicates("ticker", keep="last")
    score_ok = score["universe_eligible"].map(_explicit_true)
    score_ok &= ~score["exclusion_reasons"].map(
        lambda value: bool(parse_exclusion_reasons(value) & CANDIDATE_HARD_EXCLUSIONS)
    )
    scored_tickers = set(score.loc[score_ok, "ticker"])

    krx = master[["ticker", "sect"]].copy()
    krx["ticker"] = krx["ticker"].astype(str).str.zfill(6)
    krx = krx.drop_duplicates("ticker", keep="last")
    master_tickers = set(krx.loc[~krx["sect"].map(krx_risk_class_excluded), "ticker"])

    allowed = active_tickers & scored_tickers & master_tickers
    return TradabilityGateResult(
        True,
        frozenset(allowed),
        as_of_date=market_as_of.date(),
    )


def evaluate_event_universe_tradability(
    prices: pd.DataFrame,
    scored: pd.DataFrame,
    master: pd.DataFrame,
) -> TradabilityGateResult:
    """Build a fail-closed but research-broad event/theme universe.

    Unlike the final quant-candidate gate, this permits low-liquidity or
    incomplete-fundamental rows so the UI can show the full mapped event
    universe. It still requires a current positive-price/volume observation,
    a valid KRX common-security master row, and no explicit halt, management,
    distress, delisting, or other trading-status exclusion.
    """
    errors: list[str] = []
    price_required = {"ticker", "close", "volume"}
    date_col = "trade_date" if "trade_date" in prices.columns else "date" if "date" in prices.columns else None
    if prices.empty or date_col is None or not price_required.issubset(prices.columns):
        errors.append("PRICE_SOURCE_NOT_READY")
    if scored.empty or not {"ticker", "exclusion_reasons"}.issubset(scored.columns):
        errors.append("SCORED_UNIVERSE_NOT_READY")
    if master.empty or not {"ticker", "sect"}.issubset(master.columns):
        errors.append("KRX_RISK_MASTER_NOT_READY")
    if errors:
        return TradabilityGateResult(False, frozenset(), errors=tuple(errors))

    px = prices[["ticker", date_col, "close", "volume"]].copy()
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px[date_col] = pd.to_datetime(px[date_col], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px["volume"] = pd.to_numeric(px["volume"], errors="coerce")
    px = px.dropna(subset=[date_col]).sort_values(["ticker", date_col])
    if px.empty:
        return TradabilityGateResult(False, frozenset(), errors=("PRICE_SOURCE_NOT_READY",))

    market_as_of = px[date_col].max()
    last = px.groupby("ticker", as_index=False).tail(1)
    price_tickers = set(
        last.loc[
            (last[date_col] == market_as_of)
            & (last["close"] >= 1000.0)
            & (last["volume"] > 0),
            "ticker",
        ]
    )

    score = scored.copy()
    score["ticker"] = score["ticker"].astype(str).str.zfill(6)
    score = score.drop_duplicates("ticker", keep="last")
    score_ok = ~score["exclusion_reasons"].map(
        lambda value: bool(parse_exclusion_reasons(value) & EVENT_UNIVERSE_HARD_EXCLUSIONS)
    )
    scored_tickers = set(score.loc[score_ok, "ticker"])

    krx = master[["ticker", "sect"]].copy()
    krx["ticker"] = krx["ticker"].astype(str).str.zfill(6)
    krx = krx.drop_duplicates("ticker", keep="last")
    master_tickers = set(krx.loc[~krx["sect"].map(krx_risk_class_excluded), "ticker"])

    allowed = price_tickers & scored_tickers & master_tickers
    return TradabilityGateResult(
        True,
        frozenset(allowed),
        as_of_date=market_as_of.date(),
    )
