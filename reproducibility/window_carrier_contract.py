"""Complete additional moving-window carriers, widths and admission controls."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-window-carriers'
MANIFEST_SHA256='b122ef1d3805b792a2a601ce22c78046a27766cf93bf25fb54d524ace391af93'
CAPABILITY='PyFLASH.utils.moving_average'
CAPABILITIES=frozenset({CAPABILITY})
CAPABILITY_PREFIXES={CAPABILITY:('window-carrier.',)}
COMPLETE_CAPABILITIES=CAPABILITIES

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import window_carrier_reference as reference
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes()==(ARCHIVE/'original/original-freeze_whole_window_carriers_20261008.py').read_bytes()
    original=read('original/run.json');qualified=read('qualified/before.json');proof=read('qualified/run.json')
    assert original['actual_calls']==400 and original['failed']==12 and not original['source_changes']
    assert qualified['actual_calls']==400 and qualified['failed']==3 and not qualified['source_changes']
    assert proof['passed'] and proof['actual_calls']==400 and proof['control_calls']==260 and not proof['source_changes']
    assert not read('first-private/run.json')['passed']
    assert 'missing 1 required positional argument' in read('first-private/run.json')['error']
    assert [row['case'] for row in original['rows']]==reference.cases()==[row['case'] for row in qualified['rows']]
    amendment=read('qualified/refusal-class-amendment.json')
    assert amendment['unchanged_inputs'] and amendment['unchanged_numeric_predictions'] and not amendment['production_changes']
    changed=[(old,new) for old,new in zip(original['rows'],qualified['rows']) if old['expected']!=new['expected']]
    assert len(changed)==len(amendment['amendments'])==9
    assert all(old['case']['pattern']=='text' and old['expected']=={'error':'TypeError'}
        and new['expected']=={'error':'ValueError'} for old,new in changed)
    assert read('installed/installation.json')['candidate_sha256']==proof['candidate_sha256']

def cases():
    return [dict(key=row['case']['key'],case=copy.deepcopy(row['case']),expected=copy.deepcopy(row['expected']))
            for row in read('qualified/qualified-predictions.json')]

def required_keys(capability):
    if capability!=CAPABILITY:return set()
    from reproducibility import scientific_utility_contract,object_mean_contract,mixed_mean_fidelity_contract
    return ({row['key'] for row in cases()}|scientific_utility_contract.required_keys(capability)
        |{row['key'] for row in object_mean_contract.cases()}|{row['key'] for row in mixed_mean_fidelity_contract.cases()})

def production(item,observation=None,*,qualify_reference=False):
    from reproducibility import window_carrier_reference as reference
    before=next(row for row in read('qualified/qualified-predictions.json') if row['case']==item['case'])
    assert before['expected']==item['expected']
    if qualify_reference:
        original=next(row for row in read('original/predictions.json') if row['case']==item['case'])
        assert reference.prediction(item['case'])==original['expected']
    actual=reference.production(item['case'],item['expected'])
    if observation is not None:observation.update(actual=actual,expected=item['expected'])
    return actual

def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,observed,qualify_reference=True),output,
        reference='Native SymPy finite-index exact expectations for original measurement cells; NumPy fallback refusal qualification and literal admission/alias controls. Supporting arithmetic, no additional published whole smoother vote.',
        family='whole-moving-window-carriers-widths-and-admission',shape='every-output-coordinate-shape-dtype-noop-alias-refusal-and-input-ownership',rtol=1e-12,atol=0.)
