"""Whole-cleaner typed-coordinate, density-domain and dimensional obligations."""
from pathlib import Path
from functools import lru_cache
from types import SimpleNamespace
import contextlib,copy,hashlib,io,json,warnings
ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-marker-cleaning-edges'
MANIFEST_SHA256='6b35ceb51f585ba3bedcddb1704549b385a7e972935de8c927fd756f329d274b'
TYPED='whole-marker-cleaning-typed-edges-original-20261008-v2'
DIMENSIONAL='whole-marker-cleaning-dimensional-routes-original-20261008-v1'
CAPABILITIES=frozenset('PyFLASH.markers.'+owner+'.clean_df' for owner in ('cellMarker','objectMarker'))
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={owner:('whole-marker-cleaning-edges.'+owner.split('.')[-2]+'.',) for owner in CAPABILITIES}

@lru_cache(maxsize=24)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

@lru_cache(maxsize=8)
def _catalogue(archive):
    result={}
    for kind,folder in (('typed',TYPED),('dimensional',DIMENSIONAL)):
        for item in _read(archive/folder/'predictions.json'):
            case=item['input']['case'] if kind=='typed' else item['case']
            key='whole-marker-cleaning-edges.'+case['key'];assert key not in result
            result[key]=dict(key=key,kind=kind,input=item,expected=item['expected'])
    return result

def cases():return copy.deepcopy(list(_catalogue(ARCHIVE.resolve()).values()))

def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    owner=capability.split('.')[-2]
    return {row['key'] for row in _catalogue(ARCHIVE.resolve()).values() if (row['input']['input']['case'] if row['kind']=='typed' else row['input']['case'])['owner']==owner}

def _batches(kind,items):
    if kind=='typed':
        for offset in range(0,len(items),100):yield str(offset)+'/typed-whole-cleaning',items[offset:offset+100]
    else:yield 'dimensional-whole-cleaning',items

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_cleaning_typed_reference as typed,marker_cleaning_dimensional_reference as dim
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    for kind,folder,count,failures,ref in (('typed',TYPED,296,48,typed),('dimensional',DIMENSIONAL,48,0,dim)):
        assert Path(ref.__file__).read_bytes()==(ARCHIVE/('qualified-'+kind+'-reference.py')).read_bytes()
        receipt=read(folder+'/run.json');items=read(folder+'/predictions.json')
        assert receipt['status']=='finished' and receipt['actual_calls']==count and receipt['failed']==failures and receipt['passed']==(failures==0) and not receipt['source_changes']
        assert hashlib.sha256((ARCHIVE/folder/'predictions.json').read_bytes()).hexdigest()==receipt['predictions_sha256']
        observed=[json.loads(line) for line in (ARCHIVE/folder/'paired.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(observed)==count and sum(not row['passed'] for row in observed)==failures
        for actual,item in zip(observed,items,strict=True):
            case=item['input']['case'] if kind=='typed' else item['case']
            assert (actual['key'] if kind=='typed' else actual['case']['key'])==case['key'] and actual['expected']==item['expected']
        assert [row['input'] if kind=='typed' else row['case'] for row in items]==ref.cases()
        for stem,batch in _batches(kind,items):
            queries=[ref.query(row['input'] if kind=='typed' else row['case']) for row in batch]
            prefix=folder+'/native/'+stem
            assert queries==read(prefix+'-queries.json')
            answer=read(prefix+'-results.json');execution=read(prefix+'-execution.json')
            assert execution['status']=='completed' and execution['returncode']==0 and execution['timeout_seconds']==180
            assert answer['webR']=='0.6.0' and answer['wasm_sha256']=='5df459fb222d332e358cf08e4019c0e114398579ed8c62242bfcceeda81222ba'
            for item,query,row in zip(batch,queries,answer['rows'],strict=True):
                assert row['status']=='executed' and all(row[name]==value for name,value in query.items())
                assert ref.expected(item['input'] if kind=='typed' else item['case'],row['values'])==item['expected']
    qualification=read('whole-marker-cleaning-legacy-domain-private-20261008-v2/run.json')
    assert qualification['status']=='finished' and qualification['passed'] and qualification['actual_calls']==2728 and qualification['failed']==0 and not qualification['source_changes']
    assert {key:value['actual_calls'] for key,value in qualification['groups'].items()}=={'typed-domain':296,'dimensional-routes':48,'whole-original':1952,'whole-options':396,'native-calibration':36}

def production(row,observation=None):
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.config import Config
    from reproducibility import marker_cleaning_reference as original,marker_cleaning_typed_reference as typed,marker_cleaning_dimensional_reference as dim
    from reproducibility.marker_cleaning_whole_contract import equal
    assert row==_catalogue(ARCHIVE.resolve())[row['key']]
    is_typed=row['kind']=='typed';item=row['input'];control=item['input'] if is_typed else item['case'];case=control['case'] if is_typed else control
    frame,labels,areas=typed.inputs(control) if is_typed else dim.inputs(case)
    labels_before=None if labels is None else labels.copy(deep=True);areas_before={name:value.df.copy(deep=True) for name,value in areas.items()}
    exp=SimpleNamespace(data=areas)
    if labels is not None:exp.condition_labels=labels
    obj=object.__new__(getattr(markers,case['owner']));obj.name=case['name'];obj.df=frame;obj.experiment=exp;obj.color='grey';obj.threshold=30;sentinel=object();obj._unrelated=sentinel
    old_density=Config.PIXEL_SIZE;old_threshold=Config.THRESHOLD
    try:
        if is_typed and control['kind']=='density':Config.PIXEL_SIZE=typed.DENSITIES[control['density']]
        failure=None;returned=None
        with contextlib.redirect_stdout(io.StringIO()),warnings.catch_warnings():
            warnings.simplefilter('ignore')
            try:returned=obj.clean_df()
            except (TypeError,ValueError) as exc:failure=type(exc).__name__
        actual=dict(table=original.categorical_table(obj.df),raw_after=original.categorical_table(frame),same_raw_owner=obj.df is frame)
        if is_typed:actual=typed.encode(actual)
        if observation is not None:observation.update(actual=actual,expected=row['expected'],error_type=failure,returned_own=returned is obj.df)
        if is_typed and typed.is_refused(control):assert failure==('TypeError' if control['kind']=='density' and control['density']=='text' else 'ValueError') and returned is None
        else:assert failure is None and returned is obj.df
        assert equal(actual,row['expected']) and obj._unrelated is sentinel and obj.experiment is exp and obj.color=='grey' and obj.threshold==30
        if labels is not None:pd.testing.assert_frame_equal(labels,labels_before,check_exact=True)
        for name,value in areas.items():pd.testing.assert_frame_equal(value.df,areas_before[name],check_exact=True)
        return actual
    finally:Config.PIXEL_SIZE=old_density;Config.THRESHOLD=old_threshold

def validate(output):
    from reproducibility import marker_cleaning_typed_reference as typed,marker_cleaning_dimensional_reference as dim
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity();output=Path(output)
    for kind,folder,ref in (('typed',TYPED,typed),('dimensional',DIMENSIONAL,dim)):
        for stem,batch in _batches(kind,read(folder+'/predictions.json')):
            queries=[ref.query(row['input'] if kind=='typed' else row['case']) for row in batch]
            answers=execute_queries(queries,output/'native-edges'/kind/Path(stem).parent,name=Path(stem).name,timeout=180)
            for item,row in zip(batch,answers['rows'],strict=True):assert ref.expected(item['input'] if kind=='typed' else item['case'],row['values'])==item['expected']
    return replay(cases(),lambda item,observed,path:production(item,observed),output,reference='Native R complete typed-coordinate and dimensional tables; literal invalid-density and nonreal-coordinate refusal, ownership and return controls; no additional statistical-method vote',family='functional-whole-marker-cleaning-edges',shape='all-final-and-partial-table-fields-complex-components-storage-index-attributes-return-and-caller-ownership',rtol=1e-12,atol=0.)
