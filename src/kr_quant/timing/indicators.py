from __future__ import annotations

from typing import Any


def _sma(vals: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    if n <= 0:
        return out
    for i in range(len(vals)):
        if i + 1 < n:
            continue
        window = vals[i - n + 1 : i + 1]
        if any(v is None for v in window):
            continue
        out[i] = sum(window) / n  # type: ignore[arg-type]
    return out


def midpoint(high: list[float], low: list[float], i: int, period: int) -> float | None:
    if i < 0 or period <= 0 or i + 1 < period:
        return None
    lo = i - period + 1
    return (max(high[lo : i + 1]) + min(low[lo : i + 1])) / 2


def stochastic_slow(
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    k_period: int = 5,
    k_smooth: int = 3,
    d_period: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """Korean-style slow stochastic (default 5,3,3)."""
    n = min(len(high), len(low), len(close))
    fast_k: list[float | None] = [None] * n
    for i in range(n):
        if i + 1 < k_period:
            continue
        hh = max(high[i - k_period + 1 : i + 1])
        ll = min(low[i - k_period + 1 : i + 1])
        denom = hh - ll
        fast_k[i] = 50.0 if denom == 0 else (close[i] - ll) / denom * 100.0
    slow_k = _sma(fast_k, k_smooth)
    slow_d = _sma(slow_k, d_period)
    return slow_k, slow_d


def ichimoku_lines(
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    tenkan_n: int = 9,
    kijun_n: int = 26,
    span_b_n: int = 52,
    displacement: int = 26,
) -> dict[str, list[float | None]]:
    n = min(len(high), len(low), len(close))
    tenkan: list[float | None] = [midpoint(high, low, i, tenkan_n) for i in range(n)]
    kijun: list[float | None] = [midpoint(high, low, i, kijun_n) for i in range(n)]
    span_a_raw: list[float | None] = [None] * n
    span_b_raw: list[float | None] = [None] * n
    for i in range(n):
        if tenkan[i] is not None and kijun[i] is not None:
            span_a_raw[i] = (tenkan[i] + kijun[i]) / 2  # type: ignore[operator]
        span_b_raw[i] = midpoint(high, low, i, span_b_n)
    # Cloud at bar i is the span calculated `displacement` bars earlier.
    cloud_a: list[float | None] = [None] * n
    cloud_b: list[float | None] = [None] * n
    for i in range(n):
        src = i - displacement
        if src >= 0:
            cloud_a[i] = span_a_raw[src]
            cloud_b[i] = span_b_raw[src]
    return {
        "tenkan": tenkan,
        "kijun": kijun,
        "span_a": span_a_raw,
        "span_b": span_b_raw,
        "cloud_a": cloud_a,
        "cloud_b": cloud_b,
        "chikou": list(close),
    }


def _crossed_up(prev_a: float | None, prev_b: float | None, a: float | None, b: float | None) -> bool:
    if None in (prev_a, prev_b, a, b):
        return False
    return prev_a <= prev_b and a > b  # type: ignore[operator]


def _crossed_down(prev_a: float | None, prev_b: float | None, a: float | None, b: float | None) -> bool:
    if None in (prev_a, prev_b, a, b):
        return False
    return prev_a >= prev_b and a < b  # type: ignore[operator]


def _r(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def last_signals(
    high: list[float],
    low: list[float],
    close: list[float],
) -> dict[str, Any]:
    n = min(len(high), len(low), len(close))
    empty: dict[str, Any] = {
        "bars": n,
        "used_in_quant": False,
        "labels": [],
        "ok": False,
    }
    if n < 8:
        return empty
    k_s, d_s = stochastic_slow(high, low, close)
    ichi = ichimoku_lines(high, low, close)
    i = n - 1
    k, d = k_s[i], d_s[i]
    prev_k = k_s[i - 1] if i else None
    prev_d = d_s[i - 1] if i else None
    golden = _crossed_up(prev_k, prev_d, k, d)
    dead = _crossed_down(prev_k, prev_d, k, d)
    over_sold = k is not None and k < 20
    over_bought = k is not None and k > 80
    tenkan, kijun = ichi["tenkan"][i], ichi["kijun"][i]
    prev_tenkan = ichi["tenkan"][i - 1] if i else None
    prev_kijun = ichi["kijun"][i - 1] if i else None
    tk_up = tenkan is not None and kijun is not None and tenkan > kijun
    tk_golden = _crossed_up(prev_tenkan, prev_kijun, tenkan, kijun)
    tk_dead = _crossed_down(prev_tenkan, prev_kijun, tenkan, kijun)
    ca, cb = ichi["cloud_a"][i], ichi["cloud_b"][i]
    cloud = None
    px = close[i]
    if ca is not None and cb is not None:
        top, bot = max(ca, cb), min(ca, cb)
        if px > top:
            cloud = "above"
        elif px < bot:
            cloud = "below"
        else:
            cloud = "inside"
    labels: list[str] = []
    if over_sold:
        labels.append("과매도")
    if over_bought:
        labels.append("과매수")
    if golden:
        labels.append("스토 골든")
    if dead:
        labels.append("스토 데드")
    if cloud == "above":
        labels.append("구름 위")
    elif cloud == "below":
        labels.append("구름 아래")
    elif cloud == "inside":
        labels.append("구름 안")
    if tk_golden:
        labels.append("전환 골든")
    elif tk_dead:
        labels.append("전환 데드")
    elif tk_up:
        labels.append("전환>기준")
    elif tenkan is not None and kijun is not None:
        labels.append("전환<기준")
    stoch_bias = None
    if golden or (k is not None and d is not None and k > d and not over_bought):
        stoch_bias = "bull"
    elif dead or (k is not None and d is not None and k < d and not over_sold):
        stoch_bias = "bear"
    ichi_bias = None
    if cloud == "above" and tk_up:
        ichi_bias = "bull"
    elif cloud == "below" and not tk_up:
        ichi_bias = "bear"
    elif cloud == "above" or tk_golden:
        ichi_bias = "bull"
    elif cloud == "below" or tk_dead:
        ichi_bias = "bear"
    return {
        "ok": True,
        "bars": n,
        "used_in_quant": False,
        "stoch_k": _r(k, 1),
        "stoch_d": _r(d, 1),
        "stoch_over_sold": over_sold,
        "stoch_over_bought": over_bought,
        "stoch_golden": golden,
        "stoch_dead": dead,
        "stoch_bias": stoch_bias,
        "ichi_tenkan": _r(tenkan),
        "ichi_kijun": _r(kijun),
        "ichi_cloud": cloud,
        "ichi_tk_up": bool(tk_up),
        "ichi_tk_golden": tk_golden,
        "ichi_tk_dead": tk_dead,
        "ichi_bias": ichi_bias,
        "close": _r(px),
        "labels": labels,
    }
