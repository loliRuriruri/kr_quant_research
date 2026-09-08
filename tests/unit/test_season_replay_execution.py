from copy import deepcopy

import pandas as pd
import pytest

from tests.unit.test_pre_entry_replay import inputs, MARKET
from kr_quant.research.pre_entry_replay import payload_hash
from kr_quant.research.season_replay_execution import replay_selection_execution

DECISION = '2025-09-02T08:00:00+09:00'


def fixture():
    parts = inputs()
    for part in parts:
        part['payload']['decision_at'] = DECISION
        part['metadata']['sha256'] = payload_hash(part['payload'])
    payload = {'decision_at': DECISION, 'market_date': MARKET, 'model_id': 'fixture-v1',
               'config': {'costs': {'commission_bps': 1.5, 'slippage_bps': 5., 'sell_tax_bps': 20.,
                                   'sell_tax_schedule_bps': []},
                          'execution': {'position_notional_krw': 10000., 'max_participation_rate': .1,
                                        'impact_bps_at_max_participation': 20., 'price_limit_pct': .3,
                                        'lock_tolerance_pct': .005, 'max_pending_days': 3,
                                        'block_zero_volume': True}},
               'exit_plans': [{'ticker': '000001', 'pattern_id': 'a', 'exit_date': '2025-09-05'},
                              {'ticker': '000002', 'pattern_id': 'b', 'exit_date': '2025-09-05'}]}
    policy = {'payload': payload, 'metadata': {**parts[0]['metadata'], 'input': 'execution_policy',
                  'partition_id': 'policy', 'sha256': payload_hash(payload)}}
    days = pd.bdate_range('2025-09-01', '2025-09-09')
    prices = pd.DataFrame([{'ticker': code, 'trade_date': day, 'open': 2000., 'close': 2000.,
                           'volume': 100000.} for code in ('000001', '000002') for day in days])
    return parts, policy, prices, days


def run(parts, policy, prices, days, decision=DECISION):
    return replay_selection_execution(parts, policy, prices, sessions=days,
                decision_at=decision, market_date=MARKET, as_of='2025-09-09')


def test_locked_selection_and_policy_connect_without_mutation():
    parts, policy, prices, days = fixture()
    before = deepcopy((parts, policy))
    result = run(parts, policy, prices, days)
    assert result['status'] == 'REPLAY_EXECUTION_UNVERIFIED'
    assert result['summary']['completed_count'] == 2
    assert result['summary']['verified_count'] == 0
    assert [r['ticker'] for r in result['rows']] == ['000001', '000002']
    assert all(r['execution']['net_return'] < 0 for r in result['rows'])
    assert (parts, policy) == before


@pytest.mark.parametrize('bad', ['future', 'hash', 'missing_cost', 'late', 'model', 'null_cost'])
def test_invalid_or_late_policy_blocks_execution(bad):
    parts, policy, prices, days = fixture()
    decision = DECISION
    if bad == 'future':
        policy['metadata']['available_at'] = '2025-09-03T08:00:00+09:00'
    elif bad == 'hash':
        policy['payload']['exit_plans'][0]['exit_date'] = '2025-09-08'
    elif bad == 'missing_cost':
        del policy['payload']['config']['costs']['sell_tax_bps']
    elif bad == 'null_cost':
        policy['payload']['config']['costs']['sell_tax_bps'] = None
    elif bad == 'model':
        policy['payload']['model_id'] = 'another-model'
    elif bad == 'late':
        decision = '2025-09-02T09:00:00+09:00'
        for part in parts:
            part['payload']['decision_at'] = decision
            part['metadata']['sha256'] = payload_hash(part['payload'])
        policy['payload']['decision_at'] = decision
    if bad != 'hash':
        policy['metadata']['sha256'] = payload_hash(policy['payload'])
    result = run(parts, policy, prices, days, decision)
    assert result['status'] == 'BLOCKED'
    assert not result['rows']


def test_missing_plan_and_unfilled_candidates_remain_in_denominator():
    parts, policy, prices, days = fixture()
    policy['payload']['exit_plans'].pop()
    policy['metadata']['sha256'] = payload_hash(policy['payload'])
    prices.loc[prices.trade_date > MARKET, 'open'] = float('nan')
    result = run(parts, policy, prices, days)
    assert result['summary']['selected_count'] == 2
    assert result['summary']['completed_count'] == 0
    assert result['summary']['status_counts'] == {'ENTRY_UNFILLED': 1, 'EXIT_PLAN_MISSING': 1}


def test_future_returns_cannot_rerank_candidates():
    parts, policy, prices, days = fixture()
    before = run(parts, policy, prices, days)
    prices.loc[(prices.ticker == '000002') & (prices.trade_date > MARKET), ['open', 'close']] = 2400.
    after = run(parts, policy, prices, days)
    assert after['ranking'] == before['ranking']
    assert after['policy_hash'] == before['policy_hash']


def test_current_config_shape_compatible_not_historical_certification():
    from pathlib import Path
    import yaml
    parts, policy, prices, days = fixture()
    config = yaml.safe_load((Path(__file__).parents[2]/'config/strategy_lab.yaml').read_text(encoding='utf-8'))
    # Fixture envelope ONLY: do not write a backdated production policy record.
    policy['payload']['config'] = {k: config[k] for k in ('costs', 'execution')}
    policy['metadata']['sha256'] = payload_hash(policy['payload'])
    result = run(parts, policy, prices, days)
    assert result['status'] == 'REPLAY_EXECUTION_UNVERIFIED'
    assert result['summary']['verified_count'] == 0
