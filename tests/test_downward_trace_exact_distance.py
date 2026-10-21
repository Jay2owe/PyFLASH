from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

REFERENCE = (ROOT/'reproducibility/reference-sources/scientific-utilities/downward-trace-extremes-native-20261006-v1/frozen-before.json')
ROWS = json.loads(REFERENCE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',[list,tuple,np.array],ids=['list','tuple','array'])
def test_exact_represented_distance_and_slope_preserve_all_returned_coordinates(row,carrier):
    case=row['case']
    x,y=carrier(case['x']),carrier(case['y'])
    with np.errstate(all='raise'):
        if not row['expected_indices']:
            with pytest.raises(ValueError,match='downward path'):
                utils.trace_downward_nearest(x,y)
        else:
            returned_x,returned_y,indices=utils.trace_downward_nearest(x,y)
            assert indices.tolist()==row['expected_indices']
            np.testing.assert_array_equal(returned_x,row['expected_x'])
            np.testing.assert_array_equal(returned_y,row['expected_y'])
            assert returned_x.dtype==np.asarray(x).dtype
            assert returned_y.dtype==np.asarray(y).dtype
            np.testing.assert_array_equal(np.asarray(x)[indices],returned_x)
            np.testing.assert_array_equal(np.asarray(y)[indices],returned_y)
    np.testing.assert_array_equal(x,case['x'])
    np.testing.assert_array_equal(y,case['y'])


@pytest.mark.parametrize('dtype',['int8','int64','uint64','float32','float64'])
def test_numeric_carrier_type_does_not_change_the_geometric_path(dtype):
    x=np.array([0,3,1],dtype=dtype)
    y=np.array([0,4,1],dtype=dtype)
    a,b,indices=utils.trace_downward_nearest(x,y)
    assert indices.tolist()==[0,2,1]
    assert a.dtype==b.dtype==np.dtype(dtype)


def test_unequal_axis_binary_denominators_share_one_distance_unit():
    x=[0.,.25,.5]
    y=[0.,2.,.125]
    a,b,indices=utils.trace_downward_nearest(x,y)
    assert indices.tolist()==[0,2,1]


@pytest.mark.parametrize('x,y',[(np.array([0+1j,1+2j]),np.array([0.,1.])),
    (np.array([0.,1.]),np.array([0+1j,1+2j])),(np.array(['bad','good']),np.array([0.,1.]))])
def test_nonreal_coordinates_refuse_before_geometric_work(x,y):
    with pytest.raises(ValueError,match='real coordinates'):
        utils.trace_downward_nearest(x,y)
