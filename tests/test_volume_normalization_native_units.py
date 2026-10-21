from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
from PyFLASH.config import Config
import numpy as np
import pandas as pd
import pytest

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/volume-normalization-native-before-20261006-v1/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
def test_complete_native_unit_conversion_and_original_area_ownership(row,monkeypatch):
    case=row['case']
    original=row['original_input']
    frame=pd.DataFrame(original,index=pd.Index(row['index'],name=row['index_name']))
    frame.attrs=row['attrs']
    before=frame.copy(deep=True)
    expected=before.copy(deep=True)
    for name,values in row['expected'].items():
        expected[name]=[np.nan if value is None else value for value in values]
    monkeypatch.setattr(Config,'SECTION_THICKNESS_UM',case['thickness'])
    with np.errstate(all='raise'):
        assert utils.adjust_for_volumemm(frame,case['columns'],'Area') is frame
    pd.testing.assert_frame_equal(frame,expected,rtol=1e-12,atol=0.)
    unchanged=[name for name in frame if name not in case['columns']]
    pd.testing.assert_frame_equal(frame[unchanged],before[unchanged],check_exact=True)
    assert frame.attrs==before.attrs


@pytest.mark.parametrize('kind',['missing-later','malformed-later','zero-area','negative-area','infinite-area',
    'zero-thickness','missing-thickness','infinite-thickness','infinite-measurement','overflow-output','duplicate'])
def test_invalid_request_leaves_all_original_measurements_untouched(kind,monkeypatch):
    frame=pd.DataFrame({'Area':[1000.],'Count':[2.],'Intensity':[10.]})
    columns=['Count','Intensity']
    if kind=='missing-later':columns.append('Missing')
    elif kind=='malformed-later':frame['Intensity']='unavailable'
    elif kind.endswith('-area'):frame['Area']={'zero-area':0.,'negative-area':-1.,'infinite-area':np.inf}[kind]
    elif kind.endswith('-thickness'):monkeypatch.setattr(Config,'SECTION_THICKNESS_UM',
        {'zero-thickness':0.,'missing-thickness':np.nan,'infinite-thickness':np.inf}[kind])
    elif kind=='infinite-measurement':frame['Intensity']=np.inf
    elif kind=='overflow-output':frame['Area']=1e-300;frame['Intensity']=1e308
    else:frame=pd.DataFrame([[1.,2.,3.]],columns=['Area','Count','Count'])
    before=frame.copy(deep=True)
    expected_error=KeyError if kind=='missing-later' else TypeError if kind=='malformed-later' else ValueError
    with pytest.raises(expected_error):utils.adjust_for_volumemm(frame,columns,'Area')
    pd.testing.assert_frame_equal(frame,before,check_exact=True)


def test_no_requested_columns_preserves_an_empty_table_without_requiring_an_area():
    frame=pd.DataFrame({'Subject':[]})
    assert utils.adjust_for_volumemm(frame,[],'absent') is frame


def test_single_string_column_uses_original_area_and_preserves_other_values(monkeypatch):
    monkeypatch.setattr(Config,'SECTION_THICKNESS_UM',10.)
    frame=pd.DataFrame({'Area':[1000.],'Count':[2.],'Intensity':[10.]})
    utils.adjust_for_volumemm(frame,'Count','Area')
    assert frame.to_dict('list')=={'Area':[1000.],'Count':[20000.],'Intensity':[10.]}
