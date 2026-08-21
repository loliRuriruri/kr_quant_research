"""Multi-timeframe timing state and confidence. Overlay only — never writes quant_score."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from kr_quant.timing.indicators import last_signals

STATE_KO = {
    "TREND": "추세",
    "PULLBACK": "눌림",
    "OVERSOLD": "과매도",
    "RECOVERY": "회복",
    "OVERHEATED": "과열",
    "NEUTRAL": "중립",
}
TREND_KO = {"UP": "상승", "DOWN": "하락", "MIXED": "혼조"}
VOL_KO = {
    "QUIET": "한산",
    "NORMAL": "보통",
    "ACTIVE": "활발",
    "HIGH": "많음",
    "EXTREME": "급증",
}
STAB_SCORE = {"HIGH": 90.0, "MEDIUM": 55.0, "LOW": 20.0}

_DEFAULT = {
    "used_in_quant": False,
    "timeframes": {
        "short": {"label": "단기", "lookback": 20, "ma_fast": 5, "ma_slow": 20},
        "mid": {"label": "중기", "lookback": 60, "ma_fast": 20, "ma_slow": 60},
        "long": {"label": "장기", "lookback": 252, "ma_fast": 60, "ma_slow": 120},
    },
    "volume": {"quiet_max": 0.7, "active_min": 1.3, "high_min": 2.0, "extreme_min": 4.0},
    "confidence_weights": {
        "sample": 25,
        "alignment": 30,
        "volume_clarity": 15,
        "trend_clarity": 15,
        "distance_52w": 15,
    },
    "min_bars": {"short": 20, "mid": 60, "long": 180, "full_sample": 250},
    "strategy_blend": True,
    "disclaimer": "타이밍 상태·신뢰도는 조사 오버레이입니다. Quant 점수에 넣지 않으며 매수 지시가 아닙니다.",
}


def load_timing_config(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        return dict(_DEFAULT)
    path = Path(root) / "config" / "timing.yaml"
    if not path.exists():
        return dict(_DEFAULT)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = dict(_DEFAULT)
    out.update(raw)
    return out


def _sma(vals: list[float], n: int) -> float | None:
    if n <= 0 or len(vals) < n:
        return None
    window = vals[-n:]
    return sum(window) / n


def _ret(vals: list[float], lookback: int) -> float | None:
    if len(vals) < lookback + 1 or vals[-1 - lookback] == 0:
        return None
    return (vals[-1] / vals[-1 - lookback]) - 1.0


def _vol_state(ratio: float | None, cfg: dict[str, Any]) -> str:
    if ratio is None:
        return "NORMAL"
    vol = cfg.get("volume") or {}
    if ratio >= float(vol.get("extreme_min") or 4):
        return "EXTREME"
    if ratio >= float(vol.get("high_min") or 2):
        return "HIGH"
    if ratio >= float(vol.get("active_min") or 1.3):
        return "ACTIVE"
    if ratio <= float(vol.get("quiet_max") or 0.7):
        return "QUIET"
    return "NORMAL"


def _series(hist: pd.DataFrame, col: str) -> list[float]:
    if col not in hist.columns:
        return []
    return [float(x) for x in pd.to_numeric(hist[col], errors="coerce").dropna().tolist()]


def _prepare(hist: pd.DataFrame) -> pd.DataFrame:
    work = hist.copy()
    date_col = "trade_date" if "trade_date" in work.columns else "date"
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    for col in ("high", "low", "close"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["close"])
    return work


def _tf_block(close: list[float], volume: list[float], spec: dict[str, Any], min_bars: int) -> dict[str, Any]:
    lookback = int(spec.get("lookback") or 20)
    fast_n = int(spec.get("ma_fast") or 5)
    slow_n = int(spec.get("ma_slow") or 20)
    ok = len(close) >= max(min_bars, slow_n, lookback)
    fast = _sma(close, fast_n)
    slow = _sma(close, slow_n)
    last = close[-1] if close else None
    ret = _ret(close, lookback) if ok else None
    trend = "MIXED"
    if last is not None and fast is not None and slow is not None:
        if last > fast > slow:
            trend = "UP"
        elif last < fast < slow:
            trend = "DOWN"
        elif last > slow:
            trend = "UP" if (ret or 0) >= 0 else "MIXED"
        elif last < slow:
            trend = "DOWN" if (ret or 0) <= 0 else "MIXED"
    vol_ratio = None
    if volume and len(volume) >= max(5, min(lookback, len(volume))):
        avg = sum(volume[-lookback:]) / min(lookback, len(volume))
        if avg > 0:
            vol_ratio = volume[-1] / avg
    vol = _vol_state(vol_ratio, {"volume": {}})
    # volume state uses caller cfg later; keep ratio here
    return {
        "ok": ok,
        "label": spec.get("label") or "",
        "lookback": lookback,
        "trend": trend if ok else None,
        "trend_ko": TREND_KO.get(trend, trend) if ok else "표본 부족",
        "ma_fast": None if fast is None else round(fast, 2),
        "ma_slow": None if slow is None else round(slow, 2),
        "return": None if ret is None else round(ret, 4),
        "volume_ratio": None if vol_ratio is None else round(vol_ratio, 2),
        "bars": len(close),
        "used_in_quant": False,
    }


def _timing_state(tfs: dict[str, dict[str, Any]], daily: dict[str, Any], dist_52w: float | None) -> str:
    short = (tfs.get("short") or {}).get("trend")
    mid = (tfs.get("mid") or {}).get("trend")
    long = (tfs.get("long") or {}).get("trend")
    oversold = bool(daily.get("stoch_over_sold"))
    overbought = bool(daily.get("stoch_over_bought"))
    if overbought and dist_52w is not None and dist_52w > -0.05:
        return "OVERHEATED"
    if oversold and short == "DOWN":
        return "OVERSOLD"
    if short == "UP" and mid == "DOWN":
        return "RECOVERY"
    if short == "DOWN" and mid == "UP":
        return "PULLBACK"
    aligned_up = [t for t in (short, mid, long) if t == "UP"]
    aligned_down = [t for t in (short, mid, long) if t == "DOWN"]
    live = [t for t in (short, mid, long) if t in {"UP", "DOWN"}]
    if len(aligned_up) >= 2 and len(aligned_up) >= len(live) - 0:
        if long == "UP" or mid == "UP":
            return "TREND"
    if len(aligned_down) >= 2:
        return "TREND"
    if oversold:
        return "OVERSOLD"
    if overbought:
        return "OVERHEATED"
    return "NEUTRAL"


def _clip(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _price_confidence(tfs: dict[str, dict[str, Any]], bars: int, vol_state: str, dist_52w: float | None, cfg: dict[str, Any]) -> tuple[float, dict[str, float], str]:
    weights = cfg.get("confidence_weights") or _DEFAULT["confidence_weights"]
    full = float((cfg.get("min_bars") or {}).get("full_sample") or 250)
    sample = _clip(bars / full * 100.0)
    live = [b for b in tfs.values() if b.get("ok") and b.get("trend") in {"UP", "DOWN", "MIXED"}]
    if len(live) >= 2:
        ups = sum(1 for b in live if b.get("trend") == "UP")
        downs = sum(1 for b in live if b.get("trend") == "DOWN")
        align = _clip(max(ups, downs) / len(live) * 100.0)
        if max(ups, downs) == 0:
            align = 40.0
    else:
        align = 25.0
    if vol_state in {"NORMAL", "ACTIVE"}:
        vol_s = 80.0
    elif vol_state == "HIGH":
        vol_s = 70.0
    elif vol_state == "QUIET":
        vol_s = 45.0
    else:
        vol_s = 35.0
    mixed = sum(1 for b in live if b.get("trend") == "MIXED")
    trend_s = 80.0 if live and mixed == 0 else 55.0 if live else 30.0
    if dist_52w is None:
        dist_s = 50.0
    elif dist_52w > -0.03:
        dist_s = 40.0
    elif dist_52w < -0.35:
        dist_s = 45.0
    else:
        dist_s = 75.0
    parts = {
        "sample": sample,
        "alignment": align,
        "volume_clarity": vol_s,
        "trend_clarity": trend_s,
        "distance_52w": dist_s,
    }
    total_w = sum(float(weights.get(k, 0)) for k in parts) or 1.0
    score = sum(parts[k] * float(weights.get(k, 0)) for k in parts) / total_w
    if bars < 60:
        score = min(score, 45.0)
        note = f"표본 {bars}일로 짧아 신뢰도를 낮게 둡니다."
    elif bars < 180:
        score = min(score, 75.0)
        note = f"표본 {bars}일. 장기는 아직 얇습니다."
    else:
        note = f"표본 {bars}일."
    return round(_clip(score), 1), {k: round(v, 1) for k, v in parts.items()}, note


def strategy_confidence(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row or not isinstance(row, dict):
        return None
    best = (row.get("strategies") or [None])[0] if row.get("strategies") else row
    if not isinstance(best, dict):
        best = row
    oos = float(best.get("oos_sharpe") or 0)
    mdd = float(best.get("max_drawdown") or 0)
    wf = float(best.get("wf_hit") if best.get("wf_hit") is not None else (best.get("wf_score") or 0) / 100.0)
    trades = int(best.get("trade_count") or 0)
    stab = STAB_SCORE.get(str(row.get("stability_label") or best.get("stability_label") or "LOW"), 20.0)
    oos_s = _clip(50.0 + oos * 25.0)
    dd_s = _clip(100.0 + mdd * 200.0)  # mdd is negative
    wf_s = _clip(wf * 100.0 if wf <= 1 else wf)
    trade_s = _clip(trades / 12.0 * 100.0)
    score = oos_s * 0.30 + dd_s * 0.20 + stab * 0.20 + wf_s * 0.20 + trade_s * 0.10
    return {
        "score": round(_clip(score), 1),
        "parts": {
            "oos_sharpe": round(oos_s, 1),
            "oos_drawdown": round(dd_s, 1),
            "stability": round(stab, 1),
            "walk_forward": round(wf_s, 1),
            "trade_count": round(trade_s, 1),
        },
        "used_in_quant": False,
    }


def apply_strategy_confidence(timing: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
    extra = strategy_confidence(row)
    if not extra:
        return timing
    timing = dict(timing)
    price = float(timing.get("confidence") or 0)
    blended = round(price * 0.55 + extra["score"] * 0.45, 1)
    if int(timing.get("bars") or 0) < 200:
        blended = min(blended, 70.0)
    timing["strategy_confidence"] = extra
    timing["confidence"] = blended
    timing["confidence_source"] = "price+strategy"
    comment = str(timing.get("comment") or "")
    timing["comment"] = (comment + f" 전략 랩 OOS를 섞어 신뢰 {blended}점.").strip()
    return timing


def timing_from_history(hist: pd.DataFrame | None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or dict(_DEFAULT)
    empty = {
        "ok": False,
        "used_in_quant": False,
        "bars": 0,
        "state": "NEUTRAL",
        "state_ko": STATE_KO["NEUTRAL"],
        "confidence": 0.0,
        "timeframes": {},
        "disclaimer": cfg.get("disclaimer") or _DEFAULT["disclaimer"],
    }
    if hist is None or hist.empty:
        return empty
    work = _prepare(hist)
    close = _series(work, "close")
    high = _series(work, "high") or close
    low = _series(work, "low") or close
    volume = _series(work, "volume") or _series(work, "trading_value")
    bars = len(close)
    if bars < 8:
        empty["bars"] = bars
        return empty
    daily = last_signals(high, low, close)
    mins = cfg.get("min_bars") or _DEFAULT["min_bars"]
    tfs: dict[str, dict[str, Any]] = {}
    for key, spec in (cfg.get("timeframes") or _DEFAULT["timeframes"]).items():
        block = _tf_block(close, volume, spec, int(mins.get(key) or 20))
        block["volume_state"] = _vol_state(block.get("volume_ratio"), cfg)
        block["volume_state_ko"] = VOL_KO.get(block["volume_state"], block["volume_state"])
        tfs[key] = block
    last = close[-1]
    window = close[-252:] if bars >= 60 else close
    high_52 = max(window) if window else last
    dist_52w = None if high_52 <= 0 else (last / high_52) - 1.0
    vol_ratio = (tfs.get("short") or {}).get("volume_ratio")
    vol_state = _vol_state(vol_ratio, cfg)
    state = _timing_state(tfs, daily, dist_52w)
    score, parts, note = _price_confidence(tfs, bars, vol_state, dist_52w, cfg)
    aligned = [b.get("trend_ko") for b in tfs.values() if b.get("ok")]
    comment = (
        f"{STATE_KO[state]}. {note} "
        f"단기/중기/장기: {' · '.join(aligned) or '미산출'}. "
        f"52주 고점 대비 {dist_52w * 100:.1f}%." if dist_52w is not None else f"{STATE_KO[state]}. {note}"
    )
    comment += " Quant 점수에 넣지 않습니다."
    date_col = "trade_date" if "trade_date" in work.columns else "date"
    as_of = work[date_col].iloc[-1]
    as_of_s = as_of.date().isoformat() if hasattr(as_of, "date") else str(as_of)[:10]
    return {
        "ok": True,
        "used_in_quant": False,
        "bars": bars,
        "as_of": as_of_s,
        "close": round(last, 2),
        "state": state,
        "state_ko": STATE_KO[state],
        "confidence": score,
        "confidence_parts": parts,
        "confidence_source": "price",
        "volume_state": vol_state,
        "volume_state_ko": VOL_KO[vol_state],
        "volume_ratio": None if vol_ratio is None else round(float(vol_ratio), 2),
        "high_52w_distance": None if dist_52w is None else round(dist_52w, 4),
        "timeframes": tfs,
        "daily": {
            "stoch_k": daily.get("stoch_k"),
            "stoch_d": daily.get("stoch_d"),
            "labels": daily.get("labels") or [],
            "ichi_cloud": daily.get("ichi_cloud"),
        },
        "comment": comment,
        "disclaimer": cfg.get("disclaimer") or _DEFAULT["disclaimer"],
    }
