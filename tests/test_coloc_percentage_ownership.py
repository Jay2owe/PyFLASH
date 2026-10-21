from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pandas as pd
import pytest

FIXTURE = (ROOT/'reproducibility/reference-sources/scientific-utilities/coloc-percentage-original-native-20261006-v1/frozen-before.json')
ROWS = json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
def test_complete_original_native_tables_and_repeat(row):
    case = row['case']
    index = pd.Index(case['index'],name=case['index_name'])
    frame = pd.DataFrame({name:case['values'][name] for name in case['columns']},index=index)
    before = frame.copy(deep=True)
    expected = row['expected']
    answer = pd.DataFrame([[np.nan if item=='__nan__' else item for item in values] for values in expected['rows']],
        columns=expected['columns'],index=index)
    assert utils.add_coloc_percentages(frame) is frame
    pd.testing.assert_frame_equal(frame,answer,rtol=1e-12,atol=1e-12)
    pd.testing.assert_frame_equal(frame[case['columns']],before,check_exact=True)
    unchanged = frame.copy(deep=True)
    assert utils.add_coloc_percentages(frame) is frame
    pd.testing.assert_frame_equal(frame,unchanged,check_exact=True)


@pytest.mark.parametrize('kind',['duplicate','ambiguous-negative','ambiguous-positive','malformed-later'])
def test_invalid_pairing_or_calculation_preserves_the_whole_table(kind):
    if kind == 'duplicate':
        frame = pd.DataFrame([[1.,2.,3.]],columns=['A_ColocCountB','A_ColocCountB','A_NonColocCountB'])
    elif kind == 'ambiguous-negative':
        frame = pd.DataFrame({'A_NonColocCountB_NonColocCountC':[2.],
            'A_ColocCountB_NonColocCountC':[1.],'A_NonColocCountB_ColocCountC':[3.]})
    elif kind == 'ambiguous-positive':
        frame = pd.DataFrame({'A_ColocCountB_ColocCountC':[2.],
            'A_NonColocCountB_ColocCountC':[1.],'A_ColocCountB_NonColocCountC':[3.]})
    else:
        frame = pd.DataFrame({'A_ColocCountB':[2.],'A_NonColocCountB':[6.],
            'A_ColocCountB%':[999.], 'Z_ColocCountB':['unavailable'],'Z_NonColocCountB':[3.]})
    before = frame.copy(deep=True)
    with pytest.raises(TypeError if kind=='malformed-later' else ValueError):
        utils.add_coloc_percentages(frame)
    pd.testing.assert_frame_equal(frame,before,check_exact=True)


def test_unrelated_headers_and_unpaired_counts_are_preserved():
    frame = pd.DataFrame({1:['metadata'],'ColocCountBare':[4.],'A_ColocCountB':[2.]})
    before = frame.copy(deep=True)
    assert utils.add_coloc_percentages(frame) is frame
    pd.testing.assert_frame_equal(frame,before,check_exact=True)


def test_empty_counts_keep_index_and_original_types():
    frame = pd.DataFrame({'A_ColocCountB':pd.Series([],dtype='int64'),
        'A_NonColocCountB':pd.Series([],dtype='int64')},index=pd.Index([],name='subject'))
    before = frame.copy(deep=True)
    assert utils.add_coloc_percentages(frame) is frame
    assert list(frame.columns)==list(before.columns)+['A_ColocCountB%','A_NonColocCountB%']
    assert list(frame.dtypes.astype(str))==['int64','int64','float64','float64']
    pd.testing.assert_frame_equal(frame[list(before.columns)],before,check_exact=True)
