from datetime import date
import pandas as pd
import pytest
from kr_quant.research.statistical_reliability import sample_reliability
from kr_quant.pit.filings import assert_no_future_rows
from kr_quant.exceptions import PointInTimeLeak


def test_three_wins_are_not_certain_or_multiple_testing_significant():
    result = sample_reliability([{'year':y, 'return':.1} for y in range(2021, 2024)], family_size=1200)
    assert result['positive_fraction'] == 1
    assert result['wilson95'][0] == pytest.approx(.438502968, abs=1e-8)
    assert result['p_raw_reference'] == .125
    assert result['p_bonferroni_reference'] == 1
    assert result['verified'] is False


def test_family_size_never_uses_only_winners():
    records = [{'year':y, 'return':.1} for y in range(2000, 2010)]
    one = sample_reliability(records, family_size=1)
    many = sample_reliability(records, family_size=12000)
    assert many['p_bonferroni_reference'] >= one['p_bonferroni_reference']
    assert sample_reliability(records)['p_bonferroni_reference'] is None


@pytest.mark.parametrize('records', [[{'year':2020, 'return':float('nan')}], [{'year':2020, 'return':1}]*2])
def test_invalid_and_duplicate_years_not_counted(records):
    assert sample_reliability(records)['status'] == 'INVALID_SAMPLE'


@pytest.mark.parametrize('data', [{'x':[1]}, {'available_date':[None]}, {'available_date':['2027-01-01']}])
def test_missing_or_future_availability_blocks_pit(data):
    with pytest.raises(PointInTimeLeak):
        assert_no_future_rows(pd.DataFrame(data), date(2026, 9, 8))
