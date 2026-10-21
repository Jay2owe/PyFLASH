from pathlib import Path
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1]

from PyFLASH import utils
import numpy as np
import pytest

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/moving-average-complex-native-before-20261006-v1/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text())['rows']
def decode(values):return np.asarray([math.nan if v=='NaN' else math.inf if v=='Inf' else -math.inf if v=='-Inf' else v for v in values])
def signal(row,dtype=np.complex128):
 array=np.empty(len(row['case']['real']),dtype=dtype)
 array.real=decode(row['case']['real']);array.imag=decode(row['case']['imaginary'])
 return array
def exact_float32(row):
 with np.errstate(all='ignore'):
  narrowed=signal(row,np.complex64);original=signal(row)
 return bool(np.array_equal(narrowed.real,original.real,equal_nan=True) and
  np.array_equal(narrowed.imag,original.imag,equal_nan=True))
CASES=[(row,dtype,carrier) for row in ROWS for dtype in (np.complex64,np.complex128)
 for carrier in ('list','tuple','array') if dtype==np.complex128 or exact_float32(row)]

@pytest.mark.parametrize('row,dtype,carrier',CASES,ids=[row['case']['key']+'.'+np.dtype(dtype).name+'.'+carrier for row,dtype,carrier in CASES])
def test_complete_native_complex_components(row,dtype,carrier):
 assert row['native_same_input']
 array=signal(row,dtype);snapshot=array.copy()
 if carrier=='array':array.flags.writeable=False;values=array
 elif carrier=='list':values=list(array)
 else:values=tuple(array)
 with np.errstate(all='raise'):result=utils.moving_average(values,row['case']['width'])
 assert result.dtype==np.complex128 and result.shape==tuple(row['expected']['shape'])
 np.testing.assert_allclose(result.real,decode(row['expected']['real']),rtol=1e-12,atol=0.,equal_nan=True)
 np.testing.assert_allclose(result.imag,decode(row['expected']['imaginary']),rtol=1e-12,atol=0.,equal_nan=True)
 np.testing.assert_array_equal(array.real,snapshot.real)
 np.testing.assert_array_equal(array.imag,snapshot.imag)

@pytest.mark.parametrize('dtype',[np.complex64,np.complex128])
@pytest.mark.parametrize('width',[-3,0,1,1.5,True])
def test_legacy_noop_keeps_exact_input_object(dtype,width):
 array=np.asarray([1+2j,3-4j],dtype=dtype)
 assert utils.moving_average(array,width) is array

@pytest.mark.parametrize('array',[np.asarray(1+2j),np.asarray([[1+2j,3+4j]]),np.asarray([],dtype=complex)])
def test_unavailable_complex_signal_shapes_refuse(array):
 with pytest.raises(ValueError):utils.moving_average(array,3)

def test_default_width_matches_independent_native_case():
 row=next(row for row in ROWS if row['case']['key']=='complex-mean.ordinary.w7')
 result=utils.moving_average(signal(row))
 np.testing.assert_allclose(result.real,decode(row['expected']['real']),rtol=1e-12,atol=0.)
 np.testing.assert_allclose(result.imag,decode(row['expected']['imaginary']),rtol=1e-12,atol=0.)

def test_numpy_integer_width_preserves_native_envelope():
 row=next(row for row in ROWS if row['case']['key']=='complex-mean.smallest.w4')
 with np.errstate(all='raise'):result=utils.moving_average(signal(row),np.uint64(4))
 np.testing.assert_array_equal(result.real,decode(row['expected']['real']))
 np.testing.assert_array_equal(result.imag,decode(row['expected']['imaginary']))
