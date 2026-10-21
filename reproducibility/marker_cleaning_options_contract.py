"""Whole-cleaner configuration and full partial-table refusal obligations."""
from pathlib import Path
from functools import lru_cache
from types import SimpleNamespace
import contextlib,copy,hashlib,io,json,warnings
ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-marker-cleaning-options'
MANIFEST_SHA256='6c869f5581f18267fd2103cff7fb7a089003cd374922db86f0001146a67cbf1b'
CONFIGURED='whole-marker-cleaning-configurations-original-20261008-v1'
REFUSED='whole-marker-cleaning-refusals-original-20261008-v1'
CAPABILITIES=frozenset('PyFLASH.markers.'+owner+'.clean_df' for owner in ('Antibody','cellMarker','objectMarker'))
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={owner:('whole-marker-cleaning-options.'+owner.split('.')[-2]+'.',) for owner in CAPABILITIES}

@lru_cache(maxsize=24)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())

@lru_cache(maxsize=8)
def _catalogue(archive):
    rows={}
    for kind,folder in (('configured',CONFIGURED),('refused',REFUSED)):
        for item in _read(archive/folder/'predictions.json'):
            key='whole-marker-cleaning-options.'+item['case']['key']
            assert key not in rows
            rows[key]=dict(key=key,kind=kind,input=item,expected=item['expected'])
    return rows

def cases():return copy.deepcopy(list(_catalogue(ARCHIVE.resolve()).values()))

def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    return {row['key'] for row in _catalogue(ARCHIVE.resolve()).values() if row['input']['case']['owner']==capability.split('.')[-2]}

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_cleaning_options_reference as ref,marker_cleaning_reference as original
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    assert Path(ref.__file__).read_bytes()==(ARCHIVE/'qualified-reference.py').read_bytes()
    for kind,folder,count in (('configured',CONFIGURED,252),('refused',REFUSED,144)):
        receipt=read(folder+'/run.json');items=read(folder+'/predictions.json')
        assert receipt['passed'] and receipt['actual_calls']==count and receipt['failed']==0 and not receipt['source_changes']
        assert hashlib.sha256((ARCHIVE/folder/'predictions.json').read_bytes()).hexdigest()==receipt['predictions_sha256']
        observed=[json.loads(line) for line in (ARCHIVE/folder/'paired.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(observed)==count and all(row['passed'] and row['expected']==item['expected'] for row,item in zip(observed,items,strict=True))
        for offset in range(0,count,100):
            stem=folder+'/native/'+str(offset)+'/'+('configured' if kind=='configured' else 'refused')+'-whole-marker-cleaning'
            batch=items[offset:offset+100]
            queries=[ref.configured_query(item) if kind=='configured' else ref.reference_query(item['case']) for item in batch]
            assert queries==read(stem+'-queries.json')
            answer=read(stem+'-results.json');execution=read(stem+'-execution.json')
            assert execution['status']=='completed' and execution['returncode']==0 and execution['timeout_seconds']==180
            assert answer['webR']=='0.6.0' and answer['wasm_sha256']=='5df459fb222d332e358cf08e4019c0e114398579ed8c62242bfcceeda81222ba'
            assert len(answer['rows'])==len(batch)
            for item,query,row in zip(batch,queries,answer['rows'],strict=True):
                assert row['status']=='executed' and all(row[name]==value for name,value in query.items())
                prediction=original.expected(item['case'],row['values']) if kind=='configured' else ref.expected(item['case'],row['values'])
                assert prediction==item['expected']

def production(row,observation=None):
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.config import Config
    from reproducibility import marker_cleaning_reference as original,marker_cleaning_options_reference as ref
    from reproducibility.marker_cleaning_whole_contract import equal
    frozen=_catalogue(ARCHIVE.resolve())[row['key']]
    assert row==frozen
    item=row['input'];case=item['case'];configured=row['kind']=='configured'
    frame,labels,areas=original.inputs(case) if configured else ref.inputs(case)
    labels_before=None if labels is None else labels.copy(deep=True);areas_before={name:value.df.copy(deep=True) for name,value in areas.items()}
    exp=SimpleNamespace(data=areas)
    if labels is not None:exp.condition_labels=labels
    old_density=Config.PIXEL_SIZE;old_threshold=Config.THRESHOLD
    returned_own=None;refusal=None;actual=None
    try:
        if configured:Config.PIXEL_SIZE=item['density'];Config.THRESHOLD=item['threshold']
        cls=getattr(markers,case['owner'])
        with contextlib.redirect_stdout(io.StringIO()),warnings.catch_warnings():
            warnings.simplefilter('ignore')
            if configured and item['mode']=='constructor':
                args=[case['name'],frame,exp,'grey']
                obj=cls(*args,threshold=item['threshold']) if case['owner']=='objectMarker' else cls(*args)
                returned_own=True
            else:
                obj=object.__new__(cls);obj.name=case['name'];obj.df=frame;obj.experiment=exp;obj.color='grey';sentinel=object();obj._unrelated=sentinel
                if not configured or case['owner']=='objectMarker' and item['threshold_source']=='instance':obj.threshold=item['threshold'] if configured else 30
                try:returned_own=obj.clean_df() is obj.df
                except ValueError as exc:
                    if configured:raise
                    refusal=str(exc)
                assert obj._unrelated is sentinel
        actual=dict(table=original.categorical_table(obj.df),raw_after=original.categorical_table(frame),same_raw_owner=obj.df is frame)
        if observation is not None:observation.update(actual=actual,expected=row['expected'],returned_own=returned_own,refusal=refusal)
        assert equal(actual,row['expected'])
        if configured:assert returned_own and refusal is None
        else:assert refusal and 'Source calibration' in refusal and returned_own is None
        assert obj.experiment is exp and obj.color=='grey'
        if case['owner']=='objectMarker' and (not configured or item['threshold_source']=='instance'):
            assert obj.threshold==(item['threshold'] if configured else 30)
        if labels is not None:pd.testing.assert_frame_equal(labels,labels_before,check_exact=True)
        for name,value in areas.items():pd.testing.assert_frame_equal(value.df,areas_before[name],check_exact=True)
        return actual
    finally:Config.PIXEL_SIZE=old_density;Config.THRESHOLD=old_threshold

def validate(output):
    from reproducibility import marker_cleaning_options_reference as ref,marker_cleaning_reference as original
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity();output=Path(output)
    for kind,folder,count in (('configured',CONFIGURED,252),('refused',REFUSED,144)):
        items=read(folder+'/predictions.json')
        for offset in range(0,count,100):
            batch=items[offset:offset+100]
            queries=[ref.configured_query(item) if kind=='configured' else ref.reference_query(item['case']) for item in batch]
            answers=execute_queries(queries,output/'native-options'/kind/str(offset),name=kind+'-whole-marker-cleaning',timeout=180)
            assert len(answers['rows'])==len(batch)
            for item,row in zip(batch,answers['rows'],strict=True):
                prediction=original.expected(item['case'],row['values']) if kind=='configured' else ref.expected(item['case'],row['values'])
                assert prediction==item['expected']
    return replay(cases(),lambda item,observed,path:production(item,observed),output,reference='Native R complete tables for public cleaning constructors, nondefault configuration and refused invalid calibration; literal return/input-ownership controls, no additional scientific-method vote',family='functional-whole-marker-cleaning-options',shape='all-final-and-partial-table-fields-raw-input-types-index-attributes-refusal-return-and-caller-ownership',rtol=1e-12,atol=0.)
