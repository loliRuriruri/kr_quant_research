"""Read-time candidate gates. Keep source history intact; never fetch on GET."""
from collections import Counter
from datetime import date
import math

import pandas as pd

from kr_quant.freshness import expected_price_date
from kr_quant.universe.tradability import krx_risk_class_excluded

FLOW_LISTS = ('rows', 'dual', 'private_equity', 'dual_pe', 'dual_pe_retail',
              'other_corp', 'pension', 'empty', 'comeback', 'low_foreign',
              'trading', 'trading_ex_quant')


def day(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def latest_status_date(settings, expected):
    """Newest krx_status session at or before expected. Missing file → None."""
    expected = day(expected)
    if not expected:
        return None
    try:
        rows = pd.read_csv(settings.status_csv, dtype={'ticker': str})
        dates = [day(v) for v in rows['as_of_date'].astype(str)]
        dates = [d for d in dates if d and d <= expected]
        return max(dates) if dates else None
    except (OSError, ValueError, KeyError):
        return None


def toss_session(payload, settings, expected):
    """Display the clock session, or the last stored toss session if it matches warehouse.

    After 18:00 the clock expected date can jump to today while prices, krx_status
    and the Toss cache are still the previous close. Showing an empty table then
    hides real stored flow. An older cache than the warehouse still fails closed.
    """
    expected = day(expected)
    warehouse = latest_status_date(settings, expected)
    tos = [day(r.get('to')) for r in (payload.get('rows') or []) if isinstance(r, dict)]
    tos = [d for d in tos if d]
    if expected in tos:
        return expected
    latest_to = max((d for d in tos if d <= expected), default=None)
    if latest_to and warehouse and latest_to == warehouse:
        return latest_to
    return expected


def active_tickers(settings, expected):
    """Unknown, conflicting, halted or stale status fails closed.

    If the expected session is missing from krx_status, use the latest stored
    status date as the universe. A missing status file still fails closed.
    """
    try:
        rows = pd.read_csv(settings.status_csv, dtype={'ticker': str})
        expected = str(expected)[:10]
        dated = rows[rows['as_of_date'].astype(str).str[:10] == expected]
        if dated.empty and not rows.empty and 'as_of_date' in rows.columns:
            latest = latest_status_date(settings, expected) or str(rows['as_of_date'].astype(str).max())[:10]
            dated = rows[rows['as_of_date'].astype(str).str[:10] == latest]
        ok = (dated['status'] == 'ACTIVE') & ~dated['krx_risk_class'].map(krx_risk_class_excluded)
        ok &= pd.to_numeric(dated['close'], errors='coerce') > 0
        ok &= pd.to_numeric(dated['volume'], errors='coerce') > 0
        valid = set(dated.loc[ok, 'ticker'].astype(str).str.zfill(6))
        invalid = set(dated.loc[~ok, 'ticker'].astype(str).str.zfill(6))
        return valid - invalid
    except (OSError, ValueError, KeyError):
        return set()


def toss_reason(row, expected, active, window=1):
    if not isinstance(row, dict) or str(row.get('ticker', '')).zfill(6) not in active:
        return 'STATUS_UNVERIFIED_OR_INELIGIBLE'
    if day(row.get('to')) != expected:
        return 'FLOW_DATE_MISMATCH'
    if row.get('source_complete') is False:
        return 'FLOW_SOURCE_VALUE_MISSING'
    daily = row.get('daily')
    if not isinstance(daily, list) or not daily:
        return 'FLOW_DAILY_MISSING'
    dates = [day(r.get('date')) for r in daily if isinstance(r, dict)]
    if (len(dates) != len(daily) or None in dates or max(dates) != expected
            or len(set(dates)) != len(dates) or len(dates) < window):
        return 'FLOW_WINDOW_UNVERIFIED'
    for item in daily:
        if item.get('is_final') is False:
            return 'FLOW_PROVISIONAL'
        for field in ('foreign', 'institution'):
            try:
                if not math.isfinite(float(item.get(field))):
                    return 'FLOW_VALUE_MISSING'
            except (TypeError, ValueError):
                return 'FLOW_VALUE_MISSING'
    return None


def gate_toss_payload(payload, settings, expected=None):
    clock = day(expected or expected_price_date())
    session = toss_session(payload, settings, clock)
    active = active_tickers(settings, session)
    out = dict(payload)
    window = max(1, int(payload.get('days') or 1))
    reasons = Counter()
    source_rows = payload.get('rows') or []
    occurrences = Counter(str(r.get('ticker', '')).zfill(6) for r in source_rows if isinstance(r, dict))
    current = {}
    for row in source_rows:
        reason = toss_reason(row, session, active, window)
        code = str(row.get('ticker', '')).zfill(6) if isinstance(row, dict) else ''
        if occurrences[code] > 1:
            reason = 'DUPLICATE_CANDIDATE'
        if reason:
            reasons[reason] += 1
        else:
            current[code] = dict(row)
    for key in FLOW_LISTS:
        if isinstance(payload.get(key), list):
            out[key] = list({str(r.get('ticker', '')).zfill(6): current[str(r.get('ticker', '')).zfill(6)]
                             for r in payload[key] if isinstance(r, dict)
                             and str(r.get('ticker', '')).zfill(6) in current
                             and toss_reason(r, session, active, window) is None}.values())
    # Never show hit rates/counts computed over excluded source candidates.
    if sum(reasons.values()):
        out['stats'] = {}
    current_n = len(out.get('rows') or [])
    excluded_n = sum(reasons.values())
    out['reliability'] = {
        'expected_date': session,
        'clock_expected': clock,
        'session_fallback': session != clock,
        'source_rows': len(source_rows),
        'current_rows': current_n,
        'excluded_rows': excluded_n,
        'reasons': dict(reasons),
    }
    out['need_scan'] = bool(payload.get('need_scan') or not current_n)
    out['candidate_as_of'] = session
    lag = (f" 기대 종가일 {clock}은 아직 토스 캐시·거래상태에 없어 직전 세션 {session}을 표시합니다."
           if session != clock else "")
    out['reliability_note'] = (f"{session} 기준 확인 {current_n}/{len(source_rows)}종목 · "
                               f"날짜·거래상태·자료 미확인 {excluded_n}종목 후보 제외.{lag} 원천 이력은 보존합니다.")
    return out


def gate_official_rows(rows, settings, expected=None):
    expected = day(expected or expected_price_date())
    active = active_tickers(settings, expected)
    final = [r for r in rows if r.get('is_final') is True and day(r.get('trade_date'))
             and day(r['trade_date']) <= expected]
    # Official event totals are monetary amounts. Never replace absent amounts
    # with share quantities or zero, or bridge a missing day into a streak.
    # Exclude the whole affected party series in the supplied history window.
    invalid_parties = set()
    occurrences = Counter((r.get('ticker'), r.get('investor_type'), day(r['trade_date'])) for r in final)
    for row in final:
        try:
            valid = not isinstance(row.get('net_value'), bool) and math.isfinite(float(row.get('net_value')))
        except (TypeError, ValueError):
            valid = False
        if not valid or occurrences[(row.get('ticker'), row.get('investor_type'), day(row['trade_date']))] != 1:
            invalid_parties.add((row.get('ticker'), row.get('investor_type')))
    final = [r for r in final if (r.get('ticker'), r.get('investor_type')) not in invalid_parties]
    # Both parties must have today's confirmed observation, not just any row.
    current = {r['ticker'] for r in final if day(r['trade_date']) == expected
               and r.get('investor_type') == 'FOREIGN'} & {
        r['ticker'] for r in final if day(r['trade_date']) == expected
        and r.get('investor_type') == 'INSTITUTION_TOTAL'} & active
    current_parties = {(r['ticker'], r.get('investor_type')) for r in final
                       if day(r['trade_date']) == expected}
    return [r for r in final if r.get('ticker') in current
            and (r['ticker'], r.get('investor_type')) in current_parties]
