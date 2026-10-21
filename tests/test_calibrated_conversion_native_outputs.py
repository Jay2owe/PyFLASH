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

FIXTURE=(ROOT/'reproducibility/reference-sources/scientific-utilities/conversion-calibration-native-before-20261006-v2/frozen-before.json')
ROWS=json.loads(FIXTURE.read_text())['rows']
SCALARS=[(row,index) for row in ROWS for index in range(len(row['case']['values']))]


def request(row,monkeypatch):
    case=row['case'];monkeypatch.setattr(Config,'PIXEL_SIZE',case['calibration'])
    function=utils.convert_microns_to_pixels if case['direction']=='microns-to-pixels' else utils.convert_pixels_to_microns
    options={'pixel_size':case['calibration']} if case['mode']=='explicit-um-per-pixel' else {}
    return function,options


@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('carrier',['array','readonly-array','series','frame'])
def test_complete_calibrated_arrays_and_owned_containers(row,carrier,monkeypatch):
    function,options=request(row,monkeypatch);case=row['case']
    values=np.asarray(case['values'],dtype=np.int64 if case.get('carrier')=='int64' else float)
    if carrier=='readonly-array':values.flags.writeable=False
    if carrier=='series':
        values=pd.Series(values,index=pd.Index([4]*len(values),name='row'),name='coordinate')
        values.attrs={'source':'immutable-calibration'}
    elif carrier=='frame':
        values=pd.DataFrame({'coordinate':values},index=pd.Index([4]*len(values),name='row'))
        values.attrs={'source':'immutable-calibration'}
    before=values.copy()
    with np.errstate(all='raise'):
        if row['domain']=='refuse-unrepresentable-output':
            with pytest.raises(ValueError,match='floating-point range'):function(values,**options)
        else:
            actual=function(values,**options)
            array=np.asarray(actual).reshape(-1)
            assert array.dtype==np.float64
            assert len(array)==len(row['expected'])
            for a,b in zip(array,row['expected']):assert a==b or math.isclose(float(a),b,rel_tol=1e-12,abs_tol=0.)
            if carrier in ('series','frame'):
                assert isinstance(actual,type(values)) and actual.index.equals(values.index) and actual.attrs==values.attrs
                if carrier=='series':assert actual.name==values.name
                else:assert actual.columns.equals(values.columns)
    np.testing.assert_array_equal(np.asarray(values),np.asarray(before))


@pytest.mark.parametrize('row,index',SCALARS,ids=[row['case']['key']+f'.scalar{i}' for row,i in SCALARS])
def test_each_native_coordinate_and_unrepresentable_boundary(row,index,monkeypatch):
    function,options=request(row,monkeypatch);value=row['case']['values'][index];expected=row['expected'][index]
    with np.errstate(all='raise'):
        if expected in ('Inf','-Inf'):
            with pytest.raises(ValueError,match='floating-point range'):function(value,**options)
        else:
            result=function(value,**options)
            assert isinstance(result,float)
            assert result==expected or math.isclose(result,expected,rel_tol=1e-12,abs_tol=0.)


@pytest.mark.parametrize('function',[utils.convert_microns_to_pixels,utils.convert_pixels_to_microns])
@pytest.mark.parametrize('calibration',[0.,-1.,np.nan,np.inf,-np.inf])
@pytest.mark.parametrize('default',[True,False])
def test_invalid_calibration_refuses_before_conversion(function,calibration,default,monkeypatch):
    monkeypatch.setattr(Config,'PIXEL_SIZE',calibration)
    with pytest.raises(ValueError):function(np.array([1.,2.]),**({} if default else {'pixel_size':calibration}))


@pytest.mark.parametrize('function',[utils.convert_microns_to_pixels,utils.convert_pixels_to_microns])
def test_missing_coordinates_preserve_nullable_labels(function):
    frame=pd.Series([1,None,3],dtype='Int64',index=['a','a','z'],name='coordinate')
    result=function(frame,pixel_size=2.)
    assert result.index.equals(frame.index) and result.name==frame.name and np.isnan(result.iloc[1])
    assert np.isnan(function(np.nan,pixel_size=2.))
    assert function(np.empty((0,2)),pixel_size=2.).shape==(0,2)


@pytest.mark.parametrize('function',[utils.convert_microns_to_pixels,utils.convert_pixels_to_microns])
@pytest.mark.parametrize('value',[np.inf,-np.inf])
def test_infinite_coordinate_refuses(function,value):
    with pytest.raises(ValueError):function(value,pixel_size=2.)
