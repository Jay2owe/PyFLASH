from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

REFERENCE=(ROOT/'reproducibility/reference-sources/scientific-utilities/moving-average-window-means-before-20261006-v1/frozen-before.json')
ROWS=json.loads(REFERENCE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',[list,tuple,np.array],ids=['list','tuple','array'])
def test_complete_arrays_against_unchanged_native_window_means(row,carrier):
    case=row['case']
    assert row['native_same_input'] and row['native_r_exact_agreement']
    data=carrier([np.nan if v is None else v for v in case['values']])
    expected=np.array([np.nan if v is None else v for v in row['native_r_colMeans']['values']])
    before=np.asarray(data).copy()
    with np.errstate(all='raise'):
        actual=utils.moving_average(data,w=case['width'])
    assert isinstance(actual,np.ndarray) and actual.dtype==np.dtype('float64')
    # Exact protects zero cancellation and nonzero subnormal means.
    np.testing.assert_array_equal(actual,expected)
    assert len(actual)==len(data)+2*(case['width']//2)-case['width']+1
    np.testing.assert_array_equal(data,before)


@pytest.mark.parametrize('width',[0,1,-3,1.5,True])
def test_legacy_no_op_preserves_dtype_and_array_identity(width):
    a=np.array([1,2,3],dtype='int16')
    assert utils.moving_average(a,w=width) is a


@pytest.mark.parametrize('dtype',['int8','uint64','float32','float64'])
def test_integer_and_float_types_preserve_constant_values(dtype):
    data=np.array([7,7,7],dtype=dtype)
    np.testing.assert_array_equal(utils.moving_average(data,w=7),[7.,7.,7.])


@pytest.mark.parametrize('width',[np.int32(3),np.int64(7),np.uint64(10)])
def test_numpy_integer_widths_preserve_tiny_values(width):
    small=float.fromhex('0x0.0000000000001p-1022')
    actual=utils.moving_average([small,small,small],w=width)
    np.testing.assert_array_equal(actual,[small]*len(actual))


@pytest.mark.parametrize('values,expected',[
    ([1.,np.inf,3.],[np.inf,np.inf,np.inf]),
    ([1.,-np.inf,3.],[-np.inf,-np.inf,-np.inf]),
    ([np.inf,-np.inf,3.],[np.nan,np.nan,-np.inf]),
    ([np.nan,2.,3.],[np.nan,np.nan,8/3]),
])
def test_infinite_and_missing_windows_keep_their_own_states(values,expected):
    with np.errstate(all='raise'):
        np.testing.assert_array_equal(utils.moving_average(values,w=3),expected)


def test_complex_carrier_retains_the_existing_convolution_contract():
    data=np.array([1+2j,3-4j,5+6j])
    np.testing.assert_array_equal(utils.moving_average(data,w=4),
        np.convolve(np.pad(data,(2,2),mode='edge'),np.ones(4)/4,mode='valid'))
