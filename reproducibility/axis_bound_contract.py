"""Whole scalar display-bound policy; explicitly not a scientific estimator."""
from pathlib import Path
from functools import lru_cache
import copy
import json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-axis-bound-policy'
MANIFEST_SHA256='4f5696508054ac2537866d968e9c59d9af95cb14505fc305b71dff8224581a53'
CAPABILITY='PyFLASH.utils.round_up_to_nearest_5'
CAPABILITIES=frozenset({CAPABILITY})
CAPABILITY_PREFIXES={CAPABILITY:('axis-bound-policy.',)}
COMPLETE_CAPABILITIES=CAPABILITIES

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import axis_bound_reference as reference
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes()==(ARCHIVE/'qualified/original-1-freeze_axis_bound_whole_policy_20261008_v3.py').read_bytes()
    before=read('original/before.json');qualified=read('qualified/before.json')
    assert before['actual_calls']==211 and before['failed']==1 and not before['source_changes']
    assert qualified['actual_calls']==211 and not qualified['failed'] and not qualified['source_changes']
    assert [row['case'] for row in before['rows']]==[row['case'] for row in qualified['rows']]
    amendment=read('qualified/transport-amendment.json')
    assert amendment['unchanged_inputs'] and amendment['unchanged_grid'] and not amendment['production_changes']
    changed=[row['case']['key'] for row,old in zip(qualified['rows'],before['rows']) if row['expected']!=old['expected']]
    assert changed==['axis-bound.grid.-308.1.0.above']
    assert read('first-qualification/preflight-failure.json')['actual_calls']==0
    assert [reference.describe(case) for case in reference.cases()]==[row['case'] for row in qualified['rows']]

def cases():
    return [dict(key='axis-bound-policy.'+row['case']['key'],case=copy.deepcopy(row['case']),expected=copy.deepcopy(row['expected']))
            for row in read('qualified/before.json')['rows']]

def required_keys(capability):
    if capability!=CAPABILITY:return set()
    from reproducibility.scientific_utility_contract import required_keys as retained_keys
    return {row['key'] for row in cases()}|retained_keys(capability)

def production(item,observation=None,*,qualify_reference=False):
    import numpy as np
    from PyFLASH import utils
    from reproducibility import axis_bound_reference as reference
    before=next(row for row in read('qualified/before.json')['rows'] if row['case']==item['case'])
    assert item['expected']==before['expected']
    case=next(case for case in reference.cases() if case['key']==item['case']['key'])
    value=case['value'];snapshot=value.copy() if isinstance(value,np.ndarray) else None
    if qualify_reference:assert reference.prediction(value)==before['expected']
    try:
        with np.errstate(all='raise'):result=utils.round_up_to_nearest_5(value)
        actual=dict(value=result,type=type(result).__name__)
    except Exception as error:actual=dict(error=type(error).__name__)
    if snapshot is not None:np.testing.assert_array_equal(value,snapshot)
    if observation is not None:observation.update(actual=actual,expected=before['expected'])
    assert actual==before['expected']
    return actual

def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,observed,qualify_reference=True),output,
        reference='Native 400-digit SymPy and 4096-bit mpmath exhaustive exact half-decade grid, independently qualified binary64 transport and literal admission/type controls; custom display policy, no scientific-method vote',
        family='functional-scalar-axis-bound-policy',shape='every-scalar-bound-returned-type-and-input-refusal')
