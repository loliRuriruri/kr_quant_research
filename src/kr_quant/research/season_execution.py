"""Explicit fixed-date, next-open execution diagnostic, not production OOS.

Raw OHLC cannot certify corporate actions or actual auction fills. All outcomes,
including missing prices and unfilled exits, remain in the returned ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict

import pandas as pd

from kr_quant.strategy.engine import ExecutionModel


def evaluate_fixed_window(prices, *, ticker, sessions, signal_date, exit_date,
                          as_of, model: ExecutionModel) -> dict:
    """Signal after close; enter next session, exit at preselected date's open.

    max_pending_days is the maximum number of eligible exchange sessions per
    order, including the first attempt. Zero means no attempts. Participation
    uses up to 20 immediately preceding supplied sessions; missing history fails
    closed. Daily volume is used only as an explicitly ex-post no-trade check.
    """
    def day(value):
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is not None or stamp != stamp.normalize():
            raise ValueError("Expected unambiguous calendar dates")
        return stamp.date()

    signal, scheduled_exit, cutoff = map(day, (signal_date, exit_date, as_of))
    if not signal < scheduled_exit or cutoff < signal:
        raise ValueError("Invalid signal/exit/as_of order")
    costs = [model.commission_bps, model.slippage_bps, model.sell_tax_bps,
             model.impact_bps_at_max_participation] + [v for _, v in model.sell_tax_schedule_bps]
    if any(not math.isfinite(v) or v < 0 or v >= 10000 for v in costs):
        raise ValueError("Costs must be finite nonnegative basis points below 10000")
    for effective, _ in model.sell_tax_schedule_bps:
        day(effective)
    if (not math.isfinite(model.position_notional_krw) or model.position_notional_krw < 0
            or not 0 <= model.max_participation_rate <= 1
            or not 0 < model.price_limit_pct < 1
            or not 0 <= model.lock_tolerance_pct < model.price_limit_pct
            or not isinstance(model.max_pending_days, int) or model.max_pending_days < 0):
        raise ValueError("Invalid execution policy")
    if model.impact_bps_at_max_participation and not model.max_participation_rate:
        raise ValueError("Impact requires an explicit participation limit")
    if model.max_participation_rate and model.position_notional_krw <= 0:
        raise ValueError("Participation requires an explicit positive position size")
    policy = {**asdict(model), "version": "SEASON_FIXED_OPEN_V1", "adv_sessions": 20,
              "price_basis": "UNVERIFIED_RAW_OPEN", "exit": "preselected date or next session open"}
    result = {"status": "ENTRY_UNFILLED", "verified": False, "ticker": str(ticker).zfill(6),
              "signal_date": str(signal), "scheduled_exit": str(scheduled_exit), "as_of": str(cutoff),
              "entry": None, "exit": None, "gross_return": None, "net_return": None,
              "attempts": [], "policy": policy,
              "policy_hash": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
              "limitations": ["원시가격·기업행위·당시 유니버스 미검증; 독립 OOS 성과 아님",
                              "시가 제한가 접근은 보수적으로 미체결 처리; 실제 호가·잔량 없음",
                              "당일 거래량 0 검사는 사후 무거래 확인이며 장 시작 전 정보가 아님"]}
    market = sorted({day(d) for d in sessions if day(d) <= cutoff})
    if signal not in market:
        result["status"] = "SIGNAL_SESSION_MISSING"
        return result
    frame = prices.copy()
    date_col = "trade_date" if "trade_date" in frame else "date"
    if not {"ticker", date_col, "open", "close", "volume"}.issubset(frame):
        raise ValueError("Required raw prices missing")
    frame = frame[frame.ticker.astype(str).str.zfill(6) == result["ticker"]].copy()
    frame["_day"] = frame[date_col].map(day)
    frame = frame[frame._day <= cutoff]
    if frame._day.duplicated().any():
        raise ValueError("Duplicate ticker session")
    rows = frame.set_index("_day").to_dict("index")

    def positive(value):
        try:
            return math.isfinite(float(value)) and float(value) > 0
        except (TypeError, ValueError):
            return False

    def attempt(when, side, notional):
        row = rows.get(when, {})
        reason = None
        impact = 0.0
        index = market.index(when)
        previous = rows.get(market[index-1], {}) if index else {}
        if not positive(row.get("open")):
            reason = "OPEN_MISSING"
        elif not positive(previous.get("close")):
            reason = "PREVIOUS_CLOSE_MISSING"
        elif model.block_zero_volume and not positive(row.get("volume")):
            reason = "NO_VOLUME_EX_POST"
        else:
            change = float(row["open"]) / float(previous["close"]) - 1
            if abs(change) > model.price_limit_pct + model.lock_tolerance_pct:
                reason = "PRICE_DISCONTINUITY"
            elif ((side == "BUY" and change >= model.price_limit_pct-model.lock_tolerance_pct)
                  or (side == "SELL" and change <= -model.price_limit_pct+model.lock_tolerance_pct)):
                reason = "LIMIT_OPEN_CONSERVATIVE"
        if reason is None and model.max_participation_rate:
            history = [rows.get(d, {}) for d in market[max(0, index-20):index]]
            if not history or any(not positive(r.get("close")) or not positive(r.get("volume")) for r in history):
                reason = "PRIOR_LIQUIDITY_MISSING"
            else:
                adv = sum(float(r["close"])*float(r["volume"]) for r in history)/len(history)
                participation = notional/adv
                if participation > model.max_participation_rate:
                    reason = "PRIOR_LIQUIDITY_LIMIT"
                else:
                    impact = model.impact_bps_at_max_participation * participation/model.max_participation_rate
        result["attempts"].append({"date": str(when), "side": side, "reason": reason or "FILLED_PROXY"})
        return None if reason else {"date": str(when), "open": float(row["open"]), "impact_bps": impact}

    for when in [d for d in market if signal < d < scheduled_exit][:model.max_pending_days]:
        result["entry"] = attempt(when, "BUY", model.position_notional_krw)
        if result["entry"]:
            break
    if not result["entry"]:
        return result
    result["status"] = "EXIT_UNFILLED"
    for when in [d for d in market if d >= scheduled_exit][:model.max_pending_days]:
        # Mark the original fixed position to the candidate open for exit liquidity.
        opening = rows.get(when, {}).get("open")
        notional = model.position_notional_krw * float(opening)/result["entry"]["open"] if positive(opening) else 0
        result["exit"] = attempt(when, "SELL", notional)
        if result["exit"]:
            break
    if not result["exit"]:
        return result
    entry, exit_fill = result["entry"], result["exit"]
    held = [d for d in market if day(entry["date"]) <= d < day(exit_fill["date"])]
    if any(not positive(rows.get(d, {}).get("close")) for d in held):
        result["status"] = "HOLDING_PATH_MISSING"
        return result
    # Detect intervening raw-price resets too, not just the order dates.
    closes = [float(rows[d]["close"]) for d in held]
    if any(abs(b/a-1) > model.price_limit_pct+model.lock_tolerance_pct for a, b in zip(closes, closes[1:])):
        result["status"] = "PRICE_DISCONTINUITY"
        return result
    buy_bps = model.commission_bps + model.slippage_bps + entry["impact_bps"]
    sell_bps = model.commission_bps + model.slippage_bps + exit_fill["impact_bps"] + model.tax_bps(exit_fill["date"])
    if buy_bps >= 10000 or sell_bps >= 10000:
        raise ValueError("Combined costs must be below 10000 bps")
    ratio = exit_fill["open"]/entry["open"]
    result.update(status="EXECUTION_DIAGNOSTIC", gross_return=ratio-1,
                  net_return=ratio*(1-sell_bps/10000)/(1+buy_bps/10000)-1,
                  buy_cost_bps=buy_bps, sell_cost_bps=sell_bps)
    return result
