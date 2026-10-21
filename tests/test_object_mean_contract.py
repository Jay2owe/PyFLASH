"""Original independently generated mean arrays guard numeric object support."""
from copy import deepcopy
import shutil
import pytest
import numpy as np
from reproducibility import object_mean_contract as M
from PyFLASH import utils
@pytest.fixture(scope='module',autouse=True)
def authenticate_native_before_calls():M.check_identity()
@pytest.mark.parametrize('item',M.cases(),ids=lambda item:item['key'])
def test_original_complete_native_object_window(item):M.production(item)
@pytest.mark.parametrize('name',['source-manifest.json',M.ORIGINAL+'/run.json'])
def test_changed_original_evidence_refuses(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(M.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(M,'ARCHIVE',archive)
    with pytest.raises(ValueError):M.check_identity()
@pytest.mark.parametrize('damage',['lost-small-value','wrong-dtype','missing-value'])
def test_wrong_scientific_mean_or_carrier_cannot_pass(damage):
    item=next(row for row in M.cases() if row['case']['key']=='moving-average.subnormal-constant.w3')
    actual=deepcopy(M.production(item))
    if damage=='lost-small-value':actual['values'][0]=0.
    elif damage=='wrong-dtype':actual['dtype']='float64'
    else:actual['values'][0]='NaN'
    with pytest.raises(AssertionError):M.check_result(item,actual)
@pytest.mark.parametrize('scalar',[int,np.int64,np.float32,np.float64])
def test_same_original_operands_as_readonly_numeric_scalar_objects(scalar):
    item=next(row for row in M.cases() if row['case']['key']=='moving-average.signed.w3')
    values=np.asarray([scalar(v) for v in item['case']['values']],dtype=object);values.flags.writeable=False
    M.production(item,values)
@pytest.mark.parametrize('scalar',[np.complex64,np.complex128])
def test_same_original_complex_operands_as_readonly_scalar_objects(scalar):
    item=next(row for row in M.cases() if row['case']['key']=='complex-mean.ordinary.w3')
    values=np.asarray([scalar(v) for v in M.inputs(item)],dtype=object);values.flags.writeable=False
    M.production(item,values)
@pytest.mark.parametrize('width',[-3,0,1,1.5,True])
def test_noop_object_input_retains_identity(width):
    values=np.asarray([1.,2.,3.],dtype=object);assert utils.moving_average(values,width) is values
