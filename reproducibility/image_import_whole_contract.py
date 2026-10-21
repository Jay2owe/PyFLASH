"""Complete public image indexing; filename metadata only, no pixel decoding."""
from pathlib import Path
from functools import lru_cache
import contextlib,copy,io,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-image-import'
MANIFEST_SHA256='99a3931fbe8508d6f7560708649ced09d7f78c70d6f5594591093b059048b48b'
CAPABILITIES=frozenset('PyFLASH.'+module+'.'+owner+'.importImages' for module,owner in
    (('experiment','Experiment'),('experiment','MiniExperiment'),('batch','Batch')))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={capability:('whole-image-import.'+capability.split('.')[-2]+'.',) for capability in CAPABILITIES}

@lru_cache(maxsize=16)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import image_import_whole_reference as ref,image_table_contract
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    image_table_contract.check_identity()
    assert Path(ref.__file__).read_bytes()==(ARCHIVE/'original-v3/original-image_import_whole_reference.py').read_bytes()
    original=read('original-v1/predictions.json')
    assert len(original)==330 and [row['case'] for row in original]==list(ref.cases())
    for version in (2,3):
        assert read(f'original-v{version}/predictions.json')==original
    failure=read('original-v2/run.json')
    assert not failure['passed'] and failure['failed']==168 and failure['actual_calls']==330 and not failure['source_changes']
    success=read('original-v3/run.json')
    assert success['passed'] and success['failed']==0 and success['actual_calls']==330 and not success['source_changes']
    assert all(row['passed'] and row['actual']==row['expected'] for row in read('original-v3/paired.json'))

def cases():
    return [dict(key='whole-image-import.'+row['case']['key'],case=copy.deepcopy(row['case']),expected=copy.deepcopy(row['expected']))
        for row in read('original-v3/predictions.json')]

def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    return {item['key'] for item in cases() if item['case']['owner']==capability.split('.')[-2]}

def production(item,directory,observation=None):
    from reproducibility import image_import_whole_reference as ref
    original=next(row for row in read('original-v3/predictions.json') if row['case']==item['case'])
    assert item['expected']==original['expected']
    directory=Path(directory)
    with contextlib.redirect_stdout(io.StringIO()):
        prepared=ref.prepare(item['case'],directory)
        assert prepared[-1]==item['expected']
        row=ref.observe(item['case'],directory,prepared,item['expected'])
    if observation is not None:observation.update(actual=row['actual'],expected=item['expected'])
    assert row['passed'],row['error']
    assert row['actual']==row['expected']==item['expected']
    return row['actual']

def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,path,observed),output,
        reference='Literal authored image filenames and metadata, all six supported extensions, three export layouts, missing/empty/nested folders and cached batch children; functional indexing only, no pixel-decoder or statistical-method vote',
        family='functional-whole-image-indexing',shape='complete-return-and-stored-tables-types-indexes-lookup-summary-path-and-unrelated-state-ownership')
