"""Describe measured non-positive windows without inventing a historical cause."""
import math


def failure_observations(years):
    observations = []
    for row in years or []:
        if not isinstance(row, dict):
            continue
        value = row.get('return')
        if value is None or isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value > 0:
            continue
        year = row.get('year')
        if year is None:
            continue
        outcome = '하락' if value < 0 else '보합'
        observations.append({'year': year, 'return': value,
            'outcome': outcome, 'cause_status': 'UNVERIFIED', 'cause_sources': [],
            'text': f'{year}년: 해당 월 가격 수익률 {value * 100:+.1f}% ({outcome}). 원인 미확인: 해당 연도 공시·실적·수급 근거를 대조하지 않았습니다.'})
    return observations
