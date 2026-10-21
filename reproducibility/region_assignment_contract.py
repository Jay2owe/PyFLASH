"""Whole functional region assignment and inherited lightweight entry points.

These literal state/table comparisons provide no independent numerical-method
vote and cannot certify CSV processing, aggregation or fitted scientific parents.
"""
from copy import deepcopy
from functools import lru_cache
import importlib.util
import inspect
import json
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-region-assignment'/'v1'
MANIFEST_SHA256='ad66f6268ffcb20ad6238fb130df12b6f5a0bfcd27c556f43c58c82bb8bb6747'
CAPABILITIES=frozenset('PyFLASH.experiment.'+owner+'.assign_region' for owner in ('Experiment','MiniExperiment'))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('whole-region-assignment.'+name.split('.')[-2]+'.',) for name in CAPABILITIES}


@lru_cache(maxsize=8)
def _helper(path):
    spec=importlib.util.spec_from_file_location('frozen_region_assignment_client',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def read(name):return json.loads((ARCHIVE/name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import dataframe_table_protocol as codec
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    assert Path(codec.__file__).read_bytes()==(ARCHIVE/'table-transport.py').read_bytes()
    original=read('original-v3/run.json');qualified=read('qualified-private/run.json')
    assert original['executed_cases']==312 and original['failures']==312 and not original['source_changes']
    assert qualified['passed'] and qualified['executed_cases']==312 and qualified['failures']==0
    assert not qualified['source_changes'] and qualified['actual_calls']==592
    assert not read('first-private/run.json')['passed']
    assert read('first-private/run.json')['executed_cases']==248 and read('first-private/run.json')['failures']==80
    assert read('original-v1/run.json')['failures']==248 and read('original-v2/run.json')['failures']==248
    amendment=read('original-v2/reasoned-declaration-amendment.json')
    extension=read('original-v3/reasoned-declaration-amendment.json')
    assert len(amendment['changes'])==80 and extension['changes']==[] and extension['new_cases']==64
    rows=read('original-v3/declared-before.json')['rows']
    assert len(rows)==len({row['key'] for row in rows})==312
    assert _helper(str((ARCHIVE/'literal-reference.py').resolve())).cases()==rows
    assert read('original-v3/declared-before.json')['scientific_engine_votes']==0
    paired=read('qualified-private/paired.json')
    assert [row['key'] for row in paired]==[row['key'] for row in rows]
    assert all(row['agrees'] and row['actual']==row['expected']==case['expected'] for row,case in zip(paired,rows))
    return rows


@lru_cache(maxsize=8)
def _sealed_rows(archive,manifest):
    assert archive==str(ARCHIVE.resolve()) and manifest==MANIFEST_SHA256
    return {row['key']:row for row in check_identity()}


def _declared():return _sealed_rows(str(ARCHIVE.resolve()),MANIFEST_SHA256)


def cases():return deepcopy(list(_declared().values()))


def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    assert_parameter_inventory()
    owner=capability.split('.')[-2]
    return {row['key'] for row in cases() if row['owner']==owner}


def assert_parameter_inventory():
    from PyFLASH import experiment
    for owner in ('Experiment','MiniExperiment'):
        for entry in ('assign_region','assign_scn_number'):
            assert list(inspect.signature(getattr(getattr(experiment,owner),entry)).parameters)==['self'], 'Unclassified region-assignment parameter'


def production(row,output,observation=None):
    frozen=_declared()[row['key']]
    assert row==frozen,'Declared whole region-assignment input or answer changed'
    assert_parameter_inventory()
    helper=_helper(str((ARCHIVE/'literal-reference.py').resolve()))
    actual=helper.production(row)
    if observation is not None:observation.update(actual=actual,expected=row['expected'])
    assert actual==row['expected'],'Whole region-assignment state or table differs'
    return actual,row['expected']


def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    result=replay(cases(),lambda row,observed,path:production(row,path,observed),output,
        reference='Predeclared literal functional region labels, complete pandas tables/dtypes/index/metadata, source drawing order, aliases and atomic refusals; actual Experiment/MiniExperiment calls; no independent numerical engine vote',
        family='whole-functional-region-assignment',shape='every-label-row-field-dtype-index-attribute-alias-and-refusal-with-three-call-stability')
    check_identity()
    return result
