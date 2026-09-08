from dataclasses import replace

import pandas as pd
import pytest

from kr_quant.research.season_execution import evaluate_fixed_window
from kr_quant.strategy.engine import ExecutionModel


def fixture():
    days = pd.bdate_range('2025-01-02', periods=8)
    frame = pd.DataFrame({'ticker': '005930', 'trade_date': days,
                          'open': [100, 100, 101, 102, 103, 104, 105, 106],
                          'close': [100, 101, 102, 103, 104, 105, 106, 107], 'volume': 10000})
    return frame, days


def run(frame=None, model=None, **kwargs):
    prices, days = fixture()
    return evaluate_fixed_window(prices if frame is None else frame, ticker='005930', sessions=days,
                                 signal_date=days[0], exit_date=days[4], as_of=kwargs.get('as_of', days[-1]),
                                 model=model or ExecutionModel(commission_bps=10, slippage_bps=5,
                                                              sell_tax_bps=20, block_zero_volume=True))


def test_next_open_fixed_exit_and_exact_cost_arithmetic():
    result = run()
    assert result['entry']['date'] == '2025-01-03'
    assert result['exit']['date'] == '2025-01-08'
    assert result['gross_return'] == pytest.approx(.03)
    assert result['net_return'] == pytest.approx(1.03 * (1-.0035)/(1+.0015)-1)
    assert result['net_return'] < result['gross_return']
    assert result['verified'] is False


def test_missing_open_waits_without_close_fallback():
    frame, _ = fixture()
    frame.loc[1, 'open'] = float('nan')
    result = run(frame)
    assert result['attempts'][0]['reason'] == 'OPEN_MISSING'
    assert result['entry']['open'] == 101
    frame.loc[1:3, 'open'] = float('nan')
    result = run(frame)
    assert result['status'] == 'ENTRY_UNFILLED'
    assert result['net_return'] is None


def test_exit_failure_is_not_dropped_or_forced_closed():
    frame, _ = fixture()
    frame.loc[4:6, 'open'] = float('nan')
    result = run(frame)
    assert result['entry'] is not None
    assert result['exit'] is None
    assert result['status'] == 'EXIT_UNFILLED'
    assert result['gross_return'] is None


def test_entry_liquidity_does_not_use_same_day_total_volume():
    frame, _ = fixture()
    model = ExecutionModel(position_notional_krw=50000, max_participation_rate=.1,
                           impact_bps_at_max_participation=10, max_pending_days=1)
    result = run(frame, model)
    frame.loc[1, 'volume'] = 1  # Entry remains identical; later exit liquidity may change.
    changed = run(frame, model)
    assert changed['entry'] == result['entry']
    frame.loc[0, 'volume'] = 1
    assert run(frame, model)['status'] == 'ENTRY_UNFILLED'


def test_tax_effective_date_and_negative_cost_rejection():
    base = ExecutionModel(sell_tax_schedule_bps=(('2025-01-08', 40),))
    assert run(model=base)['sell_cost_bps'] == 45
    with pytest.raises(ValueError):
        run(model=replace(base, commission_bps=-1))


def test_limit_open_zero_volume_and_zero_wait():
    frame, _ = fixture()
    frame.loc[1, 'open'] = 130
    assert run(frame)['attempts'][0]['reason'] == 'LIMIT_OPEN_CONSERVATIVE'
    frame.loc[1, 'open'] = 100
    frame.loc[1, 'volume'] = 0
    assert run(frame)['attempts'][0]['reason'] == 'NO_VOLUME_EX_POST'
    assert run(model=ExecutionModel(max_pending_days=0))['entry'] is None


def test_asof_cutoff_and_future_price_invariance():
    frame, days = fixture()
    result = run(frame, as_of=days[4])
    frame.loc[5:, ['open', 'close']] = 9999
    assert run(frame, as_of=days[4]) == result
    assert run(as_of=days[2])['status'] == 'EXIT_UNFILLED'


def test_duplicate_dates_and_holding_gaps_fail_closed():
    frame, _ = fixture()
    with pytest.raises(ValueError):
        run(pd.concat([frame, frame.iloc[[2]]]))
    assert run(frame.drop(index=2))['status'] == 'HOLDING_PATH_MISSING'


def test_zero_cost_gross_equals_net_and_losses_remain():
    frame, _ = fixture()
    frame.loc[4, 'open'] = 90
    result = run(frame, ExecutionModel(slippage_bps=0))
    assert result['gross_return'] == pytest.approx(-.1)
    assert result['net_return'] == result['gross_return']


def test_exit_close_and_intraday_high_do_not_choose_the_exit():
    frame, _ = fixture()
    original = run(frame)
    frame.loc[4, 'close'] = float('nan')
    frame['high'] = 99999
    result = run(frame)
    assert result['exit'] == original['exit']
    assert result['net_return'] == original['net_return']
