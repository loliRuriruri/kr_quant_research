from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Sequence

# KRX 휴장일. 가격 스냅샷이 있으면 그 날짜가 우선한다.
# 2024-2026 확정/공지된 주요 휴장일 + 주말.
_STATIC_HOLIDAYS = {
    # 2024
    date(2024, 1, 1),
    date(2024, 2, 9),
    date(2024, 2, 12),
    date(2024, 3, 1),
    date(2024, 4, 10),
    date(2024, 5, 1),
    date(2024, 5, 6),
    date(2024, 5, 15),
    date(2024, 6, 6),
    date(2024, 8, 15),
    date(2024, 9, 16),
    date(2024, 9, 17),
    date(2024, 9, 18),
    date(2024, 10, 3),
    date(2024, 10, 9),
    date(2024, 12, 25),
    date(2024, 12, 31),
    # 2025
    date(2025, 1, 1),
    date(2025, 1, 27),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 3, 3),
    date(2025, 5, 1),
    date(2025, 5, 5),
    date(2025, 5, 6),
    date(2025, 6, 6),
    date(2025, 8, 15),
    date(2025, 10, 3),
    date(2025, 10, 6),
    date(2025, 10, 7),
    date(2025, 10, 8),
    date(2025, 10, 9),
    date(2025, 12, 25),
    date(2025, 12, 31),
    # 2026
    date(2026, 1, 1),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 3, 2),
    date(2026, 5, 1),
    date(2026, 5, 5),
    date(2026, 5, 25),
    date(2026, 6, 8),
    date(2026, 8, 17),
    date(2026, 9, 24),
    date(2026, 9, 25),
    date(2026, 10, 5),
    date(2026, 10, 9),
    date(2026, 12, 25),
    date(2026, 12, 31),
}


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_static_holiday(d: date) -> bool:
    return d in _STATIC_HOLIDAYS


def is_default_trading_day(d: date) -> bool:
    return not is_weekend(d) and not is_static_holiday(d)


def trading_days_from_dates(dates: Iterable[date]) -> list[date]:
    return sorted({d for d in dates if d is not None})


def next_trading_day(d: date, calendar: Sequence[date] | None = None) -> date:
    if calendar:
        after = [x for x in calendar if x > d]
        if after:
            return after[0]
    cur = d + timedelta(days=1)
    for _ in range(30):
        if is_default_trading_day(cur):
            return cur
        cur += timedelta(days=1)
    return d + timedelta(days=1)


def previous_trading_day(d: date, calendar: Sequence[date] | None = None) -> date:
    if calendar:
        before = [x for x in calendar if x < d]
        if before:
            return before[-1]
    cur = d - timedelta(days=1)
    for _ in range(30):
        if is_default_trading_day(cur):
            return cur
        cur -= timedelta(days=1)
    return d - timedelta(days=1)


def shift_trading_days(d: date, n: int, calendar: Sequence[date] | None = None) -> date | None:
    """Move n trading days. Negative n goes backward. None if calendar cannot support it."""
    if n == 0:
        return d
    if calendar:
        days = list(calendar)
        if d not in days:
            # snap to previous available
            before = [x for x in days if x <= d]
            if not before:
                return None
            d = before[-1]
        idx = days.index(d) + n
        if 0 <= idx < len(days):
            return days[idx]
        return None
    cur = d
    step = 1 if n > 0 else -1
    remaining = abs(n)
    guard = 0
    while remaining > 0 and guard < 2000:
        cur = cur + timedelta(days=step)
        if is_default_trading_day(cur):
            remaining -= 1
        guard += 1
    return cur if remaining == 0 else None
