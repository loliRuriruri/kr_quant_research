"""Year-split month/exit-day reference rule; not the production pre-entry model.

Only raw price diagnostics are exposed. Temporal isolation does not certify
corporate actions, historical universe membership, or executable performance.
"""
from __future__ import annotations

import calendar
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd


def evaluate_season_holdout(prices, *, ticker: str, as_of: date, sessions,
                            lookback_years: int = 5, min_train_years: int = 3) -> dict:
    if lookback_years not in (0, 2, 3, 5) or min_train_years < 2:
        raise ValueError('지원 기간 0/2/3/5년, 최소 학습 표본 2년 이상')
    ticker = str(ticker).zfill(6)
    frame = prices.copy()
    required = {'ticker', 'open', 'close', 'volume'}
    if not required.issubset(frame.columns):
        raise ValueError('필수 가격 열 누락')
    frame = frame[frame['ticker'].astype(str).str.zfill(6) == ticker].copy()
    column = 'trade_date' if 'trade_date' in frame else 'date'
    frame['_date'] = pd.to_datetime(frame[column], errors='coerce')
    if frame['_date'].isna().any():
        raise ValueError('가격 날짜 오류')
    frame = frame[frame['_date'].dt.date <= as_of].sort_values('_date')
    if frame['_date'].duplicated().any():
        raise ValueError('중복 거래일 가격')
    for col in ('open', 'close', 'volume'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    # Include month-boundary gaps: a split/rights reset at the first session
    # must not disappear when monthly groups are formed.
    frame['_overnight_jump'] = (frame['open']/frame['close'].shift()-1).abs().gt(.35)
    market_days = sorted({pd.Timestamp(d).date() for d in sessions if pd.Timestamp(d).date() <= as_of})
    calendar_months = {}
    for day in market_days:
        calendar_months.setdefault((day.year, day.month), []).append(day)
    groups = {(int(y), int(m)): g for (y, m), g in frame.groupby([frame['_date'].dt.year, frame['_date'].dt.month])}

    def quality(group, year, month, end_day=None):
        expected = calendar_months.get((year, month), [])
        if end_day is not None:
            expected = [d for d in expected if d <= end_day]
        if not expected or expected[0].day > 7 or (end_day is None and (len(expected) < 8 or expected[-1].day < calendar.monthrange(year, month)[1]-7)):
            return 'MARKET_CALENDAR_INCOMPLETE'
        if group is None or list(group['_date'].dt.date) != expected:
            return 'PRICE_PATH_MISSING'
        if not (np.isfinite(group['open']) & (group['open'] > 0) & np.isfinite(group['close']) & (group['close'] > 0)).all():
            return 'INVALID_PRICE'
        if not (np.isfinite(group['volume']) & (group['volume'] > 0)).all():
            return 'NO_TRADING_VOLUME'
        if group['_overnight_jump'].any() or group['close'].pct_change().abs().gt(.35).any() or (group['close']/group['open']-1).abs().gt(.35).any():
            return 'PRICE_DISCONTINUITY'
        return 'OK'

    # Complete months only. Current year is not an evaluation fold.
    stats, excluded = {}, Counter()
    for (year, month), group in groups.items():
        if year >= as_of.year:
            continue
        problem = quality(group, year, month)
        if problem != 'OK':
            excluded[problem] += 1
            continue
        stats[(year, month)] = {
            'year': year, 'month': month,
            'return': float(group['close'].iloc[-1]/group['open'].iloc[0]-1),
            'peak_day': int(group.loc[group['close'].idxmax(), '_date'].day),
        }
    folds = []
    first_year = int(frame['_date'].dt.year.min()) if not frame.empty else as_of.year
    for year in range(first_year + 1, as_of.year):
        candidates = []
        for month in range(1, 13):
            history = [v for (y, m), v in sorted(stats.items()) if m == month and y < year
                       and (lookback_years == 0 or y >= year-lookback_years)]
            if len(history) < min_train_years:
                continue
            candidates.append({'month': month, 'train_years': [v['year'] for v in history],
                               'median_return': float(np.median([v['return'] for v in history])),
                               'exit_day': min(28, max(1, int(round(float(np.median([v['peak_day'] for v in history]))))))})
        candidates.sort(key=lambda v: (-v['median_return'], v['month']))
        fold = {'test_year': year, 'selected_at': f'{year}-01-01', 'train_cutoff': f'{year-1}-12-31',
                'candidates': candidates, 'selection': None, 'status': 'INSUFFICIENT_TRAIN',
                'entry_date': None, 'exit_date': None, 'diagnostic_return': None,
                'verified_return': None, 'worst_close_return': None, 'cost_scenarios': {}}
        if not candidates:
            folds.append(fold)
            continue
        selected = candidates[0]
        fold['selection'] = selected
        if selected['median_return'] <= 0:
            fold['status'] = 'NO_POSITIVE_TRAIN_MONTH'
            folds.append(fold)
            continue
        month = selected['month']
        group = groups.get((year, month))
        anchor = date(year, month, selected['exit_day'])
        scheduled = [d for d in calendar_months.get((year, month), []) if d >= anchor]
        if not scheduled:
            fold['status'] = 'EXIT_DATE_MISSING'
            folds.append(fold)
            continue
        exit_day = scheduled[0]
        path = group[group['_date'].dt.date <= exit_day] if group is not None else None
        problem = quality(path, year, month, end_day=exit_day)
        if problem != 'OK':
            fold['status'] = problem
            folds.append(fold)
            continue
        # Fixed before viewing the test year. Never choose this year's high.
        exit_row = path.iloc[-1]
        entry = float(path['open'].iloc[0])
        value = float(exit_row['close']/entry-1)
        fold.update(status='RAW_PRICE_DIAGNOSTIC', entry_date=str(path['_date'].iloc[0].date()),
                    exit_date=str(exit_row['_date'].date()), diagnostic_return=round(value, 8),
                    worst_close_return=round(float(path['close'].min()/entry-1), 8),
                    cost_scenarios={str(bps): round(value-bps/10000, 8) for bps in (20, 50, 100)})
        folds.append(fold)
    values = [f['diagnostic_return'] for f in folds if f['diagnostic_return'] is not None]
    summary = {'folds_total': len(folds), 'diagnostic_count': len(values), 'verified_count': 0,
               'status_counts': dict(Counter(f['status'] for f in folds)),
               'mean': float(np.mean(values)) if values else None,
               'median': float(np.median(values)) if values else None,
               'positive_fraction': sum(v > 0 for v in values)/len(values) if values else None,
               'min': min(values) if values else None, 'max': max(values) if values else None}
    from kr_quant.research.statistical_reliability import sample_reliability
    summary['uncertainty'] = sample_reliability([
        {'year': f['test_year'], 'return': f['diagnostic_return']}
        for f in folds if f['diagnostic_return'] is not None])
    summary['excluded_or_unavailable_count'] = len(folds)-len(values)
    return {'ticker': ticker, 'as_of': str(as_of), 'lookback_years': lookback_years,
            'record_type': 'RECONSTRUCTED_REFERENCE_RULE',
            'validation_status': 'TEMPORAL_HOLDOUT_RAW_DIAGNOSTIC', 'summary': summary, 'folds': folds,
            'excluded_training_months': dict(excluded),
            'methodology': {'min_train_years': min_train_years, 'price_basis': 'UNVERIFIED_RAW_OHLC',
                'rule': 'prior-year data: best median monthly open-to-close return, median historical peak day capped at 28; next year month open to fixed exit close',
                'calendar': 'supplied observed market dates, not certified exchange calendar',
                'current_year_excluded': True, 'production_pre_entry_model_validated': False,
                'limitations': ['사후 설계한 기준모형의 재구성입니다. 미열람 잠금 OOS나 실제 당시 선정 이력이 아닙니다.',
                    '현재 종목·사후 수집 자료를 사용하므로 과거 유니버스·생존편향은 해결되지 않았습니다.',
                    '기존 선취매의 진입 30일 전·수급·등급·전체 종목 순위 모델 검증이 아닌 월 선택 기준모형입니다.',
                    '수정주가·기업행위·상장폐지 정산·체결을 검증하지 않은 원시 가격 진단이며 검증 성과는 0건입니다.',
                    '20/50/100bps는 단순 비용 민감도 가정이며 실제 세금·수수료가 아닙니다.',
                    '최소 3개년 학습 표본이 필요합니다. 2년 선택에서는 검증 표본이 부족할 수 있습니다.',
                    '여러 월·종목 탐색의 다중검정, 불확실성 추정과 외부 검증은 추가로 필요합니다.']}}
