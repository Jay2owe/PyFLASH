from pathlib import Path
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1]
from PyFLASH import utils
from PyFLASH.config import Config
import numpy as np
import pandas as pd
import pytest

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/conversion-calibration-typed-before-20261006-v1/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text())['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',['array','series'])
def test_native_typed_coordinates_survive_unit_conversion(row,carrier,monkeypatch):
    case=row['case'];values=np.asarray(case['values'],dtype=case['dtype'])
    assert row['numeric_input_witness_exact'] and values.astype(float).tolist()==case['values']
    assert row['expected']==row['native_original_row']['expected'][:3]
    if carrier=='series':
        values=pd.Series(values,index=pd.Index(['a','a','z'],name='row'),name='coordinate')
        values.attrs={'input_dtype':case['dtype']}
    before=values.copy()
    monkeypatch.setattr(Config,'PIXEL_SIZE',case['calibration'])
    owner=utils.convert_microns_to_pixels if case['direction']=='microns-to-pixels' else utils.convert_pixels_to_microns
    options={'pixel_size':case['calibration']} if case['mode']=='explicit-um-per-pixel' else {}
    with np.errstate(all='raise'):
        if row['domain']=='refuse-unrepresentable-output':
            with pytest.raises(ValueError,match='floating-point range'):owner(values,**options)
        else:
            result=owner(values,**options)
            assert result.dtype==np.float64 and result.shape==values.shape
            assert all(a==b or math.isclose(float(a),b,rel_tol=1e-12,abs_tol=0.) for a,b in zip(result,row['expected']))
            if carrier=='series':
                assert result.index.equals(values.index) and result.name==values.name and result.attrs==values.attrs
    np.testing.assert_array_equal(np.asarray(values),np.asarray(before))
