from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pandas as pd
import pytest

REFERENCE = (ROOT/'reproducibility/reference-sources/scientific-utilities/coloc-percentage-extremes-before-20261006-v2/frozen-before.json')
ROWS = json.loads(REFERENCE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row['case']['key'])
def test_exact_input_percentage_diagnostics(row):
    case = row['case']
    frame = pd.DataFrame({'A_ColocCountB':[case['positive']], 'A_NonColocCountB':[case['negative']]})
    original = frame.copy(deep=True)
    assert utils.add_coloc_percentages(frame) is frame
    # Exact equality intentionally protects nonzero subnormal percentages.
    assert frame[['A_ColocCountB%', 'A_NonColocCountB%']].iloc[0].tolist() == row['expected']
    pd.testing.assert_frame_equal(frame[original.columns], original, check_exact=True)


@pytest.mark.parametrize('value', [-1, -1e-300, np.inf, -np.inf])
@pytest.mark.parametrize('side', ['positive', 'negative'])
def test_invalid_later_counts_refuse_without_touching_any_column(value, side):
    frame = pd.DataFrame({'A_ColocCountB':[2.], 'A_NonColocCountB':[6.],
        'A_ColocCountB%':[999.], 'Z_ColocCountB':[1.], 'Z_NonColocCountB':[3.]})
    frame.loc[0, 'Z_ColocCountB' if side=='positive' else 'Z_NonColocCountB'] = value
    original = frame.copy(deep=True)
    with pytest.raises(ValueError):
        utils.add_coloc_percentages(frame)
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_large_numpy_integer_and_nullable_missing_counts_preserve_input_types():
    maximum = np.iinfo(np.uint64).max
    frame = pd.DataFrame({'A_ColocCountB': pd.Series([maximum, maximum], dtype='UInt64'),
        'A_NonColocCountB': pd.Series([maximum, pd.NA], dtype='UInt64')})
    original = frame.copy(deep=True)
    utils.add_coloc_percentages(frame)
    assert frame[['A_ColocCountB%', 'A_NonColocCountB%']].iloc[0].tolist() == [50.,50.]
    assert frame[['A_ColocCountB%', 'A_NonColocCountB%']].iloc[1].isna().all()
    pd.testing.assert_frame_equal(frame[original.columns], original, check_exact=True)
