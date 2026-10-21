"""Complete declared custom tracing outputs, exact metrics and input ownership."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-trace-policy'
MANIFEST_SHA256='2e17b2a613d7115687d790308659901904434b06f661b30a94bc19bb3c83a9c8'
CAPABILITY='PyFLASH.utils.trace_downward_nearest'
CAPABILITIES=frozenset({CAPABILITY})
CAPABILITY_PREFIXES={CAPABILITY:('whole-trace-policy.',)}
COMPLETE_CAPABILITIES=CAPABILITIES

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import trace_dense_reference as dense,trace_carrier_reference as carriers
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    for module,name in [(dense,'dense/original-1-freeze_dense_downward_trace_20261008.py'),
                        (carriers,'carriers/original-1-freeze_trace_carrier_and_domain_profiles_20261008_v2.py')]:
        assert Path(module.__file__).read_bytes()==(ARCHIVE/name).read_bytes()
    for group,count in [('dense',180),('carriers',111)]:
        before=read(group+'/before.json')
        assert before['actual_calls']==count and not before['failed'] and not before['source_changes']
    assert read('dense/before.json')['dense_branch_calls']==120
    assert read('carrier-first/run.json')['actual_calls']==0
    assert not read('carrier-first/run.json')['passed']
    assert [dense.query(case) for case in dense.cases()]==read('dense/native/dense-downward-trace-queries.json')
    assert [carriers.encode(case) for case in carriers.cases()]==[row['case'] for row in read('carriers/before.json')['rows']]

def cases():
    return [dict(key='whole-trace-policy.'+group+'.'+row['case']['key']+('.'+row['carrier'] if group=='dense' else ''),
        group=group,row=copy.deepcopy(row)) for group in ('dense','carriers') for row in read(group+'/before.json')['rows']]

def required_keys(capability):
    if capability!=CAPABILITY:return set()
    from reproducibility.scientific_utility_contract import required_keys as previous_keys
    return {item['key'] for item in cases()}|previous_keys(capability)

def production(item,observation=None,*,qualify_reference=False):
    import numpy as np
    from PyFLASH import utils
    from reproducibility import trace_carrier_reference as reference
    before=next(row for row in read(item['group']+'/before.json')['rows'] if row['case']==item['row']['case']
                and (item['group']!='dense' or row['carrier']==item['row']['carrier']))
    assert item['row']==before
    if item['group']=='dense':
        points=np.asarray(before['case']['points'],dtype=float if before['carrier']=='float64' else np.int64)
        x,y=points[:,0].copy(),points[:,1].copy()
        if before['carrier']=='list':x,y=x.tolist(),y.tolist()
        if before['carrier']=='tuple':x,y=tuple(x.tolist()),tuple(y.tolist())
        if before['carrier']=='readonly':x.flags.writeable=y.flags.writeable=False
        expected=dict(selected_x=[r[0] for r in before['expected']],selected_y=[r[1] for r in before['expected']],
                      indices=[int(r[2]) for r in before['expected']],x_dtype=str(np.asarray(x).dtype),y_dtype=str(np.asarray(y).dtype))
    else:
        case=next(case for case in reference.cases() if case['key']==before['case']['key'])
        if qualify_reference:assert reference.encode(reference.prediction(case))==before['expected']
        x,y=reference.inputs(case)
        expected={k:v for k,v in before['expected'].items() if k!='native_distance_comparisons'}
    def snapshot(values):
        array=np.asarray(values)
        return dict(values=reference.encode(np.array(values,dtype=object).tolist()),dtype=str(array.dtype),shape=list(array.shape),
           writable=values.flags.writeable if isinstance(values,np.ndarray) else None,
           bytes=values.tobytes().hex() if isinstance(values,np.ndarray) and values.dtype.kind!='O' else None)
    original_x,original_y=snapshot(x),snapshot(y)
    result=None;refusal=None
    try:result=utils.trace_downward_nearest(x,y)
    except Exception as error:refusal=error
    assert snapshot(x)==original_x and snapshot(y)==original_y
    if 'error' in expected:
        assert refusal is not None and type(refusal).__name__==expected['error']
        assert expected['message_contains'] in str(refusal)
        actual=dict(error=type(refusal).__name__,message_contains=expected['message_contains'])
        if observation is not None:observation['refusal_message']=str(refusal)
    else:
        assert refusal is None,str(refusal)
        assert isinstance(result,tuple) and len(result)==3
        a,b,indices=result
        assert all(isinstance(v,np.ndarray) and v.ndim==1 for v in result)
        assert indices.dtype==np.dtype(int)
        expected=dict(expected,selected_x=np.asarray(expected['selected_x'],dtype=expected['x_dtype']).tolist(),
                               selected_y=np.asarray(expected['selected_y'],dtype=expected['y_dtype']).tolist())
        actual=dict(selected_x=reference.encode(a.tolist()),selected_y=reference.encode(b.tolist()),indices=indices.tolist(),
                    x_dtype=str(a.dtype),y_dtype=str(b.dtype))
        expected=reference.encode(expected)
        assert actual==expected
        np.testing.assert_array_equal(np.array(x,dtype=object)[indices],np.array(a,dtype=object))
        np.testing.assert_array_equal(np.array(y,dtype=object)[indices],np.array(b,dtype=object))
        a[0]=1 if a[0]==0 else 0;b[0]=1 if b[0]==0 else 0
        assert snapshot(x)==original_x and snapshot(y)==original_y
    if observation is not None:observation.update(actual=actual,expected=expected,input_and_return_ownership_preserved=True)
    return actual

def validate(output):
    from reproducibility import trace_dense_reference as dense
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    native=execute_queries([dense.query(case) for case in dense.cases()],Path(output)/'native',name='dense-downward-trace')
    assert native['rows']==read('dense/native/dense-downward-trace-results.json')['rows']
    return replay(cases(),lambda item,observed,path:production(item,observed,qualify_reference=True),output,
        reference='Native R exhaustive trajectories and native SymPy exact point distances under the declared custom selection policy, plus literal carrier/refusal/copy ownership; no independently published whole-trace-method vote',
        family='custom-whole-downward-trace-policy',shape='complete-original-coordinate-arrays-original-indices-dtypes-input-refusals-and-return-copy-ownership')
