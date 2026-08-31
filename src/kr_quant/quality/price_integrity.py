from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


ISSUE_COLUMNS = [
    "ticker",
    "trade_date",
    "previous_trade_date",
    "issue_code",
    "severity",
    "action",
    "raw_return",
    "market_cap_return",
    "listed_shares_change",
    "details",
]


def _settings(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(config or {})
    if isinstance(cfg.get("corporate_actions"), dict):
        cfg = dict(cfg["corporate_actions"])
    if isinstance(cfg.get("price_integrity"), dict):
        cfg = dict(cfg["price_integrity"])
    return {
        "raw_return_break_threshold": float(cfg.get("raw_return_break_threshold", 0.35)),
        "market_cap_break_threshold": float(cfg.get("market_cap_break_threshold", 0.35)),
        "listed_shares_change_threshold": float(cfg.get("listed_shares_change_threshold", 0.02)),
        "validate_ohlc": bool(cfg.get("validate_ohlc", True)),
    }


def latest_clean_price_segments(
    prices: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return only each ticker's most recent uninterrupted price segment.

    The gate never labels a row as a confirmed corporate action. It uses KRX
    OHLC, listed-shares and market-cap fields as observable proxies and starts
    a new segment when raw returns cannot safely be joined.
    """
    settings = _settings(config)
    if prices is None or prices.empty:
        empty = pd.DataFrame(columns=ISSUE_COLUMNS)
        return pd.DataFrame() if prices is None else prices.copy(), empty, _summary(0, 0, empty, 0, settings)

    date_column = "trade_date" if "trade_date" in prices.columns else "date"
    if date_column not in prices.columns:
        raise ValueError("price integrity requires trade_date or date")

    work = prices.copy()
    temporary_ticker = "ticker" not in work.columns
    if temporary_ticker:
        work["ticker"] = "_SINGLE_"
    work["ticker"] = work["ticker"].fillna("_MISSING_TICKER_").astype(str)
    work[date_column] = pd.to_datetime(work[date_column], errors="coerce")
    work = work.dropna(subset=[date_column]).sort_values(["ticker", date_column]).reset_index(drop=True)
    input_rows = len(work)
    ticker_count = int(work["ticker"].nunique(dropna=False))

    def numeric(column: str) -> pd.Series:
        if column not in work.columns:
            return pd.Series(float("nan"), index=work.index, dtype="float64")
        return pd.to_numeric(work[column], errors="coerce")

    # A zero-volume row is not an executable OHLC bar. Remove it from factor
    # and strategy timelines, but record it as an observed warning rather than
    # pretending that it is a critical corporate-action break.
    initial_close = numeric("close")
    initial_volume = numeric("volume")
    no_trade = (
        initial_volume.notna()
        & (initial_volume <= 0)
        & initial_close.notna()
        & (initial_close > 0)
    )
    no_trade_issues = pd.DataFrame(columns=ISSUE_COLUMNS)
    if no_trade.any():
        idx = no_trade[no_trade].index
        no_trade_issues = pd.DataFrame(
            {
                "ticker": work.loc[idx, "ticker"].values,
                "trade_date": work.loc[idx, date_column].dt.strftime("%Y-%m-%d").values,
                "previous_trade_date": None,
                "issue_code": "NO_TRADE_BAR_DROPPED",
                "severity": "WARNING",
                "action": "DROP_NON_TRADING_BAR",
                "raw_return": None,
                "market_cap_return": None,
                "listed_shares_change": None,
                "details": "거래량 0인 비체결 행을 수익률·백테스트 관측치에서 제외합니다.",
            }
        )[ISSUE_COLUMNS]
        work = work.loc[~no_trade].reset_index(drop=True)

    keys = work["ticker"]
    close = numeric("close")
    open_price = numeric("open")
    high = numeric("high")
    low = numeric("low")
    volume = numeric("volume")
    shares = numeric("listed_shares")
    market_cap = numeric("market_cap")
    fallback_level = (close * shares).where((close > 0) & (shares > 0))
    level = market_cap.where(market_cap > 0, fallback_level)

    invalid_code = pd.Series(pd.NA, index=work.index, dtype="object")
    invalid_code.loc[close.isna() | (close <= 0)] = "INVALID_CLOSE"
    has_ohlc = all(column in work.columns for column in ("open", "high", "low"))
    if settings["validate_ohlc"] and has_ohlc:
        non_positive = (
            open_price.isna()
            | high.isna()
            | low.isna()
            | (open_price <= 0)
            | (high <= 0)
            | (low <= 0)
        )
        invalid_code.loc[invalid_code.isna() & non_positive] = "INVALID_OHLC_NON_POSITIVE"
        invalid_range = (high < pd.concat([open_price, close], axis=1).max(axis=1)) | (
            low > pd.concat([open_price, close], axis=1).min(axis=1)
        ) | (low > high)
        invalid_code.loc[invalid_code.isna() & invalid_range] = "INVALID_OHLC_RANGE"
    if "volume" in work.columns:
        invalid_code.loc[invalid_code.isna() & volume.notna() & (volume < 0)] = "NEGATIVE_VOLUME"
    invalid = invalid_code.notna()

    first = work.groupby("ticker", sort=False, dropna=False).cumcount().eq(0)
    previous_invalid = invalid.groupby(keys, sort=False, dropna=False).shift().fillna(False).astype(bool)
    previous_date = work[date_column].groupby(keys, sort=False, dropna=False).shift()
    previous_close = close.groupby(keys, sort=False, dropna=False).shift()
    previous_shares = shares.groupby(keys, sort=False, dropna=False).shift()
    previous_level = level.groupby(keys, sort=False, dropna=False).shift()
    valid_pair = ~first & ~invalid & ~previous_invalid

    raw_return = (close / previous_close - 1).where(valid_pair & (previous_close > 0))
    shares_change = (shares / previous_shares - 1).where(
        valid_pair & (shares > 0) & (previous_shares > 0)
    )
    market_cap_return = (level / previous_level - 1).where(
        valid_pair & (level > 0) & (previous_level > 0)
    )
    raw_break = raw_return.abs() > settings["raw_return_break_threshold"]
    share_break = shares_change.abs() > settings["listed_shares_change_threshold"]
    market_cap_break = market_cap_return.abs() > settings["market_cap_break_threshold"]

    sequential_code = pd.Series(pd.NA, index=work.index, dtype="object")
    likely_share_reset = raw_break & share_break & ~market_cap_break
    sequential_code.loc[likely_share_reset] = "LIKELY_SHARE_CHANGE_PRICE_RESET"
    sequential_code.loc[sequential_code.isna() & raw_break] = "UNEXPLAINED_PRICE_DISCONTINUITY"
    sequential_code.loc[sequential_code.isna() & share_break] = "LISTED_SHARES_CHANGE"
    sequential_code.loc[sequential_code.isna() & market_cap_break] = "MARKET_CAP_DISCONTINUITY"
    sequential_break = sequential_code.notna()

    # Invalid rows form an empty segment. A sequential break retains the current
    # row as the first safe observation of the new segment.
    new_segment = first | invalid | previous_invalid | sequential_break
    segment_id = new_segment.astype("int64").groupby(keys, sort=False, dropna=False).cumsum()
    last_segment = segment_id.groupby(keys, sort=False, dropna=False).transform("max")
    keep = ~invalid & segment_id.eq(last_segment)
    cleaned = work.loc[keep].copy().reset_index(drop=True)

    details = {
        "INVALID_CLOSE": "종가가 없거나 0 이하라 이 봉과 이전 구간을 연결하지 않습니다.",
        "INVALID_OHLC_NON_POSITIVE": "OHLC 중 누락 또는 0 이하 값이 있어 이 봉과 이전 구간을 연결하지 않습니다.",
        "INVALID_OHLC_RANGE": "고가·저가가 시가·종가 범위를 포함하지 않아 이 봉과 이전 구간을 연결하지 않습니다.",
        "NEGATIVE_VOLUME": "거래량이 음수라 이 봉과 이전 구간을 연결하지 않습니다.",
        "NO_TRADE_BAR_DROPPED": "거래량 0인 비체결 행을 수익률·백테스트 관측치에서 제외합니다.",
        "LIKELY_SHARE_CHANGE_PRICE_RESET": (
            "종가와 상장주식수가 크게 변했으나 시가총액 변화는 임계값 안입니다. "
            "기업행위 확정이 아닌 주식수 변화 추정으로 기록하고 원시 가격 구간을 분리합니다."
        ),
        "UNEXPLAINED_PRICE_DISCONTINUITY": (
            "원시 종가가 임계값을 초과해 변했으며 KRX 주식수·시가총액 필드로 설명되지 않습니다."
        ),
        "LISTED_SHARES_CHANGE": "상장주식수 변화가 임계값을 초과해 기업행위 가능 구간을 분리합니다.",
        "MARKET_CAP_DISCONTINUITY": "시가총액 기반 수준이 임계값을 초과해 변해 모멘텀 수익률 구간을 분리합니다.",
    }

    issue_frames: list[pd.DataFrame] = [no_trade_issues] if not no_trade_issues.empty else []
    if invalid.any():
        idx = invalid[invalid].index
        issue_frames.append(
            pd.DataFrame(
                {
                    "ticker": keys.loc[idx].values,
                    "trade_date": work.loc[idx, date_column].dt.strftime("%Y-%m-%d").values,
                    "previous_trade_date": None,
                    "issue_code": invalid_code.loc[idx].values,
                    "severity": "CRITICAL",
                    "action": "START_NEW_CLEAN_SEGMENT",
                    "raw_return": None,
                    "market_cap_return": None,
                    "listed_shares_change": None,
                    "details": invalid_code.loc[idx].map(details).values,
                }
            )
        )
    if sequential_break.any():
        idx = sequential_break[sequential_break].index
        codes = sequential_code.loc[idx]
        severity = codes.map(
            lambda code: "WARNING" if code in {"LIKELY_SHARE_CHANGE_PRICE_RESET", "LISTED_SHARES_CHANGE"} else "CRITICAL"
        )
        issue_frames.append(
            pd.DataFrame(
                {
                    "ticker": keys.loc[idx].values,
                    "trade_date": work.loc[idx, date_column].dt.strftime("%Y-%m-%d").values,
                    "previous_trade_date": previous_date.loc[idx].dt.strftime("%Y-%m-%d").values,
                    "issue_code": codes.values,
                    "severity": severity.values,
                    "action": "START_NEW_CLEAN_SEGMENT",
                    "raw_return": raw_return.loc[idx].values,
                    "market_cap_return": market_cap_return.loc[idx].values,
                    "listed_shares_change": shares_change.loc[idx].values,
                    "details": codes.map(details).values,
                }
            )
        )
    issues = (
        pd.concat(issue_frames, ignore_index=True)[ISSUE_COLUMNS].sort_values(["ticker", "trade_date"]).reset_index(drop=True)
        if issue_frames
        else pd.DataFrame(columns=ISSUE_COLUMNS)
    )
    if temporary_ticker:
        cleaned = cleaned.drop(columns=["ticker"], errors="ignore")
    summary = _summary(input_rows, ticker_count, issues, len(cleaned), settings)
    return cleaned, issues, summary


def _summary(
    input_rows: int,
    ticker_count: int,
    issues: pd.DataFrame,
    output_rows: int,
    settings: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(issues["issue_code"].tolist()) if not issues.empty else Counter()
    critical = int((issues["severity"] == "CRITICAL").sum()) if not issues.empty else 0
    breaking = issues[issues["action"] == "START_NEW_CLEAN_SEGMENT"] if not issues.empty else issues
    affected = int(breaking["ticker"].nunique()) if not breaking.empty else 0
    return {
        "source_fields": ["KRX OHLC", "listed_shares", "market_cap"],
        "corporate_action_confirmation": False,
        "policy": "latest_clean_segment_per_ticker",
        "input_rows": int(input_rows),
        "output_rows": int(output_rows),
        "excluded_pre_break_rows": int(max(0, input_rows - output_rows)),
        "tickers_analyzed": int(ticker_count),
        "tickers_with_breaks": affected,
        "issue_count": int(len(issues)),
        "non_trading_bar_count": int((issues["issue_code"] == "NO_TRADE_BAR_DROPPED").sum()) if not issues.empty else 0,
        "critical_issue_count": critical,
        "issue_counts": dict(counts),
        "thresholds": settings,
    }
