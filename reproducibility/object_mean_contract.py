"""Numeric object carriers on original native full-window answers."""
from pathlib import Path
import json
import math
ARCHIVE=Path(__file__).with_name('reference-sources')/'object-window-means'
MANIFEST_SHA256='d62e226a92d61575fbaf86e0abc3fee9f21253e0f9f4a4235b0289fe80943572'
ORIGINAL='moving-average-object-carrier-before-20261007-v1'
NATIVE='moving-average-object-native-sympy-indexed-20261007-v1'
CAPABILITY_PREFIXES={'PyFLASH.utils.moving_average':('object-mean.',)}
COMPLETE_CAPABILITIES=frozenset()
def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import scientific_utility_contract as Original
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256);Original.check_identity()
def cases():
    original=json.loads((ARCHIVE/ORIGINAL/'run.json').read_text(encoding='utf-8'))['rows']
    native=json.loads((ARCHIVE/NATIVE/'run.json').read_text(encoding='utf-8'))['rows']
    rows=[]
    for before,accepted in zip(original,native):
        assert before['key']==accepted['key'] and before['expected']==accepted['actual'] and accepted['outcome']=='agree'
        rows.append(dict(key='object-mean.'+before['case']['key'],case=before['case'],kind=before['kind'],expected=before['expected']))
    assert len(rows)==len(original)==len(native)==100
    return rows
def decode(value):
    return math.nan if value in (None,'NaN') else math.inf if value=='Inf' else -math.inf if value=='-Inf' else value
def inputs(item):
    import numpy as np
    case=item['case']
    if item['kind']=='mean':return np.asarray([decode(v) for v in case['values']],dtype=object)
    values=np.empty(len(case['real']),dtype=object)
    for i,(real,imaginary) in enumerate(zip(case['real'],case['imaginary'])):values[i]=complex(decode(real),decode(imaginary))
    return values
def check_result(item,actual):
    import numpy as np
    assert actual['dtype']=='object' and actual['shape']==item['expected']['shape'] and actual['caller_unchanged']
    for key in ('values','real','imaginary'):
        if key in item['expected']:
            np.testing.assert_allclose([decode(v) for v in actual[key]],[decode(v) for v in item['expected'][key]],rtol=1e-12,atol=0,equal_nan=True)
def production(item,values=None):
    from PyFLASH import utils
    from reproducibility.scientific_utility_contract import encode
    import numpy as np
    import warnings
    values=inputs(item) if values is None else values
    numeric=np.asarray(values,dtype=complex if item['kind']=='mean-complex' else float)
    snapshot=numeric.copy()
    with warnings.catch_warnings():
        warnings.simplefilter('error');returned=utils.moving_average(values,item['case']['width'])
    result=np.asarray(returned,dtype=complex if item['kind']=='mean-complex' else float)
    after=np.asarray(values,dtype=numeric.dtype)
    np.testing.assert_array_equal(after.real,snapshot.real)
    if item['kind']=='mean-complex':np.testing.assert_array_equal(after.imag,snapshot.imag)
    actual=dict(dtype=str(returned.dtype),shape=list(returned.shape),caller_unchanged=True)
    if item['kind']=='mean-complex':actual.update(real=encode(result.real),imaginary=encode(result.imag))
    else:actual['values']=encode(result)
    check_result(item,actual);return actual
def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for item in cases():
        try:actual=production(item);agree=True
        except Exception as exc:actual=dict(error_type=type(exc).__name__,error=str(exc));agree=False
        scope='Supported real/complex numeric object cells, original complete native window arrays, missingness, shape/dtype and ownership. Frozen authenticated references reused; no new native engine execution or whole downstream method claim.'
        rows.append(comparison(item['key'],'Original native R window means + qualified native SymPy expectations','object-array-numeric-window-and-ownership',actual,item,agree,True,scope,1e-12,0))
        paired.append(dict(item=item,actual=actual,agree=agree))
    write_json(Path(output)/'object-window-paired.json',dict(rows=paired,scope='Selected object carrier branch; extended precision/custom object classes and whole procedures remain open.'))
    return rows
