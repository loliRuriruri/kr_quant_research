"""Join timestamped prepared selection to locked execution plans, fail closed.

Never relabel today's config or reconstructed inputs as original historical data.
Passing structural checks remains an unverified raw-price diagnostic.
"""
from collections import Counter
from copy import deepcopy
import math

import pandas as pd

from kr_quant.research.pit_readiness import _aware, validate_replay_inputs
from kr_quant.research.pre_entry_replay import payload_hash, replay_prepared_ranking
from kr_quant.research.season_execution import evaluate_fixed_window
from kr_quant.strategy.engine import execution_model_from_mapping


def replay_selection_execution(partitions, policy_partition, prices, *, sessions,
                               decision_at, market_date, as_of):
    """Policy payload: decision_at, market_date, model_id, config, exit_plans.

    exit_plans contains ticker, pattern_id, exit_date. config uses the existing
    strategy_lab costs/execution shape. Envelope metadata input is execution_policy.
    The caller supplies an exchange-session calendar; open assumed 09:00 KST.
    Special-session opens and source provenance are not certified here.
    """
    ranking = replay_prepared_ranking(partitions, decision_at=decision_at, market_date=market_date)
    result = {"status": "BLOCKED", "verified": False, "ranking": ranking,
              "rows": [], "issues": [], "policy_hash": None, "as_of": str(as_of),
              "limitations": ['제공 거래일의 정규장 09:00 KST 가정; 특별 개장시간 미검증',
                              '정책·입력 시점의 구조 검사이며 원본 출처와 기업행위 검증 아님']}
    if ranking['status'] != 'RANKED_UNVERIFIED':
        result['issues'] = ranking['issues']
        return result
    result['selection_input_hashes'] = {p['metadata']['input']: p['metadata']['sha256'] for p in partitions}
    policy = deepcopy(policy_partition)
    try:
        meta, payload = policy['metadata'], policy['payload']
        check = validate_replay_inputs([meta], decision_at=decision_at,
                                       required_inputs=('execution_policy',))
        if check['issues']:
            result['issues'] = check['issues']
            return result
        if meta.get('input') != 'execution_policy' or meta.get('sha256') != payload_hash(payload):
            raise ValueError('POLICY_HASH_MISMATCH')
        if (_aware(payload.get('decision_at')) != _aware(decision_at)
                or payload.get('market_date') != market_date
                or payload.get('model_id') != ranking['model_id']):
            raise ValueError('POLICY_CONTEXT_MISMATCH')
        cfg = payload['config']
        costs, execution = cfg['costs'], cfg['execution']
        required_costs = {'commission_bps', 'slippage_bps', 'sell_tax_bps', 'sell_tax_schedule_bps'}
        required_execution = {'position_notional_krw', 'max_participation_rate',
                              'impact_bps_at_max_participation', 'price_limit_pct',
                              'lock_tolerance_pct', 'max_pending_days', 'block_zero_volume'}
        if set(costs) != required_costs or set(execution) != required_execution:
            raise ValueError('EXPLICIT_POLICY_FIELDS_REQUIRED')
        numeric = [costs[k] for k in required_costs - {'sell_tax_schedule_bps'}]
        numeric += [execution[k] for k in required_execution - {'block_zero_volume'}]
        numeric += [item['bps'] for item in costs['sell_tax_schedule_bps']]
        if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in numeric):
            raise ValueError('INVALID_NUMERIC_POLICY')
        if not 0 < execution['price_limit_pct'] < 1:
            raise ValueError('INVALID_PRICE_LIMIT')
        # The general mapper accepts malformed schedule entries silently; this
        # stricter historical boundary must reject rather than drop them.
        for item in costs['sell_tax_schedule_bps']:
            if set(item) != {'effective_from', 'bps'}:
                raise ValueError('INVALID_TAX_SCHEDULE')
            pd.Timestamp(item['effective_from'])
        if type(execution['block_zero_volume']) is not bool:
            raise ValueError('INVALID_VOLUME_POLICY')
        if type(execution['max_pending_days']) is not int or execution['max_pending_days'] < 0:
            raise ValueError('INVALID_PENDING_POLICY')
        model = execution_model_from_mapping({**costs, **execution},
                    commission_bps=costs['commission_bps'], slippage_bps=costs['slippage_bps'])
        if len(model.sell_tax_schedule_bps) != len(costs['sell_tax_schedule_bps']):
            raise ValueError('INVALID_TAX_SCHEDULE')
        stamps = [pd.Timestamp(d) for d in sessions]
        if any(pd.isna(d) or d.tzinfo is not None or d != d.normalize() for d in stamps):
            raise ValueError('INVALID_SESSION_CALENDAR')
        market_days = sorted(set(d.date() for d in stamps))
        next_days = [d for d in market_days if d > pd.Timestamp(market_date).date()]
        if not next_days:
            raise ValueError('NEXT_SESSION_MISSING')
        next_open = pd.Timestamp(f'{next_days[0]} 09:00:00', tz='Asia/Seoul')
        if _aware(decision_at) >= next_open:
            raise ValueError('DECISION_NOT_BEFORE_ENTRY_OPEN')
        plans = {}
        for plan in payload['exit_plans']:
            key = (plan['ticker'], plan['pattern_id'])
            if key in plans:
                raise ValueError('DUPLICATE_EXIT_PLAN')
            plans[key] = plan['exit_date']
        result['policy_hash'] = meta['sha256']
        for row in ranking['rows']:
            record = {'ticker': row['ticker'], 'pattern_id': row['pattern_id'],
                      'rank': row['pre_entry_rank'], 'execution': None}
            key = (row['ticker'], row['pattern_id'])
            if key not in plans:
                record['status'] = 'EXIT_PLAN_MISSING'
            else:
                try:
                    diagnostic = evaluate_fixed_window(prices, ticker=row['ticker'], sessions=market_days,
                        signal_date=market_date, exit_date=plans[key], as_of=as_of, model=model)
                    record.update(status=diagnostic['status'], execution=diagnostic)
                except (ValueError, TypeError, KeyError) as exc:
                    record.update(status='EXECUTION_INPUT_INVALID', reason=str(exc))
            result['rows'].append(record)
        result.update(status='REPLAY_EXECUTION_UNVERIFIED', summary={
            'selected_count': len(result['rows']),
            'status_counts': dict(Counter(r['status'] for r in result['rows'])),
            'completed_count': sum(r['status'] == 'EXECUTION_DIAGNOSTIC' for r in result['rows']),
            'verified_count': 0})
    except (ValueError, TypeError, KeyError) as exc:
        result['issues'].append({'code': str(exc)})
    return result
