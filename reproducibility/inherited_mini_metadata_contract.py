"""Actual inherited lightweight-experiment metadata and ownership calls."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'inherited-mini-metadata'
MANIFEST_SHA256='2b5512bfccc901cf578c70d2fa50c1bafeb342937b2ad6afd688b1b7fdead87a'
UNICODE_AMENDMENT='unicode-input-amendment-20261009-v1'
UNICODE_MANIFEST_SHA256='62c0982408c8b9a2e9316cc6298a42a9ed49e561b72b2a7923e810d2ec62aec0'
CAPABILITIES=frozenset('PyFLASH.experiment.MiniExperiment.'+name for name in
    ('summary','createSavePaths','getRegionDict','getSCNDict','info'))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('inherited-mini-metadata.',) for name in CAPABILITIES}

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import experiment_metadata_contract as original
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    original.check_identity()
    frozen=read('run.json')
    assert frozen['passed'] and frozen['actual_calls']==145 and not frozen['source_changes']
    # The historical producer decoded these exact bytes with Windows cp1252.
    # Preserve and authenticate those recorded inputs rather than rewriting them.
    original_cases={row['key']:row for row in original.cases(encoding='cp1252')}
    for row in read('predictions.json'):
        assert row['case']==original_cases[row['case']['key']]
        assert row['expected']==row['case']['expected']
        assert row['capability']==row['case']['capability'].replace('.Experiment.','.MiniExperiment.')
    assert read('predictions.json')==[{key:row[key] for key in ('key','capability','case','expected')} for row in frozen['rows']]
    verify_manifest(ARCHIVE/UNICODE_AMENDMENT,'source-files.json',UNICODE_MANIFEST_SHA256)
    proof=read(UNICODE_AMENDMENT+'/run.json')
    assert proof['passed'] and proof['actual_calls']==338 and proof['failures']==0 and not proof['source_changes']
    current=cases()
    assert len(current)==169 and current[:145]==read('predictions.json')
    assert [item['case'] for item in current]==read(UNICODE_AMENDMENT+'/inputs.json')
    answers=read(UNICODE_AMENDMENT+'/answers.json')
    expected={(owner,item['case']['key']) for owner in ('Experiment','MiniExperiment') for item in current}
    assert len(answers)==len({(row['owner'],row['key']) for row in answers})==338
    assert {(row['owner'],row['key']) for row in answers}==expected
    assert all(row['passed'] and row['error'] is None and row['actual']==row['expected'] for row in answers)

def cases():
    from reproducibility import experiment_metadata_contract as original
    result=copy.deepcopy(read('predictions.json'))
    retained={item['case']['key'] for item in result}
    for row in original.cases():
        if row['owner'].startswith('Experiment.') and row['key'] not in retained:
            result.append(dict(key='inherited-mini-metadata.'+row['key'],
                capability=row['capability'].replace('.Experiment.','.MiniExperiment.'),
                case=copy.deepcopy(row),expected=copy.deepcopy(row['expected'])))
    return result

def required_keys(capability):
    return {item['key'] for item in cases() if item['capability']==capability} if capability in CAPABILITIES else set()

def production(item,output,observation=None):
    from reproducibility import experiment_metadata_contract as original
    from PyFLASH.experiment import MiniExperiment
    frozen=next(row for row in cases() if row['key']==item['key'])
    assert item==frozen
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    actual=original.calculate(item['case'],output,experiment_class=MiniExperiment)
    if observation is not None:observation.update(actual=actual,expected=item['expected'])
    assert actual==item['expected']
    return actual,item['expected']

def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,path,observed),output,
        reference='Original literal metadata/path/region/summary/reporting contracts executed on the actual lightweight experiment subclass; functional only, no numerical vote',
        family='functional-inherited-mini-metadata',shape='every-output-path-lookup-field-summary-alias-report-line-and-state-identity')
