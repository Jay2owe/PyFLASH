"""Actual inherited flat-experiment CSV serialization and ownership calls."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'inherited-mini-csv'
MANIFEST_SHA256='aa4e7b77ba48d231f4662a68b80ecae3bcf7e4a64687e3d171109ccf460a4dd2'
CAPABILITIES=frozenset('PyFLASH.experiment.MiniExperiment.'+name for name in
    ('save_csvs','save_column_csvs','save_attribute_csvs'))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('inherited-mini-csv.',) for name in CAPABILITIES}

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import csv_export_contract as original
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256);original.check_identity()
    proof=read('run.json');items=read('predictions.json')
    assert proof['passed'] and proof['actual_calls']==15 and not proof['source_changes']
    original_cases={row['key']:row for row in original.cases()}
    for item,row in zip(items,proof['rows'],strict=True):
        assert item['case']==original_cases[item['case']['key']]
        assert item['expected']==dict(files=item['case']['expected_files'],inputs_unchanged=True,returned_none=True)
        assert item=={key:row[key] for key in item}
        assert row['passed'] and row['error'] is None

def cases():return copy.deepcopy(read('predictions.json'))

def required_keys(capability):
    return {item['key'] for item in read('predictions.json') if item['capability']==capability} if capability in CAPABILITIES else set()

def production(item,output,observation=None):
    from reproducibility import csv_export_contract as original
    from PyFLASH.experiment import MiniExperiment
    assert item==next(row for row in read('predictions.json') if row['key']==item['key'])
    actual=original.production(item['case'],output,experiment_class=MiniExperiment)
    if observation is not None:observation.update(actual=actual,expected=item['expected'])
    assert actual==item['expected']
    return actual,item['expected']

def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(),lambda item,observed,path:production(item,path,observed),output,
        reference='Actual flat-experiment subclass and unchanged literal CSV tables, independently read with the standard-library CSV reader; functional serialization, no scientific vote',
        family='functional-inherited-mini-csv',shape='every-file-path-header-cell-order-empty-branch-return-and-input-ownership')
