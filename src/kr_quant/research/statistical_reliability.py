"""Descriptive year-sample uncertainty, not calibrated investment probabilities."""
from math import comb, isfinite, sqrt


def sample_reliability(records, *, family_size=None):
    years, values = [], []
    for row in records:
        try:
            year, value = int(row['year']), float(row['return'])
            if not isfinite(value) or year in years:
                raise ValueError()
            years.append(year)
            values.append(value)
        except (KeyError, TypeError, ValueError):
            return {'status': 'INVALID_SAMPLE', 'verified': False, 'n': 0}
    n = len(values)
    wins = sum(v > 0 for v in values)
    if not n:
        return {'status': 'INSUFFICIENT_SAMPLE', 'verified': False, 'n': 0}
    p, z = wins/n, 1.959963984540054
    denom = 1 + z*z/n
    center = (p + z*z/(2*n))/denom
    half = z*sqrt(p*(1-p)/n + z*z/(4*n*n))/denom
    # Exact one-sided binomial reference H0: P(positive year)=0.5.
    p_raw = sum(comb(n, k) for k in range(wins, n+1)) / (2**n)
    family = family_size if isinstance(family_size, int) and family_size > 0 else None
    adjusted = min(1., p_raw*family) if family else None
    return {'status': 'LOW_SAMPLE' if n < 5 else 'EXPLORATORY', 'verified': False,
            'used_in_quant': False, 'n': n, 'wins': wins, 'positive_fraction': p,
            'wilson95': [max(0., center-half), min(1., center+half)],
            'p_raw_reference': p_raw, 'p_bonferroni_reference': adjusted, 'family_size': family,
            'note': '연도 독립·상승확률 50%를 가정한 참고 통계입니다. 신뢰구간은 다음 매매 성공확률이 아닙니다. '
                    '동일 데이터로 패턴을 탐색했으며 기업행위·생존편향·전체 모델 OOS는 미검증입니다. '
                    '보정 범위는 이번 월×종목 탐색만이며 다른 기간·전략 반복 탐색은 포함하지 않습니다.'}
