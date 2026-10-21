"""Whole functional annotation options through each actual public class."""
from pathlib import Path
from functools import lru_cache
import json,hashlib,copy
from reproducibility import coloc_annotation_reference as reference
ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-coloc-annotation'
MANIFEST_SHA256='99ccd48235b27befe79eb47d22e1bff037bd351570d7952564d43e6a138fdab9'
CAPABILITIES=frozenset('PyFLASH.markers.'+name+'.addColocData' for name in reference.OWNERS)
COMPLETE_CAPABILITIES=CAPABILITIES # Each actual owner passes every frozen option and permanent damage guard.
CAPABILITY_PREFIXES={name:('whole-coloc.'+name.split('.')[-2]+'.',) for name in CAPABILITIES}

@lru_cache(maxsize=6)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())
def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes()==(ARCHIVE/'original-v2/original-coloc_annotation_reference.py').read_bytes()
    original=read('original-v2/run.json');proof=read('whole-candidate/run.json');nullable=read('nullable-original/run.json')
    assert original['cases']==2205 and original['failed']==270 and original['source_unchanged']
    assert nullable['actual_calls']==nullable['failed']==9 and nullable['source_unchanged']
    assert proof['passed'] and proof['cases']==2325 and proof['failed']==0 and proof['source_unchanged']
    assert reference.cases()==read('original-v2/predictions.json')
    assert len(read('whole-candidate/paired.json'))==2325
    assert proof['candidate_sha256']==hashlib.sha256((ARCHIVE/'nullable-candidate/candidate-coerce.py').read_bytes()).hexdigest()

def cases():return copy.deepcopy(read('original-v2/predictions.json'))
def required_keys(capability):
    return {item['key'] for item in cases() if 'PyFLASH.markers.'+item['owner']+'.addColocData'==capability} if capability in CAPABILITIES else set()
@lru_cache(maxsize=4)
def _index(path):return {item['key']:item for item in _read(path)}
def production(item,observation=None):
    assert item==_index((ARCHIVE/'original-v2/predictions.json').resolve())[item['key']]
    observed={};reference.production(item,observed)
    if observed['expected']['error'] is not None:
        # The original full observations stay in the archive. Expected failures
        # score the error and the byte-exact unchanged-table assertion above.
        actual=dict(error=observed['actual']['error'],table_unchanged=True)
        expected=dict(error=observed['expected']['error'],table_unchanged=True)
    else:actual,expected=observed['actual'],observed['expected']
    if observation is not None:observation.update(actual=actual,expected=expected,full_original_observation=observed)
    return actual
def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,observed),output,reference='Predeclared literal annotation policy, original failures and qualified nullable repair; functional only, no independent scientific-method vote',family='whole-functional-colocalisation-table-annotation',shape='column-order-values-types-index-metadata-return-ownership-error-and-repeat')
