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


def active_tickers(settings, expected):
    """Unknown, conflicting, halted or stale status fails closed."""
    try:
        rows = pd.read_csv(settings.status_csv, dtype={'ticker': str})
        rows = rows[rows['as_of_date'].astype(str) == expected]
        ok = (rows['status'] == 'ACTIVE') & ~rows['krx_risk_class'].map(krx_risk_class_excluded)
        ok &= pd.to_numeric(rows['close'], errors='coerce') > 0
        ok &= pd.to_numeric(rows['volume'], errors='coerce') > 0
        valid = set(rows.loc[ok, 'ticker'])
        invalid = set(rows.loc[~ok, 'ticker'])
        return valid - invalid
    except (OSError, ValueError, KeyError):
        return set()


def toss_reason(row, expected, active, window=1):
    if not isinstance(row, dict) or str(row.get('ticker', '')).zfill(6) not in active:
        return 'STATUS_UNVERIFIED_OR_INELIGIBLE'
    if day(row.get('to')) != expected:
        return 'FLOW_DATE_MISMATCH'
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
    expected = day(expected or expected_price_date())
    active = active_tickers(settings, expected)
    out = dict(payload)
    window = max(1, int(payload.get('days') or 1))
    reasons = Counter()
    source_rows = payload.get('rows') or []
    occurrences = Counter(str(r.get('ticker', '')).zfill(6) for r in source_rows if isinstance(r, dict))
    current = {}
    for row in source_rows:
        reason = toss_reason(row, expected, active, window)
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
                             and toss_reason(r, expected, active, window) is None}.values())
    # Never show hit rates/counts computed over excluded source candidates.
    if sum(reasons.values()):
        out['stats'] = {}
    out['reliability'] = {'expected_date': expected, 'source_rows': len(source_rows),
                          'current_rows': len(out.get('rows') or []),
                          'excluded_rows': sum(reasons.values()), 'reasons': dict(reasons)}
    out['need_scan'] = bool(payload.get('need_scan') or sum(reasons.values()) or not source_rows)
    out['candidate_as_of'] = expected
    out['reliability_note'] = (f"{expected} 기준 확인 {len(out.get('rows') or [])}/{len(source_rows)}종목 · "
                               f"날짜·거래상태·자료 미확인 {sum(reasons.values())}종목 후보 제외. 원천 이력은 보존합니다.")
    return out


def gate_official_rows(rows, settings, expected=None):
    expected = day(expected or expected_price_date())
    active = active_tickers(settings, expected)
    final = [r for r in rows if r.get('is_final') is True and day(r.get('trade_date'))
             and day(r['trade_date']) <= expected]
    # Both parties must have today's confirmed observation, not just any row.
    current = {r['ticker'] for r in final if day(r['trade_date']) == expected
               and r.get('investor_type') == 'FOREIGN'} & {
        r['ticker'] for r in final if day(r['trade_date']) == expected
        and r.get('investor_type') == 'INSTITUTION_TOTAL'} & active
    current_parties = {(r['ticker'], r.get('investor_type')) for r in final
                       if day(r['trade_date']) == expected}
    return [r for r in final if r.get('ticker') in current
            and (r['ticker'], r.get('investor_type')) in current_parties]
