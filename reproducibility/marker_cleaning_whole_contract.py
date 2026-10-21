"""Complete raw-marker tables and caller ownership, with native R operands.

The numeric reference is native R; ImageJ's independently retained coordinate
conversions remain separate required controls. This functional composition does
not constitute an additional independent statistical implementation.
"""
from pathlib import Path
from functools import lru_cache
import copy,hashlib,json,math

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-marker-cleaning'
MANIFEST_SHA256='0513838cc4d6f5e8b1d41aad87e76eb07b6e3296c847a8b8da1f3f17fcc5204a'
ORIGINAL='whole-marker-cleaning-original-20261008-v3'
QUALIFIED='whole-marker-cleaning-metadata-reference-20261008-v1'
INSTALLED='installed-cleaning-and-image-controls-20261008-v1'
CAPABILITIES=frozenset('PyFLASH.markers.'+name+'.clean_df' for name in ('Antibody','cellMarker','objectMarker'))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('whole-marker-cleaning.'+name.split('.')[-2]+'.',) for name in CAPABILITIES}

@lru_cache(maxsize=24)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def equal(a,b):
    if isinstance(b,dict):return isinstance(a,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in b)
    if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(b,bool):return isinstance(a,bool) and a==b
    if isinstance(b,(int,float)):return isinstance(a,(int,float)) and (a==b or math.isclose(a,b,rel_tol=1e-12,abs_tol=0.))
    return a==b

def native_batches():
    original=read(ORIGINAL+'/run.json')
    reused={item['offset'] for item in original['reused_batches']}
    fresh={item['offset'] for item in original['fresh_batches']}
    assert reused.isdisjoint(fresh) and reused|fresh=={str(i) for i in range(0,1952,100)}
    for offset in range(0,1952,100):
        name='whole-marker-cleaning-original-20261008-v2' if str(offset) in reused else ORIGINAL
        folder=f'{name}/native/{offset}/whole-marker-cleaning'
        yield offset,folder

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_cleaning_reference as ref,marker_calibration_contract
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    marker_calibration_contract.check_identity()
    assert Path(ref.__file__).read_bytes()==(ARCHIVE/'qualified-marker-cleaning-reference.py').read_bytes()
    original=read(ORIGINAL+'/run.json')
    assert not original['passed'] and original['actual_calls']==1952 and original['failed']==968 and not original['source_changes']
    unqualified=read('whole-marker-cleaning-private-qualified-20261008-v1/run.json')
    assert not unqualified['passed']
    candidate=read('whole-marker-cleaning-private-qualified-20261008-v2/run.json')
    assert candidate['passed'] and not candidate['source_changes']
    installed=read(INSTALLED+'/installed-replay-only.json')
    assert installed['passed'] and installed['actual_calls']==1952 and installed['failed']==0 and not installed['source_changes']
    combined=read(INSTALLED+'/run.json')
    assert not combined['passed'] and 'TimeoutExpired' in combined['error']
    paired_path=ARCHIVE/INSTALLED/'paired.jsonl'
    assert hashlib.sha256(paired_path.read_bytes()).hexdigest()==installed['paired_sha256']
    assert all(json.loads(line)['passed'] for line in paired_path.read_text(encoding='utf-8').splitlines())
    metadata=read(QUALIFIED+'/run.json')
    assert metadata['passed']
    original_rows=read(ORIGINAL+'/predictions.json');qualified=read(QUALIFIED+'/predictions.json')
    assert [item['case'] for item in qualified]==list(ref.cases()) and len(qualified)==1952
    amended=0
    for old,new in zip(original_rows,qualified,strict=True):
        restored=copy.deepcopy(new);restored['expected']['table']['attrs']=old['expected']['table']['attrs'];assert restored==old
        amended+=old!=new
    assert amended==320
    for offset,folder in native_batches():
        items=qualified[offset:offset+100]
        queries=read(folder+'-queries.json');result=read(folder+'-results.json');receipt=read(folder+'-execution.json')
        assert queries==[ref.query(item['case']) for item in items]
        assert receipt['status']=='completed' and receipt['returncode']==0 and receipt['timeout_seconds']==180
        assert result['webR']=='0.6.0' and result['wasm_sha256']=='5df459fb222d332e358cf08e4019c0e114398579ed8c62242bfcceeda81222ba'
        assert len(result['rows'])==len(items)
        for item,query,answer in zip(items,queries,result['rows'],strict=True):
            assert answer['status']=='executed' and all(answer[key]==value for key,value in query.items())
            assert ref.expected(item['case'],answer['values'])==item['expected']

def cases():
    return [dict(key='whole-marker-cleaning.'+item['case']['key'],case=copy.deepcopy(item['case']),expected=copy.deepcopy(item['expected'])) for item in read(QUALIFIED+'/predictions.json')]

def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    owner=capability.split('.')[-2]
    from reproducibility import marker_cleaning_options_contract as options,marker_cleaning_edges_contract as edges,marker_calibration_contract as calibration
    base={item['key'] for item in cases() if item['case']['owner']==owner}
    native={item['key'] for item in calibration.cases() if item['mode']=={'cellMarker':'cell','objectMarker':'object'}.get(owner)}
    return base|options.required_keys(capability)|edges.required_keys(capability)|native

@lru_cache(maxsize=4)
def _index(path):return {item['case']['key']:item for item in _read(path)}

def production(item,observation=None):
    from reproducibility import marker_cleaning_reference as ref
    original=_index((ARCHIVE/QUALIFIED/'predictions.json').resolve())[item['case']['key']]
    assert item['case']==original['case'] and item['expected']==original['expected']
    actual=ref.production(item['case'],item['expected'])
    if observation is not None:observation.update(actual=actual['actual'],expected=item['expected'],error=actual['error'],returned_own=actual['returned_own'])
    assert actual['error'] is None and actual['returned_own'] and equal(actual['actual'],item['expected']),actual['error']
    return actual['actual']

def validate(output):
    from reproducibility.table_family_validation import replay
    from reproducibility.reference_runtime import execute_queries
    from reproducibility import marker_cleaning_reference as ref
    check_identity();output=Path(output)
    items=cases()
    for offset,folder in native_batches():
        batch=items[offset:offset+100]
        result=execute_queries([ref.query(item['case']) for item in batch],output/'native'/str(offset),name='whole-marker-cleaning',timeout=180)
        original=read(folder+'-results.json')
        for key in ('webR','wasm_sha256'):assert result[key]==original[key]
        assert len(result['rows'])==len(batch)
        for item,answer in zip(batch,result['rows'],strict=True):assert ref.expected(item['case'],answer['values'])==item['expected']
    return replay(items,lambda item,observed,path:production(item,observed),output,reference='Native R full final and input tables, separately qualified pandas empty-merge metadata, and retained original/qualified/installed outcomes; functional cleaning composition only',family='functional-whole-marker-cleaning',shape='all-columns-values-dtypes-index-attributes-raw-input-and-return-ownership',rtol=1e-12,atol=0.)
