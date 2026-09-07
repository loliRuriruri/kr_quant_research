"""Forward observation statistics, NOT a fill simulator or an OOS claim."""
from __future__ import annotations

from collections import Counter
from datetime import date

import numpy as np
import pandas as pd

HORIZONS = (1, 5, 20)


def observe_selection_outcomes(batch: dict, prices: pd.DataFrame, market_sessions, *,
                               observed_through: date, corporate_actions_verified=False, adjusted_prices_verified=False,
                               round_trip_cost_bps: float | None = None,
                               benchmark: pd.DataFrame | None = None, benchmark_name: str | None = None):
    """D1 = first session's close after the observed selection date; D5 = fifth.

    Entry is never rolled forward to hide a missing/suspended stock. All signals
    remain in each horizon's denominator, including pending and unavailable ones.
    """
    if round_trip_cost_bps is not None and (not np.isfinite(round_trip_cost_bps) or not 0 <= round_trip_cost_bps < 10000):
        raise ValueError('비용 가정은 0 이상 10000 미만 bps이어야 합니다.')
    stamp = pd.Timestamp(batch['observed_at'])
    if stamp.tzinfo is None:
        raise ValueError('관측 시각에 시간대가 없습니다.')
    observation_day = stamp.tz_convert('Asia/Seoul').date()
    if str(batch['source_as_of'])[:10] > observation_day.isoformat():
        raise ValueError('미래 원천 기준일')
    sessions = sorted({pd.Timestamp(d).date() for d in market_sessions if pd.Timestamp(d).date() <= observed_through})
    forward = [d for d in sessions if d > observation_day]
    px = prices.copy()
    if not px.empty:
        required = {'ticker', 'open', 'close', 'volume'}
        if not required.issubset(px.columns):
            raise ValueError('관측 가격 필수 열 누락')
        day_col = 'trade_date' if 'trade_date' in px else 'date'
        parsed = pd.to_datetime(px[day_col], errors='coerce')
        if parsed.isna().any():
            raise ValueError('관측 가격 날짜 오류')
        px['_day'] = parsed.dt.date
        px = px[px['_day'] <= observed_through].copy()
        px['ticker'] = px['ticker'].astype(str).str.zfill(6)
        if px.duplicated(['ticker', '_day']).any():
            raise ValueError('종목/거래일 중복 가격')
    groups = {ticker: group.set_index('_day') for ticker, group in px.groupby('ticker')} if not px.empty else {}
    benchmark_map = {}
    if benchmark_name and benchmark is not None and not benchmark.empty:
        bp = benchmark.copy()
        bp['_day'] = pd.to_datetime(bp['trade_date'] if 'trade_date' in bp else bp['date'], errors='raise').dt.date
        if bp['_day'].duplicated().any():
            raise ValueError('벤치마크 거래일 중복')
        benchmark_map = bp.set_index('_day').to_dict('index')

    def positive(value):
        try:
            return float(value) if np.isfinite(float(value)) and float(value) > 0 else None
        except (TypeError, ValueError):
            return None

    def evaluate(signal, h):
        result = {'status': 'PENDING_ENTRY', 'entry_date': None, 'exit_date': None,
                  'gross_return': None, 'net_scenario_return': None, 'excess_return': None,
                  'price_basis': None}
        if not forward:
            return result
        result['entry_date'] = forward[0].isoformat()
        group = groups.get(signal['ticker'])
        if group is None or forward[0] not in group.index:
            result['status'] = 'ENTRY_DATA_MISSING'
            return result
        first = group.loc[forward[0]]
        entry = positive(first.get('open'))
        if entry is None or positive(first.get('volume')) is None:
            result['status'] = 'ENTRY_UNAVAILABLE'
            return result
        if len(forward) < h:
            result['status'] = 'PENDING_HORIZON'
            return result
        days = forward[:h]
        result['exit_date'] = days[-1].isoformat()
        if any(d not in group.index for d in days):
            result['status'] = 'PRICE_PATH_MISSING'
            return result
        path = group.loc[days]
        if positive(path.iloc[-1].get('volume')) is None:
            result['status'] = 'EXIT_UNAVAILABLE'
            return result
        close = pd.to_numeric(path['close'], errors='coerce')
        if not (np.isfinite(close) & (close > 0)).all():
            result['status'] = 'INVALID_PRICE'
            return result
        if adjusted_prices_verified and 'adj_close' in path and all(positive(v) is not None for v in path['adj_close']):
            adj = pd.to_numeric(path['adj_close'])
            entry *= float(adj.iloc[0]/close.iloc[0])
            close = adj
            result['price_basis'] = 'ADJUSTED_CLOSE_WITH_ADJUSTED_OPEN'
        elif corporate_actions_verified:
            result['price_basis'] = 'CALLER_VERIFIED_ACTION_FREE_RAW'
        else:
            result['status'] = 'PRICE_BASIS_UNVERIFIED'
            return result
        if abs(float(close.iloc[0])/entry-1) > 0.35 or close.pct_change().abs().gt(0.35).any():
            result['status'] = 'PRICE_DISCONTINUITY'
            return result
        gross = float(close.iloc[-1]/entry-1)
        result.update(status='OBSERVED', gross_return=round(gross, 8))
        if round_trip_cost_bps is not None:
            result['net_scenario_return'] = round(gross-round_trip_cost_bps/10000, 8)
        b0, b1 = benchmark_map.get(days[0], {}), benchmark_map.get(days[-1], {})
        bopen, bclose = positive(b0.get('open')), positive(b1.get('close'))
        if bopen is not None and bclose is not None:
            result['excess_return'] = round(gross-(bclose/bopen-1), 8)
        return result

    signals = batch['selected']
    if len({s['signal_id'] for s in signals}) != len(signals):
        raise ValueError('선정 ID 중복')
    rows = [{**{k: signal.get(k) for k in ('signal_id', 'ticker', 'company', 'quant_rank')},
             'horizons': {str(h): evaluate(signal, h) for h in HORIZONS}} for signal in signals]
    summary = {}
    for h in HORIZONS:
        counts = Counter(row['horizons'][str(h)]['status'] for row in rows)
        values = [row['horizons'][str(h)]['gross_return'] for row in rows if row['horizons'][str(h)]['status'] == 'OBSERVED']
        summary[str(h)] = {'total_signals': len(rows), 'observed': len(values), 'status_counts': dict(counts),
                           'mean_return': float(np.mean(values)) if values else None,
                           'win_rate': sum(v > 0 for v in values)/len(values) if values else None}
    return {'batch_id': batch['batch_id'], 'observed_at': batch['observed_at'], 'source_as_of': batch['source_as_of'],
            'observed_through': observed_through.isoformat(), 'summary': summary, 'rows': rows,
            'methodology': {'rule': 'NEXT_SESSION_OPEN_TO_HORIZON_CLOSE', 'd1_definition': '첫 관측 거래일 시가→당일 종가',
                'executable_backtest': False, 'calendar_source': 'caller_supplied_market_sessions',
                'adjusted_prices_verified': bool(adjusted_prices_verified),
                'corporate_actions_verified': bool(corporate_actions_verified),
                'round_trip_cost_bps': round_trip_cost_bps, 'benchmark_name': benchmark_name,
                'limitations': ['시가 체결·상하한가·호가 잔량·시장충격을 검증하지 않은 가격 관측입니다.',
                    '비용 차감값은 사용자가 지정한 단순 bps 시나리오이며 실제 세금·체결비용이 아닙니다.',
                    '공식 거래일 캘린더·기업행위·상장폐지 수익률은 원천별 추가 검증이 필요합니다.',
                    '미관측·자료 누락은 분모에 남기며 유효 관측만의 승률과 구분합니다.']}}
